from typing import Callable, Sequence

from sqlalchemy import desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from models.base_model import BaseModel
from models.db_schemas import (
    Question,
    QuestionBankChoice,
    QuestionBankItem,
)

SessionMaker = Callable[[], AsyncSession]


class QuestionModel(BaseModel):

    def __init__(self, db_client: SessionMaker) -> None:
        super().__init__()
        self.db_client = db_client

    @classmethod
    async def create_instance(cls, db_client: SessionMaker):
        instance = cls(db_client)
        return instance

    #! =============== Create Operations =============== !#

    async def create_question(self, question: Question) -> Question:
        async with self.db_client() as session:
            async with session.begin():
                session.add(question)
            await session.commit()
            await session.refresh(question)

            return question

    async def create_question_bank_item(self, question_bank_item: QuestionBankItem) -> QuestionBankItem:
        async with self.db_client() as session:
            async with session.begin():
                session.add(question_bank_item)
                await session.flush()
                created_id = question_bank_item.bank_question_id
            await session.commit()

        created_item = await self.get_question_bank_item_by_id(created_id)
        if created_item is None:
            raise ValueError("Created question bank item could not be reloaded.")
        return created_item

    #! =============== Read Operations =============== !#

    async def get_all_questions(self) -> Sequence[Question]:
        async with self.db_client() as session:
            result = await session.execute(select(Question))
            questions = result.scalars().all()
            return questions

    async def get_question_by_id(self, question_id: str) -> Question | None:
        async with self.db_client() as session:
            result = await session.execute(select(Question).where(Question.question_id == question_id))
            question = result.scalar_one_or_none()
            return question

    async def get_questions_by_exam_id(self, exam_id: str) -> Sequence[Question]:
        async with self.db_client() as session:
            result = await session.execute(select(Question).where(Question.exam_id == exam_id))
            questions = result.scalars().all()
            return questions

    async def get_question_bank_item_by_id(
        self,
        bank_question_id: str,
        *,
        include_deleted: bool = False,
    ) -> QuestionBankItem | None:
        async with self.db_client() as session:
            stmt = (
                select(QuestionBankItem)
                .options(selectinload(QuestionBankItem.choices))
                .where(QuestionBankItem.bank_question_id == bank_question_id)
            )
            if not include_deleted:
                stmt = stmt.where(QuestionBankItem.is_deleted.is_(False))
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_question_bank_items(
        self,
        *,
        query: str | None = None,
        question_type: str | None = None,
        favorites_only: bool = False,
        include_deleted: bool = False,
    ) -> Sequence[QuestionBankItem]:
        async with self.db_client() as session:
            stmt = select(QuestionBankItem).options(selectinload(QuestionBankItem.choices))

            if not include_deleted:
                stmt = stmt.where(QuestionBankItem.is_deleted.is_(False))

            normalized_type = str(question_type or "").strip().upper()
            if normalized_type and normalized_type != "ALL":
                stmt = stmt.where(QuestionBankItem.question_type == normalized_type)

            if favorites_only:
                stmt = stmt.where(QuestionBankItem.is_favorite.is_(True))

            normalized_query = str(query or "").strip().lower()
            if normalized_query:
                like_pattern = f"%{normalized_query}%"
                stmt = stmt.where(
                    or_(
                        func.lower(QuestionBankItem.question_text).like(like_pattern),
                        func.lower(func.coalesce(QuestionBankItem.question_group, "")).like(like_pattern),
                        func.lower(func.coalesce(QuestionBankItem.created_by, "")).like(like_pattern),
                        QuestionBankItem.choices.any(
                            func.lower(QuestionBankChoice.choice_text).like(like_pattern)
                        ),
                    )
                )

            stmt = stmt.order_by(
                desc(QuestionBankItem.is_favorite),
                desc(func.coalesce(QuestionBankItem.updated_at, QuestionBankItem.created_at)),
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def find_matching_question_bank_item(self, prepared_question: dict) -> QuestionBankItem | None:
        normalized_text = str(prepared_question.get("question_text") or "").strip()
        normalized_type = str(prepared_question.get("question_type") or "").upper()
        normalized_points = int(prepared_question.get("points") or 0)
        normalized_group = str(prepared_question.get("question_group") or "").strip() or None
        normalized_choices = [
            {
                "choice_text": str(choice.get("choice_text") or "").strip(),
                "is_correct": bool(choice.get("is_correct")),
            }
            for choice in prepared_question.get("choices") or []
        ]

        async with self.db_client() as session:
            stmt = (
                select(QuestionBankItem)
                .options(selectinload(QuestionBankItem.choices))
                .where(
                    QuestionBankItem.is_deleted.is_(False),
                    QuestionBankItem.question_text == normalized_text,
                    QuestionBankItem.question_type == normalized_type,
                    QuestionBankItem.points == normalized_points,
                )
            )
            if normalized_group is None:
                stmt = stmt.where(
                    or_(
                        QuestionBankItem.question_group.is_(None),
                        QuestionBankItem.question_group == "",
                    )
                )
            else:
                stmt = stmt.where(QuestionBankItem.question_group == normalized_group)

            result = await session.execute(stmt)
            candidates = result.scalars().all()
            for candidate in candidates:
                existing_choices = [
                    {
                        "choice_text": str(choice.choice_text or "").strip(),
                        "is_correct": bool(choice.is_correct),
                    }
                    for choice in sorted(
                        candidate.choices or [],
                        key=lambda choice: (choice.choice_order or 0, str(choice.bank_choice_id or "")),
                    )
                ]
                if existing_choices == normalized_choices:
                    return candidate

        return None

    #! =============== Update Operations =============== !#

    async def update_question_bank_item(self, bank_question_id: str, updates: dict) -> QuestionBankItem | None:
        async with self.db_client() as session:
            async with session.begin():
                stmt = (
                    select(QuestionBankItem)
                    .options(selectinload(QuestionBankItem.choices))
                    .where(
                        QuestionBankItem.bank_question_id == bank_question_id,
                        QuestionBankItem.is_deleted.is_(False),
                    )
                )
                result = await session.execute(stmt)
                question_bank_item = result.scalar_one_or_none()
                if question_bank_item is None:
                    return None

                question_bank_item.question_text = updates.get("question_text", question_bank_item.question_text)
                question_bank_item.question_type = updates.get("question_type", question_bank_item.question_type)
                question_bank_item.points = updates.get("points", question_bank_item.points)
                question_bank_item.question_group = updates.get("question_group", question_bank_item.question_group)
                if "is_favorite" in updates:
                    question_bank_item.is_favorite = bool(updates.get("is_favorite"))
                if "updated_by" in updates:
                    question_bank_item.updated_by = updates.get("updated_by")

                if "choices" in updates:
                    question_bank_item.choices.clear()
                    for choice in updates.get("choices") or []:
                        question_bank_item.choices.append(
                            QuestionBankChoice(
                                choice_text=choice.get("choice_text", ""),
                                is_correct=bool(choice.get("is_correct")),
                                choice_order=choice.get("choice_order"),
                            )
                        )

                session.add(question_bank_item)
            await session.commit()

        return await self.get_question_bank_item_by_id(bank_question_id)

    #! =============== Delete Operations =============== !#
    async def delete_question_by_id_softdelete(self, question_id: str) -> bool:
        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(select(Question).where(Question.question_id == question_id))
                question = result.scalar_one_or_none()
                if question is None:
                    return False
                question.is_deleted = True
                session.add(question)
            await session.commit()
        return True

    async def delete_question_by_id_harddelete(self, question_id: str) -> bool:
        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(select(Question).where(Question.question_id == question_id))
                question = result.scalar_one_or_none()
                if question is None:
                    return False
                await session.delete(question)
            await session.commit()
        return True

    async def restore_question_by_id(self, question_id: str) -> bool:
        async with self.db_client() as session:
            async with session.begin():
                query = select(Question).where(Question.question_id == question_id)
                result = await session.execute(query)
                question = result.scalar_one_or_none()
                if question is None:
                    return False
                question.is_deleted = False
            await session.commit()
        return True

    async def delete_questions_by_exam_id_harddelete(self, exam_id: str) -> None:
        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(select(Question).where(Question.exam_id == exam_id))
                questions = result.scalars().all()
                for question in questions:
                    await session.delete(question)
            await session.commit()

    async def soft_delete_question_bank_item(self, bank_question_id: str) -> bool:
        async with self.db_client() as session:
            async with session.begin():
                stmt = select(QuestionBankItem).where(
                    QuestionBankItem.bank_question_id == bank_question_id,
                    QuestionBankItem.is_deleted.is_(False),
                )
                result = await session.execute(stmt)
                question_bank_item = result.scalar_one_or_none()
                if question_bank_item is None:
                    return False
                question_bank_item.is_deleted = True
                session.add(question_bank_item)
            await session.commit()
        return True

    async def delete_all_questions(self) -> None:
        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(select(Question))
                questions = result.scalars().all()
                for question in questions:
                    await session.delete(question)
            await session.commit()
