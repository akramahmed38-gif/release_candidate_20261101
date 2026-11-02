import io
import json
import hashlib
from routes.users.admin_credentials import load_admin_credentials, verify_admin_password
from numbers import Integral, Real
import os
from pathlib import Path
import re
import pandas as pd
from urllib import request
from pydantic import BaseModel, Field
from routes.schemas.exam import AudienceFilters #!, AudiencePayload
from typing import List, Literal, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, select, update
from models.employee_model import EmployeeModel
from models.db_schemas import Employee, OTPRequest, Branch
from utils.resigned_users import (
    EMPLOYMENT_STATUS_ACTIVE,
    LOGIN_HISTORY_STATE_NATIVE,
    ResignedUsersService,
    build_inactive_account_response,
    is_employee_resigned,
    normalize_datetime,
)

from routes.users.auth_utils import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    decode_token,
    extract_auth_claims,
    get_current_user
)

router = APIRouter(
    prefix="/api/v1/users",
    tags=["Users"]
)


# ==================== MODELS ====================
class LoginRequest(BaseModel):
    email: str
    password: Optional[str] = None

class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1)

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class CreateUserRequest(BaseModel):
    # hr_id, name, title, branch, area,	region,	division (Fawry || Fawry Plus), department (Retail, admin, hr), sub_department(Mini, Flex, General, kiosik),  email, password
    hr_id: str
    name: str
    title: str = ""
    branch_code: Optional[str] = None
    department: Literal["Retail", "retail", "admin", "Admin", "hr", "HR", "auditor", "Auditor"]

    email: str
    # branch: str
    # area: str
    # region: str
    # division: Literal["Fawry", "Fawry Plus"]
    # sub_department: str
    

class UpdateUserRequest(BaseModel):
    hr_id: Optional[str] = None
    name: Optional[str] = None
    title: Optional[str] = None
    department: Optional[Literal["Retail", "retail", "admin", "Admin", "hr", "HR", "auditor", "Auditor"]] = None
    email: Optional[str] = None

    branch_code: Optional[str] = None
    # branch: Optional[str] = None
    # area: Optional[str] = None
    # region: Optional[str] = None
    # division: Optional[Literal["Fawry", "Fawry Plus"]] = None
    # sub_department: Optional[str] = None


class CreateBranchRequest(BaseModel):
    branch_code: str = Field(min_length=1)
    branch_name: str = Field(min_length=1)
    branch_region: str = Field(min_length=1)
    branch_area: str = Field(min_length=1)
    branch_division: str = Field(min_length=1)
    branch_sub_department: str = Field(min_length=1)

def employee_to_dict(emp: Employee) -> dict:
    branch = emp.branch
    return {
        "employee_id": emp.employee_id,
        "hr_id": emp.hr_id,
        "name": emp.name,
        "title": emp.title,
        "department": emp.department,
        "branch_code": emp.branch_code,

        "email": emp.email,


        "branch": branch.branch_name if branch else None,
        "area": branch.branch_area if branch else None,
        "region": branch.branch_region if branch else None,
        "division": branch.branch_division if branch else None,
        "sub_department": branch.branch_sub_department if branch else None,

        "employment_status": getattr(emp, "employment_status", EMPLOYMENT_STATUS_ACTIVE),
        "last_login_at": getattr(emp, "last_login_at", None),
        "last_activity_at": getattr(emp, "last_activity_at", None),
        "resigned_at": getattr(emp, "resigned_at", None),
        "resigned_reason": getattr(emp, "resigned_reason", None),
        "resignation_type": getattr(emp, "resignation_type", None),
        "reactivated_at": getattr(emp, "reactivated_at", None),
        "reactivated_by": getattr(emp, "reactivated_by", None),
        "auto_resign_exempt": bool(getattr(emp, "auto_resign_exempt", False)),

        "created_at": emp.created_at,
        "updated_at": emp.updated_at,
        "created_by": getattr(emp, "created_by", None),
    }

def _build_auth_response(token_data: dict, user_data: dict) -> dict:
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "access_token_expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "refresh_token_expires_in": REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        "data": {**user_data, "chatbot_test_access": token_data.get("chatbot_test_access") is True},
    }


def branch_to_dict(branch: Branch) -> dict:
    return {
        "branch_code": branch.branch_code,
        "branch_name": branch.branch_name,
        "branch_region": branch.branch_region,
        "branch_area": branch.branch_area,
        "branch_division": branch.branch_division,
        "branch_sub_department": branch.branch_sub_department,
    }


async def _get_all_branches(db_client) -> list[Branch]:
    async with db_client() as session:
        result = await session.execute(select(Branch).order_by(Branch.branch_name, Branch.branch_code))
        return result.scalars().all()

class AudienceResolveRequest(BaseModel): #! same as AudiencePayload in exam.py (Replace it ? Just import it ?)
    mode: Literal["all", "filters", "manual"] = "all"
    filters: AudienceFilters = Field(default_factory=AudienceFilters)
    manual_hr_ids: List[str] = Field(default_factory=list)


class ManageUserRequest(BaseModel):
    action: Literal["update", "delete"]
    email: str
    data: Optional[UpdateUserRequest] = None

#! ============================= OTP =============================

import random
import string
import smtplib
from email.message import EmailMessage

def _normalize_login_email(value: str | None) -> str:
    return (value or "").strip().lower()

_EMAIL_FORMAT_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _is_valid_email_format(value: str | None) -> bool:
    normalized = _normalize_login_email(value)
    if not normalized:
        return False
    if normalized in ADMIN_ALIASES or normalized == MANAGER_EMAIL:
        return True
    return bool(_EMAIL_FORMAT_REGEX.fullmatch(normalized))


def _normalize_bulk_upload_cell(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Integral) and not isinstance(value, bool):
        return str(int(value))
    if isinstance(value, Real) and not isinstance(value, bool):
        numeric_value = float(value)
        if numeric_value.is_integer():
            return str(int(numeric_value))
        return format(numeric_value, "g")
    return str(value).strip()

def _normalize_bulk_user_upload_frame(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [str(col).strip().lower() for col in normalized.columns]
    if "email" in normalized.columns:
        normalized["email"] = normalized["email"].map(
            lambda value: _normalize_login_email("" if pd.isna(value) else str(value))
        )
    if "hr id" in normalized.columns:
        normalized["hr id"] = normalized["hr id"].map(_normalize_bulk_upload_cell)
    if "branch_code" in normalized.columns:
        normalized["branch_code"] = normalized["branch_code"].map(_normalize_bulk_upload_cell)
    return normalized

def _has_normalized_duplicates(series: pd.Series, *, normalizer=None) -> bool:
    values = series.fillna("").map(lambda value: normalizer(value) if normalizer else str(value).strip())
    values = values[values != ""]
    return bool(values.duplicated().any())


def generate_otp(length: int = 6) -> str:
    return ''.join(random.choices(string.digits, k=length))

def send_otp_mail(to_email: str, user_name: str):
    smtp_disabled = str(os.getenv("TRAINING_SMTP_DISABLED", os.getenv("SMTP_DISABLED", ""))).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
    }
    SMTP_SERVER = (
        os.getenv("TRAINING_SMTP_SERVER")
        or os.getenv("SMTP_SERVER")
        or "10.100.36.40"
    ).strip()
    SMTP_PORT = int((os.getenv("TRAINING_SMTP_PORT") or os.getenv("SMTP_PORT") or "25").strip())
    SMTP_FROM = (
        os.getenv("TRAINING_SMTP_FROM")
        or os.getenv("SMTP_FROM_EMAIL")
        or "no-reply@fawry.com"
    ).strip()
    SMTP_TIMEOUT = float((os.getenv("TRAINING_SMTP_TIMEOUT") or "10").strip())

    otp = generate_otp()
    normalized_to_email = _normalize_login_email(to_email)
    normalized_user_name = (user_name or "").strip() or "User"

    # Convenience for server-side operators: also print the OTP to the terminal.
    try:
        print(f"[OTP] HR Training OTP requested for {normalized_to_email}: {otp}")
    except Exception:
        pass

    msg = EmailMessage()
    msg["Subject"] = "Your OTP Code - HR Training System"
    msg["From"] = SMTP_FROM
    msg["To"] = normalized_to_email

    # Plain text version
    text_content = f"""
Dear {normalized_user_name},

Your One-Time Password (OTP) is:
{otp}

This code will expire in 5 minutes.
If you did not request this, please ignore this email.
""".strip()

    # HTML version (same text format)
    html_content = f"""
    <html>
        <body>
            <p>Dear {normalized_user_name},</p>
            <p>Your One-Time Password (OTP) is:</p>
            <h2 style="color:#2E86C1;">{otp}</h2>
            <p>This code will expire in 5 minutes.</p>
            <p>If you did not request this, please ignore this email.</p>
        </body>
    </html>
    """

    msg.set_content(text_content)
    msg.add_alternative(html_content, subtype="html")

    if smtp_disabled:
        fallback_path = Path(__file__).resolve().parents[3] / "logs" / "training_last_otp.txt"
        fallback_path.parent.mkdir(parents=True, exist_ok=True)
        fallback_path.write_text(f"{normalized_to_email}:{otp}", encoding="utf-8")
        return otp

    try:
        print("Connecting to SMTP server...")
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=SMTP_TIMEOUT) as server:
            print("Connected. Sending email...")
            server.send_message(msg)
            print("Email sent successfully via relay.", otp)

            return otp

    except Exception as e:
        print("Failed:", str(e))
        fallback_path = Path(__file__).resolve().parents[3] / "logs" / "training_last_otp.txt"
        fallback_path.parent.mkdir(parents=True, exist_ok=True)
        fallback_path.write_text(f"{normalized_to_email}:{otp}", encoding="utf-8")
        return otp

