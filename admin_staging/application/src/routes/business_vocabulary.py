import base64
import binascii
import json
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from models.db_schemas import VocabularyCategory, VocabularyItem
from routes.users.auth_utils import get_current_user
from utils.audit_trail import append_audit_event, build_audit_event


router = APIRouter(prefix="/api/v1/business-vocabulary", tags=["Business Vocabulary"])
logger = logging.getLogger(__name__)

ADMIN_ROLES = {"admin", "auditor", "hr"}

# Keeping this seed close to the feature makes additions explicit while the database remains the source of truth.
LEGACY_VOCABULARY_SEED = (
    ("Cards & Banking", (
        ("Yellow Card", "الكارت الأصفر", None),
        ("Prepaid Card", "بطاقة مسبقة الدفع", None),
        ("Debit Card", "بطاقة خصم", None),
        ("Credit Card", "بطاقة ائتمان", None),
        ("Investment", "استثمار", None),
        ("Deposit", "إيداع", None),
        ("Withdraw", "سحب", None),
        ("Account", "حساب", None),
        ("Consumer Finance", "تمويل استهلاكي", None),
        ("Installment", "تقسيط", None),
        ("Cash Loans", "قروض نقدية", None),
        ("Early Settlement", "سداد مبكر", None),
        ("Wallets", "محافظ إلكترونية", None),
    )),
    ("Transactions & Payments", (
        ("Transaction", "معاملة", None), ("Pay", "دفع", None), ("Payment", "دفعة / عملية دفع", None),
        ("POS", "نقطة بيع", "Point of Sale"), ("Point of Sale", "نقطة بيع", None),
        ("Cash Collection", "تحصيل نقدي", None), ("Cash-in", "إيداع نقدي", None),
        ("Cash-out", "سحب نقدي", None), ("Refund", "استرداد", None),
        ("Over Amount", "مبلغ زائد", None), ("Shortage", "عجز", None),
    )),
    ("Branch & People", (
        ("Customer", "عميل", None), ("Manager", "مدير", None), ("Leader", "قائد", None),
        ("Team Leader", "قائد فريق", None), ("Agent", "موظف / وكيل", None),
        ("Indoor Sales Representative", "مندوب مبيعات داخلي", None), ("Branch", "فرع", None),
        ("Area", "منطقة", None), ("Team", "فريق", None),
    )),
    ("Operations", (
        ("Service", "خدمة", None), ("Shift", "وردية", None), ("Opening", "فتح", None),
        ("Closing", "إغلاق", None), ("KYC", "اعرف عميلك", "K Y C"),
        ("Know Your Customer", "اعرف عميلك", None), ("Ticket", "تذكرة / طلب", None),
        ("Email", "بريد إلكتروني", None), ("Printer", "طابعة", None),
    )),
    ("Performance", (
        ("Target", "هدف", None), ("Achievements", "إنجازات", None), ("Top Achiever", "صاحب أعلى إنجاز", None),
        ("Performance", "أداء", None), ("Tracking", "متابعة", None), ("Coaching", "توجيه / تدريب", None),
        ("Action Plan", "خطة عمل", None), ("Deadline", "موعد نهائي", None), ("Task", "مهمة", None),
    )),
    ("System & Issues", (
        ("Approved", "تمت الموافقة", None), ("Pending", "قيد الانتظار", None), ("Failed", "فشل", None),
        ("Error", "خطأ", None), ("System Down", "النظام متوقف", None), ("Escalation", "تصعيد", None),
        ("Rejected", "مرفوض", None), ("Accepted", "مقبول", None), ("Delay", "تأخير", None), ("Update", "تحديث", None),
    )),
    ("Business", (
        ("Customer Need", "احتياج العميل", None), ("Problem", "مشكلة", None),
        ("Investigation", "تحقيق / مراجعة", None), ("Meeting", "اجتماع", None),
        ("Business Need", "احتياج العمل", None), ("Quality", "جودة", None), ("Audit", "مراجعة / تدقيق", None),
    )),
)


