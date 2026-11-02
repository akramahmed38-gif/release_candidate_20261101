from __future__ import annotations

import asyncio
import json
import os
import socket
import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import and_, case, desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.db_schemas import Branch, Employee, EmploymentStatusHistory
from utils.audit_trail import build_audit_event, append_audit_event, parse_datetime_value, read_audit_events


SessionMaker = Callable[[], AsyncSession]

UTC = timezone.utc

EMPLOYMENT_STATUS_ACTIVE = "active"
EMPLOYMENT_STATUS_RESIGNED = "resigned"

RESIGNATION_TYPE_AUTOMATIC = "automatic_inactivity"
RESIGNATION_TYPE_MANUAL = "manual_admin"

STATUS_CHANGE_AUTOMATIC = "automatic_inactivity"
STATUS_CHANGE_REACTIVATION = "admin_reactivation"

LOGIN_HISTORY_STATE_PENDING = "pending_backfill"
LOGIN_HISTORY_STATE_NATIVE = "native_tracking"
LOGIN_HISTORY_STATE_MATCHED_LOGIN = "matched_login_event"
LOGIN_HISTORY_STATE_MATCHED_ACTIVITY = "matched_authenticated_activity"
LOGIN_HISTORY_STATE_UNVERIFIED = "unverified_historical"

USER_LOGIN_SUCCESS = "USER_LOGIN_SUCCESS"
USER_AUTO_RESIGNED = "USER_AUTO_RESIGNED"
USER_REACTIVATED = "USER_REACTIVATED"
LOGIN_HISTORY_BACKFILLED = "LOGIN_HISTORY_BACKFILLED"
AUTO_RESIGN_JOB_TRIGGERED = "AUTO_RESIGN_JOB_TRIGGERED"

AUTO_RESIGN_JOB_NAME = "auto_resign_users_daily"
DEFAULT_LAST_ACTIVITY_TOUCH_MINUTES = 15
DEFAULT_SCHEDULE_HOUR_UTC = 2
DEFAULT_SCHEDULE_MINUTE_UTC = 0
DEFAULT_JOB_LOCK_MINUTES = 30
DEFAULT_INACTIVITY_DAYS = 90

INACTIVE_ACCOUNT_MESSAGE = "Your account is inactive. Please contact the system administrator."

RESIGNED_USERS_SORT_ALLOWLIST = {
    "employee_name": "employee_name",
    "name": "employee_name",
    "hr_id": "hr_id",
    "last_login_at": "last_login_at",
    "last_activity_at": "last_activity_at",
    "resigned_at": "resigned_at",
    "inactivity_days": "inactivity_days",
}


def now_utc() -> datetime:
    return datetime.now(UTC)


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def normalize_role(value: str | None) -> str:
    return (value or "").strip().lower()


def derive_username(email: str | None) -> str:
    normalized = (email or "").strip()
    if "@" not in normalized:
        return normalized
    return normalized.split("@", 1)[0]


def normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def make_json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        normalized = normalize_datetime(value)
        return normalized.isoformat() if normalized is not None else value.isoformat()
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [make_json_safe(item) for item in value]
    if isinstance(value, set):
        return [make_json_safe(item) for item in sorted(value, key=lambda item: str(item))]
    return value


def _greatest_dt(*values: datetime | None) -> datetime | None:
    normalized = [normalize_datetime(value) for value in values if value is not None]
    if not normalized:
        return None
    return max(normalized)


def get_inactivity_days(reference_at: datetime | None, *, reference_now: datetime | None = None) -> int | None:
    if reference_at is None:
        return None
    current_now = normalize_datetime(reference_now) or now_utc()
    reference_value = normalize_datetime(reference_at)
    if reference_value is None:
        return None
    return max((current_now - reference_value).days, 0)


def get_employee_employment_status(user: Employee | Any | None) -> str:
    status = normalize_role(getattr(user, "employment_status", None))
    return status or EMPLOYMENT_STATUS_ACTIVE


def is_employee_resigned(user: Employee | Any | None) -> bool:
    return get_employee_employment_status(user) == EMPLOYMENT_STATUS_RESIGNED


def is_employee_active(user: Employee | Any | None) -> bool:
    return get_employee_employment_status(user) == EMPLOYMENT_STATUS_ACTIVE


def build_activity_reference(user: Employee | Any, *, include_historical_activity_fallback: bool = True) -> datetime | None:
    last_login_at = normalize_datetime(getattr(user, "last_login_at", None))
    reactivated_at = normalize_datetime(getattr(user, "reactivated_at", None))
    created_at = normalize_datetime(getattr(user, "created_at", None))
    if last_login_at is not None:
        return _greatest_dt(last_login_at, reactivated_at, created_at)

    login_history_state = getattr(user, "login_history_state", None)
    if include_historical_activity_fallback and login_history_state == LOGIN_HISTORY_STATE_MATCHED_ACTIVITY:
        return _greatest_dt(getattr(user, "last_activity_at", None), reactivated_at, created_at)

    return _greatest_dt(reactivated_at, created_at)


def build_activity_reference_expression():
    return case(
        (
            and_(
                Employee.last_login_at.isnot(None),
                or_(Employee.reactivated_at.is_(None), Employee.last_login_at >= Employee.reactivated_at),
            ),
            Employee.last_login_at,
        ),
        (
            Employee.reactivated_at.isnot(None),
            Employee.reactivated_at,
        ),
        (
            and_(
                Employee.login_history_state == LOGIN_HISTORY_STATE_MATCHED_ACTIVITY,
                Employee.last_activity_at.isnot(None),
            ),
            Employee.last_activity_at,
        ),
        else_=Employee.created_at,
    )


