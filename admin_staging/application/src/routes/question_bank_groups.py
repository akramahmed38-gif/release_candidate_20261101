import random

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from models.db_schemas import QuestionBankGroup, QuestionBankGroupMember, QuestionBankItem
from routes.users.auth_utils import get_current_user


router = APIRouter(prefix="/api/v1/exams/question-bank/groups", tags=["Question Bank"])
GENERAL_GROUP_ID = "general-bank"
MANAGER_ROLES = {"admin", "hr", "auditor"}


def _require_manager(user):
    if str(user.get("role") or "").lower() not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Question Bank management is not available for this role")


def _name(value):
    name = str(value or "").strip()
    if not name or len(name) > 120:
        raise HTTPException(status_code=422, detail="Group name must contain 1 to 120 characters")
    return name


class GroupPayload(BaseModel):
    name: str
    description: str = Field(default="", max_length=500)


class MovePayload(BaseModel):
    question_ids: list[str] = Field(min_length=1)
    group_id: str


class GroupSelection(BaseModel):
    group_id: str
    count: int = Field(ge=0)


class SelectionPayload(BaseModel):
    groups: list[GroupSelection] = Field(min_length=1)
    excluded_question_ids: list[str] = Field(default_factory=list)


async def ensure_question_bank_groups(db_client):
    """Idempotently map legacy bank labels; never change exam question rows."""
    async with db_client() as session:
        async with session.begin():
            groups = (await session.scalars(select(QuestionBankGroup))).all()
            by_name = {group.name.casefold(): group for group in groups}
            general = by_name.get("general bank")
            if general is None:
                general = QuestionBankGroup(group_id=GENERAL_GROUP_ID, name="General Bank", is_system=True)
                session.add(general)
                by_name["general bank"] = general
            general.is_system = True
            legacy = (await session.scalars(select(QuestionBankItem.question_group).distinct())).all()
            for label in legacy:
                name = str(label or "").strip()
                if not name or name.casefold() in {"general", "general bank"}:
                    continue
                if name.casefold() not in by_name:
                    group = QuestionBankGroup(name=name)
                    session.add(group)
                    by_name[name.casefold()] = group
            await session.flush()
            unmapped = (await session.scalars(
                select(QuestionBankItem).outerjoin(
                    QuestionBankGroupMember,
                    QuestionBankGroupMember.bank_question_id == QuestionBankItem.bank_question_id,
                ).where(QuestionBankGroupMember.bank_question_id.is_(None))
            )).all()
            for item in unmapped:
                label = str(item.question_group or "").strip().casefold()
                group = by_name.get(label, general) if label not in {"general", "general bank"} else general
                session.add(QuestionBankGroupMember(bank_question_id=item.bank_question_id, group_id=group.group_id))


async def assign_question_group(db_client, bank_question_id: str, label: str | None):
    name = str(label or "").strip()
    if name.casefold() in {"", "general"}:
        name = "General Bank"
    async with db_client() as session:
        async with session.begin():
            group = await session.scalar(select(QuestionBankGroup).where(func.lower(QuestionBankGroup.name) == name.lower()))
            if group is None:
                group = QuestionBankGroup(name=name)
                session.add(group)
                await session.flush()
            member = await session.get(QuestionBankGroupMember, bank_question_id)
            if member is None:
                session.add(QuestionBankGroupMember(bank_question_id=bank_question_id, group_id=group.group_id))
            else:
                member.group_id = group.group_id


@router.get("")
async def list_groups(request: Request, current_user: dict = Depends(get_current_user)):
    _require_manager(current_user)
    async with request.app.state.db_client() as session:
        rows = (await session.execute(
            select(QuestionBankGroup, func.count(QuestionBankItem.bank_question_id))
            .outerjoin(QuestionBankGroupMember, QuestionBankGroupMember.group_id == QuestionBankGroup.group_id)
            .outerjoin(QuestionBankItem, (QuestionBankItem.bank_question_id == QuestionBankGroupMember.bank_question_id) & (QuestionBankItem.is_deleted.is_(False)))
            .group_by(QuestionBankGroup.group_id).order_by(QuestionBankGroup.is_system.desc(), QuestionBankGroup.name)
        )).all()
    return {"groups": [{"group_id": group.group_id, "name": group.name, "description": group.description, "is_system": group.is_system, "question_count": count} for group, count in rows]}


@router.post("", status_code=201)
async def create_group(request: Request, payload: GroupPayload, current_user: dict = Depends(get_current_user)):
    _require_manager(current_user)
    name = _name(payload.name)
    async with request.app.state.db_client() as session:
        async with session.begin():
            if await session.scalar(select(QuestionBankGroup).where(func.lower(QuestionBankGroup.name) == name.lower())):
                raise HTTPException(status_code=409, detail="Group already exists")
            group = QuestionBankGroup(name=name, description=payload.description.strip())
            session.add(group)
            await session.flush()
            group_id = group.group_id
    return {"group_id": group_id, "name": name}