#! ================================================================

OTP_TTL_SECONDS = 5 * 60
_admin_credentials = load_admin_credentials()
ADMIN_USER = _admin_credentials.get("username", "").strip().lower()
ADMIN_ALIASES = {ADMIN_USER} if ADMIN_USER else set()
MANAGER_EMAIL = _normalize_login_email(os.getenv("TRAINING_MANAGER_EMAIL") or "management")
MANAGER_PASSWORD = (os.getenv("TRAINING_MANAGER_PASSWORD") or "management@111").strip() or "management@111"
MANAGER_HR_ID = (os.getenv("TRAINING_MANAGER_HR_ID") or "MGR0001").strip() or "MGR0001"
MANAGER_NAME = (os.getenv("TRAINING_MANAGER_NAME") or "Ahmed Osama").strip() or "Ahmed Osama"
MANAGER_TITLE = (os.getenv("TRAINING_MANAGER_TITLE") or "Manager Dashboard Viewer").strip() or "Manager Dashboard Viewer"
MANAGER_DEPARTMENT = "manager"
OTP_ONLY_PASSWORD = "otp-only"
USER_CREATOR_LOG = Path(__file__).resolve().parents[3] / "logs" / "training_user_created_by.json"
USER_MANAGEMENT_ROLES = {"admin", "auditor", "hr"}
DEFAULT_ADMIN_BRANCH_CODE = "000"
DEFAULT_ADMIN_BRANCH_NAME = "Admin / HR"
DEFAULT_ADMIN_BRANCH_REGION = "HQ"
DEFAULT_ADMIN_BRANCH_AREA = "HQ"
DEFAULT_ADMIN_BRANCH_DIVISION = "HQ"
DEFAULT_ADMIN_BRANCH_SUB_DEPARTMENT = "General"
VALID_BRANCH_DIVISIONS = {
    "fawry": "Fawry",
    "fawry plus": "Fawry Plus",
}


def _normalize_role_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _normalize_department_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _normalize_role_name(value)
    if normalized == "retail":
        return "Retail"
    if normalized == "admin":
        return "admin"
    if normalized == "auditor":
        return "auditor"
    if normalized == "hr":
        return "hr"
    if normalized == "manager":
        return MANAGER_DEPARTMENT
    return value


def _normalize_branch_division(value: str | None) -> str | None:
    normalized = " ".join((value or "").strip().split()).lower()
    if not normalized:
        return None
    return VALID_BRANCH_DIVISIONS.get(normalized)


def _current_user_role(current_user: dict) -> str:
    return _normalize_role_name(current_user.get("role") or current_user.get("department"))


def _is_hr_actor(current_user: dict) -> bool:
    return _current_user_role(current_user) == "hr"


def _is_admin_role_name(role_value: str | None) -> bool:
    return _normalize_role_name(role_value) == "admin"


def _is_admin_employee(employee: Employee | None) -> bool:
    if employee is None:
        return False
    return _is_admin_role_name(getattr(employee, "department", None))


def _is_hr_role_name(role_value: str | None) -> bool:
    return _normalize_role_name(role_value) == "hr"

def _is_retail_role_name(role_value: str | None) -> bool:
    normalized = _normalize_role_name(role_value)
    return normalized in {"retail", "employee"}

def _is_hr_manageable_role(role_value: str | None) -> bool:
    normalized = _normalize_role_name(role_value)
    if not normalized:
        return True
    return normalized not in {"admin", "auditor"}


def _can_manage_role(current_user: dict, role_value: str | None) -> bool:
    role = _normalize_role_name(role_value)
    actor = _current_user_role(current_user)
    if role == "auditor":
        return actor == "admin"
    return not (_is_hr_actor(current_user) and not _is_hr_manageable_role(role))


def _is_password_login_email(email: str | None) -> bool:
    normalized = _normalize_login_email(email)
    return normalized in ADMIN_ALIASES or normalized == MANAGER_EMAIL

def _can_manage_users(current_user: dict) -> bool:
    return _current_user_role(current_user) in USER_MANAGEMENT_ROLES


def _visible_employee_for_actor(employee: Employee | None, current_user: dict) -> bool:
    if employee is None:
        return False
    if not _can_manage_role(current_user, getattr(employee, "department", None)):
        return False
    return True


def _filter_employees_for_actor(employees: list[Employee], current_user: dict) -> list[Employee]:
    if _current_user_role(current_user) == "admin":
        return employees
    return [employee for employee in employees if _can_manage_role(current_user, getattr(employee, "department", None))]


def _filter_hr_ids_for_actor(hr_ids: list[str], employees: list[Employee], current_user: dict) -> list[str]:
    if _current_user_role(current_user) == "admin":
        return sorted({hr_id for hr_id in hr_ids if hr_id})
    allowed_hr_ids = {
        employee.hr_id
        for employee in employees
        if _can_manage_role(current_user, getattr(employee, "department", None))
    }
    return sorted({hr_id for hr_id in hr_ids if hr_id and hr_id in allowed_hr_ids})


def _audience_preview_row(employee: Employee) -> dict:
    return {
        "hr_id": str(getattr(employee, "hr_id", "") or "").strip(),
        "name": str(getattr(employee, "name", "") or "").strip(),
        "email": str(getattr(employee, "email", "") or "").strip(),
    }


async def _resolve_audience_preview_rows(
    employee_model: EmployeeModel,
    payload: AudienceResolveRequest,
    current_user: dict,
) -> list[dict]:
    employees = list(await employee_model.get_all_users())
    visible_employees = _filter_employees_for_actor(employees, current_user)

    if payload.mode == "manual":
        candidate_hr_ids = [str(hr_id or "").strip() for hr_id in payload.manual_hr_ids]
    elif payload.mode == "filters":
        candidate_hr_ids = await employee_model.get_hr_ids_matching_filters(payload.filters.model_dump())
    else:
        candidate_hr_ids = [str(getattr(employee, "hr_id", "") or "").strip() for employee in visible_employees]

    candidate_hr_ids = _filter_hr_ids_for_actor(candidate_hr_ids, employees, current_user)
    visible_by_hr_id = {
        str(getattr(employee, "hr_id", "") or "").strip(): employee
        for employee in visible_employees
        if str(getattr(employee, "hr_id", "") or "").strip()
    }

    rows: list[dict] = []
    for hr_id in candidate_hr_ids:
        employee = visible_by_hr_id.get(str(hr_id or "").strip())
        if employee is None:
            continue
        rows.append(_audience_preview_row(employee))

    rows.sort(key=lambda row: ((row.get("name") or "").lower(), (row.get("email") or "").lower(), row.get("hr_id") or ""))
    return rows