# Version 2 is the controlled retail vocabulary baseline.  The database, not
# this module, remains the source of truth after the one-time replacement.
VOCABULARY_SEED = (
    ("banking-products", "Banking & Products", (
        ("Yellow Card", "الكارت الأصفر", None),
        ("Prepaid Card", "بطاقة مسبقة الدفع", None),
        ("Investment", "استثمار", None),
        ("Deposit", "إيداع", None),
        ("Withdraw", "سحب", None),
        ("Account", "حساب", None),
        ("Consumer Finance", "تمويل استهلاكي", None),
        ("Installment", "تقسيط", None),
        ("Cash Loans", "قروض نقدية", None),
        ("Early Settlement", "سداد مبكر", None),
        ("Transaction", "معاملة", None),
        ("Point of Sale", "نقطة بيع", None),
        ("Refund", "استرداد", None),
    )),
    ("daily-operations", "Daily Operations", (
        ("Service", "خدمة", None),
        ("KYC", "اعرف عميلك", "K Y C"),
        ("Know Your Customer", "اعرف عميلك", None),
        ("Achievements", "إنجازات", None),
        ("Performance", "أداء", None),
        ("Tracking", "متابعة", None),
        ("Coaching", "توجيه / تدريب", None),
        ("Action Plan", "خطة عمل", None),
        ("Deadline", "موعد نهائي", None),
        ("Task", "مهمة", None),
        ("Approved", "تمت الموافقة", None),
        ("Accepted", "مقبول", None),
        ("Pending", "قيد الانتظار", None),
        ("Escalation", "تصعيد", None),
        ("Delay", "تأخير", None),
        ("Customer Need", "احتياج العميل", None),
        ("Business Need", "احتياج العمل", None),
        ("Audit", "مراجعة / تدقيق", None),
    )),
)