def is_protected_account(user: Employee | Any | None) -> bool:
    if user is None:
        return True
    if bool(getattr(user, "auto_resign_exempt", False)):
        return True
    email = normalize_email(getattr(user, "email", None))
    role = normalize_role(getattr(user, "department", None))
    if email in {"admin", "admin@fawry.com", "management"}:
        return True
    if role in {"system", "service", "scheduler"}:
        return True
    return False


def build_inactive_account_response() -> dict[str, Any]:
    return {
        "signal": "inactive_user",
        "message": INACTIVE_ACCOUNT_MESSAGE,
    }


def should_exclude_unverified_from_auto_resign(user: Employee | Any) -> bool:
    state = getattr(user, "login_history_state", None)
    return state in {LOGIN_HISTORY_STATE_PENDING, LOGIN_HISTORY_STATE_UNVERIFIED}


def get_configured_inactivity_days() -> int:
    raw_value = (os.getenv("USER_AUTO_RESIGN_INACTIVITY_DAYS") or "").strip()
    if not raw_value:
        return DEFAULT_INACTIVITY_DAYS
    try:
        return max(int(raw_value), 1)
    except Exception:
        return DEFAULT_INACTIVITY_DAYS


def get_auto_resign_effective_from() -> datetime | None:
    raw_value = (os.getenv("USER_AUTO_RESIGN_EFFECTIVE_FROM_UTC") or "").strip()
    if not raw_value:
        return None
    return normalize_datetime(parse_datetime_value(raw_value))


def is_auto_resign_enabled() -> bool:
    raw_value = (os.getenv("AUTO_RESIGN_USERS_ENABLED") or "true").strip().lower()
    return raw_value in {"1", "true", "yes", "y", "on"}


def get_last_activity_touch_minutes() -> int:
    raw_value = (os.getenv("USER_ACTIVITY_TOUCH_INTERVAL_MINUTES") or "").strip()
    if not raw_value:
        return DEFAULT_LAST_ACTIVITY_TOUCH_MINUTES
    try:
        return max(int(raw_value), 1)
    except Exception:
        return DEFAULT_LAST_ACTIVITY_TOUCH_MINUTES


def get_auto_resign_schedule_time_utc() -> tuple[int, int]:
    raw_hour = (os.getenv("AUTO_RESIGN_USERS_RUN_HOUR_UTC") or "").strip()
    raw_minute = (os.getenv("AUTO_RESIGN_USERS_RUN_MINUTE_UTC") or "").strip()
    try:
        hour = min(max(int(raw_hour), 0), 23) if raw_hour else DEFAULT_SCHEDULE_HOUR_UTC
    except Exception:
        hour = DEFAULT_SCHEDULE_HOUR_UTC
    try:
        minute = min(max(int(raw_minute), 0), 59) if raw_minute else DEFAULT_SCHEDULE_MINUTE_UTC
    except Exception:
        minute = DEFAULT_SCHEDULE_MINUTE_UTC
    return hour, minute


def get_job_lock_minutes() -> int:
    raw_value = (os.getenv("AUTO_RESIGN_JOB_LOCK_MINUTES") or "").strip()
    if not raw_value:
        return DEFAULT_JOB_LOCK_MINUTES
    try:
        return max(int(raw_value), 1)
    except Exception:
        return DEFAULT_JOB_LOCK_MINUTES


def build_auto_resign_reference(user: Employee | Any) -> datetime | None:
    activity_reference_at = build_activity_reference(user)
    effective_from = get_auto_resign_effective_from()
    if effective_from is None:
        return activity_reference_at
    return _greatest_dt(activity_reference_at, effective_from)


async def ensure_resigned_users_runtime_schema(conn, logger) -> None:
    employee_columns = {row[1] for row in (await conn.exec_driver_sql("PRAGMA table_info(employees)")).fetchall()}
    additions = {
        "employment_status": "ALTER TABLE employees ADD COLUMN employment_status VARCHAR(20) NOT NULL DEFAULT 'active'",
        "last_login_at": "ALTER TABLE employees ADD COLUMN last_login_at DATETIME",
        "last_activity_at": "ALTER TABLE employees ADD COLUMN last_activity_at DATETIME",
        "resigned_at": "ALTER TABLE employees ADD COLUMN resigned_at DATETIME",
        "resigned_reason": "ALTER TABLE employees ADD COLUMN resigned_reason VARCHAR(255)",
        "resignation_type": "ALTER TABLE employees ADD COLUMN resignation_type VARCHAR(50)",
        "resigned_by": "ALTER TABLE employees ADD COLUMN resigned_by VARCHAR(255)",
        "reactivated_at": "ALTER TABLE employees ADD COLUMN reactivated_at DATETIME",
        "reactivated_by": "ALTER TABLE employees ADD COLUMN reactivated_by VARCHAR(255)",
        "auto_resign_exempt": "ALTER TABLE employees ADD COLUMN auto_resign_exempt BOOLEAN NOT NULL DEFAULT 0",
        "login_history_state": (
            "ALTER TABLE employees ADD COLUMN login_history_state VARCHAR(50) "
            "NOT NULL DEFAULT 'pending_backfill'"
        ),
    }
    for column_name, statement in additions.items():
        if column_name in employee_columns:
            continue
        await conn.exec_driver_sql(statement)
        if logger:
            logger.info("Database migration applied: added employees.%s column", column_name)

    runtime_indexes = [
        "CREATE INDEX IF NOT EXISTS ix_employees_employment_status ON employees (employment_status)",
        "CREATE INDEX IF NOT EXISTS ix_employees_last_login_at ON employees (last_login_at)",
        "CREATE INDEX IF NOT EXISTS ix_employees_resigned_at ON employees (resigned_at)",
        "CREATE INDEX IF NOT EXISTS ix_employees_auto_resign_exempt ON employees (auto_resign_exempt)",
        "CREATE INDEX IF NOT EXISTS ix_employees_login_history_state ON employees (login_history_state)",
        "CREATE INDEX IF NOT EXISTS ix_employment_status_history_employee_id ON employment_status_history (employee_id)",
        "CREATE INDEX IF NOT EXISTS ix_employment_status_history_change_type ON employment_status_history (change_type)",
        "CREATE INDEX IF NOT EXISTS ix_employment_status_history_changed_at ON employment_status_history (changed_at)",
        "CREATE INDEX IF NOT EXISTS ix_maintenance_job_locks_locked_until ON maintenance_job_locks (locked_until)",
    ]
    for statement in runtime_indexes:
        await conn.exec_driver_sql(statement)