def _build_audience_preview_excel(rows: list[dict]) -> bytes:
    output = io.BytesIO()
    export_rows = [
        {
            "HR ID": row.get("hr_id") or "",
            "Name": row.get("name") or "",
            "Email": row.get("email") or "",
        }
        for row in rows
    ]
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(export_rows).to_excel(writer, sheet_name="Audience Preview", index=False)
    output.seek(0)
    return output.getvalue()


def _role_requires_branch(role_value: str | None) -> bool:
    normalized = _normalize_role_name(role_value)
    return normalized not in {"admin", "auditor", "hr", MANAGER_DEPARTMENT}


async def _ensure_default_admin_branch(db_client) -> None:
    async with db_client() as session:
        async with session.begin():
            result = await session.execute(
                select(Branch).where(Branch.branch_code == DEFAULT_ADMIN_BRANCH_CODE)
            )
            existing = result.scalar_one_or_none()
            if existing:
                return
            branch = Branch(
                branch_code=DEFAULT_ADMIN_BRANCH_CODE,
                branch_name=DEFAULT_ADMIN_BRANCH_NAME,
                branch_region=DEFAULT_ADMIN_BRANCH_REGION,
                branch_area=DEFAULT_ADMIN_BRANCH_AREA,
                branch_division=DEFAULT_ADMIN_BRANCH_DIVISION,
                branch_sub_department=DEFAULT_ADMIN_BRANCH_SUB_DEPARTMENT,
            )
            session.add(branch)


async def ensure_manager_employee(db_client) -> None:
    if os.environ.get("FAWRY_ISOLATED_ADMIN")=="1":
        return
    await _ensure_default_admin_branch(db_client)
    async with db_client() as session:
        async with session.begin():
            email_result = await session.execute(
                select(Employee).where(func.lower(Employee.email) == MANAGER_EMAIL)
            )
            email_user = email_result.scalar_one_or_none()
            hrid_result = await session.execute(
                select(Employee).where(Employee.hr_id == MANAGER_HR_ID)
            )
            hrid_user = hrid_result.scalar_one_or_none()
            target_user = email_user or hrid_user

            if target_user:
                target_user.name = MANAGER_NAME
                target_user.title = MANAGER_TITLE
                target_user.department = MANAGER_DEPARTMENT
                target_user.email = MANAGER_EMAIL
                target_user.branch_code = DEFAULT_ADMIN_BRANCH_CODE
                target_user.employment_status = EMPLOYMENT_STATUS_ACTIVE
                target_user.auto_resign_exempt = True
                target_user.login_history_state = LOGIN_HISTORY_STATE_NATIVE
                if target_user is hrid_user or hrid_user is None:
                    target_user.hr_id = MANAGER_HR_ID
                if not (target_user.password or "").strip() or target_user.password == OTP_ONLY_PASSWORD:
                    target_user.password = MANAGER_PASSWORD
                session.add(target_user)
                return

            session.add(
                Employee(
                    hr_id=MANAGER_HR_ID,
                    name=MANAGER_NAME,
                    title=MANAGER_TITLE,
                    branch_code=DEFAULT_ADMIN_BRANCH_CODE,
                    department=MANAGER_DEPARTMENT,
                    email=MANAGER_EMAIL,
                    password=MANAGER_PASSWORD,
                    employment_status=EMPLOYMENT_STATUS_ACTIVE,
                    auto_resign_exempt=True,
                    login_history_state=LOGIN_HISTORY_STATE_NATIVE,
                )
            )


def _not_authorized_response() -> JSONResponse:
    return JSONResponse(
        content={
            "signal": "Not authorized",
            "message": "You are not authorized to perform this action"
        },
        status_code=status.HTTP_403_FORBIDDEN,
    )


def _not_found_response() -> JSONResponse:
    return JSONResponse(
        content={
            "signal": "error",
            "message": "User not found"
        },
        status_code=status.HTTP_404_NOT_FOUND,
    )


