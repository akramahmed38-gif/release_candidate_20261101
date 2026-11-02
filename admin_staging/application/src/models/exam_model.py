import os
import json
from datetime import datetime, timedelta, timezone
from typing import Callable, Sequence, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select
from sqlalchemy import func, case, and_
from sqlalchemy.orm import selectinload
from models.base_model import BaseModel
from models.db_schemas import Exam, Material, Question, Employee, ExamAttempt, ExamAnswer, Branch

SessionMaker = Callable[[], AsyncSession]
EMPLOYMENT_STATUS_ACTIVE = "active"

class ExamModel(BaseModel):

    def __init__(self, db_client: SessionMaker) -> None:
        super().__init__()
        self.db_client = db_client

    @classmethod
    async def create_instance(cls, db_client: SessionMaker):
        instance = cls(db_client)
        return instance

    #! =============== Create Operations =============== !#

    async def create_exam(self, exam: Exam) -> Exam:
        async with self.db_client() as session:
            async with session.begin():
                session.add(exam)
            await session.commit()
            await session.refresh(exam)

            return exam
        
    async def is_exam_exists(self, exam_id: str) -> Tuple[bool, Exam | None]: 
        async with self.db_client() as session:
            async with session.begin():
                query = select(Exam).where(Exam.exam_id == exam_id)
                result = await session.execute(query)
                exam = result.scalar_one_or_none()
                
                return exam is not None, exam

    #! =============== Read Operations =============== !#

    async def get_all_exams(self) -> Sequence[Exam]:
        async with self.db_client() as session:
            result = await session.execute(select(Exam))
            exams = result.scalars().all()

            return exams

    async def get_all_attempts(self) -> Sequence[ExamAttempt]:
        async with self.db_client() as session:
            result = await session.execute(
                select(ExamAttempt).options(
                    selectinload(ExamAttempt.answers).selectinload(ExamAnswer.question),
                )
            )
            attempts = result.scalars().all()
            return attempts

    async def get_exam_by_id(self, exam_id: str) -> Exam | None:
            async with self.db_client() as session:
                result = await session.execute(select(Exam).where(Exam.exam_id == exam_id))
                exam = result.scalar_one_or_none()

                return exam

    async def get_exam_with_details(self, exam_id: str) -> Exam | None:
        async with self.db_client() as session:
            stmt = (
                select(Exam)
                .options(
                    selectinload(Exam.questions).selectinload(Question.choices),
                    selectinload(Exam.materials),
                    selectinload(Exam.employees).selectinload(Employee.branch),
                )
                .where(Exam.exam_id == exam_id)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_active_attempt_for_employee_exam(self, exam_id: str, employee_id: str) -> ExamAttempt | None:
        if not exam_id or not employee_id:
            return None

        async with self.db_client() as session:
            stmt = (
                select(ExamAttempt)
                .where(
                    (ExamAttempt.exam_id == exam_id)
                    & (ExamAttempt.employee_id == employee_id)
                    & (ExamAttempt.submitted_at.is_(None))
                )
                .order_by(ExamAttempt.started_at.desc(), ExamAttempt.attempt_number.desc())
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    async def get_active_attempts_for_employee(self, employee_id: str) -> Sequence[ExamAttempt]:
        if not employee_id:
            return []

        async with self.db_client() as session:
            stmt = (
                select(ExamAttempt)
                .options(selectinload(ExamAttempt.exam))
                .where(
                    (ExamAttempt.employee_id == employee_id)
                    & (ExamAttempt.submitted_at.is_(None))
                )
                .order_by(ExamAttempt.started_at.desc(), ExamAttempt.attempt_number.desc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    @staticmethod
    def _build_attempt_summary_payload(attempt: ExamAttempt) -> dict:
        employee = attempt.employee
        branch = employee.branch if employee else None

        duration_seconds = None
        if attempt.started_at and attempt.submitted_at:
            duration_seconds = int((attempt.submitted_at - attempt.started_at).total_seconds())
            if duration_seconds < 0:
                duration_seconds = 0

        score_percentage = None
        if attempt.max_score:
            total_score_value = float(attempt.total_score or 0.0)
            score_percentage = round((total_score_value / float(attempt.max_score)) * 100, 2)

        return {
            "attempt_id": attempt.attempt_id,
            "attempt_number": attempt.attempt_number,
            "employee_id": employee.employee_id if employee else None,
            "employee_hr_id": employee.hr_id if employee else None,
            "employee_name": employee.name if employee else None,
            "employee_title": employee.title if employee else None,
            "department": employee.department if employee else None,
            "email": employee.email if employee else None,
            "branch": {
                "branch_code": branch.branch_code,
                "branch_name": branch.branch_name,
                "region": branch.branch_region,
                "area": branch.branch_area,
                "division": branch.branch_division,
                "sub_department": branch.branch_sub_department,
            } if branch else None,
            "total_score": attempt.total_score,
            "max_score": attempt.max_score,
            "score_percentage": score_percentage,
            "passed": attempt.passed,
            "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
            "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
            "duration_seconds": duration_seconds,
        }

    async def get_exams_for_employee_hr_id(self, hr_id: str) -> Sequence[Exam]:
        if not hr_id:
            return []
        async with self.db_client() as session:
            stmt = (
                select(Exam)
                .join(Exam.employees)
                .where(
                    (Employee.hr_id == hr_id)
                    & (Employee.employment_status == EMPLOYMENT_STATUS_ACTIVE)
                    & (Exam.is_deleted == False)
                )
                .distinct()
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    def _build_employee_filter_conditions(self, filters: dict | None) -> list:
        filters = filters or {}

        def normalized(values):
            return [value for value in (values or []) if value]

        mapping = {
            Branch.branch_code: normalized(filters.get("branch_codes")),
            Branch.branch_name: normalized(filters.get("branches")),
            Branch.branch_area: normalized(filters.get("areas")),
            Branch.branch_region: normalized(filters.get("regions")),
            Branch.branch_division: normalized(filters.get("divisions")),
            Branch.branch_sub_department: normalized(filters.get("sub_departments")),
            Employee.title: normalized(filters.get("titles")),
            Employee.department: normalized(filters.get("departments")),
            Employee.hr_id: normalized(filters.get("hr_ids")),
        }

        conditions = []
        for column, values in mapping.items():
            if values:
                conditions.append(column.in_(values))
        return conditions

    def _get_employee_performance_period_bounds(
        self,
        period: str | None,
    ) -> tuple[datetime | None, datetime]:
        normalized_period = str(period or "all").strip().lower()
        now = datetime.now(timezone.utc)

        if normalized_period == "week":
            start = (now - timedelta(days=now.weekday())).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            return start, now

        if normalized_period == "month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return start, now

        if normalized_period == "year":
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            return start, now

        return None, now

    async def _get_employee_performance_leaderboard_rows(
        self,
        filters: dict | None,
        period: str | None,
        exams_joined: int | None = None,
        sort_by: str = "average_percentage",
        sort_dir: str = "desc",
        page: int | None = None,
        page_size: int | None = None,
    ) -> tuple[list[dict], int, list[int]]:
        conditions = self._build_employee_filter_conditions(filters)
        period_start, period_end = self._get_employee_performance_period_bounds(period)
        offset_value = None
        if page is not None and page_size is not None:
            offset_value = max(page - 1, 0) * page_size

        attempt_conditions = [
            ExamAttempt.submitted_at.isnot(None),
            ExamAttempt.submitted_at <= period_end,
        ]
        if period_start is not None:
            attempt_conditions.append(ExamAttempt.submitted_at >= period_start)

        latest_attempts = (
            select(
                ExamAttempt.employee_id,
                ExamAttempt.exam_id,
                ExamAttempt.total_score,
                ExamAttempt.max_score,
                ExamAttempt.submitted_at,
                case(
                    (
                        and_(
                            ExamAttempt.total_score.isnot(None),
                            ExamAttempt.max_score.isnot(None),
                            ExamAttempt.max_score != 0,
                        ),
                        (ExamAttempt.total_score * 100.0) / ExamAttempt.max_score,
                    ),
                    else_=None,
                ).label("exam_percentage"),
                func.row_number()
                .over(
                    partition_by=(ExamAttempt.employee_id, ExamAttempt.exam_id),
                    order_by=ExamAttempt.submitted_at.desc(),
                )
                .label("row_number"),
            )
            .where(and_(*attempt_conditions))
            .subquery()
        )

        leaderboard_attempts = (
            select(
                latest_attempts.c.employee_id.label("employee_id"),
                func.count(latest_attempts.c.exam_id).label("exams_joined"),
                func.avg(latest_attempts.c.exam_percentage).label("average_percentage"),
                func.max(latest_attempts.c.submitted_at).label("last_submitted_at"),
            )
            .where(latest_attempts.c.row_number == 1)
            .group_by(latest_attempts.c.employee_id)
            .subquery()
        )
        exact_exam_count_filter = None
        if exams_joined is not None:
            exact_exam_count_filter = func.coalesce(leaderboard_attempts.c.exams_joined, 0) == int(exams_joined)

        async with self.db_client() as session:
            active_employee_filter = Employee.employment_status == EMPLOYMENT_STATUS_ACTIVE
            count_stmt = (
                select(func.count())
                .select_from(Employee)
                .join(Branch, Employee.branch_code == Branch.branch_code)
                .outerjoin(
                    leaderboard_attempts,
                    Employee.employee_id == leaderboard_attempts.c.employee_id,
                )
                .where(active_employee_filter)
            )
            if conditions:
                count_stmt = count_stmt.where(and_(*conditions))
            if exact_exam_count_filter is not None:
                count_stmt = count_stmt.where(exact_exam_count_filter)
            total_records = (await session.execute(count_stmt)).scalar_one() or 0

            available_counts_stmt = (
                select(leaderboard_attempts.c.exams_joined)
                .select_from(Employee)
                .join(Branch, Employee.branch_code == Branch.branch_code)
                .outerjoin(
                    leaderboard_attempts,
                    Employee.employee_id == leaderboard_attempts.c.employee_id,
                )
                .where(active_employee_filter)
                .where(leaderboard_attempts.c.exams_joined.is_not(None))
                .distinct()
                .order_by(leaderboard_attempts.c.exams_joined.asc())
            )
            if conditions:
                available_counts_stmt = available_counts_stmt.where(and_(*conditions))
            available_exam_counts = [
                int(value)
                for value in (await session.execute(available_counts_stmt)).scalars().all()
                if value is not None and int(value) > 0
            ]

            sort_columns = {
                "hr_id": Employee.hr_id,
                "name": Employee.name,
                "branch_code": Employee.branch_code,
                "exams_joined": leaderboard_attempts.c.exams_joined,
                "average_percentage": leaderboard_attempts.c.average_percentage,
            }
            selected_sort = sort_columns.get(sort_by, leaderboard_attempts.c.average_percentage)
            nulls_last_clause = case((selected_sort.is_(None), 1), else_=0).asc()
            sort_clause = selected_sort.desc() if str(sort_dir).lower() == "desc" else selected_sort.asc()

            stmt = (
                select(
                    Employee.employee_id,
                    Employee.hr_id,
                    Employee.name,
                    Employee.title,
                    Employee.department,
                    Employee.branch_code,
                    Branch.branch_name,
                    Branch.branch_region,
                    Branch.branch_area,
                    Branch.branch_division,
                    Branch.branch_sub_department,
                    leaderboard_attempts.c.exams_joined,
                    leaderboard_attempts.c.average_percentage,
                    leaderboard_attempts.c.last_submitted_at,
                )
                .select_from(Employee)
                .join(Branch, Employee.branch_code == Branch.branch_code)
                .outerjoin(
                    leaderboard_attempts,
                    Employee.employee_id == leaderboard_attempts.c.employee_id,
                )
                .where(active_employee_filter)
                .order_by(
                    nulls_last_clause,
                    sort_clause,
                    Employee.name.asc(),
                    Employee.hr_id.asc(),
                )
            )
            if conditions:
                stmt = stmt.where(and_(*conditions))
            if exact_exam_count_filter is not None:
                stmt = stmt.where(exact_exam_count_filter)
            if offset_value is not None and page_size is not None:
                stmt = stmt.offset(offset_value).limit(page_size)

            result = await session.execute(stmt)
            rows = result.all()

        performance_rows: list[dict] = []
        for row in rows:
            performance_rows.append(
                {
                    "employee_id": row.employee_id,
                    "hr_id": row.hr_id,
                    "name": row.name,
                    "title": row.title,
                    "department": row.department,
                    "branch_code": row.branch_code,
                    "branch_name": row.branch_name,
                    "region": row.branch_region,
                    "area": row.branch_area,
                    "division": row.branch_division,
                    "sub_department": row.branch_sub_department,
                    "exams_joined": int(row.exams_joined or 0),
                    "average_percentage": (
                        round(float(row.average_percentage), 2)
                        if row.average_percentage is not None
                        else None
                    ),
                    "last_submitted_at": row.last_submitted_at,
                }
            )

        return performance_rows, int(total_records), available_exam_counts

    async def get_employee_performance(
        self,
        filters: dict | None,
        period: str | None,
        exams_joined: int | None,
        page: int,
        page_size: int,
        sort_by: str = "average_percentage",
        sort_dir: str = "desc",
    ) -> tuple[tuple[list[dict], list[int]], int]:
        rows, total_records, available_exam_counts = await self._get_employee_performance_leaderboard_rows(
            filters=filters,
            period=period,
            exams_joined=exams_joined,
            sort_by=sort_by,
            sort_dir=sort_dir,
            page=page,
            page_size=page_size,
        )
        return (rows, available_exam_counts), total_records

    async def get_employee_attempts_history(self, filters: dict | None) -> list[dict]:
        conditions = self._build_employee_filter_conditions(filters)

        async with self.db_client() as session:
            stmt = (
                select(
                    Employee.hr_id,
                    Employee.name,
                    Employee.title,
                    Employee.department,
                    Employee.branch_code,
                    Branch.branch_name,
                    Branch.branch_region,
                    Branch.branch_area,
                    Branch.branch_division,
                    Branch.branch_sub_department,
                    Exam.exam_id,
                    Exam.title.label("exam_title"),
                    ExamAttempt.attempt_number,
                    ExamAttempt.total_score,
                    ExamAttempt.max_score,
                    ExamAttempt.passed,
                    ExamAttempt.started_at,
                    ExamAttempt.submitted_at,
                )
                .select_from(Employee)
                .join(Branch, Employee.branch_code == Branch.branch_code)
                .join(ExamAttempt, ExamAttempt.employee_id == Employee.employee_id)
                .join(Exam, ExamAttempt.exam_id == Exam.exam_id)
                .where(ExamAttempt.submitted_at.isnot(None))
                .order_by(Employee.hr_id, ExamAttempt.submitted_at.desc())
            )
            if conditions:
                stmt = stmt.where(and_(*conditions))

            result = await session.execute(stmt)
            rows = result.all()

        history_rows: list[dict] = []
        for row in rows:
            history_rows.append(
                {
                    "hr_id": row.hr_id,
                    "name": row.name,
                    "title": row.title,
                    "department": row.department,
                    "branch_code": row.branch_code,
                    "branch_name": row.branch_name,
                    "region": row.branch_region,
                    "area": row.branch_area,
                    "division": row.branch_division,
                    "sub_department": row.branch_sub_department,
                    "exam_id": row.exam_id,
                    "exam_title": row.exam_title,
                    "attempt_number": row.attempt_number,
                    "total_score": row.total_score,
                    "max_score": row.max_score,
                    "passed": row.passed,
                    "started_at": row.started_at,
                    "submitted_at": row.submitted_at,
                }
            )

        return history_rows

    async def get_employee_performance_export_rows(
        self,
        filters: dict | None,
        period: str | None,
        exams_joined: int | None = None,
        sort_by: str = "average_percentage",
        sort_dir: str = "desc",
    ) -> list[dict]:
        rows, _, _ = await self._get_employee_performance_leaderboard_rows(
            filters=filters,
            period=period,
            exams_joined=exams_joined,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        return rows

    async def get_employee_attempts_history_for_employee(self, employee_id: str) -> list[dict]:
        if not employee_id:
            return []

        async with self.db_client() as session:
            stmt = (
                select(
                    Employee.hr_id,
                    Employee.name,
                    Employee.title,
                    Employee.department,
                    Employee.branch_code,
                    Branch.branch_name,
                    Branch.branch_region,
                    Branch.branch_area,
                    Branch.branch_division,
                    Branch.branch_sub_department,
                    Exam.exam_id,
                    Exam.title.label("exam_title"),
                    ExamAttempt.attempt_number,
                    ExamAttempt.total_score,
                    ExamAttempt.max_score,
                    ExamAttempt.passed,
                    ExamAttempt.started_at,
                    ExamAttempt.submitted_at,
                )
                .select_from(Employee)
                .join(Branch, Employee.branch_code == Branch.branch_code)
                .join(ExamAttempt, ExamAttempt.employee_id == Employee.employee_id)
                .join(Exam, ExamAttempt.exam_id == Exam.exam_id)
                .where(Employee.employee_id == employee_id)
                .where(ExamAttempt.submitted_at.isnot(None))
                .order_by(ExamAttempt.submitted_at.desc())
            )
            result = await session.execute(stmt)
            rows = result.all()

        history_rows: list[dict] = []
        for row in rows:
            history_rows.append(
                {
                    "hr_id": row.hr_id,
                    "name": row.name,
                    "title": row.title,
                    "department": row.department,
                    "branch_code": row.branch_code,
                    "branch_name": row.branch_name,
                    "region": row.branch_region,
                    "area": row.branch_area,
                    "division": row.branch_division,
                    "sub_department": row.branch_sub_department,
                    "exam_id": row.exam_id,
                    "exam_title": row.exam_title,
                    "attempt_number": row.attempt_number,
                    "total_score": row.total_score,
                    "max_score": row.max_score,
                    "passed": row.passed,
                    "started_at": row.started_at,
                    "submitted_at": row.submitted_at,
                }
            )

        return history_rows

    async def get_number_of_attempts_for_employee_exam(self, exam_id: str, employee_id: str) -> int:
        async with self.db_client() as session:
            stmt = select(func.count(ExamAttempt.attempt_id)).where(
                (ExamAttempt.exam_id == exam_id) & (ExamAttempt.employee_id == employee_id)
            )
            result = await session.execute(stmt)
            count = result.scalar_one()
            return int(count or 0)

    async def get_answer_count_for_attempt(self, attempt_id: str) -> int:
        async with self.db_client() as session:
            stmt = select(func.count(ExamAnswer.answer_id)).where(ExamAnswer.attempt_id == attempt_id)
            result = await session.execute(stmt)
            count = result.scalar_one()
            return int(count or 0)

    async def get_number_of_attempts_for_exam(self, exam_id: str) -> int:
        async with self.db_client() as session:
            stmt = select(func.count(ExamAttempt.attempt_id)).where(ExamAttempt.exam_id == exam_id)
            result = await session.execute(stmt)
            count = result.scalar_one()
            return int(count or 0)

    async def get_exam_results_summary(self, exam_id: str) -> dict:
        async with self.db_client() as session:
            stmt = select(
                func.count(ExamAttempt.attempt_id).label("total_attempts"),
                func.avg(ExamAttempt.total_score).label("average_score"),
                # func.sum(case([(ExamAttempt.passed == True, 1)], else_=0)).label("total_passed"),
                func.count(case((ExamAttempt.passed, 1))).label("total_passed"),
            ).where((ExamAttempt.exam_id == exam_id) & (ExamAttempt.submitted_at.isnot(None)))

            result = await session.execute(stmt)
            summary = result.one()

            return {
                "total_attempts": summary.total_attempts or 0,
                "average_score": float(summary.average_score or 0.0),
                "total_passed": summary.total_passed or 0,
            }

    async def get_exam_results_details(self, exam_id: str) -> list[dict]:
        async with self.db_client() as session:
            stmt = (
                select(ExamAttempt)
                .where((ExamAttempt.exam_id == exam_id) & (ExamAttempt.submitted_at.isnot(None)))
                .options(
                    selectinload(ExamAttempt.employee).selectinload(Employee.branch),
                    selectinload(ExamAttempt.answers)
                    .selectinload(ExamAnswer.question)
                    .selectinload(Question.choices),
                    selectinload(ExamAttempt.answers).selectinload(ExamAnswer.chosen_choice),
                )
                .order_by(ExamAttempt.submitted_at.desc(), ExamAttempt.started_at.desc())
            )
            result = await session.execute(stmt)
            attempts = result.scalars().all()

            details = []
            for attempt in attempts:
                answers_payload: list[dict] = []
                for answer in attempt.answers or []:
                    question = answer.question
                    correct_choice_id = None
                    correct_choice_text = None
                    correct_choice_ids: list[str] = []
                    correct_choice_texts: list[str] = []
                    if question and getattr(question, "choices", None):
                        correct_choices = [choice for choice in question.choices if choice.is_correct]
                        if correct_choices:
                            correct_choice_ids = [choice.choice_id for choice in correct_choices]
                            correct_choice_texts = [choice.choice_text for choice in correct_choices]
                            correct_choice_id = correct_choice_ids[0]
                            correct_choice_text = ", ".join(correct_choice_texts)

                    selected_choice_ids: list[str] = []
                    if answer.chosen_choice_ids:
                        try:
                            parsed = json.loads(answer.chosen_choice_ids)
                            if isinstance(parsed, list):
                                selected_choice_ids = [str(value) for value in parsed if value]
                        except json.JSONDecodeError:
                            selected_choice_ids = []
                    elif answer.chosen_choice_id:
                        selected_choice_ids = [answer.chosen_choice_id]

                    selected_choice_texts: list[str] = []
                    if selected_choice_ids and question and getattr(question, "choices", None):
                        choice_map = {choice.choice_id: choice.choice_text for choice in question.choices}
                        selected_choice_texts = [
                            choice_map.get(choice_id, choice_id) for choice_id in selected_choice_ids
                        ]
                    selected_choice_text = ", ".join(selected_choice_texts) if selected_choice_texts else None

                    answers_payload.append(
                        {
                            "answer_id": answer.answer_id,
                            "question_id": question.question_id if question else answer.question_id,
                            "question_text": question.question_text if question else None,
                            "question_type": question.question_type if question else None,
                            "question_group": question.question_group if question else None,
                            "question_points": question.points if question else None,
                            "selected_choice_id": answer.chosen_choice_id,
                            "selected_choice_text": selected_choice_text,
                            "selected_choice_ids": selected_choice_ids,
                            "selected_choice_texts": selected_choice_texts,
                            "correct_choice_id": correct_choice_id,
                            "correct_choice_text": correct_choice_text,
                            "correct_choice_ids": correct_choice_ids,
                            "correct_choice_texts": correct_choice_texts,
                            "is_correct": answer.is_correct,
                            "points_awarded": answer.score_obtained,
                        }
                    )

                answers_payload.sort(key=lambda payload: payload.get("question_text") or "")
                attempt_payload = self._build_attempt_summary_payload(attempt)
                attempt_payload["answers"] = answers_payload
                details.append(attempt_payload)

            return details

    async def get_exam_participant_attempts(self, exam_id: str) -> list[dict]:
        async with self.db_client() as session:
            stmt = (
                select(ExamAttempt)
                .where(ExamAttempt.exam_id == exam_id)
                .options(selectinload(ExamAttempt.employee).selectinload(Employee.branch))
                .order_by(ExamAttempt.started_at.desc(), ExamAttempt.attempt_number.desc())
            )
            result = await session.execute(stmt)
            attempts = result.scalars().all()
            return [self._build_attempt_summary_payload(attempt) for attempt in attempts]

    #! =============== Delete Operations =============== !#
    async def delete_exam_by_id_softdelete(self, exam_id: str) -> bool:
        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(select(Exam).where(Exam.exam_id == exam_id))
                exam = result.scalar_one_or_none()
                if exam is None:
                    return False
                exam.is_deleted = True
                session.add(exam)
            await session.commit()
        return True

    async def delete_exam_by_id_harddelete(self, exam_id: str) -> bool:
        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(select(Exam).where(Exam.exam_id == exam_id))
                exam = result.scalar_one_or_none()
                if exam is None:
                    return False
                await session.delete(exam)
            await session.commit()
        return True

    async def restore_exam_by_id(self, exam_id: str) -> bool:
        async with self.db_client() as session:
            async with session.begin():
                query = select(Exam).where(Exam.exam_id == exam_id)
                result = await session.execute(query)
                exam = result.scalar_one_or_none()
                if exam is None:
                    return False
                exam.is_deleted = False
            await session.commit()
        return True

    async def associate_materials_to_exam(self, exam_id: str, material_ids: Sequence[str]) -> None:
        async with self.db_client() as session:
            async with session.begin():
                #  Get Exam
                exam_result = await session.execute(select(Exam).where(Exam.exam_id == exam_id))
                exam = exam_result.scalar_one_or_none()
                if exam is None:
                    raise Exception("Exam not found")

                # 2) Get all selected materials
                materials_result = await session.execute(select(Material).where(Material.material_id.in_(material_ids)))
                materials = materials_result.scalars().all()

                if not materials:
                    print("⚠ No materials found for given IDs")

                exam.materials.extend(materials)

            # 4) Commit
            await session.commit()
            await session.refresh(exam)

    async def delete_materials_from_exam(self, exam_id: str) -> None:
        async with self.db_client() as session:
            async with session.begin():
                #  Get Exam
                exam_result = await session.execute(select(Exam).where(Exam.exam_id == exam_id))
                exam = exam_result.scalar_one_or_none()
                if exam is None:
                    raise Exception("Exam not found")

                exam.materials.clear()

            # 4) Commit
            await session.commit()
            await session.refresh(exam)

    async def associate_questions_to_exam(self, exam_id: str, question_ids: Sequence[str]) -> None:
        async with self.db_client() as session:
            async with session.begin():
                #  Get Exam
                exam_result = await session.execute(select(Exam).where(Exam.exam_id == exam_id))
                exam = exam_result.scalar_one_or_none()
                if exam is None:
                    raise Exception("Exam not found")

                # 2) Get all selected Questions
                question_result = await session.execute(select(Question).where(Question.question_id.in_(question_ids)))
                questions = question_result.scalars().all()

                if not questions:
                    print("⚠ No questions found for given IDs")
                exam.questions.extend(questions)

            # 4) Commit
            await session.commit()
            await session.refresh(exam)

    async def associate_exam_employees_by_hr_ids(self, exam_id: str, hr_ids: Sequence[str]) -> None:
        async with self.db_client() as session:
            async with session.begin():
                exam_result = await session.execute(select(Exam).where(Exam.exam_id == exam_id))
                exam = exam_result.scalar_one_or_none()
                if exam is None:
                    raise Exception("Exam not found")

                exam.employees.clear()

                if hr_ids:
                    employees_result = await session.execute(
                        select(Employee).where(
                            (Employee.hr_id.in_(hr_ids))
                            & (Employee.employment_status == EMPLOYMENT_STATUS_ACTIVE)
                        )
                    )
                    employees = employees_result.scalars().all()
                    exam.employees.extend(employees)

            await session.commit()
            await session.refresh(exam)

    #! =============== Update Operations =============== !#
    async def update_exam(self, exam_id: str, updated_fields: dict) -> Exam | None:
        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(select(Exam).where(Exam.exam_id == exam_id))
                exam = result.scalar_one_or_none()
                if exam is None:
                    return None

                for field, value in updated_fields.items():
                    setattr(exam, field, value)

                session.add(exam)
            await session.commit()
            await session.refresh(exam)
            return exam

    async def get_next_attempt_number(self, exam_id: str, employee_id: str) -> int:
        async with self.db_client() as session:
            stmt = select(func.max(ExamAttempt.attempt_number)).where(
                (ExamAttempt.exam_id == exam_id) & (ExamAttempt.employee_id == employee_id)
            )
            result = await session.execute(stmt)
            max_attempt_number = result.scalar_one()
            return int(max_attempt_number or 0) + 1

    async def create_exam_attempt(self, exam_id: str, employee_id: str, attempt_number: int) -> ExamAttempt:
        async with self.db_client() as session:
            try:
                async with session.begin():
                    attempt = ExamAttempt(
                        exam_id=exam_id,
                        employee_id=employee_id,
                        attempt_number=attempt_number,
                        started_at=datetime.now(timezone.utc),
                    )
                    session.add(attempt)

                await session.commit()
                await session.refresh(attempt)
                return attempt
            except IntegrityError:
                await session.rollback()
                raise

    async def close_attempt_as_timed_out(
        self,
        attempt_id: str,
        *,
        max_score: float,
        submitted_at: datetime,
    ) -> ExamAttempt | None:
        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(select(ExamAttempt).where(ExamAttempt.attempt_id == attempt_id))
                attempt = result.scalar_one_or_none()
                if attempt is None:
                    return None
                if attempt.submitted_at is not None:
                    return attempt

                effective_submitted_at = submitted_at
                if attempt.started_at and effective_submitted_at < attempt.started_at:
                    effective_submitted_at = attempt.started_at

                attempt.total_score = 0.0
                attempt.max_score = float(max_score or 0.0)
                attempt.passed = False
                attempt.submitted_at = effective_submitted_at
                session.add(attempt)

            await session.commit()
            await session.refresh(attempt)
            return attempt

    async def delete_attempt(self, attempt_id: str) -> bool:
        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(select(ExamAttempt).where(ExamAttempt.attempt_id == attempt_id))
                attempt = result.scalar_one_or_none()
                if attempt is None:
                    return False
                await session.delete(attempt)

            await session.commit()
            return True

    async def submit_exam_attempt(
        self,
        attempt_id: str,
        exam: Exam,
        answers_map: dict[str, list[str] | None],
        passing_percent: float = 60.0,
        submitted_at: datetime | None = None,
    ) -> dict:
        # answers_map =
        # {
        #     "question_id": [choice_id, ...] | None,
        #     ...
        # }
        questions = list(exam.questions or [])
        if not questions:
            raise ValueError("This exam has no questions configured.")

        async with self.db_client() as session:
            async with session.begin():
                attempt_result = await session.execute(select(ExamAttempt).where(ExamAttempt.attempt_id == attempt_id))
                attempt = attempt_result.scalar_one_or_none()
                if attempt is None:
                    raise ValueError("No active exam session was found for this exam.")
                if attempt.submitted_at is not None:
                    raise ValueError("This exam attempt has already been submitted.")

                total_score = 0.0
                max_score = 0.0
                correct_count = 0
                answers_to_insert: list[ExamAnswer] = []

                for question in questions: # List of Question
                    if question.question_type not in {"MCQ", "TF"}:
                        raise ValueError("Only MCQ and TF questions are supported for submission.")

                    max_score += float(question.points or 0)
                    chosen_choice_ids = answers_map.get(question.question_id) or []
                    valid_choices = {choice.choice_id for choice in question.choices}
                    if any(choice_id not in valid_choices for choice_id in chosen_choice_ids):
                        raise ValueError(f"Invalid choice selected for question {question.question_id}.")

                    if question.question_type == "TF" and len(chosen_choice_ids) > 1:
                        raise ValueError(f"Question {question.question_id} only allows one answer.")

                    correct_choice_ids = {
                        choice.choice_id for choice in question.choices if choice.is_correct
                    }
                    chosen_set = set(chosen_choice_ids)
                    is_correct = bool(correct_choice_ids and chosen_set == correct_choice_ids)
                    score_obtained = float(question.points or 0) if is_correct else 0.0
                    if is_correct:
                        correct_count += 1
                        total_score += score_obtained

                    answers_to_insert.append(
                        ExamAnswer(
                            attempt_id=attempt.attempt_id,
                            question_id=question.question_id,
                            chosen_choice_id=chosen_choice_ids[0] if chosen_choice_ids else None,
                            chosen_choice_ids=json.dumps(chosen_choice_ids) if chosen_choice_ids else None,
                            is_correct=is_correct,
                            score_obtained=score_obtained,
                        )
                    )

                session.add_all(answers_to_insert)
                attempt.total_score = total_score
                attempt.max_score = max_score
                required_score = (passing_percent / 100.0) * max_score if max_score else 0.0
                attempt.passed = bool(max_score and total_score >= required_score)
                attempt.submitted_at = submitted_at or datetime.now(timezone.utc)
                session.add(attempt)

            await session.commit()
            await session.refresh(attempt)

        return {
            "attempt_id": attempt.attempt_id,
            "total_score": total_score,
            "max_score": max_score,
            "correct_answers": correct_count,
            "total_questions": len(questions),
            "percentage": (total_score / max_score * 100) if max_score else 0,
            "passed": attempt.passed,
            "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
        }