class VocabularyTransport(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def decode_browser_payload(cls, value):
        if not isinstance(value, dict) or "payload_b64" not in value:
            return value
        if set(value) != {"payload_b64"}:
            raise ValueError("Encoded request must not contain additional fields")
        encoded = value["payload_b64"]
        if not isinstance(encoded, str) or len(encoded) > 64 * 1024:
            raise ValueError("Encoded request exceeds 64 KiB or is invalid")
        try:
            decoded = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
        except (binascii.Error, UnicodeError, ValueError, RecursionError) as exc:
            raise ValueError("Invalid encoded vocabulary request") from exc
        if not isinstance(decoded, dict) or "payload_b64" in decoded:
            raise ValueError("Vocabulary payload must be an object")
        return decoded


class VocabularyInput(VocabularyTransport):
    english_text: str = Field(min_length=1, max_length=180)
    arabic_text: str = Field(min_length=1, max_length=1000)
    category_id: str = Field(min_length=1, max_length=36)
    speech_text: str | None = Field(default=None, max_length=180)
    display_order: int = Field(default=0, ge=0, le=100000)
    is_active: bool = True


class VocabularyCategoryInput(VocabularyTransport):
    name: str = Field(min_length=1, max_length=120)
    arabic_name: str = Field(min_length=1, max_length=120)
    category_id: str | None = Field(default=None, max_length=36)
    display_order: int = Field(default=0, ge=0, le=100000)
    is_active: bool = True


def _role(user: dict) -> str:
    return str(user.get("role") or user.get("department") or "").strip().lower()


def _actor(user: dict) -> str:
    return str(user.get("email") or user.get("sub") or "unknown").strip().lower()


def _require_manager(user: dict) -> None:
    if _role(user) not in ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Vocabulary management access required")


def _serialize_category(category: VocabularyCategory, item_count: int = 0) -> dict:
    return {
        "id": category.category_id,
        "name": category.name,
        "arabic_name": category.arabic_name or category.name,
        "display_order": category.display_order,
        "is_active": category.is_active,
        "item_count": item_count,
    }


def _serialize_item(item: VocabularyItem) -> dict:
    return {
        "id": item.vocabulary_id,
        "english_text": item.english_text,
        "arabic_text": item.arabic_text,
        "speech_text": item.speech_text,
        "category_id": item.category_id,
        "category_name": item.category.name if item.category else None,
        "display_order": item.display_order,
        "is_active": item.is_active,
    }


async def ensure_business_vocabulary_seed(db_client) -> None:
    """Replace the legacy taxonomy once, then preserve administrator-managed data."""
    canonical_names = {category_name for _, category_name, _ in VOCABULARY_SEED}
    legacy_names = {category_name for category_name, _ in LEGACY_VOCABULARY_SEED}

    async with db_client() as session:
        async with session.begin():
            existing_categories = (await session.execute(select(VocabularyCategory))).scalars().all()
            existing_names = {category.name for category in existing_categories}
            needs_replacement = (
                not existing_names
                or bool(existing_names & legacy_names)
                or not canonical_names.issubset(existing_names)
            )
            if not needs_replacement:
                return

            # Deleting category ORM objects cascades their words and prevents
            # old-category records from remaining visible or orphaned.
            for category in existing_categories:
                await session.delete(category)
            await session.flush()

            for category_order, (category_id, category_name, entries) in enumerate(VOCABULARY_SEED, start=1):
                category = VocabularyCategory(
                    category_id=category_id,
                    name=category_name,
                    arabic_name={"Banking & Products": "الخدمات المصرفية والمنتجات", "Daily Operations": "العمليات اليومية"}.get(category_name, category_name),
                    display_order=category_order,
                    is_active=True,
                )
                session.add(category)
                for word_order, (english_text, arabic_text, speech_text) in enumerate(entries, start=1):
                    session.add(VocabularyItem(
                        english_text=english_text,
                        arabic_text=arabic_text,
                        speech_text=speech_text,
                        category_id=category_id,
                        display_order=word_order,
                        is_active=True,
                        created_by="system_seed_v2",
                    ))
            logger.info("Replaced Business Vocabulary with the v2 two-category baseline")


def _audit(request: Request, current_user: dict, action: str, details: str) -> None:
    try:
        append_audit_event(request.app, build_audit_event(
            actor_email=_actor(current_user), actor_role=_role(current_user), method=request.method,
            path=request.url.path, query=request.url.query, status_code=200, duration_ms=0,
            ip_address=request.client.host if request.client else "-",
            user_agent=request.headers.get("user-agent", "-"), action=action, details=details,
        ))
    except Exception:  # Audit availability must not prevent a completed vocabulary action.
        logger.exception("Unable to write vocabulary audit event")


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-") or "category"


@router.get("/categories")
async def list_categories(request: Request, include_inactive: bool = Query(default=False), current_user: dict = Depends(get_current_user)):
    if include_inactive:
        _require_manager(current_user)
    async with request.app.state.db_client() as session:
        predicates = [] if include_inactive else [VocabularyCategory.is_active.is_(True)]
        categories = (await session.execute(
            select(VocabularyCategory).where(*predicates).order_by(VocabularyCategory.display_order, VocabularyCategory.name)
        )).scalars().all()
        counts = dict((await session.execute(
            select(VocabularyItem.category_id, func.count(VocabularyItem.vocabulary_id))
            .where(VocabularyItem.is_active.is_(True))
            .group_by(VocabularyItem.category_id)
        )).all())
    return {"items": [_serialize_category(category, counts.get(category.category_id, 0)) for category in categories]}


@router.post("/categories", status_code=status.HTTP_201_CREATED)
async def create_category(payload: VocabularyCategoryInput, request: Request, current_user: dict = Depends(get_current_user)):
    _require_manager(current_user)
    category_id = _slugify(payload.category_id or payload.name)
    async with request.app.state.db_client() as session:
        try:
            async with session.begin():
                category = VocabularyCategory(category_id=category_id, name=payload.name.strip(), arabic_name=payload.arabic_name.strip(), display_order=payload.display_order, is_active=payload.is_active)
                session.add(category)
        except IntegrityError as error:
            raise HTTPException(status_code=409, detail="Category name or ID already exists") from error
    _audit(request, current_user, "VOCABULARY_CATEGORY_CREATED", category_id)
    return {"id": category_id}


@router.post("/categories/{category_id}/save")
@router.put("/categories/{category_id}")
async def update_category(category_id: str, payload: VocabularyCategoryInput, request: Request, current_user: dict = Depends(get_current_user)):
    _require_manager(current_user)
    async with request.app.state.db_client() as session:
        try:
            async with session.begin():
                category = await session.scalar(select(VocabularyCategory).where(VocabularyCategory.category_id == category_id))
                if category is None:
                    raise HTTPException(status_code=404, detail="Vocabulary category not found")
                category.name, category.arabic_name = payload.name.strip(), payload.arabic_name.strip()
                category.display_order, category.is_active = payload.display_order, payload.is_active
                category.updated_at = datetime.now(timezone.utc)
        except IntegrityError as error:
            raise HTTPException(status_code=409, detail="Category name already exists") from error
    _audit(request, current_user, "VOCABULARY_CATEGORY_UPDATED", category_id)
    return {"id": category_id}


@router.delete("/categories/{category_id}")
async def delete_category(category_id: str, request: Request, cascade: bool = Query(default=False), current_user: dict = Depends(get_current_user)):
    _require_manager(current_user)
    async with request.app.state.db_client() as session:
        async with session.begin():
            category = await session.scalar(select(VocabularyCategory).where(VocabularyCategory.category_id == category_id))
            if category is None:
                raise HTTPException(status_code=404, detail="Vocabulary category not found")
            count = await session.scalar(select(func.count(VocabularyItem.vocabulary_id)).where(VocabularyItem.category_id == category_id))
            if count and not cascade:
                raise HTTPException(status_code=409, detail=f"This category contains {count} vocabulary items. Confirm cascade deletion to continue.")
            if cascade:
                await session.execute(delete(VocabularyItem).where(VocabularyItem.category_id == category_id))
            await session.delete(category)
    _audit(request, current_user, "VOCABULARY_CATEGORY_DELETED", f"{category_id}; items={count}; cascade={cascade}")
    return {"deleted_items": count}


@router.get("/items")
async def list_items(
    request: Request,
    category_id: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=180),
    current_user: dict = Depends(get_current_user),
):
    predicates = [VocabularyItem.is_active.is_(True)]
    if category_id:
        predicates.append(VocabularyItem.category_id == category_id)
    if search and search.strip():
        term = search.strip()
        predicates.append(or_(func.lower(VocabularyItem.english_text).like(f"%{term.lower()}%"), VocabularyItem.arabic_text.like(f"%{term}%")))
    async with request.app.state.db_client() as session:
        items = (await session.execute(
            select(VocabularyItem).options(selectinload(VocabularyItem.category)).where(*predicates)
            .order_by(VocabularyItem.category_id, VocabularyItem.display_order, VocabularyItem.english_text)
        )).scalars().all()
    return {"items": [_serialize_item(item) for item in items], "total": len(items)}


