"""NLP Routes Module."""

import asyncio
import os
import re
import math
import copy
import random
from io import BytesIO
from pathlib import Path
from typing import List, Callable, Tuple
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import json
import logging
import smtplib
import sqlite3
import zlib
from time import perf_counter
from email.message import EmailMessage
from html import escape
from urllib import request
from fastapi import APIRouter, Request, status, Query, Depends, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
import pandas as pd
from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from controllers import ExamController, DataController

from models.exam_model import ExamModel
from models.employee_model import EmployeeModel
from models.material_model import MaterialModel
from models.question_model import QuestionModel

from models.db_schemas import (
    Branch,
    Employee,
    Exam,
    Question,
    Material,
    QuestionChoice,
    ExamAttempt,
    QuestionBankItem,
    QuestionBankChoice,
    QuestionBankGroup,
    QuestionBankGroupMember,
)
from models.db_schemas.learning.schemas.association_table import exam_employees
from models import ResponseSignalEnum
from routes.schemas import (
    ExamCreatePayload,
    ExamUpdatePayload,
    ExamLevelUpdatePayload,
    AudiencePayload,
    AudienceFilters,
    ExamSubmitPayload,
    EmployeePerformanceListPayload,
    EmployeePerformanceExportPayload,
    QuestionBankCreatePayload,
    QuestionBankUpdatePayload,
    EXAM_LEVEL_VALUES,
    DEFAULT_EXAM_LEVEL,
)
from routes.users.auth_utils import get_current_user
from routes.question_bank_groups import assign_question_group
from utils.audit_trail import read_audit_events
from utils.logging_utils import setup_logger
from utils.resigned_users import EMPLOYMENT_STATUS_ACTIVE, is_employee_resigned
from utils.dashboard_snapshots import (compute_kpi_overview, load_published_sources,
                                       requested_snapshot_expired)

logger = setup_logger(
    log_file=__file__,
    log_to_console=False,
    file_mode="a",
)

# logger = logging.getLogger("uvicorn")
exam_router = APIRouter(prefix="/api/v1/exams", tags=["api_v1", "exam"])
EGYPT_TZ = ZoneInfo("Africa/Cairo")
UTC_TZ = timezone.utc
EXAM_NOTIFICATION_LOG = Path(__file__).resolve().parents[2] / "logs" / "training_exam_notifications.jsonl"
DEFAULT_EXAM_NOTIFICATION_LOGIN_URL = "https://hr-training-app.fawrycorp.com:8223/training/login?lang=en"
MANAGEMENT_SUMMARY_CACHE_TTL_SECONDS = 300
MANAGEMENT_LOW_PARTICIPATION_THRESHOLD = float(
    os.getenv("TRAINING_DASHBOARD_LOW_PARTICIPATION_THRESHOLD") or "60"
)
MANAGEMENT_HIGH_FAILURE_THRESHOLD = float(
    os.getenv("TRAINING_DASHBOARD_HIGH_FAILURE_THRESHOLD") or "40"
)
MANAGEMENT_LOW_BRANCH_SCORE_THRESHOLD = float(
    os.getenv("TRAINING_DASHBOARD_LOW_BRANCH_SCORE_THRESHOLD") or "60"
)
MANAGEMENT_MIN_FAILURE_ATTEMPTS = int(
    os.getenv("TRAINING_DASHBOARD_MIN_FAILURE_ATTEMPTS") or "5"
)
MANAGEMENT_LOW_SCORE_THRESHOLD = float(
    os.getenv("TRAINING_DASHBOARD_LOW_SCORE_THRESHOLD") or "60"
)
_management_summary_cache: dict[tuple, dict] = {}
_management_kpi_cache: dict[tuple, dict] = {}
_TOPIC_CAMEL_CASE_BOUNDARY_RE = re.compile(r"(?<=[0-9a-z])(?=[A-Z])")
_TOPIC_SEPARATOR_RE = re.compile(r"[-_/.,]+")
_TOPIC_SPACING_RE = re.compile(r"\s+")
_TOPIC_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_MANAGEMENT_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_MANAGEMENT_TOPIC_LABEL_BY_KEY = {
    "insurance": "Insurance",
    "fawry taqseet": "Fawry Taqseet",
    "fawry yawmy": "Fawry Yawmy",
    "wallets": "Wallets",
    "yellow card": "Yellow Card",
    "maashy": "maashy",
    "general": "General",
}
_MANAGEMENT_TOPIC_ALIAS_BY_KEY = {
    "insurance": "insurance",
    "fawry insurance": "insurance",
    "fawry insurance and maashi": "insurance",
    "fawry insurance and maashi service": "insurance",
    "my fawry taqseet": "fawry taqseet",
    "fawry taqseet": "fawry taqseet",
    "fawry yawmy": "fawry yawmy",
    "e wallets": "wallets",
    "wallets": "wallets",
    "digital wallets": "wallets",
    "smart wallets": "wallets",
    "smart wallet": "wallets",
    "yellow card": "yellow card",
    "maashy": "maashy",
    "general": "general",
    "general questions": "general",
    "general q": "general",
}

#*  -------------------- Helper Functions --------------------

