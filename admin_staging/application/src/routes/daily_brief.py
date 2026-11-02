import asyncio
import io
import base64
import binascii
import json
import logging
import os
import re
import smtplib
import uuid
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import selectinload

from models.db_schemas import Branch, DailyBrief, DailyBriefBlock, DailyBriefEmailBatch, DailyBriefEmailRecipient, DailyBriefFeedback, DailyBriefRead, DailyBriefView, Employee
from models.db_schemas.learning.schemas.daily_brief import DailyBriefAudience, DailyBriefAction
from routes.users.auth_utils import get_current_user


router = APIRouter(prefix="/api/v1/daily-briefs", tags=["Daily Briefs"])
logger = logging.getLogger(__name__)

ADMIN_ROLES = {"admin", "auditor", "hr"}
RETAIL_ROLES = {"retail", "employee"}
DAILY_BRIEF_EMAIL_RECIPIENTS = (
    {"name": "Plus Area Supervisors", "email": "PlusArea.Supervisors@Fawry.com"},
    {"name": "Plus Area Managers", "email": "Plus.Area.Managers@Fawry.com"},
    {"name": "Plus Regional Manager", "email": "Plus.Regional.Manager@Fawry.com"},
    {"name": "Plus Branches", "email": "plus.branches@fawry-retail.com"},
    {"name": "Mohamed Morshedy", "email": "Mohamed.Morshedy@Fawry.com"},
)
DAILY_BRIEF_EMAIL_RECIPIENTS_SOURCE = "routes.daily_brief.DAILY_BRIEF_EMAIL_RECIPIENTS"
EMAIL_BATCH_PENDING, EMAIL_BATCH_PROCESSING, EMAIL_BATCH_COMPLETED, EMAIL_BATCH_COMPLETED_WITH_ERRORS = "PENDING", "PROCESSING", "COMPLETED", "COMPLETED_WITH_ERRORS"
EMAIL_RECIPIENT_PENDING, EMAIL_RECIPIENT_ACCEPTED, EMAIL_RECIPIENT_REJECTED, EMAIL_RECIPIENT_FAILED = "PENDING", "ACCEPTED", "REJECTED", "FAILED"
ALLOWED_BLOCK_TYPES = {
    "heading", "text", "highlight", "alert", "image", "bullet_list", "image_text", "cta", "divider"
}
ALLOWED_HIGHLIGHT_STYLES = {"standard", "important", "information", "success", "warning", "critical"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
RICH_TEXT_TAGS = {"p", "br", "strong", "b", "em", "i", "u", "h1", "h2", "h3", "ul", "ol", "li", "a", "blockquote", "span", "div", "font"}
RICH_TEXT_ATTRS = {"href", "target", "rel", "dir", "size", "color", "style", "data-color", "data-highlight", "data-align"}


class _RichTextSanitizer(HTMLParser):
    """Keeps a deliberately small, presentation-only HTML subset for text blocks."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag not in RICH_TEXT_TAGS:
            return
        safe = []
        for key, value in attrs:
            key = key.lower()
            value = str(value or "")
            if key not in RICH_TEXT_ATTRS:
                continue
            if key == "href" and not (value.startswith("/") or re.match(r"^https://[^\s]+$", value)):
                continue
            if key == "target" and value != "_blank":
                continue
            if key == "dir" and value not in {"ltr", "rtl", "auto"}:
                continue
            if key == "size" and value not in {"2", "3", "4", "5", "6", "7"}:
                continue
            if key == "color" and value.lower() not in {"#102a56", "black", "gray", "yellow", "red", "blue", "green"}:
                continue
            if key == "style":
                continue
            if key in {"data-color", "data-highlight", "data-align"} and not re.match(r"^[a-z-]{1,20}$", value):
                continue
            safe.append(f' {key}="{escape(value, quote=True)}"')
        self.parts.append(f"<{tag}{''.join(safe)}>")

    def handle_endtag(self, tag):
        if tag.lower() in RICH_TEXT_TAGS and tag.lower() != "br":
            self.parts.append(f"</{tag.lower()}>")

    def handle_data(self, data):
        self.parts.append(escape(data))


def _sanitize_rich_html(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parser = _RichTextSanitizer()
    parser.feed(raw[:12000])
    parser.close()
    return "".join(parser.parts)[:12000]


class AudienceRecipient(BaseModel):
    name: str = Field(default="", max_length=200)
    email: str = Field(max_length=254)

    @model_validator(mode="after")
    def validate_recipient(self):
        self.name = self.name.strip()
        self.email = self.email.strip().lower()
        if any(ord(c) < 32 for c in self.name + self.email):
            raise ValueError("Control characters are not allowed")
        if not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+", self.email):
            raise ValueError("Enter a valid email address")
        local = self.email.split('@')[0]
        if len(local) > 64 or local.startswith('.') or local.endswith('.') or '..' in local:
            raise ValueError("Enter a valid email address")
        return self


class AudienceInput(BaseModel):
    recipients: list[AudienceRecipient] = Field(max_length=500)
    revision: int = Field(ge=0)

    @model_validator(mode="before")
    @classmethod
    def decode_payload(cls, value):
        return BriefInput.decode_browser_payload(value)

    @model_validator(mode="after")
    def unique_emails(self):
        emails = [item.email for item in self.recipients]
        if len(emails) != len(set(emails)):
            raise ValueError("Duplicate email addresses are not allowed")
        return self


class BlockInput(BaseModel):
    block_type: str = Field(max_length=40)
    content: dict = Field(default_factory=dict)


class BriefInput(BaseModel):
    title: str = Field(default="", max_length=200)
    brief_date: date | None = None
    blocks: list[BlockInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="before")
    @classmethod
    def decode_browser_payload(cls, value):
        """Decode transport only; normal schema and HTML validation still apply."""
        if not isinstance(value, dict) or "payload_b64" not in value:
            return value  # Preserve existing API clients.
        if set(value) != {"payload_b64"}:
            raise ValueError("Encoded brief must not contain additional fields")
        encoded = value["payload_b64"]
        if not isinstance(encoded, str) or len(encoded) > 2 * 1024 * 1024:
            raise ValueError("Encoded brief is invalid or exceeds 2 MiB")
        try:
            decoded = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
        except (binascii.Error, UnicodeError, ValueError, RecursionError) as exc:
            raise ValueError("Invalid encoded Daily Brief") from exc
        if not isinstance(decoded, dict) or "payload_b64" in decoded:
            raise ValueError("Daily Brief must be an object")
        return decoded


class FeedbackInput(BaseModel):
    reaction: Literal["LIKE", "UNLIKE"] | None = None
    comment: str | None = Field(default=None, max_length=4000)



def _role(user: dict) -> str:
    return str(user.get("role") or user.get("department") or "").strip().lower()


def _actor(user: dict) -> str:
    return str(user.get("email") or user.get("sub") or "unknown").strip().lower()


def _require_admin(user: dict) -> None:
    if _role(user) not in ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


def _require_retail(user: dict) -> None:
    if _role(user) not in RETAIL_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Retail access required")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _smtp_disabled() -> bool:
    return str(os.getenv("TRAINING_SMTP_DISABLED", os.getenv("SMTP_DISABLED", ""))).strip().lower() in {"1", "true", "yes", "y"}


def _smtp_settings() -> tuple[str, int, str, float]:
    return (
        (os.getenv("TRAINING_SMTP_SERVER") or os.getenv("SMTP_SERVER") or "10.100.36.40").strip(),
        int((os.getenv("TRAINING_SMTP_PORT") or os.getenv("SMTP_PORT") or "25").strip()),
        (os.getenv("TRAINING_SMTP_FROM") or os.getenv("SMTP_FROM_EMAIL") or "no-reply@fawry.com").strip(),
        float((os.getenv("TRAINING_SMTP_TIMEOUT") or "10").strip()),
    )


def log_notification_runtime() -> None:
    host, port, sender, _ = _smtp_settings()
    logger.info("Daily Brief notification runtime: module=%s cwd=%s recipient_source=%s recipient_count=%s recipients=%s smtp_host=%s smtp_port=%s sender=%s", __file__, os.getcwd(), DAILY_BRIEF_EMAIL_RECIPIENTS_SOURCE, len(DAILY_BRIEF_EMAIL_RECIPIENTS), [item["email"] for item in DAILY_BRIEF_EMAIL_RECIPIENTS], host, port, sender)


def _smtp_error_details(error: Exception) -> tuple[int | None, str]:
    code, message = getattr(error, "smtp_code", None), getattr(error, "smtp_error", None)
    if isinstance(message, bytes):
        message = message.decode("utf-8", errors="replace")
    return (int(code) if isinstance(code, int) else None, str(message or error)[:500])


def _recipient_refusal(refused: dict, recipient_email: str) -> tuple[int | None, str] | None:
    for email, details in (refused or {}).items():
        if str(email).lower() == recipient_email.lower():
            code, message = details if isinstance(details, tuple) and len(details) == 2 else (None, details)
            if isinstance(message, bytes):
                message = message.decode("utf-8", errors="replace")
            return (int(code) if isinstance(code, int) else None, str(message or "Recipient rejected")[:500])
    return None


def _daily_brief_email_message(*, recipient_name: str, title: str, brief_url: str) -> tuple[str, str, str]:
    safe_name = recipient_name.strip() or "فريق Retail"
    safe_title = escape(title)
    safe_url = escape(brief_url, quote=True)
    subject = f"A new Daily Brief is available | {title}"
    plain_text = (
        f"Dear {safe_name},\n\n"
        f"A new Daily Brief is available: {title}\n\n"
        f"Please sign in to the Training System to view the latest Daily Brief:\n{brief_url}\n\n"
        "Thank you,\nFawry Plus Training System"
    )
    html_text = f"""
    <!doctype html>
    <html lang="en" dir="ltr">
      <body style="margin:0;background:#f7f8fa;color:#172b4d;font-family:Tahoma,Arial,sans-serif;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:28px 16px;background:#f7f8fa;"><tr><td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:#ffffff;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden;">
            <tr><td style="height:6px;background:#ffd200;"></td></tr>
            <tr><td style="padding:32px;">
              <p style="margin:0 0 18px;font-size:16px;line-height:1.8;">Dear {escape(safe_name)},</p>
              <h1 style="margin:0 0 14px;font-size:24px;color:#102a56;">Fawry Plus Training System</h1>
              <p style="margin:0 0 12px;font-size:16px;line-height:1.8;">A new Daily Brief is available.</p>
              <p style="margin:0 0 24px;font-size:16px;line-height:1.8;">Please sign in to the Training System to view the latest Daily Brief: <strong>{safe_title}</strong>.</p>
              <a href="{safe_url}" style="display:inline-block;padding:13px 24px;background:#ffd200;color:#102a56;text-decoration:none;font-weight:700;border-radius:999px;">Open Training System</a>
              <p style="margin:28px 0 0;font-size:14px;line-height:1.8;color:#61708a;">Thank you,<br>Fawry Plus Training System</p>
            </td></tr>
          </table>
        </td></tr></table>
      </body>
    </html>
    """.strip()
    return subject, plain_text, html_text


def _deliver_daily_brief_notifications(recipients: list[dict], title: str, brief_url: str) -> list[dict]:
    """Return per-recipient SMTP relay outcomes; accepted is not mailbox delivery."""
    if _smtp_disabled():
        return [{"email": item["email"], "status": EMAIL_RECIPIENT_FAILED, "code": None, "message": "SMTP is disabled"} for item in recipients]
    host, port, sender, timeout = _smtp_settings()
    outcomes = []
    try:
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            for item in recipients:
                email = str(item["email"] or "").strip().lower()
                subject, plain, html = _daily_brief_email_message(recipient_name=str(item["name"] or ""), title=title, brief_url=brief_url)
                message = EmailMessage()
                message["Subject"], message["From"], message["To"] = subject, sender, email
                message.set_content(plain)
                message.add_alternative(html, subtype="html")
                try:
                    # send_message returns refused recipients for partial failures instead of raising.
                    refusal = _recipient_refusal(server.send_message(message), email)
                    if refusal:
                        code, detail = refusal
                        logger.warning("Daily Brief SMTP rejected recipient=%s code=%s detail=%s", email, code, detail)
                        outcomes.append({"email": email, "status": EMAIL_RECIPIENT_REJECTED, "code": code, "message": detail})
                    else:
                        logger.info("Daily Brief SMTP accepted recipient=%s", email)
                        outcomes.append({"email": email, "status": EMAIL_RECIPIENT_ACCEPTED, "code": 250, "message": "Accepted by SMTP relay"})
                except smtplib.SMTPRecipientsRefused as error:
                    code, detail = _recipient_refusal(error.recipients, email) or _smtp_error_details(error)
                    outcomes.append({"email": email, "status": EMAIL_RECIPIENT_REJECTED, "code": code, "message": detail})
                except Exception as error:
                    code, detail = _smtp_error_details(error)
                    logger.exception("Daily Brief SMTP failed recipient=%s", email)
                    outcomes.append({"email": email, "status": EMAIL_RECIPIENT_FAILED, "code": code, "message": detail})
    except Exception as error:
        code, detail = _smtp_error_details(error)
        logger.exception("Unable to connect to SMTP server for Daily Brief notifications")
        outcomes = [{"email": item["email"], "status": EMAIL_RECIPIENT_FAILED, "code": code, "message": detail} for item in recipients]
    return outcomes


async def _send_daily_brief_notifications(db_client, batch_id: str, recipients: list[dict], title: str, brief_url: str) -> None:
    async with db_client() as session:
        async with session.begin():
            batch = await session.get(DailyBriefEmailBatch, batch_id)
            if batch is None:
                return
            batch.status = EMAIL_BATCH_PROCESSING
    try:
        outcomes = await asyncio.to_thread(_deliver_daily_brief_notifications, recipients, title, brief_url)
    except Exception as error:
        code, detail = _smtp_error_details(error)
        logger.exception("Daily Brief notification worker failed: batch_id=%s", batch_id)
        outcomes = [{"email": item["email"], "status": EMAIL_RECIPIENT_FAILED, "code": code, "message": detail} for item in recipients]
    indexed = {item["email"].lower(): item for item in outcomes}
    async with db_client() as session:
        async with session.begin():
            batch = await session.scalar(select(DailyBriefEmailBatch).options(selectinload(DailyBriefEmailBatch.recipients)).where(DailyBriefEmailBatch.batch_id == batch_id))
            if batch is None:
                return
            for recipient in batch.recipients:
                outcome = indexed.get(recipient.recipient_email.lower(), {"status": EMAIL_RECIPIENT_FAILED, "code": None, "message": "No SMTP result was recorded"})
                recipient.status, recipient.smtp_code, recipient.smtp_message, recipient.attempted_at = outcome["status"], outcome["code"], outcome["message"], _now()
            batch.accepted_count = sum(item.status == EMAIL_RECIPIENT_ACCEPTED for item in batch.recipients)
            batch.rejected_count = sum(item.status == EMAIL_RECIPIENT_REJECTED for item in batch.recipients)
            batch.failed_count = sum(item.status == EMAIL_RECIPIENT_FAILED for item in batch.recipients)
            batch.completed_at = _now()
            batch.status = EMAIL_BATCH_COMPLETED if not batch.rejected_count and not batch.failed_count else EMAIL_BATCH_COMPLETED_WITH_ERRORS
            session.add(DailyBriefAction(brief_id=batch.brief_id, action="EMAIL_SEND_COMPLETED", actor=batch.triggered_by, occurred_at=_now()))
            logger.info("Daily Brief notification completed: batch_id=%s accepted=%s rejected=%s failed=%s", batch_id, batch.accepted_count, batch.rejected_count, batch.failed_count)


def _serialize_datetime(value):
    return value.isoformat() if value else None


def _serialize_email_batch(batch: DailyBriefEmailBatch) -> dict:
    return {
        "id": batch.batch_id,
        "brief_id": batch.brief_id,
        "triggered_by": batch.triggered_by,
        "triggered_at": _serialize_datetime(batch.triggered_at),
        "completed_at": _serialize_datetime(batch.completed_at),
        "recipient_count": batch.recipient_count,
        "accepted_count": batch.accepted_count,
        "rejected_count": batch.rejected_count,
        "failed_count": batch.failed_count,
        "status": batch.status,
        "recipients": [{
            "name": item.recipient_name,
            "email": item.recipient_email,
            "status": item.status,
            "smtp_code": item.smtp_code,
            "smtp_message": item.smtp_message,
            "attempted_at": _serialize_datetime(item.attempted_at),
        } for item in batch.recipients],
    }


def _parse_content(block: DailyBriefBlock) -> dict:
    try:
        content = json.loads(block.content_json or "{}")
        return content if isinstance(content, dict) else {}
    except (TypeError, ValueError):
        return {}


def _serialize_brief(brief: DailyBrief, *, include_blocks: bool = False, read: bool = False) -> dict:
    payload = {
        "id": brief.brief_id,
        "title": brief.title,
        "brief_date": brief.brief_date.isoformat() if brief.brief_date else None,
        "status": brief.status,
        "audience_type": brief.audience_type,
        "created_by": brief.created_by,
        "created_at": _serialize_datetime(brief.created_at),
        "updated_at": _serialize_datetime(brief.updated_at),
        "published_by": brief.published_by,
        "published_at": _serialize_datetime(brief.published_at),
        "archived_at": _serialize_datetime(brief.archived_at),
        "read": read,
    }
    if include_blocks:
        payload["blocks"] = [
            {"id": block.block_id, "block_type": block.block_type, "position": block.position, "content": _parse_content(block)}
            for block in sorted(brief.blocks, key=lambda item: item.position)
        ]
    return payload


def _text(value, *, required: bool = False, limit: int = 4000) -> str:
    result = str(value or "").strip()
    if required and not result:
        raise HTTPException(status_code=422, detail="Required block content is missing")
    if len(result) > limit:
        raise HTTPException(status_code=422, detail="Block content is too long")
    return result


def _validate_blocks(blocks: list[BlockInput], *, publishing: bool) -> list[dict]:
    validated = []
    for item in blocks:
        block_type = item.block_type.strip().lower()
        if block_type not in ALLOWED_BLOCK_TYPES:
            raise HTTPException(status_code=422, detail=f"Invalid block type: {block_type}")
        content = dict(item.content or {})
        if block_type == "heading":
            content = {
                "heading": _text(content.get("heading"), required=publishing, limit=240),
                "subtitle": _text(content.get("subtitle"), limit=500),
                "alignment": content.get("alignment") if content.get("alignment") in {"left", "center", "right"} else "left",
            }
        elif block_type == "text":
            # Older briefs use plain text; newer briefs may include sanitized rich text.
            text_value = _text(content.get("text"), required=publishing and not content.get("html"), limit=6000)
            html_value = _sanitize_rich_html(content.get("html"))
            if publishing and not (text_value or html_value):
                raise HTTPException(status_code=422, detail="Required block content is missing")
            content = {"text": text_value, "html": html_value}
        elif block_type in {"highlight", "alert"}:
            content = {
                "heading": _text(content.get("heading") or content.get("title"), required=publishing, limit=240),
                "text": _text(content.get("text") or content.get("message"), required=publishing, limit=4000),
                "style": content.get("style") if content.get("style") in ALLOWED_HIGHLIGHT_STYLES else "standard",
            }
        elif block_type == "image":
            content = {
                "image_url": _text(content.get("image_url"), required=publishing, limit=500),
                "caption": _text(content.get("caption"), limit=500),
                "alt": _text(content.get("alt"), limit=300),
            }
        elif block_type == "bullet_list":
            items = content.get("items") if isinstance(content.get("items"), list) else []
            clean_items = [_text(value, required=publishing, limit=500) for value in items[:50] if _text(value, limit=500)]
            if publishing and not clean_items:
                raise HTTPException(status_code=422, detail="Bullet list needs at least one item")
            content = {"heading": _text(content.get("heading"), limit=240), "items": clean_items}
        elif block_type == "image_text":
            content = {
                "image_url": _text(content.get("image_url"), required=publishing, limit=500),
                "heading": _text(content.get("heading"), limit=240),
                "text": _text(content.get("text"), required=publishing, limit=4000),
                "alt": _text(content.get("alt"), limit=300),
                "image_position": "right" if content.get("image_position") == "right" else "left",
            }
        elif block_type == "cta":
            link = _text(content.get("link"), required=publishing, limit=500)
            if link and not (link.startswith("/") or re.match(r"^https://[^\s]+$", link)):
                raise HTTPException(status_code=422, detail="CTA link must be an internal path or HTTPS URL")
            content = {"label": _text(content.get("label"), required=publishing, limit=100), "link": link}
        else:
            content = {}
        validated.append({"block_type": block_type, "content": content})
    return validated


async def _get_brief(request: Request, brief_id: str, *, include_blocks: bool = True) -> DailyBrief:
    query = select(DailyBrief).where(and_(DailyBrief.brief_id == brief_id, DailyBrief.deleted_at.is_(None)))
    if include_blocks:
        query = query.options(selectinload(DailyBrief.blocks))
    async with request.app.state.db_client() as session:
        result = await session.execute(query)
        brief = result.scalar_one_or_none()
    if brief is None:
        raise HTTPException(status_code=404, detail="Daily Brief not found")
    return brief


async def _replace_blocks(session, brief: DailyBrief, blocks: list[dict]) -> None:
    existing = await session.execute(select(DailyBriefBlock).where(DailyBriefBlock.brief_id == brief.brief_id))
    for block in existing.scalars().all():
        await session.delete(block)
    # Flush removals before reusing the same (brief_id, position) unique keys.
    await session.flush()
    for position, block in enumerate(blocks):
        session.add(DailyBriefBlock(brief_id=brief.brief_id, block_type=block["block_type"], position=position, content_json=json.dumps(block["content"])))


def _image_directory(request: Request) -> Path:
    directory = Path(__file__).resolve().parents[2] / "daily_brief" / "brief_images"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _record_action(session, brief_id, action, user):
    session.add(DailyBriefAction(brief_id=brief_id, action=action, actor=_actor(user), occurred_at=_now()))


@router.get("/{brief_id}/actions")
async def brief_actions(brief_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    async with request.app.state.db_client() as session:
        brief = await session.get(DailyBrief, brief_id)
        if brief is None:
            raise HTTPException(status_code=404, detail="Daily Brief not found")
        rows = (await session.scalars(select(DailyBriefAction).where(DailyBriefAction.brief_id == brief_id).order_by(DailyBriefAction.occurred_at.desc(), DailyBriefAction.action_id.desc()))).all()
        return {"items": [{"id": row.action_id, "action": row.action, "actor": row.actor, "occurred_at": _serialize_datetime(row.occurred_at.replace(tzinfo=timezone.utc) if row.occurred_at.tzinfo is None else row.occurred_at)} for row in rows]}


async def _audience_snapshot(session):
    saved = await session.get(DailyBriefAudience, 1)
    if saved is None:
        return {"recipients": [dict(item) for item in DAILY_BRIEF_EMAIL_RECIPIENTS], "revision": 0}
    return {"recipients": json.loads(saved.recipients_json), "revision": saved.revision}


@router.get("/audience")
async def get_audience(request: Request, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    async with request.app.state.db_client() as session:
        return await _audience_snapshot(session)


@router.post("/audience/save")
async def save_audience(payload: AudienceInput, request: Request, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    recipients = [item.model_dump() for item in payload.recipients]
    conflict = "The audience was changed by another administrator. Reload before saving."
    async with request.app.state.db_client() as session:
        try:
            async with session.begin():
                if payload.revision == 0:
                    session.add(DailyBriefAudience(audience_id=1, recipients_json=json.dumps(recipients), revision=1, updated_by=_actor(current_user)))
                else:
                    result = await session.execute(update(DailyBriefAudience).where(
                        DailyBriefAudience.audience_id == 1, DailyBriefAudience.revision == payload.revision
                    ).values(recipients_json=json.dumps(recipients), revision=payload.revision + 1, updated_by=_actor(current_user)))
                    if result.rowcount != 1:
                        raise HTTPException(status_code=409, detail=conflict)
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail=conflict) from exc
    return {"recipients": recipients, "revision": payload.revision + 1}


@router.get("/summary")
async def summary(request: Request, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    async with request.app.state.db_client() as session:
        result = await session.execute(
            select(DailyBrief.status, func.count(DailyBrief.brief_id)).where(DailyBrief.deleted_at.is_(None)).group_by(DailyBrief.status)
        )
    counts = {status_name: total for status_name, total in result.all()}
    return {"drafts": counts.get("DRAFT", 0), "live": counts.get("LIVE", 0), "archived": counts.get("ARCHIVED", 0)}


@router.get("")
async def list_briefs(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    predicates = [DailyBrief.deleted_at.is_(None)]
    if status_filter in {"DRAFT", "LIVE", "ARCHIVED"}:
        predicates.append(DailyBrief.status == status_filter)
    if search and search.strip():
        predicates.append(DailyBrief.title.ilike(f"%{search.strip()}%"))
    async with request.app.state.db_client() as session:
        total = await session.scalar(select(func.count(DailyBrief.brief_id)).where(*predicates))
        result = await session.execute(
            select(DailyBrief).where(*predicates).order_by(DailyBrief.updated_at.desc(), DailyBrief.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        items = result.scalars().all()
    return {"items": [_serialize_brief(item) for item in items], "total": total or 0, "page": page, "page_size": page_size}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_brief(payload: BriefInput, request: Request, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    blocks = _validate_blocks(payload.blocks, publishing=False)
    async with request.app.state.db_client() as session:
        async with session.begin():
            brief = DailyBrief(title=payload.title.strip() or "Untitled Daily Brief", brief_date=payload.brief_date or date.today(), created_by=_actor(current_user))
            session.add(brief)
            await session.flush()
            _record_action(session, brief.brief_id, "CREATED", current_user)
            for position, block in enumerate(blocks):
                session.add(DailyBriefBlock(brief_id=brief.brief_id, block_type=block["block_type"], position=position, content_json=json.dumps(block["content"])))
        await session.refresh(brief)
    return _serialize_brief(brief)


@router.get("/current")
async def current_brief(request: Request, current_user: dict = Depends(get_current_user)):
    async with request.app.state.db_client() as session:
        result = await session.execute(
            select(DailyBrief).options(selectinload(DailyBrief.blocks)).where(and_(DailyBrief.status == "LIVE", DailyBrief.deleted_at.is_(None)))
        )
        brief = result.scalar_one_or_none()
        if brief is None:
            return {"item": None}
        read = False
        if _role(current_user) in RETAIL_ROLES:
            email = _actor(current_user)
            read = bool(await session.scalar(select(DailyBriefRead.read_id).where(and_(DailyBriefRead.brief_id == brief.brief_id, DailyBriefRead.user_email == email))))
            now = _now()
            view_insert = sqlite_insert(DailyBriefView).values(
                brief_id=brief.brief_id,
                user_email=email,
                first_viewed_at=now,
                last_viewed_at=now,
                view_count=1,
            )
            await session.execute(
                view_insert.on_conflict_do_update(
                    index_elements=[DailyBriefView.brief_id, DailyBriefView.user_email],
                    set_={"last_viewed_at": now, "view_count": DailyBriefView.view_count + 1},
                )
            )
            view_count = await session.scalar(
                select(func.count(func.distinct(func.lower(DailyBriefView.user_email)))).where(
                    DailyBriefView.brief_id == brief.brief_id
                )
            )
            feedback = await session.scalar(
                select(DailyBriefFeedback).where(
                    and_(DailyBriefFeedback.brief_id == brief.brief_id, DailyBriefFeedback.user_email == email)
                )
            )
            await session.commit()
        payload = _serialize_brief(brief, include_blocks=True, read=read)
        if _role(current_user) in RETAIL_ROLES:
            read_record = await session.scalar(select(DailyBriefRead).where(and_(DailyBriefRead.brief_id == brief.brief_id, DailyBriefRead.user_email == _actor(current_user))))
            payload["read_at"] = _serialize_datetime(read_record.read_at) if read_record else None
            payload["total_view_count"] = view_count or 0
            payload["current_user_reaction"] = feedback.reaction if feedback else None
            payload["current_user_comment"] = feedback.comment if feedback else None
        return {"item": payload}


@router.get("/history")
async def history(request: Request, current_user: dict = Depends(get_current_user)):
    async with request.app.state.db_client() as session:
        result = await session.execute(
            select(DailyBrief).where(and_(DailyBrief.status == "ARCHIVED", DailyBrief.deleted_at.is_(None))).order_by(DailyBrief.archived_at.desc()).limit(100)
        )
        items = result.scalars().all()
        read_dates = {}
        if _role(current_user) in RETAIL_ROLES and items:
            reads = await session.execute(select(DailyBriefRead.brief_id, DailyBriefRead.read_at).where(and_(DailyBriefRead.user_email == _actor(current_user), DailyBriefRead.brief_id.in_([item.brief_id for item in items]))))
            read_dates = dict(reads.all())
    payload = []
    for item in items:
        serialized = _serialize_brief(item, read=item.brief_id in read_dates)
        serialized["read_at"] = _serialize_datetime(read_dates.get(item.brief_id))
        payload.append(serialized)
    return {"items": payload}


@router.get("/history/{brief_id}")
async def public_history_brief(brief_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    async with request.app.state.db_client() as session:
        result = await session.execute(
            select(DailyBrief).options(selectinload(DailyBrief.blocks)).where(
                and_(DailyBrief.brief_id == brief_id, DailyBrief.status == "ARCHIVED", DailyBrief.deleted_at.is_(None))
            )
        )
        brief = result.scalar_one_or_none()
    if brief is None:
        raise HTTPException(status_code=404, detail="Previous Daily Brief not found")
    read_record = None
    if _role(current_user) in RETAIL_ROLES:
        async with request.app.state.db_client() as session:
            read_record = await session.scalar(select(DailyBriefRead).where(and_(DailyBriefRead.brief_id == brief_id, DailyBriefRead.user_email == _actor(current_user))))
    payload = _serialize_brief(brief, include_blocks=True, read=bool(read_record))
    payload["read_at"] = _serialize_datetime(read_record.read_at) if read_record else None
    return {"item": payload}


@router.get("/{brief_id}")
async def get_brief(brief_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    return {"item": _serialize_brief(await _get_brief(request, brief_id), include_blocks=True)}


async def _save_brief(brief_id: str, payload: BriefInput, request: Request, current_user: dict):
    _require_admin(current_user)
    actor = _actor(current_user)
    role = _role(current_user)
    logger.info(
        "Daily Brief save requested: method=%s brief_id=%s user=%s subject=%s role=%s blocks=%s",
        request.method,
        brief_id,
        actor,
        current_user.get("sub") or "unknown",
        role,
        len(payload.blocks),
    )
    try:
        blocks = _validate_blocks(payload.blocks, publishing=False)
    except HTTPException as error:
        logger.warning(
            "Daily Brief save validation failed: brief_id=%s user=%s status=%s detail=%s",
            brief_id,
            actor,
            error.status_code,
            error.detail,
        )
        raise

    logger.info("Daily Brief save validation passed: brief_id=%s user=%s blocks=%s", brief_id, actor, len(blocks))
    async with request.app.state.db_client() as session:
        try:
            async with session.begin():
                result = await session.execute(select(DailyBrief).where(and_(DailyBrief.brief_id == brief_id, DailyBrief.deleted_at.is_(None))))
                brief = result.scalar_one_or_none()
                if brief is None:
                    logger.warning("Daily Brief save lookup failed: brief_id=%s user=%s", brief_id, actor)
                    raise HTTPException(status_code=404, detail="Daily Brief not found")
                logger.info("Daily Brief save lookup passed: brief_id=%s user=%s", brief_id, actor)
                brief.title = payload.title.strip() or "Untitled Daily Brief"
                brief.brief_date = payload.brief_date or brief.brief_date
                brief.updated_at = _now()
                _record_action(session, brief_id, "EDITED", current_user)
                await _replace_blocks(session, brief, blocks)
                await session.flush()
            logger.info("Daily Brief save commit succeeded: brief_id=%s user=%s", brief_id, actor)
        except HTTPException:
            raise
        except Exception:
            await session.rollback()
            logger.exception("Daily Brief save failed and was rolled back: brief_id=%s user=%s role=%s", brief_id, actor, role)
            raise
    # Verify the committed values through a separate session before responding.
    async with request.app.state.db_client() as verification_session:
        result = await verification_session.execute(
            select(DailyBrief).options(selectinload(DailyBrief.blocks)).where(DailyBrief.brief_id == brief_id)
        )
        persisted_brief = result.scalar_one()
    logger.info(
        "Daily Brief persisted: id=%s title=%s brief_date=%s block_count=%s",
        persisted_brief.brief_id,
        persisted_brief.title,
        persisted_brief.brief_date,
        len(persisted_brief.blocks),
    )
    return {"item": _serialize_brief(persisted_brief, include_blocks=True)}


@router.put("/{brief_id}")
async def update_brief(brief_id: str, payload: BriefInput, request: Request, current_user: dict = Depends(get_current_user)):
    """Legacy update route retained for API clients that already use PUT."""
    return await _save_brief(brief_id, payload, request, current_user)


@router.post("/{brief_id}/save")
async def save_brief(brief_id: str, payload: BriefInput, request: Request, current_user: dict = Depends(get_current_user)):
    """Browser-safe save route for deployments that restrict PUT requests."""
    return await _save_brief(brief_id, payload, request, current_user)


@router.delete("/{brief_id}")
async def delete_brief(brief_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    async with request.app.state.db_client() as session:
        async with session.begin():
            result = await session.execute(select(DailyBrief).where(DailyBrief.brief_id == brief_id))
            brief = result.scalar_one_or_none()
            if brief is None:
                raise HTTPException(status_code=404, detail="Daily Brief not found")
            if brief.status == "LIVE":
                brief.status = "ARCHIVED"
                brief.archived_at = _now()
            _record_action(session, brief_id, "DELETED", current_user)
            brief.deleted_at = _now()
    return {"message": "Daily Brief deleted"}


@router.post("/{brief_id}/duplicate", status_code=status.HTTP_201_CREATED)
async def duplicate_brief(brief_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    async with request.app.state.db_client() as session:
        async with session.begin():
            result = await session.execute(select(DailyBrief).options(selectinload(DailyBrief.blocks)).where(and_(DailyBrief.brief_id == brief_id, DailyBrief.deleted_at.is_(None))))
            source = result.scalar_one_or_none()
            if source is None:
                raise HTTPException(status_code=404, detail="Daily Brief not found")
            copy = DailyBrief(title=f"Copy of {source.title}"[:200], brief_date=source.brief_date, status="DRAFT", created_by=_actor(current_user))
            session.add(copy)
            await session.flush()
            _record_action(session, copy.brief_id, "DUPLICATED", current_user)
            for position, block in enumerate(sorted(source.blocks, key=lambda item: item.position)):
                session.add(DailyBriefBlock(brief_id=copy.brief_id, block_type=block.block_type, position=position, content_json=block.content_json))
        result = await session.execute(select(DailyBrief).options(selectinload(DailyBrief.blocks)).where(DailyBrief.brief_id == copy.brief_id))
        copy = result.scalar_one()
    return {"item": _serialize_brief(copy, include_blocks=True)}


@router.post("/{brief_id}/publish")
async def publish_brief(brief_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    async with request.app.state.db_client() as session:
        try:
            async with session.begin():
                result = await session.execute(select(DailyBrief).options(selectinload(DailyBrief.blocks)).where(and_(DailyBrief.brief_id == brief_id, DailyBrief.deleted_at.is_(None))))
                brief = result.scalar_one_or_none()
                if brief is None:
                    raise HTTPException(status_code=404, detail="Daily Brief not found")
                if brief.status != "DRAFT":
                    raise HTTPException(status_code=409, detail="Only drafts may be published")
                if not brief.title.strip() or not brief.brief_date:
                    raise HTTPException(status_code=422, detail="Title and brief date are required before publishing")
                _validate_blocks([BlockInput(block_type=block.block_type, content=_parse_content(block)) for block in brief.blocks], publishing=True)
                if not brief.blocks:
                    raise HTTPException(status_code=422, detail="Add at least one content block before publishing")
                previous_live = (await session.scalars(select(DailyBrief).where(DailyBrief.status == "LIVE"))).all()
                for previous in previous_live:
                    _record_action(session, previous.brief_id, "AUTO_ARCHIVED", current_user)
                now = _now()
                # Soft-deleted legacy briefs can retain LIVE status. Archive every
                # LIVE row before promoting this draft so the single-live rule holds.
                await session.execute(update(DailyBrief).where(DailyBrief.status == "LIVE").values(status="ARCHIVED", archived_at=now))
                brief.status = "LIVE"
                brief.published_by = _actor(current_user)
                _record_action(session, brief_id, "PUBLISHED", current_user)
                brief.published_at = now
                brief.archived_at = None
        except IntegrityError as error:
            raise HTTPException(status_code=409, detail="Another Daily Brief is being published. Please retry.") from error
    return {"message": "Daily Brief published"}


@router.post("/{brief_id}/archive")
async def archive_brief(brief_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    async with request.app.state.db_client() as session:
        async with session.begin():
            result = await session.execute(select(DailyBrief).where(and_(DailyBrief.brief_id == brief_id, DailyBrief.deleted_at.is_(None))))
            brief = result.scalar_one_or_none()
            if brief is None:
                raise HTTPException(status_code=404, detail="Daily Brief not found")
            if brief.status != "LIVE":
                raise HTTPException(status_code=409, detail="Only the live Daily Brief may be archived")
            brief.status = "ARCHIVED"
            brief.archived_at = _now()
            _record_action(session, brief_id, "ARCHIVED", current_user)
    return {"message": "Daily Brief archived"}


@router.post("/{brief_id}/restore-live")
async def restore_live_brief(brief_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Restore one archived brief as the only Retail-visible Daily Brief."""
    _require_admin(current_user)
    async with request.app.state.db_client() as session:
        try:
            async with session.begin():
                brief = await session.scalar(
                    select(DailyBrief).where(and_(DailyBrief.brief_id == brief_id, DailyBrief.deleted_at.is_(None)))
                )
                if brief is None:
                    raise HTTPException(status_code=404, detail="Daily Brief not found")
                if brief.status != "ARCHIVED":
                    raise HTTPException(status_code=409, detail="Only archived Daily Briefs may be restored")
                previous_live = (await session.scalars(select(DailyBrief).where(and_(DailyBrief.status == "LIVE", DailyBrief.deleted_at.is_(None))))).all()
                for previous in previous_live:
                    _record_action(session, previous.brief_id, "AUTO_ARCHIVED", current_user)
                now = _now()
                await session.execute(
                    update(DailyBrief)
                    .where(and_(DailyBrief.status == "LIVE", DailyBrief.deleted_at.is_(None)))
                    .values(status="ARCHIVED", archived_at=now)
                )
                brief.status = "LIVE"
                brief.archived_at = None
                brief.published_by = _actor(current_user)
                brief.published_at = now
                _record_action(session, brief_id, "RESTORED", current_user)
        except IntegrityError as error:
            raise HTTPException(status_code=409, detail="Another Daily Brief is being made live. Please retry.") from error
    return {"message": "Daily Brief restored as live"}


@router.post("/{brief_id}/read")
async def mark_read(brief_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    _require_retail(current_user)
    email = _actor(current_user)
    async with request.app.state.db_client() as session:
        async with session.begin():
            brief = await session.scalar(select(DailyBrief).where(and_(DailyBrief.brief_id == brief_id, DailyBrief.status == "LIVE", DailyBrief.deleted_at.is_(None))))
            if brief is None:
                raise HTTPException(status_code=404, detail="Live Daily Brief not found")
            existing = await session.scalar(select(DailyBriefRead).where(and_(DailyBriefRead.brief_id == brief_id, DailyBriefRead.user_email == email)))
            if existing is None:
                session.add(DailyBriefRead(brief_id=brief_id, user_email=email))
    return {"message": "Marked as read", "read": True}


@router.post("/{brief_id}/feedback")
async def save_feedback(
    brief_id: str,
    payload: FeedbackInput,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    _require_retail(current_user)
    email = _actor(current_user)
    comment = _text(payload.comment, limit=4000) or None
    reaction = payload.reaction
    now = _now()

    async with request.app.state.db_client() as session:
        async with session.begin():
            brief = await session.scalar(
                select(DailyBrief).where(
                    and_(DailyBrief.brief_id == brief_id, DailyBrief.status == "LIVE", DailyBrief.deleted_at.is_(None))
                )
            )
            if brief is None:
                raise HTTPException(status_code=404, detail="Live Daily Brief not found")

            if reaction is None and comment is None:
                existing = await session.scalar(
                    select(DailyBriefFeedback).where(
                        and_(DailyBriefFeedback.brief_id == brief_id, DailyBriefFeedback.user_email == email)
                    )
                )
                if existing is not None:
                    await session.delete(existing)
            else:
                feedback_insert = sqlite_insert(DailyBriefFeedback).values(
                    brief_id=brief_id,
                    user_email=email,
                    reaction=reaction,
                    comment=comment,
                    feedback_updated_at=now,
                )
                await session.execute(
                    feedback_insert.on_conflict_do_update(
                        index_elements=[DailyBriefFeedback.brief_id, DailyBriefFeedback.user_email],
                        set_={"reaction": reaction, "comment": comment, "feedback_updated_at": now},
                    )
                )

    return {
        "message": "Feedback saved",
        "reaction": reaction,
        "comment": comment,
        "feedback_updated_at": _serialize_datetime(now) if reaction is not None or comment is not None else None,
    }


@router.post("/{brief_id}/notify-retail")
async def notify_retail(
    brief_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Queue the Arabic Daily Brief notification for the approved email allowlist."""
    _require_admin(current_user)
    log_notification_runtime()
    now, actor = _now(), _actor(current_user)
    async with request.app.state.db_client() as session:
        async with session.begin():
            brief = await session.scalar(select(DailyBrief).where(and_(DailyBrief.brief_id == brief_id, DailyBrief.status == "LIVE", DailyBrief.deleted_at.is_(None))))
            if brief is None:
                raise HTTPException(status_code=409, detail="Only the Live Daily Brief can be emailed")
            duplicate = await session.scalar(select(DailyBriefEmailBatch.batch_id).where(and_(
                DailyBriefEmailBatch.brief_id == brief_id,
                or_(DailyBriefEmailBatch.status == EMAIL_BATCH_PROCESSING,
                    and_(DailyBriefEmailBatch.status == EMAIL_BATCH_PENDING,
                         DailyBriefEmailBatch.triggered_at >= now - timedelta(minutes=5))),
            )))
            if duplicate:
                raise HTTPException(status_code=409, detail="A Daily Brief email attempt is already in progress")
            # The send allowlist is intentionally fixed; a stale saved audience must not add recipients.
            recipients = [{"name": item["name"], "email": item["email"].lower()} for item in DAILY_BRIEF_EMAIL_RECIPIENTS]
            batch = DailyBriefEmailBatch(brief_id=brief_id, triggered_by=actor, triggered_at=now, recipient_count=len(recipients), status=EMAIL_BATCH_PENDING)
            session.add(batch)
            await session.flush()
            session.add_all(DailyBriefEmailRecipient(batch_id=batch.batch_id, recipient_name=item["name"], recipient_email=item["email"], position=position, status=EMAIL_RECIPIENT_PENDING) for position, item in enumerate(recipients))
            _record_action(session, brief_id, "EMAIL_SEND_STARTED", current_user)
            batch_id, brief_title = batch.batch_id, brief.title

    root_path = str(request.scope.get("root_path") or "").rstrip("/")
    brief_url = f"{str(request.base_url).rstrip('/')}{root_path}/login"
    background_tasks.add_task(_send_daily_brief_notifications, request.app.state.db_client, batch_id, recipients, brief_title, brief_url)
    return {
        "message": "Daily Brief email delivery has started.",
        "batch_id": batch_id,
        "recipient_count": len(recipients),
        "smtp_disabled": _smtp_disabled(),
    }


@router.get("/{brief_id}/email-delivery-history")
async def email_delivery_history(brief_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    async with request.app.state.db_client() as session:
        rows = (await session.scalars(select(DailyBriefEmailBatch).options(selectinload(DailyBriefEmailBatch.recipients)).where(DailyBriefEmailBatch.brief_id == brief_id).order_by(DailyBriefEmailBatch.triggered_at.desc()).limit(20))).all()
    return {"items": [_serialize_email_batch(row) for row in rows]}


@router.get("/{brief_id}/email-delivery/latest")
async def latest_email_delivery(brief_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    async with request.app.state.db_client() as session:
        row = await session.scalar(select(DailyBriefEmailBatch).options(selectinload(DailyBriefEmailBatch.recipients)).where(DailyBriefEmailBatch.brief_id == brief_id).order_by(DailyBriefEmailBatch.triggered_at.desc()).limit(1))
    return {"item": _serialize_email_batch(row) if row else None}


@router.get("/{brief_id}/analytics")
async def analytics(brief_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    async with request.app.state.db_client() as session:
        brief = await session.scalar(select(DailyBrief).where(and_(DailyBrief.brief_id == brief_id, DailyBrief.deleted_at.is_(None))))
        if brief is None:
            raise HTTPException(status_code=404, detail="Daily Brief not found")
        read = await session.scalar(select(func.count(DailyBriefRead.read_id)).where(DailyBriefRead.brief_id == brief_id))
        employee_rows = await session.execute(
            select(
                Employee.name,
                Employee.email,
                Employee.hr_id,
                Employee.branch_code,
                Branch.branch_name,
                Branch.branch_region,
                Branch.branch_area,
            )
            .outerjoin(Branch, Employee.branch_code == Branch.branch_code)
            .where(
                and_(
                    func.lower(Employee.department).in_(["retail", "employee"]),
                    func.lower(Employee.employment_status) == "active",
                )
            )
            .order_by(Employee.name.asc(), Employee.hr_id.asc())
        )
        view_rows = await session.execute(
            select(DailyBriefView.user_email, DailyBriefView.first_viewed_at, DailyBriefView.last_viewed_at)
            .where(DailyBriefView.brief_id == brief_id)
        )
        feedback_rows = await session.execute(
            select(
                DailyBriefFeedback.user_email,
                DailyBriefFeedback.reaction,
                DailyBriefFeedback.comment,
                DailyBriefFeedback.feedback_updated_at,
            ).where(DailyBriefFeedback.brief_id == brief_id)
        )

    views_by_email = {}
    for email, first_viewed_at, last_viewed_at in view_rows:
        normalized_email = (email or "").strip().lower()
        current = views_by_email.get(normalized_email)
        if current is None or first_viewed_at < current["first_viewed_at"]:
            views_by_email[normalized_email] = {"first_viewed_at": first_viewed_at, "last_viewed_at": last_viewed_at}
        elif last_viewed_at > current["last_viewed_at"]:
            current["last_viewed_at"] = last_viewed_at

    feedback_by_email = {
        (email or "").strip().lower(): {"reaction": reaction, "comment": comment, "feedback_updated_at": updated_at}
        for email, reaction, comment, updated_at in feedback_rows
    }
    employees = []
    for row in employee_rows:
        email = (row.email or "").strip().lower()
        viewed_record = views_by_email.get(email)
        feedback = feedback_by_email.get(email, {})
        employees.append(
            {
                "name": row.name,
                "email": row.email,
                "hr_id": row.hr_id,
                "branch_code": row.branch_code,
                "branch": row.branch_name or "Unassigned",
                "region": row.branch_region or "Unassigned",
                "area": row.branch_area or "Unassigned",
                "viewed": viewed_record is not None,
                "viewed_at": _serialize_datetime(viewed_record["first_viewed_at"]) if viewed_record else None,
                "last_viewed_at": _serialize_datetime(viewed_record["last_viewed_at"]) if viewed_record else None,
                "reaction": feedback.get("reaction"),
                "comment": feedback.get("comment") or "",
                "feedback_updated_at": _serialize_datetime(feedback.get("feedback_updated_at")),
            }
        )

    eligible = len(employees)
    viewed = sum(employee["viewed"] for employee in employees)
    not_viewed = max(eligible - viewed, 0)
    likes = sum(employee["reaction"] == "LIKE" for employee in employees)
    unlikes = sum(employee["reaction"] == "UNLIKE" for employee in employees)
    comments = sum(bool(employee["comment"].strip()) for employee in employees)
    areas_by_name = {}
    for employee in employees:
        area_key = (employee["region"], employee["area"])
        area = areas_by_name.setdefault(
            area_key,
            {"region": employee["region"], "area": employee["area"], "eligible": 0, "viewed": 0, "likes": 0, "unlikes": 0, "comments": 0},
        )
        area["eligible"] += 1
        area["viewed"] += int(employee["viewed"])
        area["likes"] += int(employee["reaction"] == "LIKE")
        area["unlikes"] += int(employee["reaction"] == "UNLIKE")
        area["comments"] += int(bool(employee["comment"].strip()))
    area_summary = []
    for area in areas_by_name.values():
        area["not_viewed"] = area["eligible"] - area["viewed"]
        area["view_rate"] = round(area["viewed"] / area["eligible"] * 100, 1) if area["eligible"] else 0
        area["coverage_status"] = (
            "complete" if area["view_rate"] == 100 else "no_views" if area["viewed"] == 0 else "low" if area["view_rate"] < 70 else "on_track"
        )
        area_summary.append(area)
    area_summary.sort(key=lambda area: (area["region"].casefold(), area["area"].casefold()))
    viewed_users = [
        {"name": employee["name"], "hr_id": employee["hr_id"], "email": employee["email"], "first_viewed_at": employee["viewed_at"], "last_viewed_at": employee["last_viewed_at"]}
        for employee in employees if employee["viewed"]
    ]
    viewed_users.sort(key=lambda viewer: viewer["first_viewed_at"] or "", reverse=True)
    latest_comments = [
        {"name": employee["name"], "email": employee["email"], "area": employee["area"], "branch": employee["branch"], "reaction": employee["reaction"], "comment": employee["comment"], "feedback_updated_at": employee["feedback_updated_at"]}
        for employee in employees if employee["comment"].strip()
    ]
    latest_comments.sort(key=lambda comment: comment["feedback_updated_at"] or "", reverse=True)
    read = read or 0
    return {
        "eligible_retail_users": eligible,
        "viewed": viewed,
        "read": read,
        "not_read": max(eligible - read, 0),
        "read_rate": round((read / eligible * 100) if eligible else 0, 1),
        "total_eligible_employees": eligible,
        "total_viewed": viewed,
        "not_viewed": not_viewed,
        "view_rate": round((viewed / eligible * 100) if eligible else 0, 1),
        "total_likes": likes,
        "total_unlikes": unlikes,
        "total_comments": comments,
        "viewed_users": viewed_users,
        "employees": employees,
        "area_summary": area_summary,
        "latest_comments": latest_comments[:10],
    }


@router.get("/{brief_id}/analytics/export")
async def export_analytics(brief_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Export distinct Retail viewers and their branch geography for one Daily Brief."""
    _require_admin(current_user)
    coverage = await analytics(brief_id, request, current_user)
    async with request.app.state.db_client() as session:
        brief = await session.scalar(
            select(DailyBrief).where(
                and_(DailyBrief.brief_id == brief_id, DailyBrief.deleted_at.is_(None))
            )
        )
        if brief is None:
            raise HTTPException(status_code=404, detail="Daily Brief not found")

        viewer_rows = await session.execute(
            select(
                Employee.hr_id,
                Employee.name,
                DailyBriefView.user_email,
                DailyBriefView.first_viewed_at,
                Branch.branch_name,
                Branch.branch_area,
                Branch.branch_region,
            )
            .select_from(DailyBriefView)
            .outerjoin(
                Employee,
                func.lower(DailyBriefView.user_email) == func.lower(Employee.email),
            )
            .outerjoin(Branch, Employee.branch_code == Branch.branch_code)
            .where(DailyBriefView.brief_id == brief_id)
            .order_by(Employee.name.asc(), Employee.hr_id.asc())
        )

        viewers = [
            {
                "User": row.name or "Unknown user",
                "Mail": row.user_email or "",
                "Time": (
                    row.first_viewed_at.replace(tzinfo=timezone.utc)
                    if row.first_viewed_at and row.first_viewed_at.tzinfo is None
                    else row.first_viewed_at
                ),
                "ID": row.hr_id or "",
                "Branch": row.branch_name or "Unassigned",
                "Area": row.branch_area or "Unassigned",
                "Region": row.branch_region or "Unassigned",
            }
            for row in viewer_rows
        ]

    # Excel requires timezone-naive datetimes; store every viewing time in UTC.
    for viewer in viewers:
        if viewer["Time"] is not None:
            viewer["Time"] = viewer["Time"].astimezone(timezone.utc).replace(tzinfo=None)

    summary_rows = [
        {
            "Area": area["area"],
            "Region": area["region"],
            "Eligible": area["eligible"],
            "Viewed": area["viewed"],
            "Not Viewed": area["not_viewed"],
            "View Rate": area["view_rate"] / 100,
            "Likes": area["likes"],
            "Unlikes": area["unlikes"],
            "Comments": area["comments"],
            "Coverage": {
                "complete": "100% viewed",
                "no_views": "No views",
                "low": "Low coverage",
                "on_track": "In progress",
            }[area["coverage_status"]],
        }
        for area in coverage["area_summary"]
    ]
    region_views = {}
    for area in coverage["area_summary"]:
        region = area["region"] or "Unassigned"
        region_views[region] = region_views.get(region, 0) + area["viewed"]
    region_rows = sorted(region_views.items(), key=lambda row: row[0].casefold())
    area_title_row = max(10, len(region_rows) + 2)
    area_header_row = area_title_row + 1
    area_data_row = area_header_row + 1

    import pandas as pd

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(viewers, columns=["User", "Mail", "Time", "ID", "Branch", "Area", "Region"]).to_excel(
            writer, sheet_name="Viewer Details", index=False
        )
        summary = writer.book.create_sheet("View Summary")
        summary.append(["Daily Brief View Summary", brief.title])
        for label, value in [
            ("Total Eligible Employees", coverage["total_eligible_employees"]),
            ("Total Viewed", coverage["total_viewed"]),
            ("Not Viewed", coverage["not_viewed"]),
            ("View Rate", coverage["view_rate"] / 100),
            ("Total Likes", coverage["total_likes"]),
            ("Total Unlikes", coverage["total_unlikes"]),
            ("Total Comments", coverage["total_comments"]),
        ]:
            summary.append([label, value])
        summary["B5"].number_format = "0.0%"
        for _ in range(9, area_title_row):
            summary.append([""])
        summary.append(["Area Coverage", "Low coverage is below 70%"])
        columns = ["Area", "Region", "Eligible", "Viewed", "Not Viewed", "View Rate", "Likes", "Unlikes", "Comments", "Coverage"]
        summary.append(columns)
        for row in summary_rows:
            summary.append([row[column] for column in columns])
            summary.cell(summary.max_row, 6).number_format = "0.0%"
        summary["C1"] = "Region"
        summary["D1"] = "Number of views per region"
        for row_number, (region, views) in enumerate(region_rows, start=2):
            summary.cell(row_number, 3, region)
            summary.cell(row_number, 4, views)

        from openpyxl.comments import Comment
        from openpyxl.styles import Alignment, Font, PatternFill

        details = writer.book["Viewer Details"]
        details["C1"].comment = Comment("First viewed time in UTC.", "Daily Brief")
        for cell in list(details.columns)[2][1:]:
            cell.number_format = 'yyyy-mm-dd hh:mm:ss "UTC"'

        for worksheet in writer.book.worksheets:
            # Names and other user data must remain literal text in Excel.
            for row in worksheet.iter_rows(min_row=2):
                for cell in row:
                    if cell.data_type == "f":
                        cell.data_type = "s"
            worksheet.freeze_panes = f"A{area_data_row}" if worksheet == summary else "A2"
            worksheet.auto_filter.ref = f"A{area_header_row}:J{max(area_header_row, worksheet.max_row)}" if worksheet == summary else worksheet.dimensions
            for column_cells in worksheet.columns:
                width = min(max(len(str(cell.value or "")) for cell in column_cells) + 2, 42)
                worksheet.column_dimensions[column_cells[0].column_letter].width = width
        details.column_dimensions["C"].width = 28
        summary.column_dimensions["A"].width = 28
        summary.column_dimensions["B"].width = 30
        summary.column_dimensions["C"].width = 24
        summary.column_dimensions["D"].width = 30
        summary["B1"].data_type = "s"
        summary["A1"].font = Font(bold=True, color="102A56", size=14)
        summary.cell(area_title_row, 1).font = Font(bold=True, color="102A56", size=12)
        for cell in (summary["C1"], summary["D1"]):
            cell.fill = PatternFill("solid", fgColor="102A56")
            cell.font = Font(bold=True, color="FFFFFF")
            cell.alignment = Alignment(wrap_text=True)
        for cell in summary[area_header_row]:
            cell.fill = PatternFill("solid", fgColor="102A56")
            cell.font = Font(bold=True, color="FFFFFF")
            cell.alignment = Alignment(wrap_text=True)
        summary.row_dimensions[area_header_row].height = 30
        for row in summary.iter_rows(min_row=area_data_row, max_col=10):
            status = row[9].value
            row[9].fill = PatternFill("solid", fgColor="FCE8DE" if status in {"Low coverage", "No views"} else "E4F3E8")

    filename = f"daily_brief_viewers_{brief_id}.xlsx"
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/images")
async def upload_image(request: Request, image: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    suffix = Path(image.filename or "").suffix.lower()
    if suffix not in IMAGE_EXTENSIONS or image.content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(status_code=422, detail="Only PNG, JPEG, and WEBP images are supported")
    data = await image.read()
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail="Image must be between 1 byte and 5 MB")
    filename = f"{uuid.uuid4().hex}{suffix}"
    (_image_directory(request) / filename).write_bytes(data)
    return {"image_url": f"/api/v1/daily-briefs/images/{quote(filename)}"}


@router.get("/images/{filename}")
async def get_image(filename: str, request: Request, current_user: dict = Depends(get_current_user)):
    safe_name = Path(filename).name
    path = _image_directory(request) / safe_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path)