async def _category_or_404(session, category_id: str) -> VocabularyCategory:
    category = await session.scalar(select(VocabularyCategory).where(
        VocabularyCategory.category_id == category_id,
        VocabularyCategory.is_active.is_(True),
    ))
    if category is None:
        raise HTTPException(status_code=404, detail="Vocabulary category not found")
    return category


@router.post("/items", status_code=status.HTTP_201_CREATED)
async def create_item(payload: VocabularyInput, request: Request, current_user: dict = Depends(get_current_user)):
    _require_manager(current_user)
    async with request.app.state.db_client() as session:
        try:
            async with session.begin():
                await _category_or_404(session, payload.category_id)
                item = VocabularyItem(
                    english_text=payload.english_text.strip(), arabic_text=payload.arabic_text.strip(),
                    speech_text=(payload.speech_text or "").strip() or None, category_id=payload.category_id,
                    display_order=payload.display_order, is_active=payload.is_active,
                    created_by=_actor(current_user),
                )
                session.add(item)
                await session.flush()
            result = await session.execute(select(VocabularyItem).options(selectinload(VocabularyItem.category)).where(VocabularyItem.vocabulary_id == item.vocabulary_id))
            item = result.scalar_one()
        except IntegrityError as error:
            raise HTTPException(status_code=409, detail="This English word already exists in the selected category") from error
    _audit(request, current_user, "VOCABULARY_CREATED", item.english_text)
    return {"item": _serialize_item(item)}


@router.post("/items/{vocabulary_id}/save")
@router.patch("/items/{vocabulary_id}")
@router.put("/items/{vocabulary_id}")
async def update_item(vocabulary_id: str, payload: VocabularyInput, request: Request, current_user: dict = Depends(get_current_user)):
    _require_manager(current_user)
    async with request.app.state.db_client() as session:
        try:
            async with session.begin():
                item = await session.scalar(select(VocabularyItem).where(VocabularyItem.vocabulary_id == vocabulary_id))
                if item is None:
                    raise HTTPException(status_code=404, detail="Vocabulary item not found")
                await _category_or_404(session, payload.category_id)
                item.english_text = payload.english_text.strip()
                item.arabic_text = payload.arabic_text.strip()
                item.speech_text = (payload.speech_text or "").strip() or None
                item.category_id = payload.category_id
                item.display_order = payload.display_order
                item.is_active = payload.is_active
                item.updated_at = datetime.now(timezone.utc)
            result = await session.execute(select(VocabularyItem).options(selectinload(VocabularyItem.category)).where(VocabularyItem.vocabulary_id == vocabulary_id))
            item = result.scalar_one()
        except IntegrityError as error:
            raise HTTPException(status_code=409, detail="This English word already exists in the selected category") from error
    _audit(request, current_user, "VOCABULARY_UPDATED", item.english_text)
    return {"item": _serialize_item(item)}


@router.delete("/items/{vocabulary_id}")
async def delete_item(vocabulary_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    _require_manager(current_user)
    async with request.app.state.db_client() as session:
        async with session.begin():
            item = await session.scalar(select(VocabularyItem).where(VocabularyItem.vocabulary_id == vocabulary_id))
            if item is None:
                raise HTTPException(status_code=404, detail="Vocabulary item not found")
            english_text = item.english_text
            await session.delete(item)
    _audit(request, current_user, "VOCABULARY_DELETED", english_text)
    return {"message": "Vocabulary deleted"}