@router.put("/{group_id}")
async def edit_group(group_id: str, request: Request, payload: GroupPayload, current_user: dict = Depends(get_current_user)):
    _require_manager(current_user)
    name = _name(payload.name)
    async with request.app.state.db_client() as session:
        async with session.begin():
            group = await session.get(QuestionBankGroup, group_id)
            if group is None:
                raise HTTPException(status_code=404, detail="Group not found")
            if group.is_system and name.casefold() != group.name.casefold():
                raise HTTPException(status_code=400, detail="General Bank cannot be renamed")
            duplicate = await session.scalar(select(QuestionBankGroup).where(func.lower(QuestionBankGroup.name) == name.lower(), QuestionBankGroup.group_id != group_id))
            if duplicate:
                raise HTTPException(status_code=409, detail="Group already exists")
            group.name = name
            group.description = payload.description.strip()
    return {"group_id": group_id, "name": name}


@router.delete("/{group_id}")
async def delete_group(group_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    _require_manager(current_user)
    async with request.app.state.db_client() as session:
        async with session.begin():
            group = await session.get(QuestionBankGroup, group_id)
            if group is None:
                raise HTTPException(status_code=404, detail="Group not found")
            if group.is_system:
                raise HTTPException(status_code=400, detail="General Bank cannot be deleted")
            await session.execute(update(QuestionBankGroupMember).where(QuestionBankGroupMember.group_id == group_id).values(group_id=GENERAL_GROUP_ID))
            await session.delete(group)
    return {"message": "Group deleted; questions moved to General Bank"}


@router.post("/move")
async def move_questions(request: Request, payload: MovePayload, current_user: dict = Depends(get_current_user)):
    _require_manager(current_user)
    ids = list(dict.fromkeys(payload.question_ids))
    async with request.app.state.db_client() as session:
        async with session.begin():
            group = await session.get(QuestionBankGroup, payload.group_id)
            if group is None:
                raise HTTPException(status_code=404, detail="Destination group not found")
            existing = (await session.scalars(select(QuestionBankItem.bank_question_id).where(QuestionBankItem.bank_question_id.in_(ids), QuestionBankItem.is_deleted.is_(False)))).all()
            if len(existing) != len(ids):
                raise HTTPException(status_code=404, detail="One or more bank questions were not found")
            result = await session.execute(update(QuestionBankGroupMember).where(QuestionBankGroupMember.bank_question_id.in_(ids)).values(group_id=payload.group_id))
            if result.rowcount != len(ids):
                raise HTTPException(status_code=409, detail="A question is missing its group assignment")
    return {"moved": len(ids), "group_id": payload.group_id}


@router.get("/{group_id}/questions")
async def group_questions(group_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    _require_manager(current_user)
    async with request.app.state.db_client() as session:
        group = await session.get(QuestionBankGroup, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Group not found")
        rows = (await session.scalars(
            select(QuestionBankItem).join(QuestionBankGroupMember)
            .where(QuestionBankGroupMember.group_id == group_id, QuestionBankItem.is_deleted.is_(False))
            .order_by(QuestionBankItem.created_at.desc())
        )).all()
    return {"group": {"group_id": group.group_id, "name": group.name, "description": group.description},
            "items": [{"bank_question_id": item.bank_question_id, "question_text": item.question_text,
                       "question_type": item.question_type, "points": item.points,
                       "is_favorite": item.is_favorite} for item in rows]}


@router.post("/select")
async def select_from_groups(request: Request, payload: SelectionPayload, current_user: dict = Depends(get_current_user)):
    _require_manager(current_user)
    counts = {}
    for selected in payload.groups:
        if selected.group_id in counts:
            raise HTTPException(status_code=422, detail="Each group may appear only once")
        counts[selected.group_id] = selected.count
    if not any(counts.values()):
        raise HTTPException(status_code=422, detail="Select at least one question")
    excluded = set(payload.excluded_question_ids)
    result = []
    async with request.app.state.db_client() as session:
        groups = {group.group_id: group for group in (await session.scalars(select(QuestionBankGroup).where(QuestionBankGroup.group_id.in_(counts)))).all()}
        if len(groups) != len(counts):
            raise HTTPException(status_code=404, detail="One or more groups were not found")
        for group_id, count in counts.items():
            if count == 0:
                continue
            questions = (await session.scalars(
                select(QuestionBankItem).options(selectinload(QuestionBankItem.choices))
                .join(QuestionBankGroupMember)
                .where(QuestionBankGroupMember.group_id == group_id,
                       QuestionBankItem.is_deleted.is_(False),
                       QuestionBankItem.question_type.in_(["MCQ", "TF"]),
                       QuestionBankItem.bank_question_id.not_in(excluded))
            )).all()
            if count > len(questions):
                raise HTTPException(status_code=422, detail=f"{groups[group_id].name} contains only {len(questions)} available questions")
            for item in random.SystemRandom().sample(questions, count):
                excluded.add(item.bank_question_id)
                result.append({
                    "bank_question_id": item.bank_question_id,
                    "question_text": item.question_text,
                    "question_type": item.question_type,
                    "points": item.points,
                    "question_group": groups[group_id].name,
                    "group_id": group_id,
                    "is_favorite": item.is_favorite,
                    "choices": [{"choice_text": choice.choice_text, "is_correct": choice.is_correct,
                                 "choice_order": choice.choice_order} for choice in item.choices],
                })
    return {"items": result}