def _load_user_creator_map() -> dict[str, str]:
    if not USER_CREATOR_LOG.exists():
        return {}
    try:
        payload = json.loads(USER_CREATOR_LOG.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return {str(k).strip().lower(): str(v).strip() for k, v in payload.items()}
    except Exception:
        pass
    return {}


def _save_user_creator_map(payload: dict[str, str]) -> None:
    USER_CREATOR_LOG.parent.mkdir(parents=True, exist_ok=True)
    USER_CREATOR_LOG.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _remember_user_creator(user_email: str, creator_email: str | None) -> None:
    email_key = (user_email or "").strip().lower()
    creator_value = (creator_email or "").strip() or "unknown"
    if not email_key:
        return

    payload = _load_user_creator_map()
    if not payload.get(email_key):
        payload[email_key] = creator_value
        _save_user_creator_map(payload)


def _get_logged_user_creator(user_email: str) -> str | None:
    email_key = _normalize_login_email(user_email)
    if not email_key:
        return None
    return _load_user_creator_map().get(email_key)

def _hash_otp(otp: str) -> str:
    return hashlib.sha256(str(otp).encode("utf-8")).hexdigest()


async def store_otp(db_client, email: str, otp: str) -> None:
    normalized_email = _normalize_login_email(email)
    expires_at = datetime.utcnow() + timedelta(seconds=OTP_TTL_SECONDS)
    async with db_client() as session:
        async with session.begin():
            await session.execute(
                update(OTPRequest)
                .where(func.lower(OTPRequest.email) == normalized_email, OTPRequest.is_used == False)
                .values(is_used=True)
            )
            session.add(
                OTPRequest(
                    email=normalized_email,
                    otp_hash=_hash_otp(otp),
                    expires_at=expires_at,
                    is_used=False,
                )
            )


async def verify_otp(db_client, email: str, otp: str) -> bool:
    normalized_email = _normalize_login_email(email)
    async with db_client() as session:
        result = await session.execute(
            select(OTPRequest)
            .where(func.lower(OTPRequest.email) == normalized_email, OTPRequest.is_used == False)
            .order_by(OTPRequest.created_at.desc())
        )
        record = result.scalars().first()
        if not record:
            return False
        if datetime.utcnow() > record.expires_at:
            record.is_used = True
            await session.commit()
            return False
        if record.otp_hash != _hash_otp(otp):
            return False
        record.is_used = True
        await session.commit()
        return True


def _find_user_by_email(employees: list[Employee], email: str):
    normalized = _normalize_login_email(email)
    return next((user for user in employees if (user.email or "").strip().lower() == normalized), None)


def _find_admin_employee(employees: list[Employee]):
    return next(
        (
            user
            for user in employees
            if _normalize_login_email(getattr(user, "email", "")) in ADMIN_ALIASES
        ),
        None,
    )


async def _get_resigned_users_service(request: Request) -> ResignedUsersService:
    service = getattr(request.app.state, "resigned_users_service", None)
    if service is not None:
        return service
    service = await ResignedUsersService.create_instance(request.app.state.db_client, app=request.app)
    request.app.state.resigned_users_service = service
    return service


def _inactive_user_response() -> JSONResponse:
    payload = build_inactive_account_response()
    return JSONResponse(content=payload, status_code=status.HTTP_403_FORBIDDEN)


def _active_users_only(employees: list[Employee]) -> list[Employee]:
    return [employee for employee in employees if not is_employee_resigned(employee)]



# ==================== LOGIN ==================== 
@router.post("/login/request-otp")
async def request_login_otp(request: Request, payload: LoginRequest):
    email = _normalize_login_email(payload.email)

    if _is_password_login_email(email):
        return JSONResponse(
            content={
                "signal": "error",
                "message": "This account uses password login only.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    employees = await employee_model.get_all_users()
    user = _find_user_by_email(employees, email)

    print (f"SEND OTP :: OTP login requested for email: {email}")
    if not user:
        print("Email not found in the system.")
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Email not found. Please check your email address or Contact Admin"
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if is_employee_resigned(user):
        return _inactive_user_response()

    user_email = _normalize_login_email(getattr(user, "email", email))
    user_name = ((getattr(user, "name", "") or "").strip()) or (user_email.split("@")[0] if "@" in user_email else "User")
    otp_sent = send_otp_mail(to_email=user_email, user_name=user_name)
    # otp_sent = 12345678

    if otp_sent == -1:
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Failed to send OTP email. Please try again later."
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    await store_otp(request.app.state.db_client, user_email, otp_sent)
    return {
        "signal": "success",
        "message": "OTP sent successfully",
    }


@router.post("/login")
async def login(request: Request, payload: LoginRequest):
    email = _normalize_login_email(payload.email)
    secret_input = (payload.password or "").strip()  # OTP for users, password for admin

    if email in ADMIN_ALIASES:
        if not secret_input:
            return JSONResponse(
                content={
                    "signal": "error",
                    "message": "Password is required for admin login",
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if not verify_admin_password(secret_input):
            return JSONResponse(
                content={
                    "signal": "error",
                    "message": "Invalid admin password",
                },
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
        employees = await employee_model.get_all_users()
        admin_user = _find_admin_employee(employees)
        if admin_user:
            if is_employee_resigned(admin_user):
                return _inactive_user_response()
            service = await _get_resigned_users_service(request)
            await service.mark_successful_login(admin_user.email, actor_role=admin_user.department)
            token_data = {
                "sub": admin_user.employee_id,
                "chatbot_test_access": True,
                "role": "admin",
                "email": admin_user.email,
            }
            admin_data = employee_to_dict(admin_user)
            admin_data["department"] = "admin"
            return _build_auth_response(token_data, admin_data)

        return JSONResponse(status_code=401, content={"signal":"error","message":"The staging administrator record is missing; restore the isolated account store."})

    if email == MANAGER_EMAIL:
        if not secret_input:
            return JSONResponse(
                content={
                    "signal": "error",
                    "message": "Password is required for manager login",
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
        employees = await employee_model.get_all_users()
        manager_user = _find_user_by_email(employees, MANAGER_EMAIL)
        if not manager_user:
            return JSONResponse(
                content={
                    "signal": "error",
                    "message": "Manager account is not available. Please contact system admin.",
                },
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if is_employee_resigned(manager_user):
            return _inactive_user_response()

        if secret_input != (manager_user.password or ""):
            return JSONResponse(
                content={
                    "signal": "error",
                    "message": "Invalid manager password",
                },
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        service = await _get_resigned_users_service(request)
        await service.mark_successful_login(manager_user.email, actor_role=manager_user.department)
        token_data = {
            "sub": manager_user.employee_id,
            "role": manager_user.department,
            "email": manager_user.email,
        }
        return _build_auth_response(token_data, employee_to_dict(manager_user))

    print("LOGIN :: Identity and credential omitted.")

    # find user by email
    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    employees = await employee_model.get_all_users()
    user = _find_user_by_email(employees, email)
    if not user:
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Email not found. Please check your email address or Contact Admin",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if is_employee_resigned(user):
        return _inactive_user_response()

    if not secret_input:
        user_email = _normalize_login_email(getattr(user, "email", email))
        user_name = ((getattr(user, "name", "") or "").strip()) or (user_email.split("@")[0] if "@" in user_email else "User")
        otp_sent = send_otp_mail(to_email=user_email, user_name=user_name)
        if otp_sent == -1:
            return JSONResponse(
                content={
                    "signal": "error",
                    "message": "Failed to send OTP email. Please try again later.",
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        await store_otp(request.app.state.db_client, user_email, otp_sent)
        return JSONResponse(
            content={
                "signal": "otp_sent",
                "message": "OTP sent successfully",
            },
            status_code=status.HTTP_200_OK,
        )

    if not await verify_otp(request.app.state.db_client, _normalize_login_email(getattr(user, "email", email)), secret_input):
        print("LOGIN :: Invalid email or OTP.")
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Incorrect email or OTP"
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    service = await _get_resigned_users_service(request)
    await service.mark_successful_login(user.email, actor_role=user.department)
    token_data = {"sub": user.employee_id, "role": user.department, "email": user.email}
    return _build_auth_response(token_data, employee_to_dict(user))


@router.post("/refresh")
async def refresh_access_token(request: Request, payload: RefreshTokenRequest):
    try:
        refresh_payload = decode_token(payload.refresh_token, expected_token_type="refresh")
    except Exception:
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Invalid or expired refresh token",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token_data = extract_auth_claims(refresh_payload)
    if not token_data.get("sub") or not token_data.get("email"):
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Refresh token payload is incomplete",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    service = await _get_resigned_users_service(request)
    employee = await service.get_employee_by_email(token_data.get("email"))
    if employee is not None and is_employee_resigned(employee):
        return _inactive_user_response()

    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
        "access_token_expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "refresh_token_expires_in": REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    }
    
# ==================== CHANGE PASSWORD ====================
@router.put("/change-password")
async def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user)
):
    
    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    employees = await employee_model.get_all_users()
    employees = _active_users_only(list(employees))
    email = current_user["email"]

    old_password = payload.old_password
    new_password = payload.new_password
    
    user = next((u for u in employees if u.email == email), None)
    if not user:
        # raise HTTPException(status_code=404, detail="User not found")
        return JSONResponse(
            content={
                "signal": "error",
                "message": "User not found"
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if old_password !=  user.password:
        # raise HTTPException(status_code=400, detail="Old password is incorrect")
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Old password is incorrect"
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    await employee_model.update_user(user.hr_id, {"password": new_password})

    return {
        "signal": "success",
        "message": "Password changed successfully"
    }    

# ==================== GET ALL USERS ====================
@router.get("/users")
async def get_all_users(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=-1, le=100),
    sort_by: str = Query(default="role"),
    sort_direction: str = Query(default="asc"),
    filters: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    if not _can_manage_users(current_user):
        return _not_authorized_response()

    try:
        requested_filters = json.loads(filters) if filters else {}
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid user filters")
    if not isinstance(requested_filters, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid user filters")
    if page_size not in {20, 50, 100, -1}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="page_size must be 20, 50, 100, or -1 for all users",
        )

    predicates = [func.lower(Employee.employment_status) != "resigned"]
    if _is_hr_actor(current_user):
        predicates.append(func.lower(Employee.department) != "admin")
    if _current_user_role(current_user) != "admin":
        predicates.append(func.lower(Employee.department) != "auditor")

    filter_columns = {
        "email": func.lower(Employee.email),
        "hr_id": Employee.hr_id,
        "name": Employee.name,
        "branch": Branch.branch_name,
        "branch_code": Employee.branch_code,
        "role": func.lower(Employee.department),
    }
    for key, column in filter_columns.items():
        raw_values = requested_filters.get(key, [])
        values = raw_values if isinstance(raw_values, list) else []
        values = [str(value).strip() for value in values if str(value).strip()]
        if values:
            if key in {"email", "role"}:
                values = [value.lower() for value in values]
            predicates.append(column.in_(values))

    normalized_direction = sort_direction.lower()
    if normalized_direction not in {"asc", "desc"}:
        normalized_direction = "asc"
    sort_columns = {
        "email": func.lower(Employee.email),
        "hr_id": Employee.hr_id,
        "name": func.lower(Employee.name),
        "branch": func.lower(Branch.branch_name),
        "branch_code": Employee.branch_code,
    }
    if sort_by == "role":
        role_order = case(
            (func.lower(Employee.department) == "admin", 0),
            (func.lower(Employee.department).in_(["retail", "employee"]), 1),
            (func.lower(Employee.department) == "hr", 2),
            else_=3,
        )
        sort_column = role_order
    else:
        sort_column = sort_columns.get(sort_by, func.lower(Employee.email))
    ordering = sort_column.desc() if normalized_direction == "desc" else sort_column.asc()

    async with request.app.state.db_client() as session:
        base_query = select(Employee).outerjoin(Branch, Employee.branch_code == Branch.branch_code).where(*predicates)
        total = await session.scalar(
            select(func.count(Employee.employee_id)).select_from(Employee).outerjoin(Branch, Employee.branch_code == Branch.branch_code).where(*predicates)
        )
        ordered_query = base_query.order_by(ordering, func.lower(Employee.email))
        if page_size != -1:
            ordered_query = ordered_query.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(ordered_query)
        data = [employee_to_dict(employee) for employee in result.scalars().all()]

    return {
        "signal": "success",
        "users": data,
        "total": total or 0,
        "page": page,
        "page_size": page_size,
    }


@router.get("/users/filter-options")
async def get_user_filter_options(
    request: Request,
    field: str = Query(...),
    search: str | None = Query(default=None),
    filters: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Return distinct filter values without loading the complete user list."""
    if not _can_manage_users(current_user):
        return _not_authorized_response()

    try:
        requested_filters = json.loads(filters) if filters else {}
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid user filters")
    if not isinstance(requested_filters, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid user filters")

    filter_columns = {
        "email": func.lower(Employee.email),
        "hr_id": Employee.hr_id,
        "name": Employee.name,
        "branch": Branch.branch_name,
        "branch_code": Employee.branch_code,
        "role": func.lower(Employee.department),
    }
    column = filter_columns.get(field)
    if column is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid user filter field")

    predicates = [func.lower(Employee.employment_status) != "resigned"]
    if _is_hr_actor(current_user):
        predicates.append(func.lower(Employee.department) != "admin")
    if _current_user_role(current_user) != "admin":
        predicates.append(func.lower(Employee.department) != "auditor")

    # Apply every other selected filter so options remain relevant to the current result set.
    for key, filter_column in filter_columns.items():
        if key == field:
            continue
        raw_values = requested_filters.get(key, [])
        values = raw_values if isinstance(raw_values, list) else []
        values = [str(value).strip() for value in values if str(value).strip()]
        if values:
            if key in {"email", "role"}:
                values = [value.lower() for value in values]
            predicates.append(filter_column.in_(values))

    search_value = (search or "").strip().lower()
    if search_value:
        predicates.append(func.lower(column).like(f"%{search_value}%"))

    async with request.app.state.db_client() as session:
        result = await session.execute(
            select(column)
            .outerjoin(Branch, Employee.branch_code == Branch.branch_code)
            .where(*predicates, column.is_not(None))
            .distinct()
            .order_by(func.lower(column))
            .limit(limit)
        )
        options = [str(value).strip() for value in result.scalars().all() if str(value).strip()]

    return {"signal": "success", "options": options}

@router.get("/user/{hr_id}")
async def get_user_by_hr_id(
    request: Request, 
    hr_id: str,
    current_user: dict = Depends(get_current_user)
):

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)

    if not _can_manage_users(current_user):
        return _not_authorized_response()
    
    employee = await employee_model.get_user_by_hrid(hr_id)
    if not _visible_employee_for_actor(employee, current_user):
        return _not_found_response()

    data = employee_to_dict(employee)

    print("\n\n\nFetched user data:", data, "\n\n\n\n")
    return {
        "signal": "success",
        "user": data,
    }

# get users in excel format
@router.get("/users/export")
async def export_users_excel(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    if not _can_manage_users(current_user):
        return _not_authorized_response()

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    employees = list(await employee_model.get_all_users())
    employees = _active_users_only(employees)
    employees = _filter_employees_for_actor(employees, current_user)
    data = [employee_to_dict(e) for e in employees]

    export_rows = []
    for item in data:
        created_by = item.get("created_by") or _get_logged_user_creator(item.get("email"))
        export_rows.append(
            {
                "Email": item.get("email"),
                "HR ID": item.get("hr_id"),
                "Name": item.get("name"),
                "Title": item.get("title"),
                "Role": item.get("department"),
                "Branch": item.get("branch"),
                "Branch Code": item.get("branch_code"),
                "Region": item.get("region"),
                "Area": item.get("area"),
                "Division": item.get("division"),
                "Sub Department": item.get("sub_department"),
                "Created At": item.get("created_at"),
                "Updated At": item.get("updated_at"),
                "Created By": created_by or "N/A",
            }
        )

    df = pd.DataFrame(export_rows)
    print("Exporting users to Excel:", df.columns)
    
    # Create Excel file in memory (openpyxl is available offline in requirements)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Users')
    
    output.seek(0)

    # Return as StreamingResponse
    headers = {
        'Content-Disposition': 'attachment; filename="users.xlsx"'
    }
    
    return StreamingResponse(
        io.BytesIO(output.getvalue()),
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers=headers
    )

# =========================== INITIAL ADMIN USER ===========================
@router.post("/init-admin")
async def init_admin_user(request: Request):
    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    employees = await employee_model.get_all_users()
    admin_email = "mohammad.fawzy@fawry.com"
    existing_admin = next((u for u in employees if u.email == admin_email), None)
    if existing_admin:
        return {
            "signal": "info",
            "message": "Admin user already exists"
        }
    print("Creating admin user...\n\n\n\n\n")
    admin_employee = Employee(
        hr_id="HR0003",
        name="Admin User",
        title="Administrator",
        branch_code="000",
        department="admin",
        email=admin_email,
        password="admin1234",
        employment_status=EMPLOYMENT_STATUS_ACTIVE,
        auto_resign_exempt=True,
        login_history_state=LOGIN_HISTORY_STATE_NATIVE,
    )
    await employee_model.create_user(admin_employee)
    return {
        "signal": "success",
        "message": "Admin user created successfully",
        "info" : {
            "email": admin_email, 
            "password": "admin123"
        }
    }

# ==================== CREATE USER ====================
@router.post("/users")
async def create_user(
    request: Request,
    payload: CreateUserRequest,
    current_user: dict = Depends(get_current_user)
):
    if not _can_manage_users(current_user):
        return _not_authorized_response()

    normalized_department = _normalize_department_value(payload.department)
    if not _can_manage_role(current_user, normalized_department):
        return _not_authorized_response()

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    exists, _ = await employee_model.is_user_exists_by_hrid(hr_id=payload.hr_id)
    if exists:
        return JSONResponse(
            content={
                "signal": "error",
                "message": "HR ID already exists"
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    branch_code = (payload.branch_code or "").strip()
    if _role_requires_branch(normalized_department):
        if not branch_code:
            return JSONResponse(
                content={
                    "signal": "error",
                    "message": "Branch code is required"
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        branch_code_exists = await employee_model.is_branch_exists(branch_code=branch_code)
        if not branch_code_exists:
            return JSONResponse(
                content={
                    "signal": "error",
                    "message": "Branch code does not exist"
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    else:
        await _ensure_default_admin_branch(request.app.state.db_client)
        branch_code = DEFAULT_ADMIN_BRANCH_CODE

    normalized_email = _normalize_login_email(payload.email)
    if not _is_valid_email_format(normalized_email):
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Invalid email format"
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    employees = await employee_model.get_all_users()
    if any(_normalize_login_email(e.email) == normalized_email for e in employees):
        return JSONResponse(
            content={
                "signal": "error",
                "message": "User already exists"
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # _ = await employee_model.delete_user_by_hr_id("HRRR")
    # _ = await employee_model.delete_user_by_hr_id("HR0006")
    # _ = await employee_model.delete_user_by_hr_id("scaklbkl")
    # _ = await employee_model.delete_user_by_hr_id("HR0004")


    employee = Employee(
        hr_id=payload.hr_id,
        name=payload.name,
        title=payload.title or "",
        department=normalized_department or payload.department,
        email=normalized_email,
        password=OTP_ONLY_PASSWORD,
        branch_code=branch_code,
        employment_status=EMPLOYMENT_STATUS_ACTIVE,
        login_history_state=LOGIN_HISTORY_STATE_NATIVE,
        # branch=payload.branch,
        # area=payload.area,
        # region=payload.region,
        # division=payload.division,
        # sub_department=payload.sub_department,
    )

    created_employee = await employee_model.create_user(employee)
    _remember_user_creator(normalized_email, current_user.get("email"))
  
    return {
        "signal": "success",
        # "user": employee_to_dict(created_employee),
        "message": f"User {payload.email} created successfully"
    }

# ==================== BULK CREATE USERS ====================
@router.post("/bulkusers")
async def create_user_bulk(
    request: Request,
    current_user: dict = Depends(get_current_user),
    excel_file: UploadFile = File(...)
):
    if not _can_manage_users(current_user):
        return _not_authorized_response()

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)

    if not excel_file.filename.lower().endswith((".xls", ".xlsx")):
        # raise HTTPException(status_code=400, detail="Only Excel files are allowed")
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Invalid file format. Only Excel files are allowed."
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    contents = await excel_file.read()
    df = _normalize_bulk_user_upload_frame(pd.read_excel(io.BytesIO(contents)))
    expected_columns = ["hr id", "name", "title", "department", "email", "branch_code"]

# ['HR ID', 'Name', 'Title', 'Branch', 'Area', 'Region', 'Division', 'Department', 'Sub Department', 'E-mail']

    print("Excel file read successfully", len(df), df.columns.tolist())
    print("difference:", set(df.columns).symmetric_difference(set(expected_columns)))
    if set(df.columns) != set(expected_columns) or df.empty:
        # raise HTTPException(status_code=400, detail="Invalid Excel format")
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Invalid Excel format. Please ensure the file has the correct columns and is not empty."
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if _has_normalized_duplicates(df["hr id"]):
        # raise HTTPException(status_code=400, detail="Duplicate HR IDs in the Excel file") #! Show message to user to fix the file
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Duplicate HR IDs found in the Excel file. Please fix the file and try again."
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if _has_normalized_duplicates(df["email"], normalizer=_normalize_login_email):
        # raise HTTPException(status_code=400, detail="Duplicate Emails in the Excel file") #! Show message to user to fix the file
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Duplicate Emails found in the Excel file. Please fix the file and try again."
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if (df["email"] == "").any() or (df["hr id"] == "").any():
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Empty email or HR ID found in the Excel file. Please fix the file and try again."
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    num_existing_updating, num_created = 0, 0
    num_skipped, num_failed = 0, 0
    unadded_users = []
    for _, row in df.iterrows():

        hr_id = str(row['hr id'])
        email = _normalize_login_email(str(row['email']))
        if not _is_valid_email_format(email):
            unadded_users.append({"hr_id": hr_id, "email": email, "reason": "Invalid email format"})
            num_skipped += 1
            continue
        row_department = _normalize_department_value(str(row["department"])) if not pd.isna(row["department"]) else "Retail"
        if not _can_manage_role(current_user, row_department):
            unadded_users.append({"hr_id": hr_id, "email": email, "reason": "Not authorized to manage admin users"})
            num_skipped += 1
            continue

        branch_code_value = str(row["branch_code"]).strip() if not pd.isna(row["branch_code"]) else ""
        if _role_requires_branch(row_department):
            if not branch_code_value:
                unadded_users.append({"hr_id": hr_id, "email": email, "reason": "Branch code is required"})
                num_skipped += 1
                continue
            branch_code_exists = await employee_model.is_branch_exists(branch_code=branch_code_value)
            if not branch_code_exists:
                unadded_users.append({"hr_id": hr_id, "email": email, "reason": "Branch code does not exist"})
                num_skipped += 1
                continue
        else:
            await _ensure_default_admin_branch(request.app.state.db_client)
            branch_code_value = DEFAULT_ADMIN_BRANCH_CODE

        exists_pair, _ = await employee_model.is_user_exists_by_email_and_hrid(email, hr_id)
        
        if exists_pair:
            _, existing_user = await employee_model.is_user_exists_by_hrid(hr_id)
            if not _can_manage_role(current_user, getattr(existing_user, "department", None)):
                unadded_users.append({"hr_id": hr_id, "email": email, "reason": "Not authorized to manage admin users"})
                num_skipped += 1
                continue
            try:
                # update existing same HR+email
                update_data = {
                    "name": row["name"],
                    "title": "" if pd.isna(row["title"]) else str(row["title"]),
                    "branch_code": branch_code_value,
                    "department": row_department,
                }
                ok = await employee_model.update_user(hr_id, update_data)
                if not ok:
                    unadded_users.append({"hr_id": hr_id, "email": email, "reason": "Please try again later or contact support."})
                    num_failed += 1
                    continue
                num_existing_updating += 1
            except Exception as e:
                unadded_users.append({"hr_id": hr_id, "email": email, "reason": "Please try again later or contact support."})
                num_failed += 1
            continue

        # HR+email pair does not exist → check conflicts on hr OR email
        exists_email, _ = await employee_model.is_user_exists_by_email(email)
        exists_hrid, _ = await employee_model.is_user_exists_by_hrid(hr_id)
        if exists_hrid or exists_email:
            reason = "Email already exists" if exists_email else "HR ID already exists"
            unadded_users.append({"hr_id": hr_id, "email": email, "reason": reason})
            num_skipped += 1
            continue

        # truly new user → create
        try:
            employee = Employee(
                # ["hr id", "name", "title", "department", "email", "branch_code"]
                hr_id=hr_id,
                name=row["name"],
                title="" if pd.isna(row["title"]) else str(row["title"]),
                branch_code=branch_code_value,
                # "area": row["area"] if not pd.isna(row["area"]) else "NO",
                # "region": row["region"] if not pd.isna(row["region"]) else "NO",
                # "division": row["division"] if not pd.isna(row["division"]) else "NO",
                department=row_department,
                # "sub_department": row["sub department"] if not pd.isna(row["sub department"]) else "NO",
                email=email,
                password=OTP_ONLY_PASSWORD,
                employment_status=EMPLOYMENT_STATUS_ACTIVE,
                login_history_state=LOGIN_HISTORY_STATE_NATIVE,
            )
            created_employee = await employee_model.create_user(employee)
            _remember_user_creator(email, current_user.get("email"))
            num_created += 1
            # print(f"Created user {created_employee.email}, {created_employee.hr_id} successfully")
        except Exception as e:
            # print(f"Error creating user {email}, {hr_id}: {e}")
            unadded_users.append({"hr_id": hr_id, "email": email, "reason": "Please try again later or contact support."})
            num_failed += 1
            continue

    return JSONResponse(
        content={
        "signal": "success",
        "total_rows": int(len(df)),
        "successful_rows": num_existing_updating + num_created,
        "updated": num_existing_updating,
        "created": num_created,
        "skipped": num_skipped,
        "failed": num_failed,
        "unadded_count": len(unadded_users),
        "unadded_users": unadded_users,
        },
        status_code=status.HTTP_200_OK,
    ) 



@router.post("/branches/bulk")
async def bulk_upload_branches(
    request: Request,
    current_user: dict = Depends(get_current_user),
    excel_file: UploadFile = File(...),
):
    if not _can_manage_users(current_user):
        return _not_authorized_response()

    if not excel_file.filename.lower().endswith((".xls", ".xlsx")):
        return JSONResponse(
            content={"signal": "error", "message": "Invalid file format. Only Excel files are allowed."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    contents = await excel_file.read()
    df = pd.read_excel(io.BytesIO(contents))

    expected_columns = [
        "branch_code",
        "branch_name",
        "branch_region",
        "branch_area",
        "branch_division",
        "branch_sub_department",
    ]

    df.columns = [col.strip().lower() for col in df.columns]
    if set(df.columns) != set(expected_columns) or df.empty:
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Invalid Excel format. Please provide all required branch columns.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if df["branch_code"].duplicated().any():
        print(df[df["branch_code"].duplicated(keep=False)])
        return JSONResponse(
            content={"signal": "error", "message": "Duplicate branch codes found in the Excel file."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if df["branch_name"].duplicated().any():
        return JSONResponse(
            content={"signal": "error", "message": "Duplicate branch names found in the Excel file."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    df = df.fillna("").applymap(lambda value: str(value).strip())
    valid_divisions = {"fawry", "fawry plus"}
    invalid_divisions = df[~df["branch_division"].str.lower().isin(valid_divisions)]
    if not invalid_divisions.empty:
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Invalid division values detected. Allowed: Fawry, Fawry Plus.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    df["branch_division"] = df["branch_division"].str.title()

    payloads = df.to_dict(orient="records")
    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    created, updated, errors = await employee_model.bulk_upsert_branches(payloads)

    return JSONResponse(
        content={
            "signal": "success",
            "created": created,
            "updated": updated,
            "errors": errors,
        },
        status_code=status.HTTP_200_OK,
    )


@router.post("/branches")
async def create_branch(
    request: Request,
    payload: CreateBranchRequest,
    current_user: dict = Depends(get_current_user),
):
    if not _can_manage_users(current_user):
        return _not_authorized_response()

    branch_code = (payload.branch_code or "").strip()
    branch_name = (payload.branch_name or "").strip()
    branch_region = (payload.branch_region or "").strip()
    branch_area = (payload.branch_area or "").strip()
    branch_sub_department = (payload.branch_sub_department or "").strip()
    branch_division = _normalize_branch_division(payload.branch_division)

    if not all([branch_code, branch_name, branch_region, branch_area, branch_sub_department]):
        return JSONResponse(
            content={
                "signal": "error",
                "message": "All branch fields are required.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not branch_division:
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Invalid division value. Allowed: Fawry, Fawry Plus.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)

    if await employee_model.get_branch_by_code(branch_code):
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Branch code already exists.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if await employee_model.get_branch_by_name(branch_name):
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Branch name already exists.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    branch = Branch(
        branch_code=branch_code,
        branch_name=branch_name,
        branch_region=branch_region,
        branch_area=branch_area,
        branch_division=branch_division,
        branch_sub_department=branch_sub_department,
    )
    created_branch = await employee_model.create_branch(branch)

    return JSONResponse(
        content={
            "signal": "success",
            "message": f"Branch {branch_name} created successfully.",
            "branch": branch_to_dict(created_branch),
        },
        status_code=status.HTTP_201_CREATED,
    )


@router.get("/branches")
async def get_branches(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    if not _can_manage_users(current_user):
        return _not_authorized_response()

    branches = await _get_all_branches(request.app.state.db_client)
    return {
        "signal": "success",
        "branches": [
            {
                "branch_code": branch.branch_code,
                "branch_name": branch.branch_name,
                "region": branch.branch_region,
                "area": branch.branch_area,
                "division": branch.branch_division,
                "sub_department": branch.branch_sub_department,
            }
            for branch in branches
        ],
    }

# ==================== UPDATE USER ====================
@router.put("/users/{email}")
@router.post("/users/{email}/update")
async def update_user(
    request: Request,
    email: str,
    payload: UpdateUserRequest,
    current_user: dict = Depends(get_current_user)
):

    if not _can_manage_users(current_user):
        return _not_authorized_response()

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    employees = await employee_model.get_all_users()

    normalized_lookup_email = _normalize_login_email(email)
    matched_users = [u for u in employees if _normalize_login_email(u.email) == normalized_lookup_email]
    if not matched_users:
        return _not_found_response()

    if any(
        not _can_manage_role(current_user, getattr(user, "department", None)) for user in matched_users
    ):
        return _not_found_response()

    user = matched_users[0]
    old_email = (user.email or "").strip().lower()
    update_data = payload.model_dump(exclude_unset=True)
    # The editor sends unchanged identifiers too. Only actual identity changes
    # conflict when several employee records share an email.
    if "email" in update_data and _normalize_login_email(update_data["email"]) == old_email:
        update_data.pop("email")
    if "hr_id" in update_data and update_data["hr_id"] == user.hr_id:
        update_data.pop("hr_id")
    if len(matched_users) > 1 and any(key in update_data for key in ("email", "hr_id")):
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Multiple users share this email. Resolve duplicates before changing email or HR ID."
            },
            status_code=status.HTTP_409_CONFLICT,
        )
    if "department" in update_data:
        update_data["department"] = _normalize_department_value(update_data.get("department"))
    if "email" in update_data:
        update_data["email"] = _normalize_login_email(update_data.get("email"))
        if not _is_valid_email_format(update_data["email"]):
            return JSONResponse(
                content={
                    "signal": "error",
                    "message": "Invalid email format"
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    if not _can_manage_role(current_user, update_data.get("department")):
        return _not_authorized_response()

    if "title" in update_data:
        update_data["title"] = update_data["title"] or ""

    target_role = update_data.get("department") or user.department
    if _role_requires_branch(target_role):
        branch_code_value = (update_data.get("branch_code") or user.branch_code or "").strip()
        if not branch_code_value:
            return JSONResponse(
                content={
                    "signal": "error",
                    "message": "Branch code is required"
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        branch_code_exists = await employee_model.is_branch_exists(branch_code=branch_code_value)
        if not branch_code_exists:
            return JSONResponse(
                content={
                    "signal": "error",
                    "message": "Branch code does not exist"
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        update_data["branch_code"] = branch_code_value
    else:
        await _ensure_default_admin_branch(request.app.state.db_client)
        update_data["branch_code"] = DEFAULT_ADMIN_BRANCH_CODE

    ok = True
    for target_user in matched_users:
        updated = await employee_model.update_user(target_user.hr_id, update_data)
        if not updated:
            ok = False
            break
    if not ok:
        # raise HTTPException(status_code=500, detail="Failed to update user")
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Failed to update user"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    new_email = (update_data.get("email") or "").strip().lower()
    if new_email and new_email != old_email and len(matched_users) == 1:
        creators = _load_user_creator_map()
        creator_value = creators.get(old_email)
        if creator_value:
            creators[new_email] = creator_value
            creators.pop(old_email, None)
            _save_user_creator_map(creators)

    # return {
    #     "signal": "success",
    #     "message": f"User {email} updated successfully"
    # }
    return JSONResponse(
        content={
            "signal": "success",
            "message": f"User {email} updated successfully"
        },  
        status_code=status.HTTP_200_OK,
    )


@router.post("/users/manage")
async def manage_user(
    request: Request,
    payload: ManageUserRequest,
    current_user: dict = Depends(get_current_user),
):
    action = (payload.action or "").strip().lower()
    email = _normalize_login_email(payload.email)
    if not email:
        return JSONResponse(
            content={"signal": "error", "message": "Email is required"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if action == "delete":
        return await delete_user(request, email, current_user)
    if action == "update":
        update_payload = payload.data or UpdateUserRequest()
        return await update_user(request, email, update_payload, current_user)
    return JSONResponse(
        content={"signal": "error", "message": "Invalid action"},
        status_code=status.HTTP_400_BAD_REQUEST,
    )


# # ==================== DELETE USER ====================

@router.delete("/users/all")
async def delete_user(
    request: Request,
):
    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    count = await employee_model.delete_all_users()
    return {
        "signal": "success",
        "message": f"Deleted {count} users successfully"
    }


@router.delete("/users/{email}")
@router.post("/users/{email}/delete")
async def delete_user(
    request: Request,
    email: str,
    current_user: dict = Depends(get_current_user)
):
    if not _can_manage_users(current_user):
        return _not_authorized_response()

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    employees = await employee_model.get_all_users()
    normalized_lookup_email = _normalize_login_email(email)
    matched_users = [u for u in employees if _normalize_login_email(u.email) == normalized_lookup_email]
    if not matched_users:
        return _not_found_response()

    if any(
        not _can_manage_role(current_user, getattr(user, "department", None)) for user in matched_users
    ):
        return _not_found_response()

    ok = True
    for target_user in matched_users:
        deleted = await employee_model.delete_user_by_hr_id(target_user.hr_id)
        if not deleted:
            ok = False
            break
    if not ok:
        # raise HTTPException(status_code=400, detail="Delete failed")
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Delete failed"
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    # return {
    #     "signal": "success",
    #     "message": f"User {email} deleted successfully"
    # }
    return JSONResponse(
        content={
            "signal": "success",
            "message": f"User {email} deleted successfully"
        },
        status_code=status.HTTP_200_OK,
    )


@router.delete("/bulkusers")
@router.post("/bulkusers/delete")
async def delete_user_bulk(
    request: Request,
    current_user: dict = Depends(get_current_user),
    excel_file: UploadFile = File(...)
):
    if not _can_manage_users(current_user):
        return _not_authorized_response()

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)

    if not excel_file.filename.lower().endswith((".xls", ".xlsx")):
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Invalid file format. Only Excel files are allowed."
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    contents = await excel_file.read()
    df = pd.read_excel(io.BytesIO(contents))
    expected_columns1 = ["hr id"]
    expected_columns2 = ["email"]


    df.columns = [col.strip().lower() for col in df.columns]

    # print("difference:", set(df.columns).symmetric_difference(set(expected_columns)))
    if (set(df.columns) != set(expected_columns1) and set(df.columns) != set(expected_columns2)) or df.empty:
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Invalid Excel format. Please ensure the file has the correct columns and is not empty."
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if df[df.columns[0]].duplicated().any():
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Duplicate HR IDs or emails found in the Excel file. Please fix the file and try again."
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    df[df.columns[0]] = df[df.columns[0]].astype(str).str.strip()
    if (df[df.columns[0]] == "").any():
        return JSONResponse(
            content={
                "signal": "error",
                "message": "Empty HR ID or email found in the Excel file. Please fix the file and try again."
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    num_deleted = 0
    for _, row in df.iterrows():
        identifier = str(row[df.columns[0]])
        if df.columns[0] == "hr id":
            exists, user = await employee_model.is_user_exists_by_hrid(identifier)
        else:
            exists, user = await employee_model.is_user_exists_by_email(identifier)
        
        if not exists:
            continue
        if not _can_manage_role(current_user, getattr(user, "department", None)):
            continue
        ok = await employee_model.delete_user_by_hr_id(user.hr_id)
        if ok:
            num_deleted += 1
    return JSONResponse(
        content={
            "signal": "success",
            "message": f"Deleted {num_deleted} users successfully"
        },
        status_code=status.HTTP_200_OK,
    )


# ==================== ANALYZE USERS ====================
@router.get("/users/analyze")
async def analyze_users(request: Request, current_user: dict = Depends(get_current_user)):
    if not _can_manage_users(current_user):
        return _not_authorized_response()
    
    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    employees = list(await employee_model.get_all_users())
    employees = _filter_employees_for_actor(employees, current_user)

    total_users = len(employees)
    roles_count = {}
    
    for employee in employees:
        role = employee.department
        roles_count[role] = roles_count.get(role, 0) + 1

    print("User analysis:", total_users, roles_count)
    return JSONResponse(
        content={
            "signal": "success",
            "data": {
                "total_users": total_users,
                "roles_count": roles_count
            }
        },
        status_code=status.HTTP_200_OK,
    )


@router.get("/users/audience/hierarchy")
async def get_audience_hierarchy(
    request: Request,
    regions: Optional[List[str]] = Query(default=None),
    areas: Optional[List[str]] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    if not _can_manage_users(current_user):
        return _not_authorized_response()

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    tree = await employee_model.get_audience_hierarchy(regions, areas)
    employees = list(await employee_model.get_all_users())
    employees = _filter_employees_for_actor(employees, current_user)

    if _current_user_role(current_user) != "admin":
        for region in tree:
            for area in region.get("areas", []):
                for branch in area.get("branches", []):
                    branch["employees"] = [
                        emp for emp in (branch.get("employees") or [])
                        if _can_manage_role(current_user, str(emp.get("department") or ""))
                    ]

    filters = {
        "hr_ids": sorted({emp.hr_id for emp in employees}),
        "titles": sorted({emp.title for emp in employees}),
        "branches": sorted({emp.branch.branch_name for emp in employees if emp.branch}),
        "areas": sorted({emp.branch.branch_area for emp in employees if emp.branch}),
        "regions": sorted({emp.branch.branch_region for emp in employees if emp.branch}),
        "divisions": sorted({emp.branch.branch_division for emp in employees if emp.branch}),
        "departments": sorted({emp.department for emp in employees}),
        "sub_departments": sorted({emp.branch.branch_sub_department for emp in employees if emp.branch}),
    }

    return JSONResponse(
        content={"signal": "success", "data": {"regions": tree, "filters": filters}},
        status_code=status.HTTP_200_OK,
    )  
    

@router.post("/users/audience/resolve")
async def resolve_audience_hr_ids(
    request: Request,
    payload: AudienceResolveRequest,
    current_user: dict = Depends(get_current_user),
):
    if not _can_manage_users(current_user):
        return _not_authorized_response()

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    audience_rows = await _resolve_audience_preview_rows(employee_model, payload, current_user)
    hr_ids = [row.get("hr_id") or "" for row in audience_rows]

    return JSONResponse(
        content={
            "signal": "success", 
            "count": len(audience_rows), 
            "hr_ids": hr_ids,
            "employees": audience_rows,
        },
        status_code=status.HTTP_200_OK,
    )


@router.post("/users/audience/resolve/export")
async def export_resolved_audience(
    request: Request,
    payload: AudienceResolveRequest,
    current_user: dict = Depends(get_current_user),
):
    if not _can_manage_users(current_user):
        return _not_authorized_response()

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    audience_rows = await _resolve_audience_preview_rows(employee_model, payload, current_user)
    excel_bytes = _build_audience_preview_excel(audience_rows)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="audience_preview_{timestamp}.xlsx"'
        },
    )


@router.post("/audience/bulk-upload")
async def upload_audience_bulk_file(
    request: Request,
    upload_file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    if not _can_manage_users(current_user):
        return _not_authorized_response()

    print("Received file:", upload_file.filename)
    filename = upload_file.filename.lower()
    if not filename.endswith((".xls", ".xlsx", ".csv")):
        return JSONResponse(
            content={"signal": "error", "message": "Invalid file format. Use Excel or CSV files."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    contents = await upload_file.read()
    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
    except Exception:
        return JSONResponse(
            content={"signal": "error", "message": "Failed to read the uploaded file. Please verify its format."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )


    if df.empty:
        return JSONResponse(
            content={"signal": "error", "message": "The uploaded sheet is empty."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    df.columns = [str(col).strip().lower() for col in df.columns]
    column_type = None
    if "hr_ids" in df.columns:
        column_type = "hr_ids"
    elif "branch_codes" in df.columns:
        column_type = "branch_codes"

    if column_type is None:
        return JSONResponse(
            content={"signal": "error", "message": 'Sheet must contain a column named "hr_ids" or "branch_codes".'},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    values = (
        df[column_type]
        .astype(str)
        .str.strip()
        .replace({"nan": "", "None": ""})
    )
    values = [value for value in values if value]

    if not values:
        return JSONResponse(
            content={"signal": "error", "message": "No valid values found in the selected column."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    employee_model = await EmployeeModel.create_instance(db_client=request.app.state.db_client)
    all_users = list(await employee_model.get_all_users(active_only=True))
    invalid_values: list[str] = []
    branches_without_employees: list[str] = []

    if column_type == "hr_ids":
        valid_hr_ids = await employee_model.get_existing_hr_ids(values, active_only=True)
        valid_set = set(valid_hr_ids)
        invalid_values = sorted({value for value in values if value not in valid_set})
        resolved_hr_ids = sorted(valid_set)
    else:
        resolved_hr_ids, missing_codes, without_employees = await employee_model.get_hr_ids_by_branch_codes(
            values,
            active_only=True,
        )
        invalid_values = sorted(set(missing_codes))
        branches_without_employees = sorted(set(without_employees))

    resolved_hr_ids = _filter_hr_ids_for_actor(resolved_hr_ids, all_users, current_user)

    return JSONResponse(
        content={
            "signal": "success",
            "data": {
                "column_type": column_type,
                "hr_ids": resolved_hr_ids,
                "invalid_values": invalid_values,
                "branches_without_employees": branches_without_employees,
            },
        },
        status_code=status.HTTP_200_OK,
    )



#! 1. User selects the audience in the UI
# The frontend sends the filters (branch, department, HR IDs, etc.) to POST /api/v1/users/audience/resolve.and returns { count, hr_ids } so the UI can preview how many people will be targeted. For Better UX.
#! 2. User saves the exam
# The exam form posts to /api/v1/exams/create (or PUT for updates). The payload includes the new audience block (mode, filters, manual IDs).
# Inside the exam router, EmployeeModel runs the same filter logic again to produce the final hr_ids.
# We store those employees in the exam_employees association so the exam now knows exactly which HR IDs belong to its audience.
# 
# 
#  So the audience selections are always resolved to HR IDs both when previewing (via the user router endpoint) and when saving (inside the exam router), ensuring the exam stores the exact people it should apply to.