def serialize_run_item(item: dict[str, Any]) -> dict[str, Any]:
    return make_json_safe(dict(item))


def _build_custom_audit_event(
    *,
    action: str,
    actor_email: str,
    actor_role: str,
    path: str,
    details: dict[str, Any],
    result: str = "success",
    status_code: int = 200,
) -> dict[str, Any]:
    return build_audit_event(
        actor_email=actor_email,
        actor_role=actor_role,
        method="SYSTEM",
        path=path,
        query="",
        status_code=status_code,
        duration_ms=0,
        ip_address="-",
        user_agent="hr-training-system",
        action=action,
        result=result,
        details=json.dumps(details, ensure_ascii=False),
    )


class ResignedUsersService:
    def __init__(self, db_client: SessionMaker, app=None) -> None:
        self.db_client = db_client
        self.app = app
        self.instance_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"

    @classmethod
    async def create_instance(cls, db_client: SessionMaker, app=None):
        return cls(db_client=db_client, app=app)

    async def ensure_default_protected_accounts(self) -> None:
        async with self.db_client() as session:
            async with session.begin():
                users = (
                    await session.execute(
                        select(Employee).where(
                            or_(
                                func.lower(Employee.email).in_(["admin", "admin@fawry.com", "management"]),
                                func.lower(Employee.department).in_(["manager"]),
                            )
                        )
                    )
                ).scalars().all()
                for user in users:
                    user.auto_resign_exempt = True
                    if user.login_history_state == LOGIN_HISTORY_STATE_PENDING:
                        user.login_history_state = LOGIN_HISTORY_STATE_NATIVE
                    session.add(user)

    async def get_employee_by_email(self, email: str | None) -> Employee | None:
        normalized_email = normalize_email(email)
        if not normalized_email:
            return None
        async with self.db_client() as session:
            result = await session.execute(
                select(Employee)
                .options(selectinload(Employee.branch))
                .where(func.lower(Employee.email) == normalized_email)
            )
            return result.scalar_one_or_none()

    async def get_employee_by_id(self, employee_id: str | None) -> Employee | None:
        if not employee_id:
            return None
        async with self.db_client() as session:
            result = await session.execute(
                select(Employee)
                .options(selectinload(Employee.branch))
                .where(Employee.employee_id == employee_id)
            )
            return result.scalar_one_or_none()

    async def mark_successful_login(self, email: str, *, actor_role: str | None = None) -> Employee | None:
        normalized_email = normalize_email(email)
        if not normalized_email:
            return None
        current_now = now_utc()
        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(
                    select(Employee).where(func.lower(Employee.email) == normalized_email)
                )
                employee = result.scalar_one_or_none()
                if employee is None:
                    return None
                employee.last_login_at = current_now
                employee.last_activity_at = current_now
                employee.login_history_state = LOGIN_HISTORY_STATE_NATIVE
                employee.updated_at = current_now
                session.add(employee)
            await session.refresh(employee)

        if self.app is not None:
            append_audit_event(
                self.app,
                _build_custom_audit_event(
                    action=USER_LOGIN_SUCCESS,
                    actor_email=normalized_email,
                    actor_role=normalize_role(actor_role) or normalize_role(getattr(employee, "department", None)) or "employee",
                    path="/api/v1/users/login",
                    details={
                        "employee_id": employee.employee_id,
                        "target_employee_email": employee.email,
                        "employment_status": employee.employment_status,
                    },
                ),
            )
        return employee

    async def maybe_touch_last_activity(self, email: str | None, *, force: bool = False) -> None:
        normalized_email = normalize_email(email)
        if not normalized_email:
            return
        current_now = now_utc()
        minimum_interval = timedelta(minutes=get_last_activity_touch_minutes())
        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(
                    select(Employee).where(func.lower(Employee.email) == normalized_email)
                )
                employee = result.scalar_one_or_none()
                if employee is None or is_employee_resigned(employee):
                    return
                current_last_activity = normalize_datetime(employee.last_activity_at)
                if not force and current_last_activity is not None and current_now - current_last_activity < minimum_interval:
                    return
                employee.last_activity_at = current_now
                employee.updated_at = current_now
                if employee.login_history_state == LOGIN_HISTORY_STATE_PENDING:
                    employee.login_history_state = LOGIN_HISTORY_STATE_NATIVE
                session.add(employee)

    async def try_acquire_job_lock(self, *, job_name: str, now: datetime | None = None) -> bool:
        current_now = normalize_datetime(now) or now_utc()
        locked_until = current_now + timedelta(minutes=get_job_lock_minutes())
        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(
                    text(
                        """
                        INSERT INTO maintenance_job_locks (
                            job_name, locked_until, locked_by, last_started_at, last_status, updated_at
                        )
                        VALUES (:job_name, :locked_until, :locked_by, :started_at, :last_status, :updated_at)
                        ON CONFLICT(job_name) DO UPDATE SET
                            locked_until = excluded.locked_until,
                            locked_by = excluded.locked_by,
                            last_started_at = excluded.last_started_at,
                            last_status = excluded.last_status,
                            updated_at = excluded.updated_at
                        WHERE maintenance_job_locks.locked_until IS NULL
                           OR maintenance_job_locks.locked_until <= :now_value
                           OR maintenance_job_locks.locked_by = :locked_by
                        """
                    ),
                    {
                        "job_name": job_name,
                        "locked_until": locked_until,
                        "locked_by": self.instance_id,
                        "started_at": current_now,
                        "last_status": "running",
                        "updated_at": current_now,
                        "now_value": current_now,
                    },
                )
                return bool(result.rowcount)

    async def release_job_lock(
        self,
        *,
        job_name: str,
        status_text: str,
        report: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> None:
        current_now = normalize_datetime(now) or now_utc()
        serialized_report = json.dumps(make_json_safe(report or {}), ensure_ascii=False)
        async with self.db_client() as session:
            async with session.begin():
                await session.execute(
                    text(
                        """
                        UPDATE maintenance_job_locks
                        SET locked_until = :locked_until,
                            last_finished_at = :last_finished_at,
                            last_status = :last_status,
                            last_report = :last_report,
                            updated_at = :updated_at
                        WHERE job_name = :job_name AND locked_by = :locked_by
                        """
                    ),
                    {
                        "job_name": job_name,
                        "locked_by": self.instance_id,
                        "locked_until": current_now,
                        "last_finished_at": current_now,
                        "last_status": status_text,
                        "last_report": serialized_report,
                        "updated_at": current_now,
                    },
                )

    def _build_resigned_users_query_parts(
        self,
        *,
        search: str | None = None,
        branch_id: str | None = None,
        role: str | None = None,
        resignation_type: str | None = None,
        resigned_from: str | None = None,
        resigned_to: str | None = None,
        sort_by: str = "resigned_at",
        sort_dir: str = "desc",
    ) -> dict[str, Any]:
        activity_reference_expr = build_activity_reference_expression().label("activity_reference_at")
        inactivity_sort_expr = activity_reference_expr
        resigned_from_dt = parse_datetime_value(resigned_from)
        resigned_to_dt = parse_datetime_value(resigned_to)
        search_value = (search or "").strip().lower()
        normalized_role = normalize_role(role)
        branch_value = (branch_id or "").strip()
        resignation_type_value = (resignation_type or "").strip()
        normalized_sort_key = RESIGNED_USERS_SORT_ALLOWLIST.get(sort_by, "resigned_at")
        sort_desc = str(sort_dir or "desc").lower() != "asc"

        filters = [Employee.employment_status == EMPLOYMENT_STATUS_RESIGNED]
        if search_value:
            pattern = f"%{search_value}%"
            filters.append(
                or_(
                    func.lower(Employee.name).like(pattern),
                    func.lower(Employee.hr_id).like(pattern),
                    func.lower(Employee.email).like(pattern),
                    func.lower(Employee.branch_code).like(pattern),
                    func.lower(Employee.department).like(pattern),
                    func.lower(Branch.branch_name).like(pattern),
                )
            )
        if branch_value:
            branch_pattern = branch_value.lower()
            filters.append(
                or_(
                    Employee.branch_code == branch_value,
                    func.lower(Branch.branch_name).like(f"%{branch_pattern}%"),
                )
            )
        if normalized_role:
            filters.append(func.lower(Employee.department) == normalized_role)
        if resignation_type_value:
            filters.append(Employee.resignation_type == resignation_type_value)
        if resigned_from_dt is not None:
            filters.append(Employee.resigned_at >= resigned_from_dt)
        if resigned_to_dt is not None:
            filters.append(Employee.resigned_at <= resigned_to_dt)

        sort_expression_map = {
            "employee_name": func.lower(Employee.name),
            "hr_id": Employee.hr_id,
            "last_login_at": Employee.last_login_at,
            "last_activity_at": Employee.last_activity_at,
            "resigned_at": Employee.resigned_at,
            "inactivity_days": inactivity_sort_expr,
        }
        sort_expression = sort_expression_map.get(normalized_sort_key, Employee.resigned_at)
        order_by_clause = desc(sort_expression) if sort_desc else sort_expression.asc()
        if normalized_sort_key == "inactivity_days":
            order_by_clause = sort_expression.asc() if sort_desc else desc(sort_expression)

        base_stmt = (
            select(Employee, Branch, activity_reference_expr)
            .outerjoin(Branch, Employee.branch_code == Branch.branch_code)
            .where(and_(*filters))
        )
        count_stmt = select(func.count()).select_from(
            select(Employee.employee_id)
            .outerjoin(Branch, Employee.branch_code == Branch.branch_code)
            .where(and_(*filters))
            .subquery()
        )

        return {
            "filters": filters,
            "activity_reference_expr": activity_reference_expr,
            "normalized_sort_key": normalized_sort_key,
            "sort_desc": sort_desc,
            "order_by_clause": order_by_clause,
            "base_stmt": base_stmt,
            "count_stmt": count_stmt,
        }

    def _build_resigned_list_item(
        self,
        employee: Employee,
        branch: Branch | None,
        *,
        activity_reference: datetime | None,
        reference_now: datetime,
    ) -> dict[str, Any]:
        inactivity_days = get_inactivity_days(activity_reference, reference_now=reference_now)
        return {
            "employee_id": employee.employee_id,
            "employee_name": employee.name,
            "hr_id": employee.hr_id,
            "username": derive_username(employee.email),
            "email": employee.email,
            "branch_code": employee.branch_code,
            "branch_name": getattr(branch, "branch_name", None),
            "role": employee.department,
            "last_login_at": employee.last_login_at,
            "last_activity_at": employee.last_activity_at,
            "resigned_at": employee.resigned_at,
            "inactivity_days": inactivity_days,
            "resignation_type": employee.resignation_type,
            "resigned_reason": employee.resigned_reason,
            "resigned_by": employee.resigned_by,
            "reactivated_at": employee.reactivated_at,
            "reactivated_by": employee.reactivated_by,
            "employment_status": employee.employment_status,
        }

    def _apply_reactivation_to_employee(
        self,
        session: AsyncSession,
        *,
        employee: Employee,
        actor_email: str,
        current_now: datetime,
        note: str | None,
    ) -> None:
        previous_status = employee.employment_status
        employee.employment_status = EMPLOYMENT_STATUS_ACTIVE
        employee.reactivated_at = current_now
        employee.reactivated_by = actor_email
        employee.resigned_at = None
        employee.resigned_reason = None
        employee.resignation_type = None
        employee.resigned_by = None
        employee.updated_at = current_now
        session.add(employee)
        session.add(
            EmploymentStatusHistory(
                employee_id=employee.employee_id,
                previous_status=previous_status,
                new_status=EMPLOYMENT_STATUS_ACTIVE,
                change_type=STATUS_CHANGE_REACTIVATION,
                reason=(note or "").strip() or "Admin reactivation",
                changed_at=current_now,
                changed_by=actor_email,
                metadata_json=json.dumps(
                    {
                        "target_employee_email": employee.email,
                        "target_hr_id": employee.hr_id,
                    },
                    ensure_ascii=False,
                ),
            )
        )

    async def list_resigned_users(
        self,
        *,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
        branch_id: str | None = None,
        role: str | None = None,
        resignation_type: str | None = None,
        resigned_from: str | None = None,
        resigned_to: str | None = None,
        sort_by: str = "resigned_at",
        sort_dir: str = "desc",
    ) -> dict[str, Any]:
        query_parts = self._build_resigned_users_query_parts(
            search=search,
            branch_id=branch_id,
            role=role,
            resignation_type=resignation_type,
            resigned_from=resigned_from,
            resigned_to=resigned_to,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

        async with self.db_client() as session:
            total_records = int((await session.execute(query_parts["count_stmt"])).scalar_one() or 0)
            result = await session.execute(
                query_parts["base_stmt"]
                .order_by(query_parts["order_by_clause"], func.lower(Employee.name), Employee.hr_id)
                .offset(max(page - 1, 0) * page_size)
                .limit(page_size)
            )
            rows = result.all()

        current_now = now_utc()
        items: list[dict[str, Any]] = []
        for employee, branch, activity_reference in rows:
            items.append(
                self._build_resigned_list_item(
                    employee,
                    branch,
                    activity_reference=activity_reference,
                    reference_now=current_now,
                )
            )

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total_records": total_records,
            "sort_by": query_parts["normalized_sort_key"],
            "sort_dir": "desc" if query_parts["sort_desc"] else "asc",
        }

    async def get_resigned_users_export_rows(self, **kwargs) -> list[dict[str, Any]]:
        query_kwargs = dict(kwargs)
        query_kwargs["page"] = 1
        query_kwargs["page_size"] = 100000
        payload = await self.list_resigned_users(**query_kwargs)
        return payload["items"]

    async def reactivate_resigned_users_bulk(
        self,
        *,
        actor_email: str,
        actor_role: str,
        note: str | None,
        search: str | None = None,
        branch_id: str | None = None,
        role: str | None = None,
        resignation_type: str | None = None,
        resigned_from: str | None = None,
        resigned_to: str | None = None,
        sort_by: str = "resigned_at",
        sort_dir: str = "desc",
    ) -> dict[str, Any]:
        query_parts = self._build_resigned_users_query_parts(
            search=search,
            branch_id=branch_id,
            role=role,
            resignation_type=resignation_type,
            resigned_from=resigned_from,
            resigned_to=resigned_to,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        current_now = now_utc()
        note_text = (note or "").strip() or "Bulk admin reactivation"

        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(
                    query_parts["base_stmt"].order_by(
                        query_parts["order_by_clause"],
                        func.lower(Employee.name),
                        Employee.hr_id,
                    )
                )
                rows = result.all()
                items: list[dict[str, Any]] = []
                employee_ids: list[str] = []
                for employee, branch, activity_reference in rows:
                    self._apply_reactivation_to_employee(
                        session,
                        employee=employee,
                        actor_email=actor_email,
                        current_now=current_now,
                        note=note_text,
                    )
                    employee_ids.append(employee.employee_id)
                    items.append(
                        self._build_resigned_list_item(
                            employee,
                            branch,
                            activity_reference=activity_reference,
                            reference_now=current_now,
                        )
                    )

        if self.app is not None:
            append_audit_event(
                self.app,
                _build_custom_audit_event(
                    action=USER_REACTIVATED,
                    actor_email=actor_email,
                    actor_role=actor_role,
                    path="/api/v1/admin/resigned-users/reactivate-all",
                    details={
                        "bulk": True,
                        "updated_users": len(employee_ids),
                        "reason": note_text,
                        "filters": {
                            "search": search,
                            "branch_id": branch_id,
                            "role": role,
                            "resignation_type": resignation_type,
                            "resigned_from": resigned_from,
                            "resigned_to": resigned_to,
                            "sort_by": sort_by,
                            "sort_dir": sort_dir,
                        },
                        "employee_ids_preview": employee_ids[:50],
                    },
                ),
            )

        return {
            "updated_users": len(employee_ids),
            "reactivated_at": current_now,
            "reactivated_by": actor_email,
            "items": items,
        }

    async def reactivate_user(
        self,
        *,
        employee_id: str,
        actor_email: str,
        actor_role: str,
        note: str | None,
    ) -> dict[str, Any]:
        current_now = now_utc()
        async with self.db_client() as session:
            async with session.begin():
                result = await session.execute(
                    select(Employee).where(Employee.employee_id == employee_id)
                )
                employee = result.scalar_one_or_none()
                if employee is None:
                    raise ValueError("Employee not found")
                if employee.employment_status != EMPLOYMENT_STATUS_RESIGNED:
                    raise ValueError("Employee is not resigned")

                self._apply_reactivation_to_employee(
                    session,
                    employee=employee,
                    actor_email=actor_email,
                    current_now=current_now,
                    note=note,
                )
            await session.refresh(employee)

        if self.app is not None:
            append_audit_event(
                self.app,
                _build_custom_audit_event(
                    action=USER_REACTIVATED,
                    actor_email=actor_email,
                    actor_role=actor_role,
                    path=f"/api/v1/admin/users/{employee_id}/reactivate",
                    details={
                        "employee_id": employee.employee_id,
                        "target_employee_email": employee.email,
                        "previous_status": EMPLOYMENT_STATUS_RESIGNED,
                        "new_status": EMPLOYMENT_STATUS_ACTIVE,
                        "reason": (note or "").strip() or "Admin reactivation",
                    },
                ),
            )

        return {
            "employee_id": employee.employee_id,
            "employment_status": employee.employment_status,
            "reactivated_at": employee.reactivated_at,
            "reactivated_by": employee.reactivated_by,
        }

    def _build_backfill_report_item(
        self,
        employee: Employee,
        *,
        last_explicit_login: datetime | None,
        last_authenticated_activity: datetime | None,
        match_source: str,
        inactivity_days: int | None,
        would_be_resigned: bool,
        exclusion_reason: str | None = None,
    ) -> dict[str, Any]:
        return {
            "employee_id": employee.employee_id,
            "employee_name": employee.name,
            "hr_id": employee.hr_id,
            "email": employee.email,
            "last_explicit_login": last_explicit_login,
            "last_authenticated_activity": last_authenticated_activity,
            "match_source": match_source,
            "inactivity_days": inactivity_days,
            "would_be_resigned": would_be_resigned,
            "exclusion_reason": exclusion_reason,
        }

    def _latest_reliable_audit_matches(self, audit_rows: list[dict[str, Any]]) -> dict[str, dict[str, datetime | None]]:
        latest_by_email: dict[str, dict[str, datetime | None]] = {}
        for row in audit_rows:
            actor_email = normalize_email(row.get("actor_email"))
            if not actor_email or actor_email == "anonymous":
                continue
            actor_role = normalize_role(row.get("actor_role"))
            if actor_role in {"system", "service", "scheduler"}:
                continue
            path = str(row.get("path") or "")
            if not path.startswith("/api/"):
                continue
            if path in {"/api/v1/users/login/request-otp"}:
                continue
            status_code = int(row.get("status_code") or 0)
            if status_code < 200 or status_code >= 400:
                continue

            timestamp_value = parse_datetime_value(row.get("timestamp_utc"))
            if timestamp_value is None:
                continue

            bucket = latest_by_email.setdefault(
                actor_email,
                {"login": None, "activity": None},
            )

            action = str(row.get("action") or "")
            if action == USER_LOGIN_SUCCESS or path == "/api/v1/users/login":
                if bucket["login"] is None or timestamp_value > bucket["login"]:
                    bucket["login"] = timestamp_value

            if path not in {"/api/v1/users/login", "/api/v1/users/login/request-otp", "/api/v1/users/refresh"}:
                if bucket["activity"] is None or timestamp_value > bucket["activity"]:
                    bucket["activity"] = timestamp_value

        return latest_by_email

    async def run_login_history_backfill(
        self,
        *,
        dry_run: bool,
        actor_email: str,
        actor_role: str,
    ) -> dict[str, Any]:
        audit_rows = read_audit_events(self.app) if self.app is not None else []
        latest_by_email = self._latest_reliable_audit_matches(audit_rows)
        oldest_audit = None
        newest_audit = None
        for row in audit_rows:
            parsed = parse_datetime_value(row.get("timestamp_utc"))
            if parsed is None:
                continue
            if oldest_audit is None or parsed < oldest_audit:
                oldest_audit = parsed
            if newest_audit is None or parsed > newest_audit:
                newest_audit = parsed

        inactivity_days = get_configured_inactivity_days()
        current_now = now_utc()
        inactivity_cutoff = current_now - timedelta(days=inactivity_days)

        async with self.db_client() as session:
            employees = (
                await session.execute(
                    select(Employee).options(selectinload(Employee.branch))
                )
            ).scalars().all()

        matched_by_login_event = 0
        matched_by_authenticated_activity = 0
        users_without_history = 0
        ambiguous_users = 0
        report_items: list[dict[str, Any]] = []
        updates: list[dict[str, Any]] = []
        eligible_for_resignation = 0

        for employee in employees:
            email = normalize_email(employee.email)
            match_bundle = latest_by_email.get(email)
            last_explicit_login = normalize_datetime(match_bundle.get("login")) if match_bundle else None
            last_authenticated_activity = normalize_datetime(match_bundle.get("activity")) if match_bundle else None

            match_source = "none"
            if last_explicit_login is not None:
                matched_by_login_event += 1
                match_source = LOGIN_HISTORY_STATE_MATCHED_LOGIN
            elif last_authenticated_activity is not None:
                matched_by_authenticated_activity += 1
                match_source = LOGIN_HISTORY_STATE_MATCHED_ACTIVITY
            else:
                users_without_history += 1
                match_source = LOGIN_HISTORY_STATE_UNVERIFIED

            candidate_reference = (
                last_explicit_login
                or last_authenticated_activity
                or normalize_datetime(employee.reactivated_at)
                or normalize_datetime(employee.created_at)
            )
            inactivity_value = get_inactivity_days(candidate_reference, reference_now=current_now)
            would_be_resigned = bool(
                candidate_reference is not None
                and candidate_reference <= inactivity_cutoff
                and not is_protected_account(employee)
                and match_source != LOGIN_HISTORY_STATE_UNVERIFIED
                and employee.employment_status == EMPLOYMENT_STATUS_ACTIVE
            )
            if would_be_resigned:
                eligible_for_resignation += 1

            report_items.append(
                self._build_backfill_report_item(
                    employee,
                    last_explicit_login=last_explicit_login,
                    last_authenticated_activity=last_authenticated_activity,
                    match_source=match_source,
                    inactivity_days=inactivity_value,
                    would_be_resigned=would_be_resigned,
                    exclusion_reason="No verifiable audit history" if match_source == LOGIN_HISTORY_STATE_UNVERIFIED else None,
                )
            )

            if dry_run:
                continue

            updates.append(
                {
                    "employee_id": employee.employee_id,
                    "last_login_at": last_explicit_login,
                    "last_activity_at": last_authenticated_activity,
                    "login_history_state": match_source,
                }
            )

        if not dry_run and updates:
            async with self.db_client() as session:
                async with session.begin():
                    for payload in updates:
                        result = await session.execute(
                            select(Employee).where(Employee.employee_id == payload["employee_id"])
                        )
                        employee = result.scalar_one_or_none()
                        if employee is None:
                            continue
                        new_last_login_at = payload["last_login_at"]
                        new_last_activity_at = payload["last_activity_at"]
                        if new_last_login_at is not None and (
                            employee.last_login_at is None or normalize_datetime(new_last_login_at) > normalize_datetime(employee.last_login_at)
                        ):
                            employee.last_login_at = new_last_login_at
                        if new_last_activity_at is not None and (
                            employee.last_activity_at is None or normalize_datetime(new_last_activity_at) > normalize_datetime(employee.last_activity_at)
                        ):
                            employee.last_activity_at = new_last_activity_at
                        employee.login_history_state = payload["login_history_state"]
                        employee.updated_at = current_now
                        session.add(employee)

            if self.app is not None:
                append_audit_event(
                    self.app,
                    _build_custom_audit_event(
                        action=LOGIN_HISTORY_BACKFILLED,
                        actor_email=actor_email,
                        actor_role=actor_role,
                        path="/api/v1/admin/resigned-users/backfill-login-history",
                        details={
                            "dry_run": False,
                            "matched_by_login_event": matched_by_login_event,
                            "matched_by_authenticated_activity": matched_by_authenticated_activity,
                            "users_without_history": users_without_history,
                            "eligible_for_resignation": eligible_for_resignation,
                        },
                    ),
                )

        return {
            "dry_run": dry_run,
            "configured_inactivity_days": inactivity_days,
            "total_active_users": len([employee for employee in employees if is_employee_active(employee)]),
            "matched_by_login_event": matched_by_login_event,
            "matched_by_authenticated_activity": matched_by_authenticated_activity,
            "users_without_history": users_without_history,
            "ambiguous_users": ambiguous_users,
            "oldest_audit_record": oldest_audit,
            "newest_audit_record": newest_audit,
            "eligible_for_resignation": eligible_for_resignation,
            "items": report_items,
        }

    async def run_inactivity_check(
        self,
        *,
        dry_run: bool,
        actor_email: str,
        actor_role: str,
        run_source: str,
        respect_feature_flag: bool,
    ) -> dict[str, Any]:
        current_now = now_utc()
        inactivity_days = get_configured_inactivity_days()
        effective_from = get_auto_resign_effective_from()
        inactivity_cutoff = current_now - timedelta(days=inactivity_days)
        actual_updates_enabled = (not respect_feature_flag) or is_auto_resign_enabled()
        effective_dry_run = dry_run or not actual_updates_enabled
        async with self.db_client() as session:
            active_users = (
                await session.execute(
                    select(Employee)
                    .options(selectinload(Employee.branch))
                    .where(Employee.employment_status == EMPLOYMENT_STATUS_ACTIVE)
                )
            ).scalars().all()
            resigned_users_count = int(
                (
                    await session.execute(
                        select(func.count()).select_from(Employee).where(
                            Employee.employment_status == EMPLOYMENT_STATUS_RESIGNED
                        )
                    )
                ).scalar_one()
                or 0
            )

        items: list[dict[str, Any]] = []
        protected_users_excluded = 0
        unverified_users_excluded = 0
        updated_count = 0
        failed_employee_ids: list[str] = []

        for employee in active_users:
            if is_protected_account(employee):
                protected_users_excluded += 1
                continue

            activity_reference_at = build_auto_resign_reference(employee)
            if activity_reference_at is None:
                unverified_users_excluded += 1
                continue

            is_eligible = activity_reference_at <= inactivity_cutoff
            inactivity_value = get_inactivity_days(activity_reference_at, reference_now=current_now)
            if not is_eligible:
                continue

            item = {
                "employee_id": employee.employee_id,
                "employee_name": employee.name,
                "hr_id": employee.hr_id,
                "email": employee.email,
                "branch_code": employee.branch_code,
                "branch_name": getattr(getattr(employee, "branch", None), "branch_name", None),
                "last_login_at": employee.last_login_at,
                "last_activity_at": employee.last_activity_at,
                "created_at": employee.created_at,
                "activity_reference_at": activity_reference_at,
                "inactivity_days": inactivity_value,
                "resignation_type": RESIGNATION_TYPE_AUTOMATIC,
                "resigned_reason": "No successful login for the configured inactivity period",
            }
            items.append(item)

            if effective_dry_run:
                continue

            try:
                async with self.db_client() as session:
                    async with session.begin():
                        result = await session.execute(
                            select(Employee).where(Employee.employee_id == employee.employee_id)
                        )
                        current_employee = result.scalar_one_or_none()
                        if current_employee is None or current_employee.employment_status != EMPLOYMENT_STATUS_ACTIVE:
                            continue
                        current_reference = build_auto_resign_reference(current_employee)
                        if current_reference is None or current_reference > inactivity_cutoff:
                            continue
                        current_employee.employment_status = EMPLOYMENT_STATUS_RESIGNED
                        current_employee.resignation_type = RESIGNATION_TYPE_AUTOMATIC
                        current_employee.resigned_reason = "No successful login for the configured inactivity period"
                        current_employee.resigned_at = current_now
                        current_employee.resigned_by = actor_email
                        current_employee.updated_at = current_now
                        session.add(current_employee)
                        session.add(
                            EmploymentStatusHistory(
                                employee_id=current_employee.employee_id,
                                previous_status=EMPLOYMENT_STATUS_ACTIVE,
                                new_status=EMPLOYMENT_STATUS_RESIGNED,
                                change_type=STATUS_CHANGE_AUTOMATIC,
                                reason=current_employee.resigned_reason,
                                changed_at=current_now,
                                changed_by=actor_email,
                                metadata_json=json.dumps(
                                    {
                                        "target_employee_email": current_employee.email,
                                        "target_hr_id": current_employee.hr_id,
                                        "configured_inactivity_days": inactivity_days,
                                        "inactivity_days": inactivity_value,
                                        "run_source": run_source,
                                    },
                                    ensure_ascii=False,
                                ),
                            )
                        )
                updated_count += 1
                if self.app is not None:
                    append_audit_event(
                        self.app,
                        _build_custom_audit_event(
                            action=USER_AUTO_RESIGNED,
                            actor_email=actor_email,
                            actor_role=actor_role,
                            path="/system/users/auto-resign",
                            details={
                                "employee_id": employee.employee_id,
                                "target_employee_email": employee.email,
                                "previous_status": EMPLOYMENT_STATUS_ACTIVE,
                                "new_status": EMPLOYMENT_STATUS_RESIGNED,
                                "configured_inactivity_days": inactivity_days,
                                "inactivity_days": inactivity_value,
                                "run_source": run_source,
                            },
                        ),
                    )
            except Exception:
                failed_employee_ids.append(employee.employee_id)

        report = {
            "dry_run": effective_dry_run,
            "requested_dry_run": dry_run,
            "configured_inactivity_days": inactivity_days,
            "effective_from": effective_from,
            "cutoff_at": inactivity_cutoff,
            "active_users_checked": len(active_users),
            "eligible_users": len(items),
            "protected_users_excluded": protected_users_excluded,
            "unverified_users_excluded": unverified_users_excluded,
            "already_resigned_skipped": resigned_users_count,
            "updated_users": updated_count,
            "failed_employee_ids": failed_employee_ids,
            "items": items,
            "feature_enabled": is_auto_resign_enabled(),
        }
        if self.app is not None:
            append_audit_event(
                self.app,
                _build_custom_audit_event(
                    action=AUTO_RESIGN_JOB_TRIGGERED,
                    actor_email=actor_email,
                    actor_role=actor_role,
                    path="/api/v1/admin/resigned-users/run-inactivity-check",
                    details={
                        "dry_run": effective_dry_run,
                        "requested_dry_run": dry_run,
                        "run_source": run_source,
                        "eligible_users": len(items),
                        "updated_users": updated_count,
                        "configured_inactivity_days": inactivity_days,
                    },
                ),
            )
        return report


async def run_scheduled_auto_resign_cycle(app) -> dict[str, Any]:
    service = await ResignedUsersService.create_instance(app.state.db_client, app=app)
    acquired = await service.try_acquire_job_lock(job_name=AUTO_RESIGN_JOB_NAME)
    if not acquired:
        return {"signal": "skipped", "reason": "lock_not_acquired"}
    report: dict[str, Any] = {}
    try:
        report = await service.run_inactivity_check(
            dry_run=not is_auto_resign_enabled(),
            actor_email="system:auto-resign-job",
            actor_role="system",
            run_source="scheduler",
            respect_feature_flag=True,
        )
        await service.release_job_lock(
            job_name=AUTO_RESIGN_JOB_NAME,
            status_text="completed",
            report={**report, "items": [serialize_run_item(item) for item in report.get("items", [])]},
        )
        return report
    except Exception as exc:
        await service.release_job_lock(
            job_name=AUTO_RESIGN_JOB_NAME,
            status_text="failed",
            report={"error": str(exc)},
        )
        raise


def _seconds_until_next_scheduled_run(now: datetime | None = None) -> float:
    current_now = normalize_datetime(now) or now_utc()
    schedule_hour, schedule_minute = get_auto_resign_schedule_time_utc()
    next_run = datetime.combine(current_now.date(), time(schedule_hour, schedule_minute, tzinfo=UTC))
    if next_run <= current_now:
        next_run += timedelta(days=1)
    return max((next_run - current_now).total_seconds(), 1.0)


async def auto_resign_scheduler(app) -> None:
    logger = getattr(app.state, "logger", None)
    first_cycle = True
    while True:
        try:
            if first_cycle:
                first_cycle = False
            else:
                await asyncio.sleep(_seconds_until_next_scheduled_run())
            report = await run_scheduled_auto_resign_cycle(app)
            if logger:
                logger.info("Auto resign scheduler cycle completed report=%s", json.dumps(report, ensure_ascii=False, default=str))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if logger:
                logger.exception("Auto resign scheduler cycle failed: %s", exc)
            await asyncio.sleep(60)