def _normalize_exam_datetime(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(UTC_TZ)

def _serialize_exam_datetime(dt: datetime | None) -> str | None:
    normalized = _normalize_exam_datetime(dt)
    if normalized is None:
        return None
    return normalized.astimezone(EGYPT_TZ).isoformat()

def _normalize_topic_display(value: object | None) -> str:
    normalized = _TOPIC_SPACING_RE.sub(" ", str(value or "").strip())
    return normalized or "Uncategorized"

def _normalize_topic_key(value: object | None) -> str:
    display_value = _normalize_topic_display(value)
    expanded_value = _TOPIC_CAMEL_CASE_BOUNDARY_RE.sub(" ", display_value)
    expanded_value = expanded_value.replace("&", " and ")
    expanded_value = _TOPIC_SEPARATOR_RE.sub(" ", expanded_value)
    normalized_key = _TOPIC_SPACING_RE.sub(" ", expanded_value).strip().casefold()
    return normalized_key or "uncategorized"

def _topic_variant_rank(label: str, count: int) -> tuple[int, int, int, int, int, str]:
    tokens = _TOPIC_TOKEN_RE.findall(label)
    title_case_tokens = 0
    lowercase_tokens = 0
    mixed_case_tokens = 0
    for token in tokens:
        if any(character.isalpha() for character in token):
            if token[:1].isupper():
                title_case_tokens += 1
            if token.islower():
                lowercase_tokens += 1
            if len(token) > 1 and any(character.isupper() for character in token[1:]) and any(character.islower() for character in token[1:]):
                mixed_case_tokens += 1

    return (
        int(count or 0),
        mixed_case_tokens,
        title_case_tokens,
        -lowercase_tokens,
        -label.count(" "),
        label.casefold(),
    )

def _pick_canonical_topic_label(variants: dict[str, int] | None) -> str:
    if not variants:
        return "Uncategorized"

    collapsed_variants: dict[str, int] = {}
    for label, count in variants.items():
        display_label = _normalize_topic_display(label)
        collapsed_variants[display_label] = collapsed_variants.get(display_label, 0) + int(count or 0)

    return max(
        collapsed_variants.items(),
        key=lambda item: _topic_variant_rank(item[0], item[1]),
    )[0]


def _resolve_management_topic_label(value: object | None) -> str | None:
    display_value = _normalize_topic_display(value)
    topic_key = _normalize_topic_key(display_value)
    if topic_key == "uncategorized":
        return None
    canonical_key = _MANAGEMENT_TOPIC_ALIAS_BY_KEY.get(topic_key, topic_key)
    return _MANAGEMENT_TOPIC_LABEL_BY_KEY.get(canonical_key, display_value)

def _coerce_payload_datetime(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        localized = dt.replace(tzinfo=EGYPT_TZ)
    else:
        localized = dt.astimezone(EGYPT_TZ)
    return localized.astimezone(UTC_TZ)

def _validate_duration_against_window(duration_minutes: int, start_dt: datetime | None, end_dt: datetime | None) -> tuple[bool, float]:
    if start_dt is None or end_dt is None:
        return False, 0.0
    window_minutes = (end_dt - start_dt).total_seconds() / 60
    return window_minutes >= float(duration_minutes), window_minutes

def _calculate_exam_max_score(exam: Exam) -> float:
    return sum(float(getattr(question, "points", 0) or 0.0) for question in getattr(exam, "questions", []) or [])

def _calculate_attempt_expiry(exam: Exam, started_at: datetime | None) -> datetime | None:
    normalized_start = _normalize_exam_datetime(started_at)
    if normalized_start is None:
        return None

    duration_minutes = max(0, int(getattr(exam, "duration_minutes", 0) or 0))
    duration_deadline = normalized_start + timedelta(minutes=duration_minutes)
    exam_end = _normalize_exam_datetime(getattr(exam, "end_date", None))
    if exam_end is None:
        return duration_deadline
    return min(duration_deadline, exam_end)

def _is_exam_window_closed(exam: Exam, now: datetime | None = None) -> bool:
    end_dt = _normalize_exam_datetime(getattr(exam, "end_date", None))
    if end_dt is None:
        return False
    reference = _normalize_exam_datetime(now) if now is not None else datetime.now(timezone.utc)
    return bool(reference and reference >= end_dt)

async def _finalize_expired_attempt(
    *,
    exam_model: ExamModel,
    exam: Exam,
    attempt: ExamAttempt,
    now: datetime,
) -> tuple[ExamAttempt | None, dict | None]:
    expires_at = _calculate_attempt_expiry(exam, attempt.started_at)
    if expires_at is None or now < expires_at:
        return attempt, None

    answer_count = await exam_model.get_answer_count_for_attempt(attempt.attempt_id)
    if answer_count <= 0:
        await exam_model.delete_attempt(attempt.attempt_id)
        return None, None

    closed_attempt = await exam_model.close_attempt_as_timed_out(
        attempt.attempt_id,
        max_score=_calculate_exam_max_score(exam),
        submitted_at=expires_at,
    )
    attempt_for_payload = closed_attempt or attempt
    session_state = _build_exam_session_payload(
        exam=exam,
        attempt=attempt_for_payload,
        attempts_used=0,
        attempts_left=0,
        now=expires_at,
        status_value="expired",
        message="Your previous exam session has expired.",
    )
    return None, session_state

def _remaining_seconds_until(target_dt: datetime | None, now: datetime | None = None) -> int:
    if target_dt is None:
        return 0
    reference = now or datetime.now(timezone.utc)
    return max(0, math.ceil((target_dt - reference).total_seconds()))

def _build_exam_session_payload(
    *,
    exam: Exam,
    attempt: ExamAttempt,
    attempts_used: int,
    attempts_left: int,
    now: datetime | None = None,
    status_value: str = "in_progress",
    message: str | None = None,
) -> dict:
    reference = now or datetime.now(timezone.utc)
    expires_at = _calculate_attempt_expiry(exam, attempt.started_at)
    return {
        "status": status_value,
        "attempt_id": attempt.attempt_id,
        "attempt_number": attempt.attempt_number,
        "started_at": _serialize_exam_datetime(attempt.started_at),
        "expires_at": _serialize_exam_datetime(expires_at),
        "remaining_seconds": _remaining_seconds_until(expires_at, reference),
        "attempts_used": attempts_used,
        "attempts_left": attempts_left,
        "message": message,
        "question_order": _attempt_question_order(exam, attempt),
    }


def _attempt_question_order(exam: Exam, attempt: ExamAttempt) -> list[str]:
    """The persisted attempt ID makes order stable across requests and resumes."""
    question_ids = sorted(
        question.question_id for question in exam.questions if not question.is_deleted
    )
    random.Random(attempt.attempt_id).shuffle(question_ids)
    return question_ids

def _serialize_timestamp_value(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _serialize_exam_datetime(value)
    if isinstance(value, str):
        parsed = _parse_iso_datetime(value)
        if parsed:
            return _serialize_exam_datetime(parsed)
    return value  # type: ignore[return-value]

def _resolve_exam_status(exam: Exam, now: datetime | None = None) -> str:
    reference = _normalize_exam_datetime(now) if now is not None else datetime.now(timezone.utc)
    start_dt = _normalize_exam_datetime(exam.start_date)
    stored_status = str(getattr(exam, "exam_status", "") or "Open").strip()
    stored_status_lower = stored_status.lower()

    # Once the exam window ends, the exam is effectively closed regardless of manual status.
    if _is_exam_window_closed(exam, reference):
        return "Closed"

    # Respect manually selected statuses while the exam window is still valid.
    if stored_status_lower == "closed":
        return "Closed"
    if stored_status_lower == "on hold":
        return "On Hold"

    # Open exams scheduled for the future should still appear on hold until they start.
    if start_dt and reference and start_dt > reference:
        return "On Hold"

    return "Open"


def _resolve_exam_level(exam: Exam) -> str:
    stored_level = str(getattr(exam, "exam_level", "") or "").strip()
    if stored_level in EXAM_LEVEL_VALUES:
        return stored_level
    return DEFAULT_EXAM_LEVEL

async def _resolve_audience_hr_ids(employee_model: EmployeeModel, audience: AudiencePayload) -> list[str]:
    if audience.mode == "manual":
        return await employee_model.get_existing_hr_ids(
            sorted({hr_id for hr_id in audience.manual_hr_ids if hr_id}),
            active_only=True,
        )
    if audience.mode == "filters":
        return await employee_model.get_hr_ids_matching_filters(
            audience.filters.model_dump(),
            active_only=True,
        )
    employees = await employee_model.get_all_users(active_only=True)
    return [emp.hr_id for emp in employees]

def _serialize_audience_payload(audience: AudiencePayload) -> tuple[str, str, str]:
    filters_payload = audience.filters.model_dump()
    manual_ids = sorted({hr_id for hr_id in audience.manual_hr_ids if hr_id})
    return (
        audience.mode,
        json.dumps(filters_payload),
        json.dumps(manual_ids),
    )

def _build_audience_config(exam: Exam) -> dict:
    default_filters = AudienceFilters().model_dump()
    try:
        stored_filters = json.loads(exam.audience_filters) if exam.audience_filters else {}
    except json.JSONDecodeError:
        stored_filters = {}
    if stored_filters:
        for key, value in stored_filters.items():
            default_filters[key] = value

    try:
        manual_ids = json.loads(exam.audience_manual_hr_ids) if exam.audience_manual_hr_ids else []
    except json.JSONDecodeError:
        manual_ids = []

    return {
        "mode": exam.audience_mode or "all",
        "filters": default_filters,
        "manual_hr_ids": manual_ids,
    }

def _build_audience_summary(exam: Exam) -> dict:
    employees = getattr(exam, "employees", [])
    return {
        "count": len(employees),
        "hr_ids": [emp.hr_id for emp in employees],
    }

def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        cleaned = value.replace("Z", "+00:00") if isinstance(value, str) else value
        parsed = datetime.fromisoformat(cleaned)  # type: ignore[arg-type]
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC_TZ)
    return parsed

def _safe_percentage(part: int | float, whole: int | float) -> float:
    return round((float(part) / float(whole)) * 100, 2) if whole else 0.0


def _build_regenerated_exam_title(title: str | None) -> str:
    base_title = str(title or "").strip() or "Untitled Exam"
    suffix = " (Regenerated)"
    max_base_length = max(1, 255 - len(suffix))
    return f"{base_title[:max_base_length]}{suffix}"


def _is_employee_dashboard_role(role_value: str | None) -> bool:
    return str(role_value or "").strip().lower() in {"retail", "employee"}


def _is_internal_dashboard_role(role_value: str | None) -> bool:
    return str(role_value or "").strip().lower() in {"admin", "auditor", "hr", "manager"}


def _is_synthetic_dashboard_audit_row(row: dict) -> bool:
    user_agent = str(row.get("user_agent") or "").strip().lower()
    ip_address = str(row.get("ip_address") or "").strip().lower()
    return "testclient" in user_agent or ip_address == "testclient"


def _build_dashboard_user_row(user, *, assigned_exams: int | None = None) -> dict:
    return {
        "email": getattr(user, "email", ""),
        "hr_id": getattr(user, "hr_id", ""),
        "name": getattr(user, "name", ""),
        "role": getattr(user, "department", ""),
        "branch_code": getattr(user, "branch_code", ""),
        "branch_name": getattr(getattr(user, "branch", None), "branch_name", None),
        "assigned_exams": max(0, int(assigned_exams or 0)),
        "created_at": _serialize_exam_datetime(getattr(user, "created_at", None)),
    }


def _prepare_questions_for_persistence(question_payloads: list) -> tuple[list[dict], str | None]:
    if not question_payloads:
        return [], "Please include at least one question."

    prepared_questions: list[dict] = []
    for idx, question_payload in enumerate(question_payloads, start=1):
        qtype = str(question_payload.question_type or "").upper()
        prepared_question = {
            "question_text": str(question_payload.question_text or "").strip(),
            "question_type": qtype,
            "points": question_payload.points,
            "question_group": (str(question_payload.question_group or "").strip() or None),
            "choices": None,
        }

        if not prepared_question["question_text"]:
            return [], f"Question #{idx} must include question text."

        if qtype in {"MCQ", "TF"}:
            if not question_payload.choices or len(question_payload.choices) < 2:
                return [], f"Question #{idx} must include at least two choices."
            if not any(choice.is_correct for choice in question_payload.choices):
                return [], f"Question #{idx} needs one correct choice."
            prepared_question["choices"] = [
                {
                    "choice_text": str(choice.choice_text or "").strip(),
                    "is_correct": bool(choice.is_correct),
                    "choice_order": order + 1,
                }
                for order, choice in enumerate(question_payload.choices)
            ]
            if any(not choice["choice_text"] for choice in prepared_question["choices"]):
                return [], f"Question #{idx} has an empty choice."

        prepared_questions.append(prepared_question)

    return prepared_questions, None


def _normalize_prepared_questions_for_compare(prepared_questions: list[dict]) -> list[dict]:
    normalized_questions: list[dict] = []
    for question in prepared_questions:
        normalized_questions.append(
            {
                "question_text": str(question.get("question_text") or "").strip(),
                "question_type": str(question.get("question_type") or "").upper(),
                "points": int(question.get("points") or 0),
                "question_group": (str(question.get("question_group") or "").strip() or None),
                "choices": [
                    {
                        "choice_text": str(choice.get("choice_text") or "").strip(),
                        "is_correct": bool(choice.get("is_correct")),
                    }
                    for choice in (question.get("choices") or [])
                ],
            }
        )
    return normalized_questions


def _normalize_existing_questions_for_compare(questions: list[Question] | None) -> list[dict]:
    normalized_questions: list[dict] = []
    for question in questions or []:
        ordered_choices = sorted(
            getattr(question, "choices", []) or [],
            key=lambda choice: (choice.choice_order or 0, str(choice.choice_id or "")),
        )
        normalized_questions.append(
            {
                "question_text": str(getattr(question, "question_text", "") or "").strip(),
                "question_type": str(getattr(question, "question_type", "") or "").upper(),
                "points": int(getattr(question, "points", 0) or 0),
                "question_group": (str(getattr(question, "question_group", "") or "").strip() or None),
                "choices": [
                    {
                        "choice_text": str(getattr(choice, "choice_text", "") or "").strip(),
                        "is_correct": bool(getattr(choice, "is_correct", False)),
                    }
                    for choice in ordered_choices
                ],
            }
        )
    return normalized_questions


def _sort_normalized_questions(questions: list[dict]) -> list[dict]:
    return sorted(
        questions,
        key=lambda question: (
            str(question.get("question_group") or ""),
            str(question.get("question_type") or ""),
            int(question.get("points") or 0),
            str(question.get("question_text") or ""),
            json.dumps(question.get("choices") or [], sort_keys=True),
        ),
    )


def _exam_questions_changed(existing_questions: list[Question] | None, prepared_questions: list[dict]) -> bool:
    existing_normalized = _sort_normalized_questions(
        _normalize_existing_questions_for_compare(existing_questions)
    )
    incoming_normalized = _sort_normalized_questions(
        _normalize_prepared_questions_for_compare(prepared_questions)
    )
    return existing_normalized != incoming_normalized


def _serialize_question_bank_item(item: QuestionBankItem) -> dict:
    ordered_choices = sorted(
        getattr(item, "choices", []) or [],
        key=lambda choice: (choice.choice_order or 0, str(choice.bank_choice_id or "")),
    )
    return {
        "bank_question_id": item.bank_question_id,
        "question_text": item.question_text,
        "question_type": item.question_type,
        "points": item.points,
        "question_group": item.question_group,
        "is_favorite": bool(item.is_favorite),
        "created_by": item.created_by,
        "updated_by": item.updated_by,
        "created_at": _serialize_exam_datetime(item.created_at),
        "updated_at": _serialize_exam_datetime(item.updated_at),
        "choices": [
            {
                "bank_choice_id": choice.bank_choice_id,
                "choice_text": choice.choice_text,
                "is_correct": bool(choice.is_correct),
                "choice_order": choice.choice_order,
            }
            for choice in ordered_choices
        ],
    }


def _normalize_email(value: str | None) -> str:
    return str(value or "").strip().lower()


def _format_exam_email_datetime(dt: datetime | None) -> str:
    normalized = _normalize_exam_datetime(dt)
    if normalized is None:
        return "N/A"
    cairo_dt = normalized.astimezone(EGYPT_TZ)
    return cairo_dt.strftime("%A, %d %B %Y at %I:%M %p Cairo Time")


def _resolve_training_portal_base_url(request_obj: Request) -> str:
    configured = (os.getenv("TRAINING_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return configured

    origin = str(request_obj.base_url).rstrip("/")
    root_path = (request_obj.scope.get("root_path") or "").strip()
    if root_path.endswith("/"):
        root_path = root_path.rstrip("/")
    if not root_path:
        root_path = "/training"
    if not root_path.startswith("/"):
        root_path = f"/{root_path}"
    return f"{origin}{root_path}"


def _build_exam_notification_links(request_obj: Request, exam_id: str) -> dict[str, str]:
    configured_login_url = (os.getenv("TRAINING_EXAM_MAIL_LOGIN_URL") or "").strip()
    training_root = _resolve_training_portal_base_url(request_obj)
    return {
        "training_root": training_root,
        "login_url": configured_login_url or DEFAULT_EXAM_NOTIFICATION_LOGIN_URL,
    }


def _build_exam_notification_snapshot(exam: Exam, created_by: str | None = None) -> dict:
    return {
        "exam_id": exam.exam_id,
        "title": exam.title,
        "description": exam.description,
        "exam_status": _resolve_exam_status(exam),
        "duration_minutes": exam.duration_minutes,
        "passing_percent": exam.passing_percent,
        "number_of_attempts_allowed": exam.number_of_attempts_allowed,
        "start_date": exam.start_date,
        "end_date": exam.end_date,
        "created_by": created_by,
    }


def _build_exam_notification_recipients(employees: list[object]) -> list[dict]:
    return [
        {
            "name": getattr(employee, "name", "") or "",
            "email": getattr(employee, "email", "") or "",
            "hr_id": getattr(employee, "hr_id", "") or "",
        }
        for employee in employees
        if _normalize_email(getattr(employee, "email", None))
    ]


def _build_exam_notification_message(recipient_name: str, exam_snapshot: dict, links: dict[str, str]) -> tuple[str, str, str]:
    safe_name = recipient_name.strip() or "Colleague"
    safe_title = str(exam_snapshot.get("title") or "New Exam").strip()
    safe_description = str(exam_snapshot.get("description") or "").strip()
    exam_status = str(exam_snapshot.get("exam_status") or "Open").strip()
    start_text = _format_exam_email_datetime(exam_snapshot.get("start_date"))
    end_text = _format_exam_email_datetime(exam_snapshot.get("end_date"))
    duration_minutes = exam_snapshot.get("duration_minutes")
    attempts_allowed = exam_snapshot.get("number_of_attempts_allowed")
    passing_percent = exam_snapshot.get("passing_percent")
    subject = f"HR Training Exam Assignment | {safe_title}"

    description_block = safe_description or "A new exam has been assigned to you in the HR Training System."
    plain_text = (
        f"Dear {safe_name},\n\n"
        f"You have been assigned a new exam in the HR Training System.\n\n"
        f"Exam Title: {safe_title}\n"
        f"Start Date: {start_text}\n"
        f"End Date: {end_text}\n"
        f"Status: {exam_status}\n"
        f"Duration: {duration_minutes} minutes\n"
        f"Allowed Attempts: {attempts_allowed}\n"
        f"Passing Score: {passing_percent}%\n\n"
        f"Description:\n{description_block}\n\n"
        f"Login Page: {links['login_url']}\n\n"
        f"Please sign in using your registered email address. After login, the assigned exam will appear in My Exams.\n"
        f"If the exam start time is in the future, it will become available once the exam window opens.\n\n"
        f"Regards,\n"
        f"HR Training Team\n"
        f"Fawry\n\n"
        f"This is an automated message. Please do not reply."
    )

    html_text = f"""
    <html>
      <body style="margin:0;padding:0;background-color:#f5f8fc;font-family:Arial,Helvetica,sans-serif;color:#17324d;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#f5f8fc;padding:24px 0;">
          <tr>
            <td align="center">
              <table role="presentation" width="680" cellspacing="0" cellpadding="0" style="max-width:680px;width:100%;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #d8e3f0;">
                <tr>
                  <td style="background:linear-gradient(135deg,#0057b8,#0a74da);padding:28px 32px;color:#ffffff;">
                    <div style="font-size:13px;letter-spacing:1px;text-transform:uppercase;opacity:0.9;">HR Training System</div>
                    <h1 style="margin:10px 0 0;font-size:26px;line-height:1.3;">New Exam Assignment</h1>
                  </td>
                </tr>
                <tr>
                  <td style="padding:32px;">
                    <p style="margin:0 0 16px;font-size:16px;">Dear {escape(safe_name)},</p>
                    <p style="margin:0 0 20px;font-size:15px;line-height:1.7;">
                      You have been assigned a new exam in the <strong>HR Training System</strong>.
                      Please review the schedule below and use the provided links to access the platform.
                    </p>
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;margin:0 0 22px;">
                      <tr>
                        <td style="padding:14px 16px;border:1px solid #d8e3f0;background:#f9fbfe;width:34%;font-weight:700;">Exam Title</td>
                        <td style="padding:14px 16px;border:1px solid #d8e3f0;">{escape(safe_title)}</td>
                      </tr>
                      <tr>
                        <td style="padding:14px 16px;border:1px solid #d8e3f0;background:#f9fbfe;font-weight:700;">Start Date</td>
                        <td style="padding:14px 16px;border:1px solid #d8e3f0;">{escape(start_text)}</td>
                      </tr>
                      <tr>
                        <td style="padding:14px 16px;border:1px solid #d8e3f0;background:#f9fbfe;font-weight:700;">End Date</td>
                        <td style="padding:14px 16px;border:1px solid #d8e3f0;">{escape(end_text)}</td>
                      </tr>
                      <tr>
                        <td style="padding:14px 16px;border:1px solid #d8e3f0;background:#f9fbfe;font-weight:700;">Status</td>
                        <td style="padding:14px 16px;border:1px solid #d8e3f0;">{escape(exam_status)}</td>
                      </tr>
                      <tr>
                        <td style="padding:14px 16px;border:1px solid #d8e3f0;background:#f9fbfe;font-weight:700;">Duration</td>
                        <td style="padding:14px 16px;border:1px solid #d8e3f0;">{escape(str(duration_minutes))} minutes</td>
                      </tr>
                      <tr>
                        <td style="padding:14px 16px;border:1px solid #d8e3f0;background:#f9fbfe;font-weight:700;">Allowed Attempts</td>
                        <td style="padding:14px 16px;border:1px solid #d8e3f0;">{escape(str(attempts_allowed))}</td>
                      </tr>
                      <tr>
                        <td style="padding:14px 16px;border:1px solid #d8e3f0;background:#f9fbfe;font-weight:700;">Passing Score</td>
                        <td style="padding:14px 16px;border:1px solid #d8e3f0;">{escape(str(passing_percent))}%</td>
                      </tr>
                    </table>
                    <div style="margin:0 0 22px;padding:16px 18px;background:#f7fbff;border:1px solid #dbe8f5;border-radius:12px;">
                      <div style="font-weight:700;margin:0 0 8px;">Exam Description</div>
                      <div style="font-size:14px;line-height:1.7;white-space:pre-line;">{escape(description_block)}</div>
                    </div>
                    <div style="margin:0 0 18px;">
                      <a href="{escape(links['login_url'])}" style="display:inline-block;background:#0057b8;color:#ffffff;text-decoration:none;padding:12px 22px;border-radius:999px;font-weight:700;">Open Login Page</a>
                    </div>
                    <p style="margin:0 0 10px;font-size:14px;line-height:1.7;">
                      If you are not signed in, you will normally be redirected to the login page first.
                      After login, the assigned exam will appear under <strong>My Exams</strong>.
                    </p>
                    <p style="margin:0 0 24px;font-size:14px;line-height:1.7;">
                      Login URL: <a href="{escape(links['login_url'])}" style="color:#0057b8;">{escape(links['login_url'])}</a>
                    </p>
                    <p style="margin:0;font-size:14px;line-height:1.7;">
                      Regards,<br />
                      <strong>HR Training Team</strong><br />
                      Fawry
                    </p>
                  </td>
                </tr>
                <tr>
                  <td style="padding:18px 32px;background:#f5f8fc;color:#5f7388;font-size:12px;line-height:1.6;">
                    This is an automated notification from the HR Training System. Please do not reply to this email.
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """.strip()
    return subject, plain_text, html_text


def _write_exam_notification_log(payload: dict) -> None:
    EXAM_NOTIFICATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with EXAM_NOTIFICATION_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _send_exam_assignment_notifications(exam_snapshot: dict, recipients: list[dict], links: dict[str, str]) -> None:
    smtp_disabled = str(os.getenv("TRAINING_SMTP_DISABLED", os.getenv("SMTP_DISABLED", ""))).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
    }
    smtp_server = (
        os.getenv("TRAINING_SMTP_SERVER")
        or os.getenv("SMTP_SERVER")
        or "10.100.36.40"
    ).strip()
    smtp_port = int((os.getenv("TRAINING_SMTP_PORT") or os.getenv("SMTP_PORT") or "25").strip())
    smtp_from = (
        os.getenv("TRAINING_SMTP_FROM")
        or os.getenv("SMTP_FROM_EMAIL")
        or "no-reply@fawry.com"
    ).strip()
    smtp_timeout = float((os.getenv("TRAINING_SMTP_TIMEOUT") or "10").strip())

    sent_count = 0
    logged_count = 0
    skipped_count = 0
    seen_emails: set[str] = set()

    for recipient in recipients:
        to_email = _normalize_email(recipient.get("email"))
        if not to_email or to_email in seen_emails:
            skipped_count += 1
            continue
        seen_emails.add(to_email)

        subject, plain_text, html_text = _build_exam_notification_message(
            recipient_name=str(recipient.get("name") or "").strip(),
            exam_snapshot=exam_snapshot,
            links=links,
        )

        if smtp_disabled:
            _write_exam_notification_log(
                {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "delivery": "logged_only",
                    "recipient_email": to_email,
                    "subject": subject,
                    "plain_text": plain_text,
                    "links": links,
                    "exam_id": exam_snapshot.get("exam_id"),
                }
            )
            logged_count += 1
            continue

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = smtp_from
        message["To"] = to_email
        message.set_content(plain_text)
        message.add_alternative(html_text, subtype="html")

        try:
            with smtplib.SMTP(smtp_server, smtp_port, timeout=smtp_timeout) as server:
                server.send_message(message)
            sent_count += 1
        except Exception as exc:
            logger.exception("Failed to send exam notification to %s", to_email)
            _write_exam_notification_log(
                {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "delivery": "fallback_after_error",
                    "recipient_email": to_email,
                    "subject": subject,
                    "plain_text": plain_text,
                    "links": links,
                    "exam_id": exam_snapshot.get("exam_id"),
                    "error": str(exc),
                }
            )
            logged_count += 1

    logger.info(
        "Exam notification task finished for exam_id=%s sent=%s logged=%s skipped=%s",
        exam_snapshot.get("exam_id"),
        sent_count,
        logged_count,
        skipped_count,
    )


def _extract_score_percentage(total_score, max_score) -> float | None:
    if total_score is None or max_score in (None, 0):
        return None
    try:
        return round((float(total_score) / float(max_score)) * 100, 2)
    except Exception:
        return None


def _build_dashboard_export_excel(rows: list[dict], sheet_name: str) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(rows or []).to_excel(writer, sheet_name=sheet_name[:31], index=False)
    output.seek(0)
    return output.getvalue()


def _get_dashboard_scoring_period_bounds(
    period: str | None,
    *,
    now: datetime | None = None,
) -> tuple[datetime | None, datetime, str]:
    normalized_period = str(period or "all").strip().lower()
    if normalized_period not in {"all", "week", "month", "year"}:
        normalized_period = "all"

    reference_utc = _normalize_exam_datetime(now) or datetime.now(UTC_TZ)
    reference_cairo = reference_utc.astimezone(EGYPT_TZ)

    if normalized_period == "week":
        start_cairo = (reference_cairo - timedelta(days=reference_cairo.weekday())).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        return start_cairo.astimezone(UTC_TZ), reference_utc, normalized_period

    if normalized_period == "month":
        start_cairo = reference_cairo.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        return start_cairo.astimezone(UTC_TZ), reference_utc, normalized_period

    if normalized_period == "year":
        start_cairo = reference_cairo.replace(
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        return start_cairo.astimezone(UTC_TZ), reference_utc, normalized_period

    return None, reference_utc, normalized_period


def _build_dashboard_analytics(
    users: list,
    active_exams: list,
    attempts: list,
    hierarchy: list[dict],
    audit_rows: list[dict],
    tr_tz_now: datetime,
    scoring_period: str | None = "all",
    employee_scoring_exams_joined: int | None = None,
) -> dict:
    now = tr_tz_now
    window_end = now + timedelta(days=7)
    scoring_period_start, scoring_period_end, normalized_scoring_period = _get_dashboard_scoring_period_bounds(
        scoring_period,
        now=now,
    )

    role_counts: dict[str, int] = {}
    users_by_employee_id: dict[str, object] = {}
    users_by_email: dict[str, object] = {}
    eligible_users: list[object] = []
    internal_users: list[object] = []
    resigned_users: list[object] = []
    for user in users:
        role_name = (getattr(user, "department", None) or "unknown").lower()
        role_counts[role_name] = role_counts.get(role_name, 0) + 1
        if getattr(user, "employee_id", None):
            users_by_employee_id[user.employee_id] = user
        normalized_email = _normalize_email(getattr(user, "email", None))
        if normalized_email:
            users_by_email[normalized_email] = user
        if is_employee_resigned(user):
            resigned_users.append(user)
            continue
        if _is_employee_dashboard_role(role_name):
            eligible_users.append(user)
        elif _is_internal_dashboard_role(role_name):
            internal_users.append(user)

    branches_flat: list[dict] = []
    for region in hierarchy:
        for area in region.get("areas", []):
            for branch in area.get("branches", []):
                employees_in_branch = branch.get("employees", []) or []
                branches_flat.append(
                    {
                        "branch_code": branch.get("branch_code"),
                        "branch_name": branch.get("branch_name"),
                        "region": region.get("region"),
                        "area": area.get("area"),
                        "user_count": len(employees_in_branch),
                    }
                )

    total_branches = len(branches_flat)
    branches_with_users = sum(1 for branch in branches_flat if (branch.get("user_count") or 0) > 0)
    branch_coverage_pct = round((branches_with_users / total_branches) * 100, 2) if total_branches else 0.0
    top_branches = sorted(
        branches_flat,
        key=lambda branch: branch.get("user_count", 0),
        reverse=True,
    )[:5]

    status_distribution = {"Open": 0, "Closed": 0, "On Hold": 0}
    exams_closing_7d = 0
    overdue_open_exams = 0
    created_last_30d = 0
    configured_open_exams = 0
    total_assigned_users = 0
    assigned_pairs: set[tuple[str, str]] = set()
    assigned_by_employee: dict[str, int] = {}
    valid_exam_ids: set[str] = set()
    for exam in active_exams:
        if getattr(exam, "exam_id", None):
            valid_exam_ids.add(exam.exam_id)
        status_name = _resolve_exam_status(exam)
        status_distribution[status_name] = status_distribution.get(status_name, 0) + 1

        end_dt = _normalize_exam_datetime(exam.end_date)
        if (exam.exam_status or "").lower() == "open":
            configured_open_exams += 1
        if status_name == "Open" and end_dt and now <= end_dt <= window_end:
            exams_closing_7d += 1
        if (exam.exam_status or "").lower() == "open" and _is_exam_window_closed(exam, now):
            overdue_open_exams += 1

        created_dt = _normalize_exam_datetime(getattr(exam, "created_at", None))
        if created_dt and created_dt >= (now - timedelta(days=30)):
            created_last_30d += 1

        exam_employees = list(getattr(exam, "employees", []) or [])
        total_assigned_users += len(exam_employees)
        for employee in exam_employees:
            if employee and employee.employee_id:
                assigned_pairs.add((exam.exam_id, employee.employee_id))
                assigned_by_employee[employee.employee_id] = assigned_by_employee.get(employee.employee_id, 0) + 1

    eligible_employee_ids = {
        user.employee_id for user in eligible_users if getattr(user, "employee_id", None)
    }
    assigned_eligible_employee_ids = {
        employee_id
        for employee_id, assignment_count in assigned_by_employee.items()
        if assignment_count > 0 and employee_id in eligible_employee_ids
    }
    attempts_in_scope = [
        attempt
        for attempt in attempts
        if getattr(attempt, "exam_id", None) in valid_exam_ids
        and getattr(attempt, "employee_id", None) in users_by_employee_id
    ]

    attempt_count = len(attempts_in_scope)
    passed_attempts = sum(1 for attempt in attempts_in_scope if bool(getattr(attempt, "passed", False)))
    attempted_pairs = {
        (attempt.exam_id, attempt.employee_id)
        for attempt in attempts_in_scope
        if attempt.exam_id and attempt.employee_id
    }
    assignment_coverage_pct = (
        round((len(attempted_pairs) / len(assigned_pairs)) * 100, 2) if assigned_pairs else 0.0
    )
    pass_rate_pct = round((passed_attempts / attempt_count) * 100, 2) if attempt_count else 0.0

    score_percentages: list[float] = []
    employee_scores: dict[str, list[float]] = {}
    employee_attempt_counts: dict[str, int] = {}
    branch_scores: dict[str, dict] = {}
    for attempt in attempts_in_scope:
        employee_id = getattr(attempt, "employee_id", None)
        if employee_id:
            employee_attempt_counts[employee_id] = employee_attempt_counts.get(employee_id, 0) + 1

        score_pct = _extract_score_percentage(
            getattr(attempt, "total_score", None),
            getattr(attempt, "max_score", None),
        )
        if score_pct is None:
            continue

        score_percentages.append(score_pct)
        if employee_id:
            employee_scores.setdefault(employee_id, []).append(score_pct)
            owner = users_by_employee_id.get(employee_id)
            branch_code = getattr(owner, "branch_code", None) if owner is not None else None
            branch_name = getattr(getattr(owner, "branch", None), "branch_name", None) if owner is not None else None
            if branch_code:
                branch_bucket = branch_scores.setdefault(
                    branch_code,
                    {
                        "branch_code": branch_code,
                        "branch_name": branch_name or branch_code,
                        "region": getattr(getattr(owner, "branch", None), "branch_region", None) if owner else None,
                        "area": getattr(getattr(owner, "branch", None), "branch_area", None) if owner else None,
                        "scores": [],
                        "employees": set(),
                    },
                )
                branch_bucket["scores"].append(score_pct)
                branch_bucket["employees"].add(employee_id)

    average_score_pct = round(sum(score_percentages) / len(score_percentages), 2) if score_percentages else 0.0

    scoring_attempts_in_scope = []
    for attempt in attempts_in_scope:
        submitted_at = _normalize_exam_datetime(getattr(attempt, "submitted_at", None))
        if submitted_at is None or submitted_at > scoring_period_end:
            continue
        if scoring_period_start is not None and submitted_at < scoring_period_start:
            continue
        scoring_attempts_in_scope.append(attempt)

    latest_distinct_attempts: dict[tuple[str, str], dict] = {}
    for attempt in scoring_attempts_in_scope:
        employee_id = getattr(attempt, "employee_id", None)
        exam_id = getattr(attempt, "exam_id", None)
        submitted_at = _normalize_exam_datetime(getattr(attempt, "submitted_at", None))
        if not employee_id or not exam_id or submitted_at is None:
            continue

        score_pct = _extract_score_percentage(
            getattr(attempt, "total_score", None),
            getattr(attempt, "max_score", None),
        )
        if score_pct is None:
            continue

        key = (employee_id, exam_id)
        current = latest_distinct_attempts.get(key)
        if current is not None and submitted_at <= current["submitted_at"]:
            continue

        latest_distinct_attempts[key] = {
            "employee_id": employee_id,
            "exam_id": exam_id,
            "submitted_at": submitted_at,
            "score_pct": score_pct,
        }

    employee_period_scores: dict[str, list[float]] = {}
    for record in latest_distinct_attempts.values():
        employee_id = record["employee_id"]
        score_pct = record["score_pct"]
        employee_period_scores.setdefault(employee_id, []).append(score_pct)

    users_with_attempts_count = len(
        {employee_id for employee_id in employee_attempt_counts if employee_id in eligible_employee_ids}
    )
    no_attempt_users: list[dict] = []
    for user in eligible_users:
        assigned_exam_count = assigned_by_employee.get(user.employee_id, 0)
        if assigned_exam_count <= 0:
            continue
        if employee_attempt_counts.get(user.employee_id, 0) > 0:
            continue
        no_attempt_users.append(_build_dashboard_user_row(user, assigned_exams=assigned_exam_count))
    no_attempt_users.sort(
        key=lambda row: (
            -int(row.get("assigned_exams") or 0),
            (row.get("name") or "").lower(),
            (row.get("email") or "").lower(),
        )
    )

    login_emails: set[str] = set()
    active_system_emails: set[str] = set()
    for row in audit_rows:
        if _is_synthetic_dashboard_audit_row(row):
            continue
        status_code = int(row.get("status_code") or 0)
        if status_code >= 400:
            continue
        actor_email = _normalize_email(row.get("actor_email"))
        if not actor_email or actor_email == "anonymous":
            continue
        path = str(row.get("path") or "")
        if path == "/api/v1/users/login":
            login_emails.add(actor_email)
        if path.startswith("/api/") and path not in {"/api/v1/users/login", "/api/v1/users/login/request-otp"}:
            active_system_emails.add(actor_email)

    eligible_emails = {_normalize_email(user.email) for user in eligible_users if _normalize_email(user.email)}
    proven_login_emails = login_emails.union(active_system_emails)
    no_login_users: list[dict] = []
    no_activity_users: list[dict] = []
    for email in sorted(eligible_emails):
        user = users_by_email.get(email)
        if user is None:
            continue
        base_row = _build_dashboard_user_row(user, assigned_exams=assigned_by_employee.get(user.employee_id, 0))
        has_login_history = _normalize_exam_datetime(getattr(user, "last_login_at", None)) is not None
        has_activity_history = _normalize_exam_datetime(getattr(user, "last_activity_at", None)) is not None
        if not has_login_history and email not in proven_login_emails:
            no_login_users.append(base_row)
        if not has_activity_history and email not in active_system_emails:
            no_activity_users.append(base_row)

    no_login_users.sort(key=lambda row: ((row.get("name") or "").lower(), (row.get("email") or "").lower()))
    no_activity_users.sort(key=lambda row: ((row.get("name") or "").lower(), (row.get("email") or "").lower()))

    employee_score_rows: list[dict] = []
    for employee_id, scores in employee_period_scores.items():
        if not scores:
            continue
        user = users_by_employee_id.get(employee_id)
        if user is None or is_employee_resigned(user):
            continue
        average_percentage = round(sum(scores) / len(scores), 2)
        employee_score_rows.append(
            {
                "employee_id": employee_id,
                "employee_name": getattr(user, "name", ""),
                "email": getattr(user, "email", ""),
                "hr_id": getattr(user, "hr_id", ""),
                "name": getattr(user, "name", ""),
                "role": getattr(user, "department", ""),
                "branch_code": getattr(user, "branch_code", ""),
                "branch_name": getattr(getattr(user, "branch", None), "branch_name", None),
                "region": getattr(getattr(user, "branch", None), "branch_region", None),
                "area": getattr(getattr(user, "branch", None), "branch_area", None),
                "exams_joined": len(scores),
                "average_percentage": average_percentage,
                "average_score_pct": average_percentage,
            }
        )

    available_employee_exam_counts = sorted(
        {
            int(row.get("exams_joined", 0) or 0)
            for row in employee_score_rows
            if int(row.get("exams_joined", 0) or 0) > 0
        }
    )
    employee_leaderboard_rows = employee_score_rows
    if employee_scoring_exams_joined is not None:
        employee_leaderboard_rows = [
            row
            for row in employee_score_rows
            if int(row.get("exams_joined", 0) or 0) == int(employee_scoring_exams_joined)
        ]

    top_employees = sorted(
        employee_leaderboard_rows,
        key=lambda row: (
            -float(row.get("average_percentage", 0) or 0),
            (row.get("employee_name") or row.get("name") or "").lower(),
            str(row.get("hr_id") or ""),
        ),
    )
    low_employees = sorted(
        employee_leaderboard_rows,
        key=lambda row: (
            float(row.get("average_percentage", 0) or 0),
            (row.get("employee_name") or row.get("name") or "").lower(),
            str(row.get("hr_id") or ""),
        ),
    )

    branch_period_rankings: dict[str, dict] = {}
    for row in employee_score_rows:
        branch_code = row.get("branch_code")
        if not branch_code:
            continue

        branch_bucket = branch_period_rankings.setdefault(
            branch_code,
            {
                "branch_code": branch_code,
                "branch_name": row.get("branch_name") or branch_code,
                "region": row.get("region"),
                "area": row.get("area"),
                "employee_average_percentages": [],
                "employees_ranked": 0,
                "total_exams_joined": 0,
            },
        )
        branch_bucket["employee_average_percentages"].append(float(row.get("average_percentage", 0) or 0))
        branch_bucket["employees_ranked"] += 1
        branch_bucket["total_exams_joined"] += int(row.get("exams_joined", 0) or 0)

    branch_score_rows: list[dict] = []
    for branch_row in branch_period_rankings.values():
        employee_average_percentages = branch_row.get("employee_average_percentages") or []
        if not employee_average_percentages:
            continue
        average_percentage = round(
            sum(employee_average_percentages) / len(employee_average_percentages),
            2,
        )
        branch_score_rows.append(
            {
                "branch_code": branch_row.get("branch_code"),
                "branch_name": branch_row.get("branch_name"),
                "region": branch_row.get("region"),
                "area": branch_row.get("area"),
                "average_percentage": average_percentage,
                "average_score_pct": average_percentage,
                "distinct_exam_submissions": branch_row.get("total_exams_joined", 0),
                "employees_attempted": branch_row.get("employees_ranked", 0),
            }
        )
    top_branches_by_score = sorted(
        branch_score_rows,
        key=lambda row: (
            row.get("average_percentage", 0),
            row.get("employees_attempted", 0),
            row.get("distinct_exam_submissions", 0),
            (row.get("branch_name") or "").lower(),
        ),
        reverse=True,
    )
    low_branches_by_score = sorted(
        branch_score_rows,
        key=lambda row: (
            row.get("average_percentage", 0),
            -int(row.get("employees_attempted", 0) or 0),
            -int(row.get("distinct_exam_submissions", 0) or 0),
            (row.get("branch_name") or "").lower(),
        ),
    )

    eligible_user_count = len(eligible_users)
    users_logged_in_count = min(len(eligible_emails.intersection(proven_login_emails)), eligible_user_count)
    users_active_in_system_count = min(len(eligible_emails.intersection(active_system_emails)), eligible_user_count)
    users_with_attempts_count = min(users_with_attempts_count, eligible_user_count)

    if len(no_attempt_users) > len(assigned_eligible_employee_ids):
        logger.warning(
            "Dashboard validation adjusted no-attempt population from %s to %s",
            len(no_attempt_users),
            len(assigned_eligible_employee_ids),
        )
    if len(no_login_users) > eligible_user_count or len(no_activity_users) > eligible_user_count:
        logger.warning(
            "Dashboard validation detected inconsistent engagement counts eligible=%s no_login=%s no_activity=%s",
            eligible_user_count,
            len(no_login_users),
            len(no_activity_users),
        )

    return {
        "users": {
            "total": len(eligible_users) + len(internal_users),
            "employee_total": eligible_user_count,
            "internal_total": len(internal_users),
            "resigned_total": len(resigned_users),
            "roles_count": role_counts,
        },
        "branches": {
            "total": total_branches,
            "with_users": branches_with_users,
            "without_users": max(total_branches - branches_with_users, 0),
            "coverage_pct": branch_coverage_pct,
            "top_by_users": top_branches,
        },
        "exams": {
            "total": len(active_exams),
            "active_open_total": status_distribution.get("Open", 0),
            "currently_open_total": status_distribution.get("Open", 0),
            "configured_open_total": configured_open_exams,
            "status_distribution": status_distribution,
            "closing_in_7_days": exams_closing_7d,
            "overdue_open_configured": overdue_open_exams,
            "created_last_30_days": created_last_30d,
            "total_assigned_users": total_assigned_users,
        },
        "attempts": {
            "total_attempts": attempt_count,
            "passed_attempts": passed_attempts,
            "pass_rate_pct": pass_rate_pct,
            "average_score_pct": average_score_pct,
            "assigned_pairs": len(assigned_pairs),
            "attempted_pairs": len(attempted_pairs),
            "assignment_coverage_pct": assignment_coverage_pct,
        },
        "engagement": {
            "eligible_users": eligible_user_count,
            "users_with_attempts": users_with_attempts_count,
            "users_without_attempts": len(no_attempt_users),
            "users_logged_in": users_logged_in_count,
            "users_without_login": len(no_login_users),
            "users_active_in_system": users_active_in_system_count,
            "users_without_activity": len(no_activity_users),
            "no_attempt_preview": no_attempt_users[:10],
            "no_login_preview": no_login_users[:10],
        },
        "leaderboards": {
            "employees_high": top_employees[:10],
            "employees_low": low_employees[:10],
            "branches_high": top_branches_by_score[:10],
            "branches_low": low_branches_by_score[:10],
        },
        "top_scoring_employees": top_employees[:10],
        "low_scoring_employees": low_employees[:10],
        "top_scoring_branches": top_branches_by_score[:10],
        "low_scoring_branches": low_branches_by_score[:10],
        "available_employee_exam_counts": available_employee_exam_counts,
        "scoring_period": {
            "period": normalized_scoring_period,
            "start_at": _serialize_exam_datetime(scoring_period_start),
            "end_at": _serialize_exam_datetime(scoring_period_end),
        },
        "exports": {
            "no_attempt_users": no_attempt_users,
            "no_login_users": no_login_users,
            "no_activity_users": no_activity_users,
        },
    }


def _build_dashboard_scoring_from_employee_rows(
    leaderboard_rows: list[dict],
    available_employee_exam_counts: list[int] | None = None,
) -> dict:
    normalized_rows: list[dict] = []
    for row in leaderboard_rows:
        average_percentage = row.get("average_percentage")
        if average_percentage is None:
            continue

        normalized_average = round(float(average_percentage), 2)
        employee_name = row.get("employee_name") or row.get("name") or ""
        normalized_rows.append(
            {
                "employee_id": row.get("employee_id"),
                "employee_name": employee_name,
                "email": row.get("email") or "",
                "hr_id": row.get("hr_id") or "",
                "name": employee_name,
                "role": row.get("role") or row.get("department") or "",
                "branch_code": row.get("branch_code") or "",
                "branch_name": row.get("branch_name"),
                "region": row.get("region"),
                "area": row.get("area"),
                "exams_joined": int(row.get("exams_joined", 0) or 0),
                "average_percentage": normalized_average,
                "average_score_pct": normalized_average,
            }
        )

    top_employees = sorted(
        normalized_rows,
        key=lambda row: (
            -float(row.get("average_percentage", 0) or 0),
            (row.get("employee_name") or row.get("name") or "").lower(),
            str(row.get("hr_id") or ""),
        ),
    )
    low_employees = sorted(
        normalized_rows,
        key=lambda row: (
            float(row.get("average_percentage", 0) or 0),
            (row.get("employee_name") or row.get("name") or "").lower(),
            str(row.get("hr_id") or ""),
        ),
    )

    branch_period_rankings: dict[str, dict] = {}
    for row in normalized_rows:
        branch_code = row.get("branch_code")
        if not branch_code:
            continue

        branch_bucket = branch_period_rankings.setdefault(
            branch_code,
            {
                "branch_code": branch_code,
                "branch_name": row.get("branch_name") or branch_code,
                "region": row.get("region"),
                "area": row.get("area"),
                "employee_average_percentages": [],
                "employees_ranked": 0,
                "total_exams_joined": 0,
            },
        )
        branch_bucket["employee_average_percentages"].append(float(row.get("average_percentage", 0) or 0))
        branch_bucket["employees_ranked"] += 1
        branch_bucket["total_exams_joined"] += int(row.get("exams_joined", 0) or 0)

    branch_score_rows: list[dict] = []
    for branch_row in branch_period_rankings.values():
        employee_average_percentages = branch_row.get("employee_average_percentages") or []
        if not employee_average_percentages:
            continue

        average_percentage = round(
            sum(employee_average_percentages) / len(employee_average_percentages),
            2,
        )
        branch_score_rows.append(
            {
                "branch_code": branch_row.get("branch_code"),
                "branch_name": branch_row.get("branch_name"),
                "region": branch_row.get("region"),
                "area": branch_row.get("area"),
                "average_percentage": average_percentage,
                "average_score_pct": average_percentage,
                "distinct_exam_submissions": branch_row.get("total_exams_joined", 0),
                "employees_attempted": branch_row.get("employees_ranked", 0),
            }
        )

    top_branches = sorted(
        branch_score_rows,
        key=lambda row: (
            row.get("average_percentage", 0),
            row.get("employees_attempted", 0),
            row.get("distinct_exam_submissions", 0),
            (row.get("branch_name") or "").lower(),
        ),
        reverse=True,
    )
    low_branches = sorted(
        branch_score_rows,
        key=lambda row: (
            row.get("average_percentage", 0),
            -int(row.get("employees_attempted", 0) or 0),
            -int(row.get("distinct_exam_submissions", 0) or 0),
            (row.get("branch_name") or "").lower(),
        ),
    )

    normalized_available_counts = (
        sorted(
            {
                int(value)
                for value in available_employee_exam_counts
                if value is not None and int(value) > 0
            }
        )
        if available_employee_exam_counts is not None
        else sorted(
            {
                int(row.get("exams_joined", 0) or 0)
                for row in normalized_rows
                if int(row.get("exams_joined", 0) or 0) > 0
            }
        )
    )

    return {
        "leaderboards": {
            "employees_high": top_employees[:10],
            "employees_low": low_employees[:10],
            "branches_high": top_branches[:10],
            "branches_low": low_branches[:10],
        },
        "top_scoring_employees": top_employees[:10],
        "low_scoring_employees": low_employees[:10],
        "top_scoring_branches": top_branches[:10],
        "low_scoring_branches": low_branches[:10],
        "available_employee_exam_counts": normalized_available_counts,
    }

def _build_group_breakdown(
    participants: list[dict],
    key_builder: Callable[[dict], tuple[str, dict]],
) -> list[dict]:
    breakdown: dict[str, dict] = {}
    for participant in participants:
        key, labels = key_builder(participant)
        key = key or "Unspecified"
        record = breakdown.setdefault(
            key,
            {
                **labels,
                "employees_assigned": 0,
                "employees_attempted": 0,
                "employees_not_attempted": 0,
                "employees_in_progress": 0,
                "employees_submitted": 0,
                "employees_passed": 0,
                "employees_failed": 0,
                "attempts_sum": 0,
                "score_sum": 0.0,
                "score_count": 0,
                "duration_sum": 0.0,
                "duration_count": 0,
                "last_submission_dt": None,
            },
        )

        record["employees_assigned"] += 1
        attempts_count = participant.get("attempts_count") or 0
        record["attempts_sum"] += attempts_count
        if attempts_count:
            record["employees_attempted"] += 1
        status_value = participant.get("status")
        if status_value == "not_attempted":
            record["employees_not_attempted"] += 1
        elif status_value == "in_progress":
            record["employees_in_progress"] += 1
        elif status_value == "submitted":
            record["employees_submitted"] += 1
        elif status_value == "passed":
            record["employees_passed"] += 1
        elif status_value == "failed":
            record["employees_failed"] += 1

        score_percentage = participant.get("last_score_percentage")
        if score_percentage is not None:
            record["score_sum"] += float(score_percentage)
            record["score_count"] += 1

        duration_seconds = participant.get("last_duration_seconds")
        if duration_seconds is not None:
            record["duration_sum"] += float(duration_seconds)
            record["duration_count"] += 1

        last_submitted_at = _parse_iso_datetime(participant.get("last_submitted_at"))
        if last_submitted_at:
            existing = record["last_submission_dt"]
            if existing is None or last_submitted_at > existing:
                record["last_submission_dt"] = last_submitted_at

    breakdown_rows: list[dict] = []
    for record in breakdown.values():
        employees_assigned = record["employees_assigned"]
        employees_attempted = record["employees_attempted"]
        employees_not_attempted = record["employees_not_attempted"]
        employees_in_progress = record["employees_in_progress"]
        employees_submitted = record["employees_submitted"]
        employees_passed = record["employees_passed"]
        employees_failed = record["employees_failed"]
        attempts_sum = record["attempts_sum"]
        score_count = record["score_count"]
        duration_count = record["duration_count"]

        breakdown_rows.append(
            {
                **{k: v for k, v in record.items() if k not in {
                    "employees_assigned",
                    "employees_attempted",
                    "employees_not_attempted",
                    "employees_in_progress",
                    "employees_submitted",
                    "employees_passed",
                    "employees_failed",
                    "attempts_sum",
                    "score_sum",
                    "score_count",
                    "duration_sum",
                    "duration_count",
                    "last_submission_dt",
                }},
                "employees_assigned": employees_assigned,
                "employees_attempted": employees_attempted,
                "employees_not_attempted": employees_not_attempted,
                "employees_in_progress": employees_in_progress,
                "employees_submitted": employees_submitted,
                "attempt_rate_percentage": _safe_percentage(employees_attempted, employees_assigned),
                "employees_passed": employees_passed,
                "employees_failed": employees_failed,
                "pass_rate_percentage": _safe_percentage(employees_passed, employees_assigned),
                # "average_attempts_per_employee": round(
                #     attempts_sum / employees_assigned, 2
                # ) if employees_assigned else 0.0,
                "average_score_percentage": round(
                    record["score_sum"] / score_count, 2
                ) if score_count else 0.0,
                "average_duration_seconds": int(
                    record["duration_sum"] / duration_count
                ) if duration_count else None,
                "last_submission_at": record["last_submission_dt"].isoformat()
                if record["last_submission_dt"]
                else None,
            }
        )

    return breakdown_rows


def _build_historical_result_employees(results_details: list[dict]) -> list[dict]:
    """Summarize every completed result, independent of the current exam audience."""
    employees: dict[str, dict] = {}
    baseline_dt = datetime.min.replace(tzinfo=timezone.utc)

    for attempt in results_details:
        employee_id = attempt.get("employee_id")
        employee_hr_id = attempt.get("employee_hr_id")
        key = str(employee_id or employee_hr_id or attempt.get("attempt_id"))
        branch = attempt.get("branch") or {}
        record = employees.setdefault(
            key,
            {
                "employee_id": employee_id,
                "employee_hr_id": employee_hr_id,
                "employee_name": attempt.get("employee_name"),
                "employee_title": attempt.get("employee_title"),
                "department": attempt.get("department"),
                "email": attempt.get("email"),
                "branch_code": branch.get("branch_code"),
                "branch_name": branch.get("branch_name"),
                "branch_region": branch.get("region"),
                "branch_area": branch.get("area"),
                "branch_division": branch.get("division"),
                "branch_sub_department": branch.get("sub_department"),
                "attempts_count": 0,
                "score_sum": 0.0,
                "score_count": 0,
                "latest_activity_dt": baseline_dt,
                "last_score": None,
                "last_max_score": None,
                "last_score_percentage": None,
                "last_duration_seconds": None,
                "last_submitted_at": None,
                "last_activity_at": None,
                "status": "submitted",
            },
        )
        record["attempts_count"] += 1

        score_percentage = attempt.get("score_percentage")
        if score_percentage is not None:
            record["score_sum"] += float(score_percentage)
            record["score_count"] += 1

        activity_dt = (
            _parse_iso_datetime(attempt.get("submitted_at"))
            or _parse_iso_datetime(attempt.get("started_at"))
            or baseline_dt
        )
        if activity_dt >= record["latest_activity_dt"]:
            record["latest_activity_dt"] = activity_dt
            record["last_score"] = attempt.get("total_score")
            record["last_max_score"] = attempt.get("max_score")
            record["last_score_percentage"] = score_percentage
            record["last_duration_seconds"] = attempt.get("duration_seconds")
            record["last_submitted_at"] = attempt.get("submitted_at")
            record["last_activity_at"] = attempt.get("submitted_at") or attempt.get("started_at")
            passed = attempt.get("passed")
            record["status"] = "passed" if passed is True else "failed" if passed is False else "submitted"

    history_rows: list[dict] = []
    for record in employees.values():
        history_rows.append(
            {
                **{key: value for key, value in record.items() if key not in {
                    "score_sum", "score_count", "latest_activity_dt",
                }},
                "average_score_percentage": round(
                    record["score_sum"] / record["score_count"], 2
                ) if record["score_count"] else 0.0,
            }
        )

    return sorted(history_rows, key=lambda item: (item.get("employee_name") or "").lower())


def _prepare_exam_results_payload(
    exam: Exam,
    results_summary: dict,
    results_details: list[dict],
    participant_attempts: list[dict] | None = None,
) -> dict:
    results_details_sorted = sorted(
        results_details,
        key=lambda detail: detail.get("submitted_at") or "",
        reverse=True,
    )

    for detail in results_details_sorted:
        for key in ("started_at", "submitted_at", "first_submitted_at", "last_submitted_at", "graded_at"):
            if key in detail:
                detail[key] = _serialize_timestamp_value(detail.get(key))
        answers = detail.get("answers") or []
        for answer in answers:
            if "submitted_at" in answer:
                answer["submitted_at"] = _serialize_timestamp_value(answer.get("submitted_at"))

    assigned_employees = list(getattr(exam, "employees", []))
    questions = list(getattr(exam, "questions", []))
    audience_summary = _build_audience_summary(exam)

    assigned_count = len(assigned_employees)
    participant_attempt_rows = participant_attempts if participant_attempts is not None else results_details_sorted
    attempted_employee_ids = {
        detail.get("employee_id")
        for detail in participant_attempt_rows
        if detail.get("employee_id")
    }
    baseline_dt = datetime.min.replace(tzinfo=timezone.utc)

    durations = [
        detail["duration_seconds"]
        for detail in results_details_sorted
        if detail.get("duration_seconds") is not None
    ]
    average_duration_seconds = int(sum(durations) / len(durations)) if durations else None

    score_percentages = [
        detail["score_percentage"]
        for detail in results_details_sorted
        if detail.get("score_percentage") is not None
    ]
    average_score_percentage = round(sum(score_percentages) / len(score_percentages), 2) if score_percentages else 0.0

    latest_submission_at = None
    latest_submission_dt = None
    for detail in results_details_sorted:
        dt = _parse_iso_datetime(detail.get("submitted_at"))
        if dt and (latest_submission_dt is None or dt > latest_submission_dt):
            latest_submission_dt = dt
            latest_submission_at = detail.get("submitted_at")

    pass_rate_percentage = _safe_percentage(
        results_summary.get("total_passed", 0),
        results_summary.get("total_attempts", 0),
    )
    max_possible_score = float(sum(float(question.points or 0) for question in questions)) if questions else 0.0

    top_performer = None
    if results_details_sorted:
        top_attempt = max(results_details_sorted, key=lambda detail: detail.get("score_percentage") or 0)
        top_performer = {
            "attempt_id": top_attempt["attempt_id"],
            "employee_hr_id": top_attempt["employee_hr_id"],
            "employee_name": top_attempt["employee_name"],
            "score_percentage": top_attempt["score_percentage"],
            "total_score": top_attempt["total_score"],
            "submitted_at": top_attempt["submitted_at"],
        }

    attempts_by_employee: dict[str, list[dict]] = {}
    for detail in participant_attempt_rows:
        employee_id = detail.get("employee_id")
        if not employee_id:
            continue
        attempts_by_employee.setdefault(employee_id, []).append(detail)

    def _resolve_attempt_activity_dt(item: dict) -> datetime:
        return (
            _parse_iso_datetime(item.get("submitted_at"))
            or _parse_iso_datetime(item.get("started_at"))
            or baseline_dt
        )

    def _resolve_latest_attempt(entries: list[dict]) -> dict | None:
        if not entries:
            return None
        return max(entries, key=_resolve_attempt_activity_dt)

    def _resolve_participant_status(latest_attempt: dict | None) -> str:
        if not latest_attempt:
            return "not_attempted"
        if latest_attempt.get("submitted_at") is None:
            return "in_progress"
        passed_value = latest_attempt.get("passed")
        if passed_value is True:
            return "passed"
        if passed_value is False:
            return "failed"
        return "submitted"

    participants_overview: list[dict] = []
    for employee in assigned_employees:
        attempts_for_employee = attempts_by_employee.get(employee.employee_id, [])
        latest_attempt = _resolve_latest_attempt(attempts_for_employee)
        status_label = _resolve_participant_status(latest_attempt)
        last_activity_at = None
        if latest_attempt:
            last_activity_at = latest_attempt.get("submitted_at") or latest_attempt.get("started_at")
        last_attempt_is_finalized = bool(latest_attempt and latest_attempt.get("submitted_at"))

        participants_overview.append(
            {
                "employee_id": employee.employee_id,
                "employee_hr_id": employee.hr_id,
                "employee_name": employee.name,
                "employee_title": employee.title,
                "department": employee.department,
                "email": employee.email,
                "branch_code": employee.branch.branch_code if employee.branch else None,
                "branch_name": employee.branch.branch_name if employee.branch else None,
                "branch_region": employee.branch.branch_region if employee.branch else None,
                "branch_area": employee.branch.branch_area if employee.branch else None,
                "branch_division": employee.branch.branch_division if employee.branch else None,
                "branch_sub_department": employee.branch.branch_sub_department if employee.branch else None,
                "attempts_count": len(attempts_for_employee),
                "last_attempt_id": latest_attempt["attempt_id"] if latest_attempt else None,
                "last_score": latest_attempt["total_score"] if last_attempt_is_finalized and latest_attempt else None,
                "last_max_score": latest_attempt["max_score"] if last_attempt_is_finalized and latest_attempt else None,
                "last_score_percentage": latest_attempt["score_percentage"] if last_attempt_is_finalized and latest_attempt else None,
                "last_duration_seconds": latest_attempt["duration_seconds"] if last_attempt_is_finalized and latest_attempt else None,
                "last_submitted_at": latest_attempt["submitted_at"] if last_attempt_is_finalized and latest_attempt else None,
                "last_activity_at": last_activity_at,
                "status": status_label,
            }
        )

    participants_overview.sort(key=lambda entry: (entry["employee_name"] or "").lower())
    historical_result_employees = _build_historical_result_employees(results_details_sorted)

    status_counts = {
        "not_attempted": 0,
        "in_progress": 0,
        "submitted": 0,
        "passed": 0,
        "failed": 0,
    }
    for participant in participants_overview:
        status_value = participant.get("status")
        if status_value in status_counts:
            status_counts[status_value] += 1

    employees_attempted = assigned_count - status_counts["not_attempted"]
    employees_pending = status_counts["not_attempted"]
    attempt_rate_percentage = _safe_percentage(
        employees_attempted,
        assigned_count,
    )

    summary_payload = {
        **results_summary,
        "max_possible_score": max_possible_score,
        "questions_count": len(questions),
        "average_score_percentage": average_score_percentage,
        "pass_rate_percentage": pass_rate_percentage,
        "employees_assigned": assigned_count,
        "employees_attempted": employees_attempted,
        "employees_pending": employees_pending,
        "employees_not_attempted": status_counts["not_attempted"],
        "employees_in_progress": status_counts["in_progress"],
        "employees_submitted": status_counts["submitted"],
        "employees_passed": status_counts["passed"],
        "employees_failed": status_counts["failed"],
        "attempt_rate_percentage": attempt_rate_percentage,
        "historical_results_count": len(results_details_sorted),
        "historical_employees_count": len(historical_result_employees),
        "average_duration_seconds": average_duration_seconds,
        "last_submission_at": _serialize_timestamp_value(latest_submission_at),
        "top_performer": top_performer,
    }

    exam_snapshot = {
        "exam_id": exam.exam_id,
        "title": exam.title,
        "description": exam.description,
        "exam_status": exam.exam_status,
        "start_date": _serialize_exam_datetime(exam.start_date),
        "end_date": _serialize_exam_datetime(exam.end_date),
        "duration_minutes": exam.duration_minutes,
        "number_of_attempts_allowed": exam.number_of_attempts_allowed,
        "audience_summary": audience_summary,
    }

    regions_breakdown = _build_group_breakdown(
        historical_result_employees,
        lambda participant: (
            participant.get("branch_region") or "Unassigned",
            {
                "region": participant.get("branch_region") or "Unassigned",
            },
        ),
    )

    areas_breakdown = _build_group_breakdown(
        historical_result_employees,
        lambda participant: (
            f"{participant.get('branch_region') or 'Unassigned'}::{participant.get('branch_area') or 'Unassigned'}",
            {
                "region": participant.get("branch_region") or "Unassigned",
                "area": participant.get("branch_area") or "Unassigned",
            },
        ),
    )

    branches_breakdown = _build_group_breakdown(
        historical_result_employees,
        lambda participant: (
            participant.get("branch_code")
            or participant.get("branch_name")
            or f"{participant.get('branch_region') or 'Unassigned'}::{participant.get('branch_area') or 'Unassigned'}",
            {
                "branch_code": participant.get("branch_code") or "-",
                "branch_name": participant.get("branch_name") or "Unassigned",
                "region": participant.get("branch_region") or "Unassigned",
                "area": participant.get("branch_area") or "Unassigned",
                "division": participant.get("branch_division"),
                "sub_department": participant.get("branch_sub_department"),
            },
        ),
    )

    employees_breakdown = [
        {
            "employee_id": participant["employee_id"],
            "employee_hr_id": participant["employee_hr_id"],
            "employee_name": participant["employee_name"],
            "employee_title": participant["employee_title"],
            "department": participant["department"],
            "email": participant["email"],
            "branch_code": participant["branch_code"],
            "branch_name": participant["branch_name"],
            "region": participant["branch_region"],
            "area": participant["branch_area"],
            "division": participant["branch_division"],
            "sub_department": participant["branch_sub_department"],
            "attempts_count": participant["attempts_count"],
            "average_score_percentage": participant["average_score_percentage"],
            "last_score_percentage": participant["last_score_percentage"],
            "last_score": participant["last_score"],
            "last_max_score": participant["last_max_score"],
            "last_duration_seconds": participant["last_duration_seconds"],
            "last_submitted_at": participant["last_submitted_at"],
            "last_activity_at": participant["last_activity_at"],
            "status": participant["status"],
        }
        for participant in historical_result_employees
    ]

    answer_rows: list[dict] = []
    question_stats: dict[str, dict] = {}
    for attempt in results_details_sorted:
        branch_info = attempt.get("branch") or {}
        for answer in attempt.get("answers") or []:
            answer_rows.append(
                {
                    "attempt_id": attempt["attempt_id"],
                    "attempt_number": attempt.get("attempt_number"),
                    "employee_id": attempt.get("employee_id"),
                    "employee_hr_id": attempt.get("employee_hr_id"),
                    "employee_name": attempt.get("employee_name"),
                    "employee_title": attempt.get("employee_title"),
                    "department": attempt.get("department"),
                    "branch_code": branch_info.get("branch_code"),
                    "branch_name": branch_info.get("branch_name"),
                    "region": branch_info.get("region"),
                    "area": branch_info.get("area"),
                    "division": branch_info.get("division"),
                    "sub_department": branch_info.get("sub_department"),
                    "question_id": answer.get("question_id"),
                    "question_text": answer.get("question_text"),
                    "question_group": answer.get("question_group"),
                    "question_type": answer.get("question_type"),
                    "question_points": answer.get("question_points"),
                    "selected_choice_id": answer.get("selected_choice_id"),
                    "selected_choice_text": answer.get("selected_choice_text"),
                    "correct_choice_id": answer.get("correct_choice_id"),
                    "correct_choice_text": answer.get("correct_choice_text"),
                    "is_correct": answer.get("is_correct"),
                    "points_awarded": answer.get("points_awarded"),
                    "submitted_at": attempt.get("submitted_at"),
                }
            )

            question_id = answer.get("question_id")
            if question_id:
                stats = question_stats.setdefault(
                    question_id,
                    {
                        "question_id": question_id,
                        "question_text": answer.get("question_text"),
                        "question_type": answer.get("question_type"),
                        "question_group": answer.get("question_group"),
                        "question_points": answer.get("question_points"),
                        "attempt_count": 0,
                        "correct_count": 0,
                        "points_awarded_sum": 0.0,
                    },
                )
                stats["attempt_count"] += 1
                if answer.get("is_correct"):
                    stats["correct_count"] += 1
                stats["points_awarded_sum"] += float(answer.get("points_awarded") or 0.0)

    questions_breakdown = []
    for stats in question_stats.values():
        attempt_count = stats["attempt_count"]
        correct_count = stats["correct_count"]
        questions_breakdown.append(
            {
                **{k: v for k, v in stats.items() if k not in {"attempt_count", "correct_count", "points_awarded_sum"}},
                "attempt_count": attempt_count,
                "correct_count": correct_count,
                "accuracy_percentage": _safe_percentage(correct_count, attempt_count),
                "average_points_awarded": round(
                    stats["points_awarded_sum"] / attempt_count, 2
                ) if attempt_count else 0.0,
            }
        )

    breakdowns = {
        "regions": regions_breakdown,
        "areas": areas_breakdown,
        "branches": branches_breakdown,
        "employees": employees_breakdown,
        "answers": answer_rows,
        "questions": questions_breakdown,
    }

    return {
        "exam_snapshot": exam_snapshot,
        "summary_payload": summary_payload,
        "participants_overview": participants_overview,
        "results_details": results_details_sorted,
        "breakdowns": breakdowns,
    }

def _build_excel_workbook(
    exam_snapshot: dict,
    summary_payload: dict,
    breakdowns: dict,
    results_details: list[dict],
) -> bytes:
    def _write_sheet(sheet_name: str, rows: list[dict] | None, drop_columns: list[str] | None = None):
        df = pd.DataFrame(rows or [])
        if drop_columns:
            existing = [column for column in drop_columns if column in df.columns]
            if existing:
                df = df.drop(columns=existing)
        df.to_excel(writer, sheet_name=sheet_name, index=False)

    def _format_answers_columns(answers: list[dict]) -> dict[str, str | None]:
        """Convert nested answers into text-only, user-friendly columns."""
        question_texts: list[str] = []
        selected_texts: list[str] = []
        correct_texts: list[str] = []
        results_texts: list[str] = []
        points_texts: list[str] = []

        for idx, answer in enumerate(answers or [], start=1):
            label = f"{idx}."
            question_texts.append(f"{label} {answer.get('question_text') or f'Question {idx}'}")
            selected_text = answer.get("selected_choice_text")
            if isinstance(selected_text, list):
                selected_text = ", ".join(str(value) for value in selected_text if value)
            correct_text = answer.get("correct_choice_text")
            if isinstance(correct_text, list):
                correct_text = ", ".join(str(value) for value in correct_text if value)
            selected_texts.append(f"{label} {selected_text or 'No answer'}")
            correct_texts.append(f"{label} {correct_text or '-'}")
            results_texts.append(f"{label} {'Correct' if answer.get('is_correct') else 'Incorrect'}")

            points_awarded = answer.get("points_awarded")
            question_points = answer.get("question_points")
            if points_awarded is not None or question_points is not None:
                points_texts.append(f"{label} {points_awarded or 0}/{question_points or 0}")
            else:
                points_texts.append(f"{label} -")

        def _join(values: list[str]) -> str | None:
            return "\n".join(values) if values else None

        return {
            "answers_questions": _join(question_texts),
            "answers_selected": _join(selected_texts),
            "answers_correct": _join(correct_texts),
            "answers_results": _join(results_texts),
            "answers_points": _join(points_texts),
        }
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        attempts_rows: list[dict] = []
        for attempt in results_details or []:
            branch_info = attempt.get("branch") or {}
            attempts_rows.append(
                {
                    "attempt_id": attempt.get("attempt_id"),
                    "attempt_number": attempt.get("attempt_number"),
                    "employee_id": attempt.get("employee_id"),
                    "employee_hr_id": attempt.get("employee_hr_id"),
                    "employee_name": attempt.get("employee_name"),
                    "employee_title": attempt.get("employee_title"),
                    "department": attempt.get("department"),
                    "email": attempt.get("email"),
                    "branch_code": branch_info.get("branch_code"),
                    "branch_name": branch_info.get("branch_name"),
                    "branch_region": branch_info.get("region"),
                    "branch_area": branch_info.get("area"),
                    "branch_division": branch_info.get("division"),
                    "branch_sub_department": branch_info.get("sub_department"),
                    "total_score": attempt.get("total_score"),
                    "max_score": attempt.get("max_score"),
                    "score_percentage": attempt.get("score_percentage"),
                    "passed": attempt.get("passed"),
                    "started_at": attempt.get("started_at"),
                    "submitted_at": attempt.get("submitted_at"),
                    "duration_seconds": attempt.get("duration_seconds"),
                    **_format_answers_columns(attempt.get("answers") or []),
                }
            )

        _write_sheet("All Results", attempts_rows, drop_columns=["attempt_id", "employee_id"])
        all_results_sheet = writer.sheets["All Results"]
        all_results_sheet.freeze_panes = "A2"
        all_results_sheet.auto_filter.ref = all_results_sheet.dimensions

        overview_rows = [
            {"Metric": "Exam Title", "Value": exam_snapshot.get("title")},
            {"Metric": "Description", "Value": exam_snapshot.get("description")},
            {"Metric": "Status", "Value": exam_snapshot.get("exam_status")},
            {"Metric": "Completed Result Attempts (All History)", "Value": summary_payload.get("historical_results_count")},
            {"Metric": "Employees With Historical Results", "Value": summary_payload.get("historical_employees_count")},
            {"Metric": "Duration (minutes)", "Value": exam_snapshot.get("duration_minutes")},
            {"Metric": "Start Date", "Value": exam_snapshot.get("start_date")},
            {"Metric": "End Date", "Value": exam_snapshot.get("end_date")},
            {"Metric": "Assigned Employees", "Value": summary_payload.get("employees_assigned")},
            {"Metric": "Attempted", "Value": summary_payload.get("employees_attempted")},
            {"Metric": "Not Attempted", "Value": summary_payload.get("employees_not_attempted")},
            {"Metric": "In Progress", "Value": summary_payload.get("employees_in_progress")},
            {"Metric": "Submitted", "Value": summary_payload.get("employees_submitted")},
            {"Metric": "Passed", "Value": summary_payload.get("employees_passed")},
            {"Metric": "Failed", "Value": summary_payload.get("employees_failed")},
            {"Metric": "Attempt Rate %", "Value": summary_payload.get("attempt_rate_percentage")},
            {"Metric": "Pass Rate %", "Value": summary_payload.get("pass_rate_percentage")},
            {"Metric": "Average Score %", "Value": summary_payload.get("average_score_percentage")},
            {"Metric": "Average Duration (sec)", "Value": summary_payload.get("average_duration_seconds")},
            {"Metric": "Max Possible Score", "Value": summary_payload.get("max_possible_score")},
            {"Metric": "Questions Count", "Value": summary_payload.get("questions_count")},
            {"Metric": "Last Submission", "Value": summary_payload.get("last_submission_at")},
        ]
        pd.DataFrame(overview_rows).to_excel(writer, sheet_name="Overview", index=False)

        _write_sheet("By Region", breakdowns.get("regions"))
        _write_sheet("By Area", breakdowns.get("areas"))
        _write_sheet("By Branch", breakdowns.get("branches"))
        _write_sheet("By Employee", breakdowns.get("employees"), drop_columns=["employee_id"])
        _write_sheet("Question Insights", breakdowns.get("questions"), drop_columns=["question_id"])
        _write_sheet(
            "Answer Details",
            breakdowns.get("answers"),
            drop_columns=["attempt_id", "employee_id", "question_id", "selected_choice_id", "correct_choice_id"],
        )

    output.seek(0)
    return output.getvalue()


def _build_employee_performance_excel(rows: list[dict]) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df = pd.DataFrame(rows or [])
        df.to_excel(writer, sheet_name="Employee Performance", index=False)
    output.seek(0)
    return output.getvalue()

#! Create Exam
@exam_router.post("/create")
async def create_exam(
    request: Request,
    payload: ExamCreatePayload, # Dates Validation happens automatically
    current_user: dict = Depends(get_current_user),
):
    

    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    material_model = await MaterialModel.create_instance(db_client=request.app.state.db_client)
    question_model = await QuestionModel.create_instance(db_client=request.app.state.db_client)
    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)

    # Validate materials
    for material_id in payload.material_ids:
        material =  await material_model.get_material_by_id(material_id)
        if material is None or material.is_deleted:
            return JSONResponse(
                content={
                    "signal": "One or more materials not found or have been deleted."
                },
                status_code=status.HTTP_404_NOT_FOUND,
            )

    # Validate status
    valid_statuses = ["Open", "Closed", "On Hold"]
    if payload.exam_status not in valid_statuses:
        return JSONResponse(
            content={"signal": f"Invalid status. Must be one of {valid_statuses}"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # validate Duration
    if payload.duration_minutes <= 5:
        return JSONResponse(
            content={"signal": "duration_minutes must be greater than 5 minutes."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if payload.passing_percent < 0 or payload.passing_percent > 100:
        return JSONResponse(
            content={"signal": "passing_percent must be between 0 and 100."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if payload.number_of_attempts_allowed is not None and payload.number_of_attempts_allowed < 1:
        return JSONResponse(
            content={"signal": "number_of_attempts_allowed must be at least 1."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    audience_mode, audience_filters_json, audience_manual_ids_json = _serialize_audience_payload(payload.audience)
    prepared_questions, question_validation_error = _prepare_questions_for_persistence(payload.questions)
    if question_validation_error is not None:
        return JSONResponse(
            content={"signal": question_validation_error},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Create Exam only after all validations succeed
    start_date_utc = _coerce_payload_datetime(payload.start_date)
    end_date_utc = _coerce_payload_datetime(payload.end_date)

    is_duration_valid, available_minutes = _validate_duration_against_window(
        payload.duration_minutes,
        start_date_utc,
        end_date_utc,
    )
    if not is_duration_valid:
        return JSONResponse(
            content={
                "signal": "duration_minutes exceeds exam window",
                "message": (
                    "Exam duration must fit between start and end times. "
                    f"Window allows {max(0, int(available_minutes))} minutes."
                ),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    created_exam = await exam_model.create_exam(
        Exam(
            title=payload.title,
            description=payload.description,
            exam_status=payload.exam_status,
            exam_level=payload.exam_level,
            duration_minutes=payload.duration_minutes,
            passing_percent=payload.passing_percent,
            number_of_attempts_allowed=payload.number_of_attempts_allowed,
            start_date=start_date_utc,
            end_date=end_date_utc,
            audience_mode=audience_mode,
            audience_filters=audience_filters_json,
            audience_manual_hr_ids=audience_manual_ids_json,
        )
    )

    target_hr_ids = await _resolve_audience_hr_ids(employee_model, payload.audience)
    await exam_model.associate_exam_employees_by_hr_ids(created_exam.exam_id, target_hr_ids)

    created_question_ids: List[str] = []
    for prepared_question in prepared_questions:
        question_instance = Question(
            exam_id=created_exam.exam_id,
            question_text=prepared_question["question_text"],
            question_type=prepared_question["question_type"],
            points=prepared_question["points"],
            question_group=prepared_question["question_group"],
        )
        if prepared_question["choices"] is not None:
            question_instance.choices = [
                QuestionChoice(
                    choice_text=choice["choice_text"],
                    is_correct=choice["is_correct"],
                    choice_order=choice["choice_order"],
                )
                for choice in prepared_question["choices"]
            ]

        created_question = await question_model.create_question(question_instance)
        created_question_ids.append(created_question.question_id)

    if payload.material_ids:
        print("INFO: Associating materials to exam...")
        await exam_model.associate_materials_to_exam(created_exam.exam_id, payload.material_ids)

    assigned_audience_count = len({str(hr_id).strip() for hr_id in target_hr_ids if str(hr_id).strip()})

    return JSONResponse(
        content={
            "signal": ResponseSignalEnum.EXAM_CREATED_SUCCESS.value,
            "exam_id": created_exam.exam_id,
            "question_ids": created_question_ids,
            "assigned_audience_count": assigned_audience_count,
            "notification_recipients_queued": 0,
        },
        status_code=status.HTTP_201_CREATED,
    )

#! Get ALL Exams and their associated Materials With Details
@exam_router.get("/all")
async def get_all_exams(request: Request):

    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    exams = await exam_model.get_all_exams()
    now = datetime.now(timezone.utc)

    exams_details = []
    for exam in exams:
        audience_summary = _build_audience_summary(exam)
        audience_config = _build_audience_config(exam)
        resolved_status = _resolve_exam_status(exam, now)
        exams_details.append(
            {
                "exam_id": exam.exam_id,
                "title": exam.title,
                "description": exam.description,
                "exam_status": resolved_status, # Open, Closed, On Hold
                "exam_level": _resolve_exam_level(exam),
                "duration_minutes": exam.duration_minutes,
                "passing_percent": exam.passing_percent,
                "number_of_attempts_allowed": exam.number_of_attempts_allowed,
                # Preserve full date-time so clients can show schedules accurately
                "start_date": _serialize_exam_datetime(exam.start_date),
                "end_date": _serialize_exam_datetime(exam.end_date),
                "created_on": _serialize_exam_datetime(exam.created_at),
                "updated_on": _serialize_exam_datetime(exam.updated_at),
                "is_deleted": exam.is_deleted,
                "materials": [
                    {
                        "material_id": material.material_id,
                        "material_name": material.material_name,
                        "material_group": material.material_group,
                        "material_training_type": material.material_training_type,
                        "is_deleted": material.is_deleted,
                    }
                        for material in exam.materials
                ] if hasattr(exam, "materials") else [],
                "audience": audience_summary,
                "audience_config": audience_config,
            }
        )
    

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": ResponseSignalEnum.EXAM_RETREIVED_SUCCESS.value,
            "number_exams_retrieved": len(exams_details),
            "exams": exams_details
        },
    )

#! Get Exams assigned to the current Employee (Student)
@exam_router.get("/student")
async def get_student_exams(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    role = (current_user.get("role") or "").lower()
    if role not in {"retail", "employee", "admin", "auditor", "hr"}:
        return JSONResponse(
            content={
                "signal": "Not authorized",
                "message": "Only employees can view assigned exams"
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    email = current_user.get("email")
    if not email:
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Missing user email in token"
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    exists, employee = await employee_model.is_user_exists_by_email(email)
    if not exists or employee is None:
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Employee record not found"
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if not employee.hr_id:
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Employee is missing an HR ID"
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    exams = await exam_model.get_exams_for_employee_hr_id(employee.hr_id)

    exams_details = []
    now = datetime.now(timezone.utc)
    for exam in exams:
        if exam.is_deleted:
            continue
        resolved_status = _resolve_exam_status(exam)
        active_attempt = await exam_model.get_active_attempt_for_employee_exam(
            exam.exam_id,
            employee.employee_id,
        )
        if active_attempt is not None:
            active_attempt, _ = await _finalize_expired_attempt(
                exam_model=exam_model,
                exam=exam,
                attempt=active_attempt,
                now=now,
            )
        number_of_attempts_made = await exam_model.get_number_of_attempts_for_employee_exam(
            exam.exam_id,
            employee.employee_id,
        )

        max_attempts = exam.number_of_attempts_allowed or 1
        attempts_left = max(max_attempts - number_of_attempts_made, 0)

        if active_attempt is None and attempts_left <= 0:
            resolved_status = "Closed"
        exams_details.append(
            {
                "exam_id": exam.exam_id,
                "title": exam.title,
                "description": exam.description,
                "exam_status": exam.exam_status,
                "exam_status": resolved_status, # Open, Closed, On Hold
                "exam_level": _resolve_exam_level(exam),
                "duration_minutes": exam.duration_minutes,
                "passing_percent": exam.passing_percent,
                "number_of_attempts_allowed": exam.number_of_attempts_allowed,
                "number_of_attempts_made": number_of_attempts_made,
                "attempts_left": attempts_left,
                "start_date": _serialize_exam_datetime(exam.start_date),
                "end_date": _serialize_exam_datetime(exam.end_date),
                "materials": [
                    {
                        "material_id": material.material_id,
                        "material_name": material.material_name,
                        "material_group": material.material_group,
                        "material_training_type": material.material_training_type,
                        "is_deleted": material.is_deleted,
                    }
                    for material in exam.materials
                ],
            }
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": ResponseSignalEnum.EXAM_RETREIVED_SUCCESS.value,
            "number_exams_retrieved": len(exams_details),
            "exams": exams_details,
        },
    )

@exam_router.get("/analyze")
async def analyze_exam_data(request: Request):

    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    exams = await exam_model.get_all_exams()

    if not exams:
        return JSONResponse(
            content={
                "signal": "success",
                "total_exams": 0,
                "status_distribution": {
                    "Open": 0,
                    "Closed": 0,
                    "On Hold": 0
                },
                "average_duration_minutes": 0,
                "average_questions_per_exam": 0,
                "material_usage": {}
            },
            status_code=status.HTTP_200_OK,
        )

    total_exams = len(exams)
    
    open_exams = sum([1 for exam in exams if exam.exam_status == "Open"])
    closed_exams = sum([1 for exam in exams if exam.exam_status == "Closed"])
    on_hold_exams = sum([1 for exam in exams if exam.exam_status == "On Hold"])

    total_duration = sum(exam.duration_minutes for exam in exams)
    average_duration = total_duration / total_exams if total_exams > 0 else 0

    total_questions = sum(len(exam.questions) for exam in exams if hasattr(exam, "questions"))
    average_questions_per_exam = total_questions / total_exams if total_exams > 0 else 0

    material_usage = {}
    for exam in exams:
        if hasattr(exam, "materials"):
            for material in exam.materials:
                if material.material_id not in material_usage:
                    material_usage[material.material_id] = {
                        "material_name": material.material_name,
                        "usage_count": 0
                    }
                material_usage[material.material_id]["usage_count"] += 1

    return JSONResponse(
        content={
            "signal": "Exam analysis completed successfully.",
            "total_exams": total_exams,
            "status_distribution": {
                "Open": open_exams,
                "Closed": closed_exams,
                "On Hold": on_hold_exams
            },
            "average_duration_minutes": average_duration,
            "average_questions_per_exam": average_questions_per_exam,
            "material_usage": material_usage
        },
        status_code=status.HTTP_200_OK,
    )


def _build_management_summary_cache_key(access_role: str, filters: dict) -> tuple:
    return (
        str(access_role or "").strip().lower(),
        str(filters.get("period") or "all").strip().lower(),
        str(filters.get("month") or "").strip().lower(),
        str(filters.get("region") or "").strip().lower(),
        str(filters.get("area") or "").strip().lower(),
        str(filters.get("branch_code") or "").strip().lower(),
        str(filters.get("role") or "").strip().lower(),
    )


def _get_management_summary_cache_entry(cache_key: tuple) -> dict | None:
    cached = _management_summary_cache.get(cache_key)
    if not cached:
        return None
    expires_at = cached.get("expires_at")
    if not isinstance(expires_at, datetime) or expires_at <= datetime.now(UTC_TZ):
        _management_summary_cache.pop(cache_key, None)
        return None
    return copy.deepcopy(cached.get("payload"))


def _store_management_summary_cache_entry(cache_key: tuple, payload: dict) -> None:
    _management_summary_cache[cache_key] = {
        "expires_at": datetime.now(UTC_TZ) + timedelta(seconds=MANAGEMENT_SUMMARY_CACHE_TTL_SECONDS),
        "payload": copy.deepcopy(payload),
    }


def _normalize_management_month(value: str | None) -> str | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    if not _MANAGEMENT_MONTH_RE.fullmatch(raw_value):
        return None
    try:
        year_value, month_value = (int(part) for part in raw_value.split("-", 1))
        normalized_date = datetime(year_value, month_value, 1)
    except ValueError:
        return None
    return normalized_date.strftime("%Y-%m")


def _normalize_management_summary_filters(
    *,
    period: str | None,
    month: str | None = None,
    region: str | None = None,
    area: str | None = None,
    branch_code: str | None = None,
    role: str | None = None,
    division: str | None = None,
    sub_department: str | None = None,
) -> dict:
    normalized_period = str(period or "all").strip().lower()
    if normalized_period not in {"all", "week", "month", "year"}:
        normalized_period = "all"

    def _clean(value: str | None) -> str | None:
        cleaned = str(value or "").strip()
        return cleaned or None

    normalized_role = _clean(role)
    if normalized_role is not None:
        normalized_role = normalized_role.lower()

    normalized_month = _normalize_management_month(month)
    if normalized_month is not None:
        normalized_period = "month"

    return {
        "period": normalized_period,
        "month": normalized_month,
        "region": _clean(region),
        "area": _clean(area),
        "branch_code": _clean(branch_code),
        "role": normalized_role,
        "division": _clean(division),
        "sub_department": _clean(sub_department),
    }


def _user_branch_value(user, attr_name: str) -> str | None:
    branch = getattr(user, "branch", None)
    value = getattr(branch, attr_name, None) if branch is not None else None
    if value in (None, "") and attr_name == "branch_code":
        value = getattr(user, "branch_code", None)
    return str(value).strip() if value not in (None, "") else None


def _user_matches_management_filters(user, filters: dict) -> bool:
    if filters.get("role"):
        user_role = str(getattr(user, "department", "") or "").strip().lower()
        if user_role != filters["role"]:
            return False
    if filters.get("region") and _user_branch_value(user, "branch_region") != filters["region"]:
        return False
    if filters.get("area") and _user_branch_value(user, "branch_area") != filters["area"]:
        return False
    if filters.get("branch_code") and _user_branch_value(user, "branch_code") != filters["branch_code"]:
        return False
    if filters.get("division") and _user_branch_value(user, "branch_division") != filters["division"]:
        return False
    if filters.get("sub_department") and _user_branch_value(user, "branch_sub_department") != filters["sub_department"]:
        return False
    return True


def _validate_management_filter_combinations(hierarchy: list[dict], filters: dict) -> str | None:
    region = filters.get("region")
    area = filters.get("area")
    branch_code = filters.get("branch_code")

    region_map: dict[str, set[str]] = {}
    area_map: dict[str, dict[str, str | None]] = {}
    branch_map: dict[str, dict[str, str | None]] = {}

    for region_row in hierarchy or []:
        region_name = str(region_row.get("region") or "").strip()
        if not region_name:
            continue
        region_map.setdefault(region_name, set())
        for area_row in region_row.get("areas", []) or []:
            area_name = str(area_row.get("area") or "").strip()
            if not area_name:
                continue
            region_map[region_name].add(area_name)
            area_map[area_name] = {"region": region_name}
            for branch_row in area_row.get("branches", []) or []:
                code = str(branch_row.get("branch_code") or "").strip()
                if not code:
                    continue
                branch_map[code] = {"region": region_name, "area": area_name}

    if region and region not in region_map:
        return "Selected region is not available."
    if area and region and area not in region_map.get(region, set()):
        return "Selected area does not belong to the selected region."
    if branch_code:
        branch_meta = branch_map.get(branch_code)
        if branch_meta is None:
            return "Selected branch is not available."
        if region and branch_meta.get("region") != region:
            return "Selected branch does not belong to the selected region."
        if area and branch_meta.get("area") != area:
            return "Selected branch does not belong to the selected area."

    return None


def _build_management_employee_row(
    user,
    *,
    assigned_exams: int = 0,
) -> dict:
    return {
        "employee_id": getattr(user, "employee_id", None),
        "hr_id": getattr(user, "hr_id", "") or "",
        "name": getattr(user, "name", "") or "",
        "email": getattr(user, "email", "") or "",
        "job_title": getattr(user, "title", None),
        "role": getattr(user, "department", "") or "",
        "branch_code": _user_branch_value(user, "branch_code"),
        "branch_name": _user_branch_value(user, "branch_name"),
        "region": _user_branch_value(user, "branch_region"),
        "area": _user_branch_value(user, "branch_area"),
        "division": _user_branch_value(user, "branch_division"),
        "sub_department": _user_branch_value(user, "branch_sub_department"),
        "assigned_exam_count": max(0, int(assigned_exams or 0)),
        "created_at": _serialize_exam_datetime(getattr(user, "created_at", None)),
        "last_login_at": _serialize_exam_datetime(getattr(user, "last_login_at", None)),
        "last_activity_at": _serialize_exam_datetime(getattr(user, "last_activity_at", None)),
        "employment_status": getattr(user, "employment_status", None),
    }


def _resolve_management_trend_grouping(period: str) -> str:
    return "day" if period in {"week", "month"} else "month"


def _get_management_summary_period_bounds(
    filters: dict,
    *,
    now: datetime,
) -> tuple[datetime | None, datetime, str]:
    normalized_month = _normalize_management_month(filters.get("month"))
    if normalized_month is None:
        return _get_dashboard_scoring_period_bounds(filters.get("period"), now=now)

    year_value, month_value = (int(part) for part in normalized_month.split("-", 1))
    start_local = datetime(
        year_value,
        month_value,
        1,
        0,
        0,
        0,
        0,
        tzinfo=EGYPT_TZ,
    )
    if month_value == 12:
        next_month_local = datetime(year_value + 1, 1, 1, tzinfo=EGYPT_TZ)
    else:
        next_month_local = datetime(year_value, month_value + 1, 1, tzinfo=EGYPT_TZ)
    end_local = next_month_local - timedelta(microseconds=1)
    return start_local.astimezone(UTC_TZ), end_local.astimezone(UTC_TZ), "month"


def _collect_management_month_options(
    attempts: list[object],
    *,
    selected_month: str | None = None,
) -> list[str]:
    month_values = {
        submitted_at.astimezone(EGYPT_TZ).strftime("%Y-%m")
        for attempt in attempts
        if (submitted_at := _normalize_exam_datetime(getattr(attempt, "submitted_at", None))) is not None
    }
    normalized_selected_month = _normalize_management_month(selected_month)
    if normalized_selected_month is not None:
        month_values.add(normalized_selected_month)
    return sorted(month_values, reverse=True)


def _build_management_trend_items(
    attempts: list,
    *,
    period: str,
    now: datetime,
) -> dict:
    grouping = _resolve_management_trend_grouping(period)
    if not attempts:
        return {"grouping": grouping, "items": []}

    cairo_attempts = []
    for attempt in attempts:
        submitted_at = _normalize_exam_datetime(getattr(attempt, "submitted_at", None))
        if submitted_at is None:
            continue
        score_pct = _extract_score_percentage(
            getattr(attempt, "total_score", None),
            getattr(attempt, "max_score", None),
        )
        cairo_attempts.append(
            {
                "employee_id": getattr(attempt, "employee_id", None),
                "submitted_at": submitted_at.astimezone(EGYPT_TZ),
                "score_pct": score_pct,
                "passed": bool(getattr(attempt, "passed", False)),
            }
        )

    if not cairo_attempts:
        return {"grouping": grouping, "items": []}

    earliest = min(item["submitted_at"] for item in cairo_attempts)
    latest = max(item["submitted_at"] for item in cairo_attempts)
    end_local = now.astimezone(EGYPT_TZ)

    if grouping == "day":
        start_local = earliest.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start_local = earliest.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_local = end_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    buckets: dict[str, dict] = {}
    current = start_local
    while current <= end_local:
        if grouping == "day":
            bucket_key = current.strftime("%Y-%m-%d")
            bucket_label = current.strftime("%d %b")
            next_bucket = current + timedelta(days=1)
        else:
            bucket_key = current.strftime("%Y-%m")
            bucket_label = current.strftime("%b %Y")
            if current.month == 12:
                next_bucket = current.replace(year=current.year + 1, month=1)
            else:
                next_bucket = current.replace(month=current.month + 1)

        buckets[bucket_key] = {
            "bucket_key": bucket_key,
            "label": bucket_label,
            "participants": set(),
            "attempts": 0,
            "passed_attempts": 0,
            "score_sum": 0.0,
            "score_count": 0,
        }
        current = next_bucket

    for item in cairo_attempts:
        submitted_local = item["submitted_at"]
        bucket_key = submitted_local.strftime("%Y-%m-%d") if grouping == "day" else submitted_local.strftime("%Y-%m")
        bucket = buckets.get(bucket_key)
        if bucket is None:
            continue
        employee_id = item["employee_id"]
        if employee_id:
            bucket["participants"].add(employee_id)
        bucket["attempts"] += 1
        if item["passed"]:
            bucket["passed_attempts"] += 1
        if item["score_pct"] is not None:
            bucket["score_sum"] += float(item["score_pct"])
            bucket["score_count"] += 1

    items = []
    for bucket in buckets.values():
        attempts_count = int(bucket["attempts"] or 0)
        items.append(
            {
                "bucket_key": bucket["bucket_key"],
                "label": bucket["label"],
                "participants": len(bucket["participants"]),
                "attempts": attempts_count,
                "average_score_pct": round(bucket["score_sum"] / bucket["score_count"], 2)
                if bucket["score_count"]
                else 0.0,
                "pass_rate_pct": _safe_percentage(bucket["passed_attempts"], attempts_count),
            }
        )

    return {"grouping": grouping, "items": items}


def _severity_rank(value: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(str(value or "").lower(), 3)


def _build_management_summary_bundle(
    *,
    users: list,
    active_exams: list,
    attempts: list,
    hierarchy: list[dict],
    audit_rows: list[dict],
    now: datetime,
    filters: dict,
    access_role: str,
) -> dict:
    period_start, period_end, normalized_period = _get_management_summary_period_bounds(filters, now=now)
    status_distribution = {"Open": 0, "Closed": 0, "On Hold": 0}
    active_users: list[object] = []
    resigned_users: list[object] = []
    users_by_employee_id: dict[str, object] = {}
    users_by_email: dict[str, object] = {}
    region_filter_scope_filters = {**filters, "region": None, "area": None, "branch_code": None}
    area_filter_scope_filters = {**filters, "area": None, "branch_code": None}
    branch_filter_scope_filters = {**filters, "branch_code": None}
    region_filter_options: set[str] = set()
    area_filter_options: set[str] = set()
    branch_filter_options: dict[str, dict] = {}

    for user in users:
        user_role = str(getattr(user, "department", "") or "").strip().lower()
        if not _is_employee_dashboard_role(user_role):
            continue
        if is_employee_resigned(user):
            if _user_matches_management_filters(user, filters):
                resigned_users.append(user)
            continue
        if _user_matches_management_filters(user, region_filter_scope_filters):
            region_name = _user_branch_value(user, "branch_region")
            if region_name:
                region_filter_options.add(region_name)
        if _user_matches_management_filters(user, area_filter_scope_filters):
            area_name = _user_branch_value(user, "branch_area")
            if area_name:
                area_filter_options.add(area_name)
        if _user_matches_management_filters(user, branch_filter_scope_filters):
            branch_code = _user_branch_value(user, "branch_code")
            if branch_code:
                branch_bucket = branch_filter_options.setdefault(
                    branch_code,
                    {
                        "branch_code": branch_code,
                        "branch_name": _user_branch_value(user, "branch_name") or branch_code,
                        "employee_count": 0,
                    },
                )
                branch_bucket["employee_count"] += 1
        if not _user_matches_management_filters(user, filters):
            continue
        active_users.append(user)
        employee_id = getattr(user, "employee_id", None)
        if employee_id:
            users_by_employee_id[employee_id] = user
        normalized_email = _normalize_email(getattr(user, "email", None))
        if normalized_email:
            users_by_email[normalized_email] = user

    active_employee_ids = {employee_id for employee_id in users_by_employee_id}

    scoped_exam_assignments: dict[str, list[object]] = {}
    scoped_exams: list[object] = []
    assigned_pairs: set[tuple[str, str]] = set()
    assigned_by_employee: dict[str, int] = {}
    assigned_by_exam: dict[str, int] = {}
    exam_lookup: dict[str, object] = {}

    for exam in active_exams:
        exam_id = getattr(exam, "exam_id", None)
        if not exam_id:
            continue
        scoped_employees = [
            employee
            for employee in list(getattr(exam, "employees", []) or [])
            if getattr(employee, "employee_id", None) in active_employee_ids
        ]
        if not scoped_employees:
            continue
        scoped_exams.append(exam)
        exam_lookup[exam_id] = exam
        scoped_exam_assignments[exam_id] = scoped_employees
        assigned_by_exam[exam_id] = len({employee.employee_id for employee in scoped_employees if employee.employee_id})
        for employee in scoped_employees:
            employee_id = getattr(employee, "employee_id", None)
            if not employee_id:
                continue
            assigned_pairs.add((exam_id, employee_id))
            assigned_by_employee[employee_id] = assigned_by_employee.get(employee_id, 0) + 1

    scoped_exam_ids = set(scoped_exam_assignments)
    scoped_all_time_attempts: list[object] = []
    scoped_period_attempts: list[object] = []
    for attempt in attempts:
        employee_id = getattr(attempt, "employee_id", None)
        exam_id = getattr(attempt, "exam_id", None)
        submitted_at = _normalize_exam_datetime(getattr(attempt, "submitted_at", None))
        if employee_id not in active_employee_ids or exam_id not in scoped_exam_ids or submitted_at is None:
            continue
        scoped_all_time_attempts.append(attempt)
        if submitted_at > period_end:
            continue
        if period_start is not None and submitted_at < period_start:
            continue
        scoped_period_attempts.append(attempt)

    attempted_employee_ids = {
        getattr(attempt, "employee_id", None)
        for attempt in scoped_period_attempts
        if getattr(attempt, "employee_id", None)
    }
    period_attempt_count_by_employee: dict[str, int] = {}
    for attempt in scoped_period_attempts:
        employee_id = getattr(attempt, "employee_id", None)
        if employee_id:
            period_attempt_count_by_employee[employee_id] = period_attempt_count_by_employee.get(employee_id, 0) + 1

    no_attempt_rows: list[dict] = []
    for user in active_users:
        employee_id = getattr(user, "employee_id", None)
        assigned_exam_count = assigned_by_employee.get(employee_id, 0)
        if assigned_exam_count <= 0:
            continue
        if period_attempt_count_by_employee.get(employee_id, 0) > 0:
            continue
        no_attempt_rows.append(
            _build_management_employee_row(
                user,
                assigned_exams=assigned_exam_count,
            )
        )
    no_attempt_rows.sort(
        key=lambda row: (
            -int(row.get("assigned_exam_count") or 0),
            str(row.get("name") or "").lower(),
            str(row.get("hr_id") or "").lower(),
        )
    )

    login_emails: set[str] = set()
    active_system_emails: set[str] = set()
    for row in audit_rows:
        if _is_synthetic_dashboard_audit_row(row):
            continue
        status_code = int(row.get("status_code") or 0)
        if status_code >= 400:
            continue
        actor_email = _normalize_email(row.get("actor_email"))
        if not actor_email or actor_email == "anonymous":
            continue
        path = str(row.get("path") or "")
        if path == "/api/v1/users/login":
            login_emails.add(actor_email)
        if path.startswith("/api/") and path not in {"/api/v1/users/login", "/api/v1/users/login/request-otp"}:
            active_system_emails.add(actor_email)

    eligible_emails = {_normalize_email(getattr(user, "email", None)) for user in active_users}
    eligible_emails.discard("")
    proven_login_emails = login_emails.union(active_system_emails)

    no_login_rows: list[dict] = []
    no_activity_rows: list[dict] = []
    for user in active_users:
        email = _normalize_email(getattr(user, "email", None))
        if not email:
            continue
        row = _build_management_employee_row(
            user,
            assigned_exams=assigned_by_employee.get(getattr(user, "employee_id", None), 0),
        )
        has_login_history = _normalize_exam_datetime(getattr(user, "last_login_at", None)) is not None
        has_activity_history = _normalize_exam_datetime(getattr(user, "last_activity_at", None)) is not None
        if not has_login_history and email not in proven_login_emails:
            no_login_rows.append(row)
        if not has_activity_history and email not in active_system_emails:
            no_activity_rows.append(row)

    no_login_rows.sort(key=lambda row: (str(row.get("name") or "").lower(), str(row.get("hr_id") or "").lower()))
    no_activity_rows.sort(key=lambda row: (str(row.get("name") or "").lower(), str(row.get("hr_id") or "").lower()))

    latest_distinct_attempts: dict[tuple[str, str], dict] = {}
    raw_attempt_score_percentages: list[float] = []
    branch_attempt_stats: dict[str, dict] = {}
    exam_attempt_stats: dict[str, dict] = {}
    repeated_failure_groups: dict[tuple[str, str], dict] = {}
    mistake_topic_stats: dict[str, dict] = {}

    for attempt in scoped_period_attempts:
        employee_id = getattr(attempt, "employee_id", None)
        exam_id = getattr(attempt, "exam_id", None)
        submitted_at = _normalize_exam_datetime(getattr(attempt, "submitted_at", None))
        score_pct = _extract_score_percentage(
            getattr(attempt, "total_score", None),
            getattr(attempt, "max_score", None),
        )
        if employee_id is None or exam_id is None or submitted_at is None:
            continue
        user = users_by_employee_id.get(employee_id)
        branch_code = _user_branch_value(user, "branch_code") if user is not None else None
        if score_pct is not None:
            raw_attempt_score_percentages.append(score_pct)

        for answer in list(getattr(attempt, "answers", []) or []):
            question = getattr(answer, "question", None)
            topic_label = getattr(question, "dashboard_topic_label", None) or _resolve_management_topic_label(getattr(question, "question_group", None))
            if not topic_label:
                continue
            topic_key = getattr(question, "dashboard_topic_key", None) or _normalize_topic_key(topic_label)
            topic_bucket = mistake_topic_stats.setdefault(
                topic_key,
                {
                    "topic": topic_label,
                    "topic_key": topic_key,
                    "total_answers": 0,
                    "wrong_answers": 0,
                    "correct_answers": 0,
                    "branches": {},
                    "variants": {},
                },
            )
            topic_bucket["variants"][topic_label] = int(topic_bucket["variants"].get(topic_label) or 0) + 1
            topic_bucket["total_answers"] += 1
            answer_is_correct = bool(getattr(answer, "is_correct", False))
            if answer_is_correct:
                topic_bucket["correct_answers"] += 1
            else:
                topic_bucket["wrong_answers"] += 1
            if branch_code:
                topic_branch_bucket = topic_bucket["branches"].setdefault(
                    branch_code,
                    {
                        "branch_code": branch_code,
                        "branch_name": _user_branch_value(user, "branch_name") or branch_code,
                        "total_answers": 0,
                        "wrong_answers": 0,
                        "correct_answers": 0,
                    },
                )
                topic_branch_bucket["total_answers"] += 1
                if answer_is_correct:
                    topic_branch_bucket["correct_answers"] += 1
                else:
                    topic_branch_bucket["wrong_answers"] += 1

        if branch_code:
            branch_bucket = branch_attempt_stats.setdefault(
                branch_code,
                {"attempts": 0, "passed_attempts": 0, "employee_ids": set(), "score_sum": 0.0, "score_count": 0},
            )
            branch_bucket["attempts"] += 1
            branch_bucket["employee_ids"].add(employee_id)
            if bool(getattr(attempt, "passed", False)):
                branch_bucket["passed_attempts"] += 1
            if score_pct is not None:
                branch_bucket["score_sum"] += float(score_pct)
                branch_bucket["score_count"] += 1

        exam_bucket = exam_attempt_stats.setdefault(
            exam_id,
            {
                "attempts": 0,
                "passed_attempts": 0,
                "score_sum": 0.0,
                "score_count": 0,
                "employee_ids": set(),
            },
        )
        exam_bucket["attempts"] += 1
        exam_bucket["employee_ids"].add(employee_id)
        if bool(getattr(attempt, "passed", False)):
            exam_bucket["passed_attempts"] += 1
        if score_pct is not None:
            exam_bucket["score_sum"] += float(score_pct)
            exam_bucket["score_count"] += 1

        key = (employee_id, exam_id)
        current = latest_distinct_attempts.get(key)
        if current is None or submitted_at > current["submitted_at"]:
            latest_distinct_attempts[key] = {
                "employee_id": employee_id,
                "exam_id": exam_id,
                "submitted_at": submitted_at,
                "score_pct": score_pct,
                "passed": bool(getattr(attempt, "passed", False)),
            }

        if not bool(getattr(attempt, "passed", False)):
            failure_key = (employee_id, exam_id)
            failure_bucket = repeated_failure_groups.setdefault(
                failure_key,
                {
                    "employee_id": employee_id,
                    "exam_id": exam_id,
                    "failure_count": 0,
                    "latest_attempt_at": submitted_at,
                    "latest_score_pct": score_pct,
                    "score_sum": 0.0,
                    "score_count": 0,
                },
            )
            failure_bucket["failure_count"] += 1
            if score_pct is not None:
                failure_bucket["score_sum"] += float(score_pct)
                failure_bucket["score_count"] += 1
            if submitted_at >= failure_bucket["latest_attempt_at"]:
                failure_bucket["latest_attempt_at"] = submitted_at
                failure_bucket["latest_score_pct"] = score_pct

    employee_period_stats: dict[str, dict] = {}
    for record in latest_distinct_attempts.values():
        employee_id = record["employee_id"]
        score_pct = record["score_pct"]
        bucket = employee_period_stats.setdefault(
            employee_id,
            {
                "scores": [],
                "passed_exams": 0,
                "failed_exams": 0,
                "exams_joined": 0,
                "latest_attempt_at": record["submitted_at"],
            },
        )
        bucket["exams_joined"] += 1
        if score_pct is not None:
            bucket["scores"].append(float(score_pct))
        if record["passed"]:
            bucket["passed_exams"] += 1
        else:
            bucket["failed_exams"] += 1
        if record["submitted_at"] > bucket["latest_attempt_at"]:
            bucket["latest_attempt_at"] = record["submitted_at"]

    low_score_rows: list[dict] = []
    for employee_id, stats in employee_period_stats.items():
        if not stats.get("scores"):
            continue
        average_pct = round(sum(stats["scores"]) / len(stats["scores"]), 2)
        if average_pct >= MANAGEMENT_LOW_SCORE_THRESHOLD:
            continue
        user = users_by_employee_id.get(employee_id)
        if user is None:
            continue
        row = _build_management_employee_row(
            user,
            assigned_exams=assigned_by_employee.get(employee_id, 0),
        )
        row.update(
            {
                "exams_attempted": int(stats.get("exams_joined") or 0),
                "average_score_pct": average_pct,
                "passed_exams": int(stats.get("passed_exams") or 0),
                "failed_exams": int(stats.get("failed_exams") or 0),
                "latest_attempt_at": _serialize_exam_datetime(stats.get("latest_attempt_at")),
            }
        )
        low_score_rows.append(row)
    low_score_rows.sort(
        key=lambda row: (
            float(row.get("average_score_pct") or 0),
            str(row.get("name") or "").lower(),
            str(row.get("hr_id") or "").lower(),
        )
    )

    repeated_failure_rows: list[dict] = []
    for failure_bucket in repeated_failure_groups.values():
        if int(failure_bucket.get("failure_count") or 0) < 2:
            continue
        user = users_by_employee_id.get(failure_bucket["employee_id"])
        exam = exam_lookup.get(failure_bucket["exam_id"])
        if user is None or exam is None:
            continue
        average_exam_score = (
            round(float(failure_bucket["score_sum"]) / int(failure_bucket["score_count"]), 2)
            if int(failure_bucket["score_count"] or 0) > 0
            else None
        )
        repeated_failure_rows.append(
            {
                "employee_id": getattr(user, "employee_id", None),
                "hr_id": getattr(user, "hr_id", "") or "",
                "name": getattr(user, "name", "") or "",
                "branch_code": _user_branch_value(user, "branch_code"),
                "branch_name": _user_branch_value(user, "branch_name"),
                "exam_id": getattr(exam, "exam_id", None),
                "exam_title": getattr(exam, "title", None),
                "failure_count": int(failure_bucket["failure_count"]),
                "latest_score_pct": failure_bucket.get("latest_score_pct"),
                "latest_attempt_at": _serialize_exam_datetime(failure_bucket.get("latest_attempt_at")),
                "average_exam_score_pct": average_exam_score,
            }
        )
    repeated_failure_rows.sort(
        key=lambda row: (
            -int(row.get("failure_count") or 0),
            str(row.get("latest_attempt_at") or ""),
            str(row.get("name") or "").lower(),
        ),
        reverse=False,
    )

    branch_employee_rows: dict[str, list[object]] = {}
    for user in active_users:
        branch_code = _user_branch_value(user, "branch_code") or "UNASSIGNED"
        branch_employee_rows.setdefault(branch_code, []).append(user)

    no_attempt_count_by_branch: dict[str, int] = {}
    for row in no_attempt_rows:
        branch_code = row.get("branch_code") or "UNASSIGNED"
        no_attempt_count_by_branch[branch_code] = no_attempt_count_by_branch.get(branch_code, 0) + 1

    no_login_count_by_branch: dict[str, int] = {}
    for row in no_login_rows:
        branch_code = row.get("branch_code") or "UNASSIGNED"
        no_login_count_by_branch[branch_code] = no_login_count_by_branch.get(branch_code, 0) + 1

    no_activity_count_by_branch: dict[str, int] = {}
    for row in no_activity_rows:
        branch_code = row.get("branch_code") or "UNASSIGNED"
        no_activity_count_by_branch[branch_code] = no_activity_count_by_branch.get(branch_code, 0) + 1

    branch_comparison_rows: list[dict] = []
    for branch_code, branch_users in branch_employee_rows.items():
        sample_user = branch_users[0]
        total_employees = len(branch_users)

        branch_stats = branch_attempt_stats.get(branch_code, {})
        attempts_count = int(branch_stats.get("attempts") or 0)
        passed_attempts = int(branch_stats.get("passed_attempts") or 0)
        participating_count = len(branch_stats.get("employee_ids") or set())
        average_score_pct = (
            round(float(branch_stats.get("score_sum") or 0.0) / int(branch_stats.get("score_count") or 1), 2)
            if int(branch_stats.get("score_count") or 0) > 0
            else 0.0
        )

        branch_comparison_rows.append(
            {
                "branch_code": branch_code,
                "branch_name": _user_branch_value(sample_user, "branch_name") or branch_code,
                "region": _user_branch_value(sample_user, "branch_region"),
                "area": _user_branch_value(sample_user, "branch_area"),
                "total_employees": total_employees,
                "participating_employees": participating_count,
                "scored_attempts": int(branch_stats.get("score_count") or 0),
                "participation_rate_pct": _safe_percentage(participating_count, total_employees),
                "average_score_pct": average_score_pct,
                "pass_rate_pct": _safe_percentage(passed_attempts, attempts_count),
                "no_attempt_employees": no_attempt_count_by_branch.get(branch_code, 0),
                "never_logged_in": no_login_count_by_branch.get(branch_code, 0),
                "never_active": no_activity_count_by_branch.get(branch_code, 0),
            }
        )

    top_branch_rows = sorted(
        branch_comparison_rows,
        key=lambda row: (
            -float(row.get("average_score_pct") or 0),
            -float(row.get("participation_rate_pct") or 0),
            -int(row.get("participating_employees") or 0),
            str(row.get("branch_name") or "").lower(),
        ),
    )
    low_branch_rows = sorted(
        branch_comparison_rows,
        key=lambda row: (
            float(row.get("average_score_pct") or 0),
            int(row.get("participating_employees") or 0),
            str(row.get("branch_name") or "").lower(),
        ),
    )
    low_participation_rows = sorted(
        branch_comparison_rows,
        key=lambda row: (
            float(row.get("participation_rate_pct") or 0),
            -int(row.get("total_employees") or 0),
            str(row.get("branch_name") or "").lower(),
        ),
    )
    high_no_attempt_rows = sorted(
        branch_comparison_rows,
        key=lambda row: (
            -int(row.get("no_attempt_employees") or 0),
            float(row.get("participation_rate_pct") or 0),
            str(row.get("branch_name") or "").lower(),
        ),
    )

    mistake_topic_rows = [
        {
            "topic": stats["topic"],
            "topic_key": stats["topic_key"],
            "wrong_answers": int(stats["wrong_answers"] or 0),
            "correct_answers": int(stats["correct_answers"] or 0),
            "total_answers": int(stats["total_answers"] or 0),
            "error_rate_pct": _safe_percentage(int(stats["wrong_answers"] or 0), int(stats["total_answers"] or 0)),
            "accuracy_pct": _safe_percentage(int(stats["correct_answers"] or 0), int(stats["total_answers"] or 0)),
            "branches": sorted(
                [
                    {
                        "branch_code": branch_stats["branch_code"],
                        "branch_name": branch_stats["branch_name"],
                        "wrong_answers": int(branch_stats["wrong_answers"] or 0),
                        "correct_answers": int(branch_stats["correct_answers"] or 0),
                        "total_answers": int(branch_stats["total_answers"] or 0),
                        "error_rate_pct": _safe_percentage(
                            int(branch_stats["wrong_answers"] or 0),
                            int(branch_stats["total_answers"] or 0),
                        ),
                        "accuracy_pct": _safe_percentage(
                            int(branch_stats["correct_answers"] or 0),
                            int(branch_stats["total_answers"] or 0),
                        ),
                    }
                    for branch_stats in (stats.get("branches") or {}).values()
                    if int(branch_stats.get("wrong_answers") or 0) > 0
                ],
                key=lambda row: (
                    -int(row.get("wrong_answers") or 0),
                    -float(row.get("error_rate_pct") or 0),
                    -int(row.get("total_answers") or 0),
                    str(row.get("branch_name") or "").lower(),
                    str(row.get("branch_code") or "").lower(),
                ),
            )[:10],
        }
        for stats in mistake_topic_stats.values()
        if int(stats.get("wrong_answers") or 0) > 0
    ]
    mistake_topic_rows.sort(
        key=lambda row: (
            -int(row.get("wrong_answers") or 0),
            -float(row.get("error_rate_pct") or 0),
            -int(row.get("total_answers") or 0),
            str(row.get("topic") or "").lower(),
        )
    )

    exam_insight_rows: list[dict] = []
    active_open_exam_rows: list[dict] = []
    overdue_exam_rows: list[dict] = []
    for exam in scoped_exams:
        exam_id = getattr(exam, "exam_id", None)
        if not exam_id:
            continue
        resolved_status = _resolve_exam_status(exam)
        status_distribution[resolved_status] = status_distribution.get(resolved_status, 0) + 1
        assigned_count = int(assigned_by_exam.get(exam_id) or 0)
        attempt_stats = exam_attempt_stats.get(exam_id, {})
        attempt_count = int(attempt_stats.get("attempts") or 0)
        passed_attempts = int(attempt_stats.get("passed_attempts") or 0)
        participating_employees = len(attempt_stats.get("employee_ids") or set())
        average_score_pct = (
            round(float(attempt_stats.get("score_sum") or 0.0) / int(attempt_stats.get("score_count") or 1), 2)
            if int(attempt_stats.get("score_count") or 0) > 0
            else 0.0
        )
        failure_rate_pct = _safe_percentage(max(attempt_count - passed_attempts, 0), attempt_count)
        participation_rate_pct = _safe_percentage(participating_employees, assigned_count)
        end_dt = _normalize_exam_datetime(getattr(exam, "end_date", None))
        open_configured = str(getattr(exam, "exam_status", "") or "").strip().lower() == "open"
        no_attempt_employee_count = max(assigned_count - participating_employees, 0)

        insight_row = {
            "exam_id": exam_id,
            "exam_name": getattr(exam, "title", None),
            "start_date": _serialize_exam_datetime(getattr(exam, "start_date", None)),
            "end_date": _serialize_exam_datetime(getattr(exam, "end_date", None)),
            "assigned_employees": assigned_count,
            "participating_employees": participating_employees,
            "participation_rate_pct": participation_rate_pct,
            "attempt_count": attempt_count,
            "average_score_pct": average_score_pct,
            "failure_rate_pct": failure_rate_pct,
            "current_status": resolved_status,
        }
        exam_insight_rows.append(insight_row)

        if resolved_status == "Open":
            active_open_exam_rows.append(insight_row)

        if open_configured and _is_exam_window_closed(exam, now):
            overdue_exam_rows.append(
                {
                    **insight_row,
                    "days_overdue": max((now - end_dt).days, 1),
                    "employees_with_no_attempt": no_attempt_employee_count,
                }
            )

    highest_failure_rate_rows = [
        row
        for row in sorted(
            exam_insight_rows,
            key=lambda row: (
                -float(row.get("failure_rate_pct") or 0),
                -int(row.get("attempt_count") or 0),
                str(row.get("exam_name") or "").lower(),
            ),
        )
        if int(row.get("attempt_count") or 0) >= MANAGEMENT_MIN_FAILURE_ATTEMPTS
    ]

    overview = {
        "active_employees": len(active_users),
        "resigned_employees": len(resigned_users),
        "users_with_attempts": len(attempted_employee_ids),
        "training_participation_rate": _safe_percentage(len(attempted_employee_ids), len(active_users)),
        "average_exam_score_pct": round(sum(raw_attempt_score_percentages) / len(raw_attempt_score_percentages), 2)
        if raw_attempt_score_percentages
        else 0.0,
        "pass_rate_pct": _safe_percentage(
            sum(1 for attempt in scoped_period_attempts if bool(getattr(attempt, "passed", False))),
            len(scoped_period_attempts),
        ),
        "no_exam_attempts": len(no_attempt_rows),
        "never_logged_in": len(no_login_rows),
        "never_active": len(no_activity_rows),
        "active_open_exams": sum(1 for exam in scoped_exams if _resolve_exam_status(exam) == "Open"),
        "overdue_open_exams": len(overdue_exam_rows),
    }

    alerts: list[dict] = []
    if overview["training_participation_rate"] < MANAGEMENT_LOW_PARTICIPATION_THRESHOLD:
        alerts.append(
            {
                "code": "LOW_PARTICIPATION",
                "severity": "high",
                "title": "Training participation is below target",
                "message": (
                    f"Current participation is {overview['training_participation_rate']:.1f}%, "
                    f"below the {MANAGEMENT_LOW_PARTICIPATION_THRESHOLD:.0f}% target."
                ),
                "value": round(overview["training_participation_rate"], 2),
                "threshold": MANAGEMENT_LOW_PARTICIPATION_THRESHOLD,
                "drilldown": "no-attempts",
            }
        )
    if overview["overdue_open_exams"] > 0:
        alerts.append(
            {
                "code": "OVERDUE_OPEN_EXAMS",
                "severity": "high",
                "title": "Open exams are overdue",
                "message": f"{overview['overdue_open_exams']} open exam(s) are past their end date.",
                "value": overview["overdue_open_exams"],
                "threshold": 0,
                "drilldown": "overdue-exams",
            }
        )
    if highest_failure_rate_rows and float(highest_failure_rate_rows[0]["failure_rate_pct"]) > MANAGEMENT_HIGH_FAILURE_THRESHOLD:
        highest_failure_exam = highest_failure_rate_rows[0]
        alerts.append(
            {
                "code": "HIGH_EXAM_FAILURE_RATE",
                "severity": "high",
                "title": "An exam failure rate is above the alert threshold",
                "message": (
                    f"{highest_failure_exam['exam_name']} is at {float(highest_failure_exam['failure_rate_pct']):.1f}% "
                    f"failure across {int(highest_failure_exam['attempt_count'] or 0)} attempts."
                ),
                "value": round(float(highest_failure_exam["failure_rate_pct"]), 2),
                "threshold": MANAGEMENT_HIGH_FAILURE_THRESHOLD,
                "drilldown": "exam-insights",
            }
        )
    if overview["no_exam_attempts"] > 0:
        alerts.append(
            {
                "code": "NO_EXAM_ATTEMPTS",
                "severity": "medium",
                "title": "Assigned employees have not attempted an exam",
                "message": f"{overview['no_exam_attempts']} assigned employee(s) have no submitted attempt in scope.",
                "value": overview["no_exam_attempts"],
                "threshold": 0,
                "drilldown": "no-attempts",
            }
        )
    if overview["never_logged_in"] > 0:
        alerts.append(
            {
                "code": "NEVER_LOGGED_IN",
                "severity": "medium",
                "title": "Employees have no recorded login evidence",
                "message": f"{overview['never_logged_in']} employee account(s) have no recorded login evidence.",
                "value": overview["never_logged_in"],
                "threshold": 0,
                "drilldown": "never-logged-in",
            }
        )
    if overview["never_active"] > 0:
        alerts.append(
            {
                "code": "NEVER_ACTIVE",
                "severity": "medium",
                "title": "Employees have no recorded activity",
                "message": f"{overview['never_active']} employee account(s) have no recorded system activity.",
                "value": overview["never_active"],
                "threshold": 0,
                "drilldown": "never-active",
            }
        )
    lowest_branch_row = low_branch_rows[0] if low_branch_rows else None
    if lowest_branch_row and float(lowest_branch_row.get("average_score_pct") or 0) < MANAGEMENT_LOW_BRANCH_SCORE_THRESHOLD:
        alerts.append(
            {
                "code": "LOW_BRANCH_SCORE",
                "severity": "high",
                "title": "A branch average score is below threshold",
                "message": (
                    f"{lowest_branch_row['branch_name']} is averaging "
                    f"{float(lowest_branch_row['average_score_pct']):.1f}%."
                ),
                "value": round(float(lowest_branch_row["average_score_pct"]), 2),
                "threshold": MANAGEMENT_LOW_BRANCH_SCORE_THRESHOLD,
                "drilldown": "branch-comparison",
            }
        )

    alerts.sort(key=lambda row: (_severity_rank(row.get("severity")), -float(row.get("value") or 0)))

    summary = {
        "filters": {
            "period": normalized_period,
            "month": filters.get("month"),
            "region": filters.get("region"),
            "area": filters.get("area"),
            "branch_code": filters.get("branch_code"),
            "role": filters.get("role"),
        },
        "access": {
            "access_role": access_role,
            "can_view_employee_attention": access_role in {"admin", "auditor", "hr"},
            "can_export_attention_lists": access_role in {"admin", "auditor", "hr"},
        },
        "filter_options": {
            "regions": sorted(region_filter_options, key=lambda value: str(value or "").lower()),
            "areas": sorted(area_filter_options, key=lambda value: str(value or "").lower()),
            "branches": sorted(
                branch_filter_options.values(),
                key=lambda row: (
                    str(row.get("branch_name") or "").lower(),
                    str(row.get("branch_code") or "").lower(),
                ),
            ),
            "months": _collect_management_month_options(
                scoped_all_time_attempts,
                selected_month=filters.get("month"),
            ),
        },
        "overview": overview,
        "trends": _build_management_trend_items(
            scoped_period_attempts,
            period=normalized_period,
            now=now,
        ),
        "branches": {
            "top": top_branch_rows[:5],
            "low": low_branch_rows[:5],
            "lowest_participation": low_participation_rows[:5],
            "highest_no_attempts": high_no_attempt_rows[:5],
            "comparison": branch_comparison_rows,
        },
        "mistake_topics": mistake_topic_rows,
        "exam_status_mix": status_distribution,
        "exam_insights": {
            "highest_participation": sorted(
                [row for row in exam_insight_rows if int(row.get("assigned_employees") or 0) > 0],
                key=lambda row: (
                    -float(row.get("participation_rate_pct") or 0),
                    -int(row.get("participating_employees") or 0),
                    str(row.get("exam_name") or "").lower(),
                ),
            )[:5],
            "lowest_participation": sorted(
                [row for row in exam_insight_rows if int(row.get("assigned_employees") or 0) > 0],
                key=lambda row: (
                    float(row.get("participation_rate_pct") or 0),
                    -int(row.get("assigned_employees") or 0),
                    str(row.get("exam_name") or "").lower(),
                ),
            )[:5],
            "highest_failure_rate": highest_failure_rate_rows[:5],
            "lowest_average_score": sorted(
                [row for row in exam_insight_rows if int(row.get("attempt_count") or 0) > 0],
                key=lambda row: (
                    float(row.get("average_score_pct") or 0),
                    -int(row.get("attempt_count") or 0),
                    str(row.get("exam_name") or "").lower(),
                ),
            )[:5],
            "active_open": sorted(
                active_open_exam_rows,
                key=lambda row: (str(row.get("end_date") or ""), str(row.get("exam_name") or "").lower()),
            )[:10],
            "overdue_open": sorted(
                overdue_exam_rows,
                key=lambda row: (-int(row.get("days_overdue") or 0), str(row.get("exam_name") or "").lower()),
            )[:10],
        },
        "attention": {
            "no_attempts_count": len(no_attempt_rows),
            "low_score_count": len(low_score_rows),
            "repeated_failure_count": len(repeated_failure_rows),
            "never_logged_in_count": len(no_login_rows),
            "never_active_count": len(no_activity_rows),
        },
        "alerts": alerts,
    }

    attention_lists = {
        "no_attempts": no_attempt_rows,
        "low_scores": low_score_rows,
        "repeated_failures": repeated_failure_rows,
        "never_logged_in": no_login_rows,
        "never_active": no_activity_rows,
    }

    return {
        "summary": summary,
        "attention_lists": attention_lists,
    }


def _management_default_filters(filters: dict) -> bool:
    return filters["period"] == "all" and not any(
        filters.get(key) for key in ("month", "region", "area", "branch_code", "role", "division", "sub_department")
    )


async def _load_management_snapshot(request: Request, snapshot_id: str | None = None,
                                    *, include_sources: bool = True):
    db_path = request.app.state.settings.SQLITE_DB_PATH
    try:
        loaded = await asyncio.to_thread(load_published_sources, db_path,
                                         snapshot_id, include_sources=include_sources)
    except (OSError, ValueError, sqlite3.Error, zlib.error) as error:
        logger.error("Dashboard snapshot unavailable: %s", error)
        loaded = None
    if loaded is None:
        try:
            if snapshot_id and await asyncio.to_thread(requested_snapshot_expired, db_path, snapshot_id):
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content={"signal": "error", "code": "DASHBOARD_SNAPSHOT_EXPIRED",
                             "message": "Dashboard data was updated. Reload using the current snapshot."},
                )
        except (OSError, ValueError, sqlite3.Error, zlib.error) as error:
            logger.error("Dashboard snapshot expiry check unavailable: %s", error)
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            content={"signal": "error", "code": "DASHBOARD_SNAPSHOT_UNAVAILABLE",
                                     "message": "Dashboard data is unavailable. Please retry after the next refresh."})
    return loaded


@exam_router.get("/dashboard/management-summary")
async def get_management_dashboard_summary(
    request: Request,
    period: str = Query("all", pattern="^(all|week|month|year)$"),
    month: str | None = Query(default=None),
    region: str | None = Query(default=None),
    area: str | None = Query(default=None),
    branch_code: str | None = Query(default=None),
    role: str | None = Query(default=None),
    snapshot_id: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    access_role = str(current_user.get("role") or "").strip().lower()
    if access_role not in {"admin", "auditor", "hr", "manager"}:
        return JSONResponse(
            content={
                "signal": "Not authorized",
                "message": "Only Admin, HR, and manager users can view the management dashboard.",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    filters = _normalize_management_summary_filters(
        period=period,
        month=month,
        region=region,
        area=area,
        branch_code=branch_code,
        role=role,
    )
    if os.getenv("TRAINING_DASHBOARD_SNAPSHOT_READS") == "1":
        default_view = _management_default_filters(filters)
        loaded = await _load_management_snapshot(request, snapshot_id, include_sources=not default_view)
        if isinstance(loaded, JSONResponse):
            return loaded
        metadata, sources, defaults = loaded
        if default_view and access_role not in defaults:
            return JSONResponse(status_code=503, content={"signal": "error", "message": "Dashboard snapshot is incomplete."})
        if default_view and access_role in defaults:
            summary_payload = defaults[access_role]["summary"]
        else:
            users, exams, attempts, hierarchy, audit_rows = sources
            validation_error = _validate_management_filter_combinations(hierarchy, filters)
            if validation_error:
                return JSONResponse(status_code=400, content={"signal": "error", "message": validation_error})
            bundle = await asyncio.to_thread(
                _build_management_summary_bundle, users=users,
                active_exams=[exam for exam in exams if not getattr(exam, "is_deleted", False)],
                attempts=attempts, hierarchy=hierarchy, audit_rows=audit_rows,
                now=datetime.fromisoformat(metadata["source_as_of"]), filters=filters, access_role=access_role,
            )
            summary_payload = bundle["summary"]
        return JSONResponse(content={"signal": "success", "generated_at": metadata["generated_at"],
                                     "snapshot": metadata, "cache": {"hit": True, "ttl_seconds": 0},
                                     **summary_payload})
    cache_key = _build_management_summary_cache_key(access_role, filters)
    cached_payload = _get_management_summary_cache_entry(cache_key)
    if cached_payload is not None:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "signal": "success",
                "generated_at": _serialize_exam_datetime(datetime.now(UTC_TZ)),
                "cache": {"hit": True, "ttl_seconds": MANAGEMENT_SUMMARY_CACHE_TTL_SECONDS},
                **cached_payload,
            },
        )

    timer_start = perf_counter()
    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)

    data_load_started = perf_counter()
    users_result, exams, attempts_result, hierarchy = await asyncio.gather(
        employee_model.get_all_users(),
        exam_model.get_all_exams(),
        exam_model.get_all_attempts(),
        employee_model.get_audience_hierarchy(active_only=True),
    )
    users = list(users_result)
    attempts = list(attempts_result)
    data_load_ms = (perf_counter() - data_load_started) * 1000

    validation_error = _validate_management_filter_combinations(hierarchy, filters)
    if validation_error:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "signal": "error",
                "message": validation_error,
            },
        )

    audit_load_started = perf_counter()
    audit_rows = read_audit_events(request.app)
    audit_load_ms = (perf_counter() - audit_load_started) * 1000
    active_exams = [exam for exam in exams if not getattr(exam, "is_deleted", False)]
    bundle_started = perf_counter()
    bundle = _build_management_summary_bundle(
        users=users,
        active_exams=active_exams,
        attempts=attempts,
        hierarchy=hierarchy,
        audit_rows=audit_rows,
        now=datetime.now(UTC_TZ),
        filters=filters,
        access_role=access_role,
    )
    bundle_build_ms = (perf_counter() - bundle_started) * 1000
    summary_payload = bundle["summary"]
    _store_management_summary_cache_entry(cache_key, summary_payload)

    logger.info(
        "Management dashboard summary built role=%s period=%s month=%s region=%s area=%s branch=%s role_filter=%s duration_ms=%.2f data_load_ms=%.2f audit_load_ms=%.2f bundle_build_ms=%.2f users=%s exams=%s attempts=%s cache_hit=false",
        access_role,
        filters.get("period"),
        filters.get("month"),
        filters.get("region"),
        filters.get("area"),
        filters.get("branch_code"),
        filters.get("role"),
        (perf_counter() - timer_start) * 1000,
        data_load_ms,
        audit_load_ms,
        bundle_build_ms,
        len(users),
        len(exams),
        len(attempts),
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": "success",
            "generated_at": _serialize_exam_datetime(datetime.now(UTC_TZ)),
            "cache": {"hit": False, "ttl_seconds": MANAGEMENT_SUMMARY_CACHE_TTL_SECONDS},
            **summary_payload,
        },
    )


def _management_sql_employee_scope(filters: dict):
    """Return employee rows scoped with the same role and geography rules as the legacy builder."""
    conditions = [func.lower(Employee.department).in_(("retail", "employee"))]
    if filters.get("role"):
        conditions.append(func.lower(Employee.department) == filters["role"])
    if filters.get("region"):
        conditions.append(Branch.branch_region == filters["region"])
    if filters.get("area"):
        conditions.append(Branch.branch_area == filters["area"])
    if filters.get("branch_code"):
        conditions.append(Employee.branch_code == filters["branch_code"])
    if filters.get("division"):
        conditions.append(Branch.branch_division == filters["division"])
    if filters.get("sub_department"):
        conditions.append(Branch.branch_sub_department == filters["sub_department"])

    return (
        select(
            Employee.employee_id,
            Employee.email,
            Employee.last_login_at,
            Employee.last_activity_at,
            Employee.employment_status,
        )
        .select_from(Employee)
        .outerjoin(Branch, Employee.branch_code == Branch.branch_code)
        .where(*conditions)
    )


@exam_router.get("/dashboard/management-kpis")
async def get_management_dashboard_kpis(
    request: Request,
    period: str = Query("all", pattern="^(all|week|month|year)$"),
    month: str | None = Query(default=None),
    region: str | None = Query(default=None),
    area: str | None = Query(default=None),
    branch_code: str | None = Query(default=None),
    role: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    """Fast dashboard contract: SQL aggregates only, with no attempt-answer loading."""
    access_role = str(current_user.get("role") or "").strip().lower()
    if access_role not in {"admin", "auditor", "hr", "manager"}:
        return JSONResponse(
            content={"signal": "Not authorized", "message": "Only Admin, HR, and manager users can view the management dashboard."},
            status_code=status.HTTP_403_FORBIDDEN,
        )

    filters = _normalize_management_summary_filters(
        period=period, month=month, region=region, area=area, branch_code=branch_code, role=role
    )
    if os.getenv("TRAINING_DASHBOARD_SNAPSHOT_READS") == "1":
        default_view = _management_default_filters(filters)
        loaded = await _load_management_snapshot(request, include_sources=not default_view)
        if isinstance(loaded, JSONResponse):
            return loaded
        metadata, sources, defaults = loaded
        if default_view and access_role not in defaults:
            return JSONResponse(status_code=503, content={"signal": "error", "message": "Dashboard snapshot is incomplete."})
        if not default_view:
            validation_error = _validate_management_filter_combinations(sources[3], filters)
            if validation_error:
                return JSONResponse(status_code=400, content={"signal": "error", "message": validation_error})
        started = perf_counter()
        now = datetime.fromisoformat(metadata["source_as_of"])
        period_bounds = _get_management_summary_period_bounds(filters, now=now)
        if default_view and access_role in defaults:
            overview = defaults[access_role]["kpi_overview"]
        else:
            overview = await asyncio.to_thread(compute_kpi_overview, sources, filters, now, period_bounds)
        normalized_period = period_bounds[2]
        payload = {"filters": {"period": normalized_period, "month": filters.get("month"),
                               "region": filters.get("region"), "area": filters.get("area"),
                               "branch_code": filters.get("branch_code"), "role": filters.get("role")},
                   "access": {"access_role": access_role,
                              "can_view_employee_attention": access_role in {"admin", "auditor", "hr"},
                              "can_export_attention_lists": access_role in {"admin", "auditor", "hr"}},
                   "overview": overview,
                   "performance": {"query_ms": {}, "total_ms": round((perf_counter() - started) * 1000, 2)}}
        return JSONResponse(content={"signal": "success", "generated_at": metadata["generated_at"],
                                     "snapshot": metadata, "cache": {"hit": True, "ttl_seconds": 0}, **payload})
    cache_key = _build_management_summary_cache_key(access_role, filters)
    cached = _management_kpi_cache.get(cache_key)
    if cached and cached.get("expires_at") > datetime.now(UTC_TZ):
        payload = copy.deepcopy(cached["payload"])
        logger.info("Management dashboard KPI cache_hit=true total_ms=0.00")
        return JSONResponse(content={"signal": "success", "generated_at": _serialize_exam_datetime(datetime.now(UTC_TZ)), "cache": {"hit": True, "ttl_seconds": MANAGEMENT_SUMMARY_CACHE_TTL_SECONDS}, **payload})

    total_started = perf_counter()
    query_timings: dict[str, float] = {}
    now = datetime.now(UTC_TZ)
    period_start, period_end, normalized_period = _get_management_summary_period_bounds(filters, now=now)
    employee_scope = _management_sql_employee_scope(filters).cte("dashboard_employees")
    active_scope = (
        select(employee_scope)
        .where(func.lower(func.coalesce(employee_scope.c.employment_status, "active")) != "resigned")
        .cte("dashboard_active_employees")
    )
    assignment_scope = (
        select(exam_employees.c.exam_id, exam_employees.c.employee_id)
        .select_from(exam_employees)
        .join(Exam, Exam.exam_id == exam_employees.c.exam_id)
        .join(active_scope, active_scope.c.employee_id == exam_employees.c.employee_id)
        .where(or_(Exam.is_deleted.is_(False), Exam.is_deleted.is_(None)))
        .cte("dashboard_assignments")
    )
    attempt_conditions = [ExamAttempt.submitted_at.isnot(None)]
    if period_start is not None:
        attempt_conditions.append(ExamAttempt.submitted_at >= period_start)
    attempt_conditions.append(ExamAttempt.submitted_at <= period_end)
    period_attempts = (
        select(
            ExamAttempt.attempt_id,
            ExamAttempt.employee_id,
            ExamAttempt.exam_id,
            ExamAttempt.total_score,
            ExamAttempt.max_score,
            ExamAttempt.passed,
        )
        .select_from(ExamAttempt)
        .join(
            assignment_scope,
            and_(
                assignment_scope.c.exam_id == ExamAttempt.exam_id,
                assignment_scope.c.employee_id == ExamAttempt.employee_id,
            ),
        )
        .where(*attempt_conditions)
        .cte("dashboard_period_attempts")
    )

    async with request.app.state.db_client() as session:
        query_started = perf_counter()
        population_row = (
            await session.execute(
                select(
                    select(func.count()).select_from(active_scope).scalar_subquery().label("active_employees"),
                    select(func.count()).select_from(employee_scope).where(
                        func.lower(func.coalesce(employee_scope.c.employment_status, "active")) == "resigned"
                    ).scalar_subquery().label("resigned_employees"),
                )
            )
        ).one()
        query_timings["population"] = (perf_counter() - query_started) * 1000

        score_percentage = case(
            (
                and_(period_attempts.c.total_score.isnot(None), period_attempts.c.max_score.isnot(None), period_attempts.c.max_score != 0),
                func.round((period_attempts.c.total_score * 100.0) / period_attempts.c.max_score, 2),
            ),
            else_=None,
        )
        query_started = perf_counter()
        attempt_row = (
            await session.execute(
                select(
                    func.count(period_attempts.c.attempt_id).label("attempt_count"),
                    func.count(func.distinct(period_attempts.c.employee_id)).label("participants"),
                    func.coalesce(func.sum(case((period_attempts.c.passed.is_(True), 1), else_=0)), 0).label("passed_attempts"),
                    func.avg(score_percentage).label("average_score_pct"),
                )
            )
        ).one()
        query_timings["attempt_aggregates"] = (perf_counter() - query_started) * 1000

        assigned_employees = select(func.distinct(assignment_scope.c.employee_id).label("employee_id")).cte("dashboard_assigned_employees")
        query_started = perf_counter()
        no_attempts = await session.scalar(
            select(func.count()).select_from(assigned_employees).where(
                ~exists(
                    select(1).select_from(period_attempts).where(
                        period_attempts.c.employee_id == assigned_employees.c.employee_id
                    )
                )
            )
        )
        query_timings["no_attempts"] = (perf_counter() - query_started) * 1000

        scoped_exams = (
            select(
                Exam.exam_id,
                Exam.exam_status,
                Exam.start_date,
                Exam.end_date,
            )
            .select_from(Exam)
            .join(assignment_scope, assignment_scope.c.exam_id == Exam.exam_id)
            .group_by(Exam.exam_id, Exam.exam_status, Exam.start_date, Exam.end_date)
            .cte("dashboard_scoped_exams")
        )
        is_open_now = and_(
            func.lower(scoped_exams.c.exam_status) != "closed",
            func.lower(scoped_exams.c.exam_status) != "on hold",
            scoped_exams.c.start_date <= now,
            scoped_exams.c.end_date > now,
        )
        query_started = perf_counter()
        exam_row = (
            await session.execute(
                select(
                    func.coalesce(func.sum(case((is_open_now, 1), else_=0)), 0).label("active_open_exams"),
                    func.coalesce(
                        func.sum(
                            case(
                                (and_(func.lower(scoped_exams.c.exam_status) == "open", scoped_exams.c.end_date <= now), 1),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("overdue_open_exams"),
                )
            )
        ).one()
        query_timings["exam_status"] = (perf_counter() - query_started) * 1000

        query_started = perf_counter()
        activity_rows = (await session.execute(select(active_scope.c.email, active_scope.c.last_login_at, active_scope.c.last_activity_at))).all()
        query_timings["activity_population"] = (perf_counter() - query_started) * 1000

    audit_started = perf_counter()
    login_emails: set[str] = set()
    active_system_emails: set[str] = set()
    for row in read_audit_events(request.app):
        if _is_synthetic_dashboard_audit_row(row) or int(row.get("status_code") or 0) >= 400:
            continue
        actor_email = _normalize_email(row.get("actor_email"))
        if not actor_email or actor_email == "anonymous":
            continue
        path = str(row.get("path") or "")
        if path == "/api/v1/users/login":
            login_emails.add(actor_email)
        if path.startswith("/api/") and path not in {"/api/v1/users/login", "/api/v1/users/login/request-otp"}:
            active_system_emails.add(actor_email)
    never_logged_in = sum(
        1 for row in activity_rows if row.last_login_at is None and _normalize_email(row.email) not in login_emails
    )
    never_active = sum(
        1 for row in activity_rows if row.last_activity_at is None and _normalize_email(row.email) not in active_system_emails
    )
    query_timings["audit_activity"] = (perf_counter() - audit_started) * 1000

    active_employees = int(population_row.active_employees or 0)
    attempts_count = int(attempt_row.attempt_count or 0)
    participants = int(attempt_row.participants or 0)
    passed_attempts = int(attempt_row.passed_attempts or 0)
    overview = {
        "active_employees": active_employees,
        "resigned_employees": int(population_row.resigned_employees or 0),
        "users_with_attempts": participants,
        "training_participation_rate": _safe_percentage(participants, active_employees),
        "average_exam_score_pct": round(float(attempt_row.average_score_pct or 0), 2),
        "pass_rate_pct": _safe_percentage(passed_attempts, attempts_count),
        "no_exam_attempts": int(no_attempts or 0),
        "never_logged_in": never_logged_in,
        "never_active": never_active,
        "active_open_exams": int(exam_row.active_open_exams or 0),
        "overdue_open_exams": int(exam_row.overdue_open_exams or 0),
    }
    payload = {
        "filters": {"period": normalized_period, "month": filters.get("month"), "region": filters.get("region"), "area": filters.get("area"), "branch_code": filters.get("branch_code"), "role": filters.get("role")},
        "access": {"access_role": access_role, "can_view_employee_attention": access_role in {"admin", "auditor", "hr"}, "can_export_attention_lists": access_role in {"admin", "auditor", "hr"}},
        "overview": overview,
        "performance": {"query_ms": {key: round(value, 2) for key, value in query_timings.items()}, "total_ms": round((perf_counter() - total_started) * 1000, 2)},
    }
    _management_kpi_cache[cache_key] = {"expires_at": datetime.now(UTC_TZ) + timedelta(seconds=MANAGEMENT_SUMMARY_CACHE_TTL_SECONDS), "payload": copy.deepcopy(payload)}
    logger.info("Management dashboard KPI cache_hit=false total_ms=%.2f query_ms=%s", payload["performance"]["total_ms"], payload["performance"]["query_ms"])
    return JSONResponse(content={"signal": "success", "generated_at": _serialize_exam_datetime(datetime.now(UTC_TZ)), "cache": {"hit": False, "ttl_seconds": MANAGEMENT_SUMMARY_CACHE_TTL_SECONDS}, **payload})


@exam_router.get("/dashboard/management-attention")
async def get_management_dashboard_attention(
    request: Request,
    kind: str = Query(
        ...,
        pattern="^(no_attempts|low_scores|repeated_failures|never_logged_in|never_active)$",
    ),
    period: str = Query("all", pattern="^(all|week|month|year)$"),
    month: str | None = Query(default=None),
    region: str | None = Query(default=None),
    area: str | None = Query(default=None),
    branch_code: str | None = Query(default=None),
    role: str | None = Query(default=None),
    snapshot_id: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    access_role = str(current_user.get("role") or "").strip().lower()
    if access_role not in {"admin", "auditor", "hr"}:
        return JSONResponse(
            content={
                "signal": "Not authorized",
                "message": "Only Admin and HR users can view employee attention lists.",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    filters = _normalize_management_summary_filters(
        period=period,
        month=month,
        region=region,
        area=area,
        branch_code=branch_code,
        role=role,
    )

    if os.getenv("TRAINING_DASHBOARD_SNAPSHOT_READS") == "1":
        loaded = await _load_management_snapshot(request, snapshot_id)
        if isinstance(loaded, JSONResponse):
            return loaded
        metadata, sources, _defaults = loaded
        users, exams, attempts, hierarchy, audit_rows = sources
        validation_error = _validate_management_filter_combinations(hierarchy, filters)
        if validation_error:
            return JSONResponse(status_code=400, content={"signal": "error", "message": validation_error})
        bundle = await asyncio.to_thread(
            _build_management_summary_bundle, users=users,
            active_exams=[exam for exam in exams if not getattr(exam, "is_deleted", False)],
            attempts=attempts, hierarchy=hierarchy, audit_rows=audit_rows,
            now=datetime.fromisoformat(metadata["source_as_of"]), filters=filters, access_role=access_role,
        )
        rows = bundle["attention_lists"].get(kind, [])
        return JSONResponse(content={"signal": "success", "generated_at": metadata["generated_at"],
                                     "snapshot": metadata, "filters": bundle["summary"]["filters"],
                                     "kind": kind, "total_records": len(rows), "rows": rows})

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)

    users = list(await employee_model.get_all_users())
    exams = await exam_model.get_all_exams()
    attempts = list(await exam_model.get_all_attempts())
    hierarchy = await employee_model.get_audience_hierarchy(active_only=True)
    validation_error = _validate_management_filter_combinations(hierarchy, filters)
    if validation_error:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": "error", "message": validation_error},
        )

    audit_rows = read_audit_events(request.app)
    active_exams = [exam for exam in exams if not getattr(exam, "is_deleted", False)]
    bundle = _build_management_summary_bundle(
        users=users,
        active_exams=active_exams,
        attempts=attempts,
        hierarchy=hierarchy,
        audit_rows=audit_rows,
        now=datetime.now(UTC_TZ),
        filters=filters,
        access_role=access_role,
    )
    rows = bundle["attention_lists"].get(kind, [])

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": "success",
            "generated_at": _serialize_exam_datetime(datetime.now(UTC_TZ)),
            "filters": bundle["summary"]["filters"],
            "kind": kind,
            "total_records": len(rows),
            "rows": rows,
        },
    )


@exam_router.get("/dashboard/kpis")
async def get_dashboard_kpis(
    request: Request,
    period: str = Query("all", pattern="^(all|week|month|year)$"),
    exams_joined: int | None = Query(default=None, ge=0),
    current_user: dict = Depends(get_current_user),
):
    role = (current_user.get("role") or "").lower()
    if role not in {"admin", "auditor", "hr", "manager"}:
        return JSONResponse(
            content={
                "signal": "Not authorized",
                "message": "Only Admin, HR, and manager users can view dashboard KPIs.",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)

    users = list(await employee_model.get_all_users())
    exams = await exam_model.get_all_exams()
    attempts = list(await exam_model.get_all_attempts())
    hierarchy = await employee_model.get_audience_hierarchy(active_only=True)
    audit_rows = read_audit_events(request.app)

    now = datetime.now(timezone.utc)
    active_exams = [exam for exam in exams if not getattr(exam, "is_deleted", False)]
    analytics_payload = _build_dashboard_analytics(
        users=users,
        active_exams=active_exams,
        attempts=attempts,
        hierarchy=hierarchy,
        audit_rows=audit_rows,
        tr_tz_now=now,
        scoring_period=period,
        employee_scoring_exams_joined=exams_joined,
    )
    leaderboard_rows, _leaderboard_total, available_exam_counts = await exam_model._get_employee_performance_leaderboard_rows(
        filters={},
        period=period,
        exams_joined=exams_joined,
        sort_by="average_percentage",
        sort_dir="desc",
        page=None,
        page_size=None,
    )
    scoring_payload = _build_dashboard_scoring_from_employee_rows(
        leaderboard_rows,
        available_employee_exam_counts=available_exam_counts,
    )
    analytics_payload = {
        **analytics_payload,
        **scoring_payload,
        "leaderboards": {
            **(analytics_payload.get("leaderboards") or {}),
            **(scoring_payload.get("leaderboards") or {}),
        },
    }

    return JSONResponse(
        content={
            "signal": "success",
            "generated_at": _serialize_exam_datetime(now),
            **analytics_payload,
        },
        status_code=status.HTTP_200_OK,
    )


@exam_router.get("/dashboard/export/no-attempts")
async def export_dashboard_no_attempts(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    role = (current_user.get("role") or "").lower()
    if role not in {"admin", "auditor", "hr", "manager"}:
        return JSONResponse(
            content={
                "signal": "Not authorized",
                "message": "Only Admin, HR, and manager users can export dashboard data.",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)

    users = list(await employee_model.get_all_users())
    exams = await exam_model.get_all_exams()
    attempts = list(await exam_model.get_all_attempts())
    hierarchy = await employee_model.get_audience_hierarchy(active_only=True)
    audit_rows = read_audit_events(request.app)
    active_exams = [exam for exam in exams if not getattr(exam, "is_deleted", False)]
    analytics_payload = _build_dashboard_analytics(
        users=users,
        active_exams=active_exams,
        attempts=attempts,
        hierarchy=hierarchy,
        audit_rows=audit_rows,
        tr_tz_now=datetime.now(timezone.utc),
    )

    rows = analytics_payload.get("exports", {}).get("no_attempt_users", [])
    excel_bytes = _build_dashboard_export_excel(rows, "No Attempt Users")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"no_exam_attempt_users_{timestamp}.xlsx"
    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@exam_router.get("/dashboard/export/no-login")
async def export_dashboard_no_login(
    request: Request,
    mode: str = Query("login", pattern="^(login|activity)$"),
    current_user: dict = Depends(get_current_user),
):
    role = (current_user.get("role") or "").lower()
    if role not in {"admin", "auditor", "hr", "manager"}:
        return JSONResponse(
            content={
                "signal": "Not authorized",
                "message": "Only Admin, HR, and manager users can export dashboard data.",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)

    users = list(await employee_model.get_all_users())
    exams = await exam_model.get_all_exams()
    attempts = list(await exam_model.get_all_attempts())
    hierarchy = await employee_model.get_audience_hierarchy(active_only=True)
    audit_rows = read_audit_events(request.app)
    active_exams = [exam for exam in exams if not getattr(exam, "is_deleted", False)]
    analytics_payload = _build_dashboard_analytics(
        users=users,
        active_exams=active_exams,
        attempts=attempts,
        hierarchy=hierarchy,
        audit_rows=audit_rows,
        tr_tz_now=datetime.now(timezone.utc),
    )

    export_key = "no_login_users" if mode == "login" else "no_activity_users"
    rows = analytics_payload.get("exports", {}).get(export_key, [])
    excel_bytes = _build_dashboard_export_excel(
        rows,
        "No Login Users" if mode == "login" else "No Activity Users",
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = "no_login_users" if mode == "login" else "no_activity_users"
    filename = f"{prefix}_{timestamp}.xlsx"
    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@exam_router.post("/performance")
async def get_employee_performance(
    request: Request,
    payload: EmployeePerformanceListPayload,
    current_user: dict = Depends(get_current_user),
):
    role = (current_user.get("role") or "").lower()
    if role not in {"admin", "auditor", "hr"}:
        return JSONResponse(
            content={
                "signal": "Not authorized",
                "message": "Only Admin and HR users can view employee performance.",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    filters_payload = payload.filters.model_dump()
    employees_payload, total_records = await exam_model.get_employee_performance(
        filters=filters_payload,
        period=payload.period,
        exams_joined=payload.exams_joined,
        page=payload.page,
        page_size=payload.page_size,
        sort_by=payload.sort_by,
        sort_dir=payload.sort_dir,
    )
    employees, available_exam_counts = employees_payload
    serialized_employees: list[dict] = []
    for employee in employees:
        serialized_employees.append(
            {
                **employee,
                "last_submitted_at": _serialize_exam_datetime(employee.get("last_submitted_at")),
            }
        )
    total_pages = math.ceil(total_records / payload.page_size) if payload.page_size else 1

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": "success",
            "page": payload.page,
            "page_size": payload.page_size,
            "total_records": total_records,
            "total_pages": total_pages,
            "available_exam_counts": available_exam_counts,
            "employees": serialized_employees,
        },
    )

@exam_router.get("/performance/me")
async def get_my_performance(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    role = (current_user.get("role") or "").lower()
    if role not in {"admin", "auditor", "hr", "retail", "employee"}:
        return JSONResponse(
            content={
                "signal": "Not authorized",
                "message": "Not authorized to view performance.",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    email = current_user.get("email")
    if not email:
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Missing user email in token",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    exists, employee = await employee_model.is_user_exists_by_email(email)
    if not exists or employee is None:
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Employee record not found",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if not employee.hr_id:
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Employee is missing an HR ID",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    history_rows = await exam_model.get_employee_attempts_history(
        {"hr_ids": [employee.hr_id]}
    )
    serialized_rows: list[dict] = []
    for row in history_rows:
        serialized_rows.append(
            {
                **row,
                "started_at": _serialize_exam_datetime(row.get("started_at")),
                "submitted_at": _serialize_exam_datetime(row.get("submitted_at")),
            }
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": "success",
            "hr_id": employee.hr_id,
            "name": employee.name,
            "performance": serialized_rows,
        },
    )


@exam_router.post("/performance/export")
async def export_employee_performance(
    request: Request,
    payload: EmployeePerformanceExportPayload,
    current_user: dict = Depends(get_current_user),
):
    role = (current_user.get("role") or "").lower()
    if role not in {"admin", "auditor", "hr"}:
        return JSONResponse(
            content={
                "signal": "Not authorized",
                "message": "Only Admin and HR users can export employee performance.",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    history_rows = await exam_model.get_employee_performance_export_rows(
        filters=payload.filters.model_dump(),
        period=payload.period,
        exams_joined=payload.exams_joined,
        sort_by=payload.sort_by,
        sort_dir=payload.sort_dir,
    )

    excel_rows: list[dict] = []
    for row in history_rows:
        excel_rows.append(
            {
                "hr_id": row.get("hr_id"),
                "name": row.get("name"),
                "title": row.get("title"),
                "department": row.get("department"),
                "branch_code": row.get("branch_code"),
                "branch_name": row.get("branch_name"),
                "region": row.get("region"),
                "area": row.get("area"),
                "division": row.get("division"),
                "sub_department": row.get("sub_department"),
                "period": payload.period,
                "exams_joined": row.get("exams_joined"),
                "average_percentage": row.get("average_percentage"),
                "last_submitted_at": _serialize_exam_datetime(row.get("last_submitted_at")),
            }
        )

    excel_bytes = _build_employee_performance_excel(excel_rows)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"employee_performance_{timestamp}.xlsx"
    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@exam_router.get("/performance/{employee_id}/history")
async def get_employee_performance_history(
    request: Request,
    employee_id: str,
    current_user: dict = Depends(get_current_user),
):
    role = (current_user.get("role") or "").lower()
    if role not in {"admin", "auditor", "hr"}:
        return JSONResponse(
            content={
                "signal": "Not authorized",
                "message": "Only Admin and HR users can view employee performance history.",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    history_rows = await exam_model.get_employee_attempts_history_for_employee(employee_id)

    formatted_rows: list[dict] = []
    for row in history_rows:
        total_score = row.get("total_score")
        max_score = row.get("max_score")
        score_percentage = (
            round((float(total_score) / float(max_score)) * 100, 2)
            if total_score is not None and max_score
            else None
        )
        formatted_rows.append(
            {
                **row,
                "score_percentage": score_percentage,
                "started_at": _serialize_exam_datetime(row.get("started_at")),
                "submitted_at": _serialize_exam_datetime(row.get("submitted_at")),
            }
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": "success",
            "employee_id": employee_id,
            "history": formatted_rows,
        },
    )

#! Exam Results Details
@exam_router.get("/{exam_id}/results_details")
async def get_exam_results_details(
    request: Request,
    exam_id: str,
    format: str = Query("json", regex="^(json|excel)$"),
    current_user: dict = Depends(get_current_user),
):
    role = (current_user.get("role") or "").lower()
    if role not in {"admin", "auditor", "hr"}:
        return JSONResponse(
            content={
                "signal": "Not authorized",
                "message": "Only Admin and HR users can view exam analytics."
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    exam = await exam_model.get_exam_with_details(exam_id)

    if exam is None or exam.is_deleted:
        return JSONResponse(
            content={
                "signal": "Exam not found."
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    results_summary = await exam_model.get_exam_results_summary(exam_id)
    results_details = await exam_model.get_exam_results_details(exam_id)
    participant_attempts = await exam_model.get_exam_participant_attempts(exam_id)

    prepared_payload = _prepare_exam_results_payload(
        exam,
        results_summary,
        results_details,
        participant_attempts=participant_attempts,
    )

    if format == "excel":
        excel_bytes = _build_excel_workbook(
            exam_snapshot=prepared_payload["exam_snapshot"],
            summary_payload=prepared_payload["summary_payload"],
            breakdowns=prepared_payload["breakdowns"],
            results_details=prepared_payload["results_details"],
        )
        filename = f"exam_{prepared_payload['exam_snapshot']['exam_id']}_analytics.xlsx"
        return StreamingResponse(
            BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store, max-age=0",
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": ResponseSignalEnum.EXAM_RETREIVED_SUCCESS.value,
            "exam": prepared_payload["exam_snapshot"],
            "results_summary": prepared_payload["summary_payload"],
            "results_details": prepared_payload["results_details"],
            "participants_overview": prepared_payload["participants_overview"],
            "breakdowns": prepared_payload["breakdowns"],
        },
    )

@exam_router.get("/question-bank")
async def get_question_bank(
    request: Request,
    query: str | None = Query(default=None),
    question_type: str | None = Query(default=None),
    favorites_only: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
):
    _ = current_user
    question_model = await QuestionModel.create_instance(db_client=request.app.state.db_client)
    question_bank_items = await question_model.list_question_bank_items(
        query=query,
        question_type=question_type,
        favorites_only=favorites_only,
    )

    async with request.app.state.db_client() as session:
        membership_rows = (await session.execute(
            select(QuestionBankGroupMember.bank_question_id, QuestionBankGroup.group_id, QuestionBankGroup.name)
            .join(QuestionBankGroup, QuestionBankGroup.group_id == QuestionBankGroupMember.group_id)
        )).all()
    membership = {bank_id: (group_id, name) for bank_id, group_id, name in membership_rows}
    items = []
    for item in question_bank_items:
        serialized = _serialize_question_bank_item(item)
        group = membership.get(item.bank_question_id)
        serialized["group_id"] = group[0] if group else None
        serialized["question_group"] = group[1] if group else "General Bank"
        items.append(serialized)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": "Question bank retrieved successfully",
            "items": items,
        },
    )


@exam_router.post("/question-bank")
async def create_question_bank_item(
    request: Request,
    payload: QuestionBankCreatePayload,
    current_user: dict = Depends(get_current_user),
):
    question_model = await QuestionModel.create_instance(db_client=request.app.state.db_client)
    prepared_questions, question_validation_error = _prepare_questions_for_persistence([payload])
    if question_validation_error is not None:
        return JSONResponse(
            content={"signal": question_validation_error},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    prepared_question = prepared_questions[0]
    existing_item = await question_model.find_matching_question_bank_item(prepared_question)
    if existing_item is not None:
        if payload.is_favorite and not existing_item.is_favorite:
            updated_item = await question_model.update_question_bank_item(
                existing_item.bank_question_id,
                {
                    "is_favorite": True,
                    "updated_by": current_user.get("email"),
                },
            )
            existing_item = updated_item or existing_item

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "signal": "Question already exists in bank",
                "created": False,
                "item": _serialize_question_bank_item(existing_item),
            },
        )

    question_bank_item = QuestionBankItem(
        question_text=prepared_question["question_text"],
        question_type=prepared_question["question_type"],
        points=prepared_question["points"],
        question_group=prepared_question["question_group"],
        is_favorite=bool(payload.is_favorite),
        created_by=current_user.get("email"),
        updated_by=current_user.get("email"),
    )
    if prepared_question["choices"] is not None:
        question_bank_item.choices = [
            QuestionBankChoice(
                choice_text=choice["choice_text"],
                is_correct=choice["is_correct"],
                choice_order=choice["choice_order"],
            )
            for choice in prepared_question["choices"]
        ]

    created_item = await question_model.create_question_bank_item(question_bank_item)
    await assign_question_group(request.app.state.db_client, created_item.bank_question_id, prepared_question["question_group"])
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "signal": "Question saved to bank successfully",
            "created": True,
            "item": _serialize_question_bank_item(created_item),
        },
    )


@exam_router.put("/question-bank/{bank_question_id}")
async def update_question_bank_item(
    request: Request,
    bank_question_id: str,
    payload: QuestionBankUpdatePayload,
    current_user: dict = Depends(get_current_user),
):
    question_model = await QuestionModel.create_instance(db_client=request.app.state.db_client)
    existing_item = await question_model.get_question_bank_item_by_id(bank_question_id)
    if existing_item is None:
        return JSONResponse(
            content={"signal": "Question bank item not found."},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    prepared_questions, question_validation_error = _prepare_questions_for_persistence([payload])
    if question_validation_error is not None:
        return JSONResponse(
            content={"signal": question_validation_error},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    prepared_question = prepared_questions[0]
    updated_item = await question_model.update_question_bank_item(
        bank_question_id,
        {
            **prepared_question,
            "is_favorite": bool(payload.is_favorite),
            "updated_by": current_user.get("email"),
        },
    )

    if updated_item is None:
        return JSONResponse(
            content={"signal": "Question bank item not found."},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    await assign_question_group(request.app.state.db_client, bank_question_id, prepared_question["question_group"])
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": "Question bank item updated successfully",
            "item": _serialize_question_bank_item(updated_item),
        },
    )


@exam_router.delete("/question-bank/{bank_question_id}")
async def delete_question_bank_item(
    request: Request,
    bank_question_id: str,
    current_user: dict = Depends(get_current_user),
):
    _ = current_user
    question_model = await QuestionModel.create_instance(db_client=request.app.state.db_client)
    deleted = await question_model.soft_delete_question_bank_item(bank_question_id)
    if not deleted:
        return JSONResponse(
            content={"signal": "Question bank item not found."},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"signal": "Question removed from bank successfully"},
    )

#! Get Exam by ID
@exam_router.get("/{exam_id}")
async def get_exam_by_id(
    request: Request,
    exam_id: str,
    current_user: dict = Depends(get_current_user),
):

    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    exam = await exam_model.get_exam_with_details(exam_id)

    if exam is None:
        return JSONResponse(
            content={
                "signal": "Exam not found."
            },
            status_code=status.HTTP_404_NOT_FOUND,
    )
    audience_summary = _build_audience_summary(exam)
    audience_config = _build_audience_config(exam)
    resolved_status = _resolve_exam_status(exam)
    attempts_used = None
    attempts_left = None
    session_state = None
    role = (current_user.get("role") or "").lower()
    if role in {"retail", "employee"}:
        employee_id = current_user.get("sub")
        if employee_id:
            active_attempt = await exam_model.get_active_attempt_for_employee_exam(exam.exam_id, employee_id)
            now = datetime.now(timezone.utc)
            if active_attempt is not None:
                active_attempt, session_state = await _finalize_expired_attempt(
                    exam_model=exam_model,
                    exam=exam,
                    attempt=active_attempt,
                    now=now,
                )
            attempts_used = await exam_model.get_number_of_attempts_for_employee_exam(
                exam.exam_id,
                employee_id,
            )
            max_attempts = exam.number_of_attempts_allowed or 1
            attempts_left = max(0, max_attempts - attempts_used)
            if active_attempt is not None and session_state is None:
                session_state = _build_exam_session_payload(
                    exam=exam,
                    attempt=active_attempt,
                    attempts_used=attempts_used,
                    attempts_left=attempts_left,
                    now=now,
                    status_value="in_progress",
                    message="Exam session restored. Continue where you left off.",
                )
            elif session_state is not None:
                session_state["attempts_used"] = attempts_used
                session_state["attempts_left"] = attempts_left
    exam_details = {
            "exam_id": exam.exam_id,
            "title": exam.title,
            "description": exam.description,
            "exam_status": resolved_status,
            "exam_level": _resolve_exam_level(exam),
            "duration_minutes": exam.duration_minutes,
            "passing_percent": exam.passing_percent,
            "number_of_attempts_allowed": exam.number_of_attempts_allowed,
            "attempts_used": attempts_used,
            "attempts_left": attempts_left,
            "start_date": _serialize_exam_datetime(exam.start_date),
            "end_date": _serialize_exam_datetime(exam.end_date),
            "is_deleted": exam.is_deleted,
            "materials": [
                {
                    "material_id": material.material_id,
                    "material_name": material.material_name,
                    "material_group": material.material_group,
                    "material_training_type": material.material_training_type,
                    "is_deleted": material.is_deleted,
                }
                    for material in exam.materials
            ] if hasattr(exam, "materials") else [],
            "questions": [
                {
                    "question_id": q.question_id,
                    "question_text": q.question_text,
                    "question_type": q.question_type,
                    "question_group": q.question_group,
                    "points": q.points,
                    "choices": [
                        {
                            "choice_id": c.choice_id,
                            "choice_text": c.choice_text,
                            "is_correct": c.is_correct,
                            "choice_order": c.choice_order
                        }
                        for c in q.choices
                    ] if hasattr(q, "choices") else []
                }
                for q in exam.questions
            ] if hasattr(exam, "questions") else [],
            "audience": audience_config,
            "audience_summary": audience_summary,
            "session_state": session_state,
        }
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": ResponseSignalEnum.EXAM_RETREIVED_SUCCESS.value,
            "exam": exam_details
        },
    )

#! Start Exam Attempt
@exam_router.post("/{exam_id}/start")
async def start_exam_attempt(
    request: Request,
    exam_id: str,
    current_user: dict = Depends(get_current_user),
):
    role = (current_user.get("role") or "").lower()
    if role not in {"retail", "employee"}:
        return JSONResponse(
            content={"signal": "Not authorized", "message": "Only employee accounts can start exams."},
            status_code=status.HTTP_403_FORBIDDEN,
        )

    employee_id = current_user.get("sub")
    email = current_user.get("email")
    if not employee_id or not email:
        return JSONResponse(
            content={"signal": "error", "message": "Missing user identity in token."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)

    exam = await exam_model.get_exam_with_details(exam_id)
    if exam is None or exam.is_deleted:
        return JSONResponse(
            content={"signal": "error", "message": "Exam not found."},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    exists, employee = await employee_model.is_user_exists_by_email(email)
    if not exists or employee is None:
        return JSONResponse(
            content={"signal": "error", "message": "Employee record not found."},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    assigned_employee_ids = {emp.employee_id for emp in getattr(exam, "employees", [])}
    if employee.employee_id not in assigned_employee_ids:
        return JSONResponse(
            content={"signal": "error", "message": "You are not assigned to this exam."},
            status_code=status.HTTP_403_FORBIDDEN,
        )

    now = datetime.now(timezone.utc)
    exam_start = _normalize_exam_datetime(exam.start_date)
    resolved_status = _resolve_exam_status(exam, now).strip()

    if exam_start and now < exam_start:
        return JSONResponse(
            content={"signal": "error", "message": "Exam has not started yet."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if _is_exam_window_closed(exam, now):
        return JSONResponse(
            content={"signal": "error", "message": "Exam window has closed."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if resolved_status.lower() != "open":
        return JSONResponse(
            content={"signal": "error", "message": "Exam is not open for attempts."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not exam.questions:
        return JSONResponse(
            content={"signal": "error", "message": "Exam does not contain questions."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    active_attempt = await exam_model.get_active_attempt_for_employee_exam(exam.exam_id, employee.employee_id)
    max_attempts = exam.number_of_attempts_allowed or 1
    if active_attempt is not None:
        active_attempt, _ = await _finalize_expired_attempt(
            exam_model=exam_model,
            exam=exam,
            attempt=active_attempt,
            now=now,
        )
        if active_attempt is not None:
            attempts_used = await exam_model.get_number_of_attempts_for_employee_exam(
                exam.exam_id,
                employee.employee_id,
            )
            attempts_left = max(0, max_attempts - attempts_used)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "signal": "Exam attempt restored",
                    "session": _build_exam_session_payload(
                        exam=exam,
                        attempt=active_attempt,
                        attempts_used=attempts_used,
                        attempts_left=attempts_left,
                        now=now,
                        status_value="in_progress",
                        message="Exam session restored. Continue where you left off.",
                    ),
                },
            )

    attempts_used = await exam_model.get_number_of_attempts_for_employee_exam(
        exam.exam_id,
        employee.employee_id,
    )
    if attempts_used >= max_attempts:
        return JSONResponse(
            content={
                "signal": "error",
                "message": "You have used all attempts for this exam.",
                "attempts_used": attempts_used,
                "attempts_left": 0,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    attempt = None
    for _ in range(3):
        next_attempt_number = await exam_model.get_next_attempt_number(
            exam.exam_id,
            employee.employee_id,
        )
        if next_attempt_number > max_attempts:
            attempts_used = await exam_model.get_number_of_attempts_for_employee_exam(
                exam.exam_id,
                employee.employee_id,
            )
            attempts_left = max(0, max_attempts - attempts_used)
            return JSONResponse(
                content={
                    "signal": "error",
                    "message": "You have used all attempts for this exam.",
                    "attempts_used": attempts_used,
                    "attempts_left": attempts_left,
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            attempt = await exam_model.create_exam_attempt(
                exam_id=exam.exam_id,
                employee_id=employee.employee_id,
                attempt_number=next_attempt_number,
            )
            break
        except IntegrityError:
            active_attempt = await exam_model.get_active_attempt_for_employee_exam(
                exam.exam_id,
                employee.employee_id,
            )
            if active_attempt is not None:
                attempts_used = await exam_model.get_number_of_attempts_for_employee_exam(
                    exam.exam_id,
                    employee.employee_id,
                )
                attempts_left = max(0, max_attempts - attempts_used)
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        "signal": "Exam attempt restored",
                        "session": _build_exam_session_payload(
                            exam=exam,
                            attempt=active_attempt,
                            attempts_used=attempts_used,
                            attempts_left=attempts_left,
                            now=now,
                            status_value="in_progress",
                            message="Exam session restored. Continue where you left off.",
                        ),
                    },
                )

    if attempt is None:
        return JSONResponse(
            content={"signal": "error", "message": "Unable to start the exam right now. Please try again."},
            status_code=status.HTTP_409_CONFLICT,
        )

    attempts_used = await exam_model.get_number_of_attempts_for_employee_exam(
        exam.exam_id,
        employee.employee_id,
    )
    attempts_left = max(0, max_attempts - attempts_used)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "signal": "Exam attempt started",
            "session": _build_exam_session_payload(
                exam=exam,
                attempt=attempt,
                attempts_used=attempts_used,
                attempts_left=attempts_left,
                now=now,
                status_value="in_progress",
                message="Exam started successfully.",
            ),
        },
    )

#! Submit Exam Answers
@exam_router.post("/{exam_id}/submit")
async def submit_exam_answers(
    request: Request,
    exam_id: str,
    payload: ExamSubmitPayload,
    current_user: dict = Depends(get_current_user),
):
    # payload=
    # {
    #     "answers": [
    #         {"question_id": "q1", "choice_id": "c2"},
    #         {"question_id": "q2", "choice_id": null},
    #         ...
    #     ]
    # }

    role = (current_user.get("role") or "").lower()
    if role not in {"retail", "employee"}:
        return JSONResponse(
            content={"signal": "Not authorized", "message": "Only employee accounts can submit exams."},
            status_code=status.HTTP_403_FORBIDDEN,
        )

    employee_id = current_user.get("sub")
    email = current_user.get("email")
    if not employee_id or not email:
        return JSONResponse(
            content={"signal": "error", "message": "Missing user identity in token."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)

    exam = await exam_model.get_exam_with_details(exam_id)
    if exam is None or exam.is_deleted:
        return JSONResponse(
            content={"signal": "error", "message": "Exam not found."},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    exists, employee = await employee_model.is_user_exists_by_email(email)
    if not exists or employee is None:
        return JSONResponse(
            content={"signal": "error", "message": "Employee record not found."},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    assigned_employee_ids = {emp.employee_id for emp in getattr(exam, "employees", [])}
    if employee.employee_id not in assigned_employee_ids:
        return JSONResponse(
            content={"signal": "error", "message": "You are not assigned to this exam."},
            status_code=status.HTTP_403_FORBIDDEN,
        )

    now = datetime.now(timezone.utc)
    exam_start = _normalize_exam_datetime(exam.start_date)
    exam_end = _normalize_exam_datetime(exam.end_date)
    stored_status = (exam.exam_status or "").strip()
    resolved_status = _resolve_exam_status(exam, now).strip()
    if stored_status and stored_status.lower() != resolved_status.lower():
        logger.warning(
            "Exam %s status mismatch (stored=%s resolved=%s start=%s end=%s now=%s)",
            exam.exam_id,
            stored_status,
            resolved_status,
            exam_start,
            exam_end,
            now,
        )

    if exam_start and now < exam_start:
        return JSONResponse(
            content={"signal": "error", "message": "Exam has not started yet."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if _is_exam_window_closed(exam, now):
        return JSONResponse(
            content={"signal": "error", "message": "Exam window has closed."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if resolved_status.lower() != "open":
        return JSONResponse(
            content={"signal": "error", "message": "Exam is not open for submission."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not exam.questions:
        return JSONResponse(
            content={"signal": "error", "message": "Exam does not contain questions."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )


    # {
    #     "answers": [
    #         {"question_id": "q1", "choice_id": "c2"},
    #         {"question_id": "q2", "choice_id": null},
    #         ...
    #     ]
    # }
    answers_map: dict[str, list[str] | None] = {}
    for answer in payload.answers:
        if answer.choice_ids is not None:
            normalized = [choice_id for choice_id in answer.choice_ids if choice_id]
            answers_map[answer.question_id] = normalized or None
        else:
            answers_map[answer.question_id] = [answer.choice_id] if answer.choice_id else None

    active_attempt = await exam_model.get_active_attempt_for_employee_exam(exam.exam_id, employee.employee_id)
    if active_attempt is None:
        return JSONResponse(
            content={"signal": "error", "message": "No active exam session was found. Please start the exam again."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    attempt_expires_at = _calculate_attempt_expiry(exam, active_attempt.started_at)
    if attempt_expires_at is not None and now >= attempt_expires_at:
        await exam_model.close_attempt_as_timed_out(
            active_attempt.attempt_id,
            max_score=_calculate_exam_max_score(exam),
            submitted_at=attempt_expires_at,
        )
        attempts_used = await exam_model.get_number_of_attempts_for_employee_exam(
            exam.exam_id,
            employee.employee_id,
        )
        max_attempts = exam.number_of_attempts_allowed or 1
        attempts_left = max(0, max_attempts - attempts_used)
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Time is up. This exam session has expired.",
                "attempts_used": attempts_used,
                "attempts_left": attempts_left,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        submission_result = await exam_model.submit_exam_attempt(
            attempt_id=active_attempt.attempt_id,
            exam=exam,
            answers_map=answers_map,
            passing_percent=exam.passing_percent or 60.0,
            submitted_at=now,
        )
    except ValueError as exc:
        return JSONResponse(
            content={"signal": "error", "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    attempts_used = await exam_model.get_number_of_attempts_for_employee_exam(
        exam.exam_id,
        employee.employee_id,
    )
    max_attempts = exam.number_of_attempts_allowed or 1
    attempts_left = max(0, max_attempts - attempts_used)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": "Exam submitted successfully",
            "result": {
                **submission_result,
                "attempts_used": attempts_used,
                "attempts_left": attempts_left,
            },
        },
    )


#! Update Exam by ID
@exam_router.put("/{exam_id}")
async def update_exam(
    request: Request,
    exam_id: str,
    payload: ExamUpdatePayload,
    current_user: dict = Depends(get_current_user),
):
    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    material_model = await MaterialModel.create_instance(db_client=request.app.state.db_client)
    question_model = await QuestionModel.create_instance(db_client=request.app.state.db_client)
    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)

    logger.debug("Update exam request received for exam_id=%s", exam_id)
    # Check if exam exists
    existing_exam = await exam_model.get_exam_by_id(exam_id)
    logger.debug("Existing exam lookup completed for exam_id=%s found=%s", exam_id, existing_exam is not None)
    if existing_exam is None or existing_exam.is_deleted:
        return JSONResponse(
            content={"signal": "Exam not found or has been deleted."},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    existing_exam_with_details = await exam_model.get_exam_with_details(exam_id)
    existing_assigned_hr_ids = {
        str(getattr(employee, "hr_id", "")).strip()
        for employee in getattr(existing_exam_with_details, "employees", []) or []
        if str(getattr(employee, "hr_id", "")).strip()
    }

    # Validate materials
    for material_id in payload.material_ids:
        material = await material_model.get_material_by_id(material_id)
        if material is None or material.is_deleted:
            return JSONResponse(
                content={"signal": "One or more materials not found or have been deleted."},
                status_code=status.HTTP_404_NOT_FOUND,
            )

    # Validate status
    valid_statuses = ["Open", "Closed", "On Hold"]
    if payload.exam_status not in valid_statuses:
        return JSONResponse(
            content={"signal": f"Invalid status. Must be one of {valid_statuses}"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Validate duration
    if payload.duration_minutes <= 5:
        return JSONResponse(
            content={"signal": "duration_minutes must be greater than 5 minutes."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if payload.passing_percent < 0 or payload.passing_percent > 100:
        return JSONResponse(
            content={"signal": "passing_percent must be between 0 and 100."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if payload.number_of_attempts_allowed is not None and payload.number_of_attempts_allowed < 1:
        return JSONResponse(
            content={"signal": "number_of_attempts_allowed must be at least 1."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    audience_mode, audience_filters_json, audience_manual_ids_json = _serialize_audience_payload(payload.audience)
    prepared_questions, question_validation_error = _prepare_questions_for_persistence(payload.questions)
    if question_validation_error is not None:
        return JSONResponse(
            content={"signal": question_validation_error},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Update exam basic info
    start_date_utc = _coerce_payload_datetime(payload.start_date)
    end_date_utc = _coerce_payload_datetime(payload.end_date)

    is_duration_valid, available_minutes = _validate_duration_against_window(
        payload.duration_minutes,
        start_date_utc,
        end_date_utc,
    )
    if not is_duration_valid:
        return JSONResponse(
            content={
                "signal": "duration_minutes exceeds exam window",
                "message": (
                    "Exam duration must fit between start and end times. "
                    f"Window allows {max(0, int(available_minutes))} minutes."
                ),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    questions_will_change = _exam_questions_changed(
        getattr(existing_exam_with_details, "questions", []) or [],
        prepared_questions,
    )
    if questions_will_change:
        attempts_count = await exam_model.get_number_of_attempts_for_exam(exam_id)
        if attempts_count > 0:
            return JSONResponse(
                content={
                    "signal": (
                        "This exam already has existing attempts, so its questions can no longer be changed. "
                        "You can still update the title, status, dates, audience, and materials without changing the questions."
                    )
                },
                status_code=status.HTTP_409_CONFLICT,
            )

    update_mode = (getattr(payload, "audience_update_mode", None) or "replace").lower()

    target_hr_ids = await _resolve_audience_hr_ids(employee_model, payload.audience)
    resolved_hr_ids = sorted({str(value) for value in target_hr_ids if value})

    if update_mode == "append":
        combined_hr_ids = sorted({*existing_assigned_hr_ids, *resolved_hr_ids})
        resolved_hr_ids = combined_hr_ids

        # Persist the effective audience in a representable way.
        # Appending two different audience definitions cannot always be expressed as filters,
        # so we store the resulting set as a manual audience (unless the new mode is `all`).
        if payload.audience.mode == "all":
            audience_mode, audience_filters_json, audience_manual_ids_json = _serialize_audience_payload(payload.audience)
        else:
            audience_mode = "manual"
            audience_filters_json = json.dumps({})
            audience_manual_ids_json = json.dumps(combined_hr_ids)

    await exam_model.update_exam(
        exam_id,
        {
            "title": payload.title,
            "description": payload.description,
            "exam_status": payload.exam_status,
            "exam_level": payload.exam_level,
            "duration_minutes": payload.duration_minutes,
            "passing_percent": payload.passing_percent,
            "number_of_attempts_allowed": payload.number_of_attempts_allowed,
            "start_date": start_date_utc,
            "end_date": end_date_utc,
            "audience_mode": audience_mode,
            "audience_filters": audience_filters_json,
            "audience_manual_hr_ids": audience_manual_ids_json,
        },
    )

    await exam_model.associate_exam_employees_by_hr_ids(exam_id, resolved_hr_ids)


    created_question_ids: List[str] = []
    if questions_will_change:
        await question_model.delete_questions_by_exam_id_harddelete(exam_id)

        for prepared_question in prepared_questions:
            question_instance = Question(
                exam_id=exam_id,
                question_text=prepared_question["question_text"],
                question_type=prepared_question["question_type"],
                points=prepared_question["points"],
                question_group=prepared_question["question_group"],
            )
            if prepared_question["choices"] is not None:
                question_instance.choices = [
                    QuestionChoice(
                        choice_text=choice["choice_text"],
                        is_correct=choice["is_correct"],
                        choice_order=choice["choice_order"],
                    )
                    for choice in prepared_question["choices"]
                ]

            created_question = await question_model.create_question(question_instance)
            created_question_ids.append(created_question.question_id)
    else:
        created_question_ids = [
            question.question_id
            for question in getattr(existing_exam_with_details, "questions", []) or []
            if getattr(question, "question_id", None)
        ]

    # Update material associations
    # Remove old associations
    await exam_model.delete_materials_from_exam(exam_id)
    
    # Add new associations
    if payload.material_ids:
        await exam_model.associate_materials_to_exam(exam_id, payload.material_ids)

    assigned_audience_count = len({str(hr_id).strip() for hr_id in resolved_hr_ids if str(hr_id).strip()})

    return JSONResponse(
        content={
            "signal": "Exam updated successfully",
            "exam_id": exam_id,
            "question_ids": created_question_ids,
            "assigned_audience_count": assigned_audience_count,
            "notification_recipients_queued": 0,
        },
        status_code=status.HTTP_200_OK,
    )


@exam_router.put("/{exam_id}/level")
async def update_exam_level(
    request: Request,
    exam_id: str,
    payload: ExamLevelUpdatePayload,
    current_user: dict = Depends(get_current_user),
):
    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    exam = await exam_model.get_exam_by_id(exam_id)

    if exam is None or exam.is_deleted:
        return JSONResponse(
            content={"signal": "Exam not found or has been deleted."},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    updated_exam = await exam_model.update_exam(exam_id, {"exam_level": payload.exam_level})
    if updated_exam is None:
        return JSONResponse(
            content={"signal": "Exam not found or has been deleted."},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return JSONResponse(
        content={
            "signal": "Exam level updated successfully",
            "exam_id": exam_id,
            "exam_level": _resolve_exam_level(updated_exam),
        },
        status_code=status.HTTP_200_OK,
    )


@exam_router.post("/{exam_id}/send-mail")
async def send_exam_mail(
    request: Request,
    exam_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    exam = await exam_model.get_exam_with_details(exam_id)

    if exam is None or exam.is_deleted:
        return JSONResponse(
            content={"signal": "Exam not found or has been deleted."},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    recipients = _build_exam_notification_recipients(list(getattr(exam, "employees", []) or []))
    if not recipients:
        return JSONResponse(
            content={
                "signal": "No audience members with valid email addresses were found for this exam.",
                "exam_id": exam_id,
                "notification_recipients_queued": 0,
            },
            status_code=status.HTTP_200_OK,
        )

    exam_snapshot = _build_exam_notification_snapshot(exam, created_by=current_user.get("email"))
    exam_links = _build_exam_notification_links(request, exam_id)
    background_tasks.add_task(
        _send_exam_assignment_notifications,
        exam_snapshot,
        recipients,
        exam_links,
    )

    return JSONResponse(
        content={
            "signal": f"Exam notification email queued for {len(recipients)} audience member(s).",
            "exam_id": exam_id,
            "notification_recipients_queued": len(recipients),
        },
        status_code=status.HTTP_200_OK,
    )


@exam_router.post("/{exam_id}/regenerate")
async def regenerate_exam(
    request: Request,
    exam_id: str,
    current_user: dict = Depends(get_current_user),
):
    role = (current_user.get("role") or "").lower()
    if role not in {"admin", "auditor", "hr"}:
        return JSONResponse(
            content={
                "signal": "Not authorized",
                "message": "Only Admin and HR users can regenerate exams.",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    question_model = await QuestionModel.create_instance(db_client=request.app.state.db_client)
    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)

    source_exam = await exam_model.get_exam_with_details(exam_id)
    if source_exam is None or source_exam.is_deleted:
        return JSONResponse(
            content={"signal": "Exam not found or has been deleted."},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    source_questions = sorted(
        list(getattr(source_exam, "questions", []) or []),
        key=lambda question: (
            getattr(question, "created_at", None) or datetime.min.replace(tzinfo=UTC_TZ),
            str(getattr(question, "question_id", "") or ""),
        ),
    )
    if not source_questions:
        return JSONResponse(
            content={"signal": "This exam has no questions to regenerate."},
            status_code=status.HTTP_409_CONFLICT,
        )

    source_audience = AudiencePayload.model_validate(_build_audience_config(source_exam))
    target_hr_ids = await _resolve_audience_hr_ids(employee_model, source_audience)
    audience_mode, audience_filters_json, audience_manual_ids_json = _serialize_audience_payload(source_audience)

    regenerated_exam = await exam_model.create_exam(
        Exam(
            title=_build_regenerated_exam_title(getattr(source_exam, "title", None)),
            description=getattr(source_exam, "description", "") or "",
            exam_status=getattr(source_exam, "exam_status", None) or "Open",
            exam_level=_resolve_exam_level(source_exam),
            duration_minutes=int(getattr(source_exam, "duration_minutes", 0) or 0),
            passing_percent=float(getattr(source_exam, "passing_percent", 60.0) or 60.0),
            number_of_attempts_allowed=int(getattr(source_exam, "number_of_attempts_allowed", 1) or 1),
            start_date=_normalize_exam_datetime(getattr(source_exam, "start_date", None)),
            end_date=_normalize_exam_datetime(getattr(source_exam, "end_date", None)),
            audience_mode=audience_mode,
            audience_filters=audience_filters_json,
            audience_manual_hr_ids=audience_manual_ids_json,
        )
    )

    await exam_model.associate_exam_employees_by_hr_ids(regenerated_exam.exam_id, target_hr_ids)

    active_material_ids = [
        material.material_id
        for material in list(getattr(source_exam, "materials", []) or [])
        if getattr(material, "material_id", None) and not getattr(material, "is_deleted", False)
    ]
    if active_material_ids:
        await exam_model.associate_materials_to_exam(regenerated_exam.exam_id, active_material_ids)

    created_question_ids: list[str] = []
    for source_question in source_questions:
        cloned_question = Question(
            exam_id=regenerated_exam.exam_id,
            question_text=getattr(source_question, "question_text", "") or "",
            question_type=getattr(source_question, "question_type", "") or "",
            points=int(getattr(source_question, "points", 1) or 1),
            question_group=(getattr(source_question, "question_group", None) or None),
        )

        source_choices = sorted(
            list(getattr(source_question, "choices", []) or []),
            key=lambda choice: (
                getattr(choice, "choice_order", None)
                if getattr(choice, "choice_order", None) is not None
                else 9999,
                str(getattr(choice, "choice_id", "") or ""),
            ),
        )
        if source_choices:
            cloned_question.choices = [
                QuestionChoice(
                    choice_text=getattr(choice, "choice_text", "") or "",
                    is_correct=bool(getattr(choice, "is_correct", False)),
                    choice_order=getattr(choice, "choice_order", None),
                )
                for choice in source_choices
            ]

        created_question = await question_model.create_question(cloned_question)
        created_question_ids.append(created_question.question_id)

    skipped_material_count = max(
        len(list(getattr(source_exam, "materials", []) or [])) - len(active_material_ids),
        0,
    )
    assigned_audience_count = len({str(hr_id).strip() for hr_id in target_hr_ids if str(hr_id).strip()})

    return JSONResponse(
        content={
            "signal": "Exam regenerated successfully",
            "exam_id": regenerated_exam.exam_id,
            "exam_title": regenerated_exam.title,
            "question_ids": created_question_ids,
            "assigned_audience_count": assigned_audience_count,
            "skipped_material_count": skipped_material_count,
            "notification_recipients_queued": 0,
        },
        status_code=status.HTTP_201_CREATED,
    )




#! Soft Delete Exam by ID
@exam_router.delete("/softdelete/{exam_id}")
async def delete_exam_by_id_softdelete(request: Request, exam_id: str):

    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    is_deleted = await exam_model.delete_exam_by_id_softdelete(exam_id)
    
    if not is_deleted:
        return JSONResponse(
            content={
                "signal": "Exam not found or already deleted."
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return JSONResponse(
        content={
            "signal": ResponseSignalEnum.EXAM_DELETED_SUCCESS.value,
        },
        status_code=status.HTTP_200_OK,
    )

#! Hard Delete Exam by ID
@exam_router.delete("/harddelete/{exam_id}")
async def delete_exam_by_id_harddelete(request: Request, exam_id: str):

    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    is_deleted = await exam_model.delete_exam_by_id_harddelete(exam_id)
    
    if not is_deleted:
        return JSONResponse(
            content={
                "signal": "Exam not found or already deleted."
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return JSONResponse(
        content={
            "signal": ResponseSignalEnum.EXAM_DELETED_SUCCESS.value,
        },
        status_code=status.HTTP_200_OK,
    )


#! Delete ALL Exams
@exam_router.delete("/delete_all")
async def delete_all_exams(request: Request):
    
    exam_model = await ExamModel.create_instance(db_client=request.app.state.db_client)
    exams = await exam_model.get_all_exams()
    for exam in exams:
        await exam_model.delete_exam_by_id(exam.exam_id)


    return JSONResponse(
        content={
            "signal": ResponseSignalEnum.ALL_EXAMS_DELETED_SUCCESS.value,
            "number_exams_deleted": len(exams)
        },
        status_code=status.HTTP_200_OK,
    )
