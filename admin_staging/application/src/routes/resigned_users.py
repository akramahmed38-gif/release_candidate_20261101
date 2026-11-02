import io
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from routes.users.auth_utils import get_current_user
from utils.resigned_users import (
    RESIGNED_USERS_SORT_ALLOWLIST,
    ResignedUsersService,
    normalize_datetime,
    serialize_run_item,
)


router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Resigned Users"],
)


class ReactivateUserRequest(BaseModel):
    reason: str = Field(default="", max_length=500)


class BulkReactivateUsersRequest(BaseModel):
    reason: str = Field(default="", max_length=500)
    search: str | None = None
    branch_id: str | None = None
    role: str | None = None
    resignation_type: str | None = None
    resigned_from: str | None = None
    resigned_to: str | None = None
    sort_by: str = Field(default="resigned_at")
    sort_dir: str = Field(default="desc", pattern="^(asc|desc)$")


def _current_role(current_user: dict) -> str:
    return str(current_user.get("role") or current_user.get("department") or "").strip().lower()


def _admin_only_response() -> JSONResponse:
    return JSONResponse(
        content={
            "signal": "Not authorized",
            "message": "Admin access required",
        },
        status_code=status.HTTP_403_FORBIDDEN,
    )


async def _get_service(request: Request) -> ResignedUsersService:
    service = getattr(request.app.state, "resigned_users_service", None)
    if service is not None:
        return service
    service = await ResignedUsersService.create_instance(request.app.state.db_client, app=request.app)
    request.app.state.resigned_users_service = service
    return service


def _serialize_datetime(value):
    normalized = normalize_datetime(value)
    return normalized.isoformat() if normalized is not None else None


def _serialize_resigned_item(item: dict) -> dict:
    payload = dict(item)
    for key in ("last_login_at", "last_activity_at", "resigned_at", "reactivated_at"):
        if key in payload:
            payload[key] = _serialize_datetime(payload.get(key))
    return payload


@router.get("/resigned-users")
async def list_resigned_users(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=200),
    search: str | None = Query(default=None),
    branch_id: str | None = Query(default=None),
    role: str | None = Query(default=None),
    resignation_type: str | None = Query(default=None),
    resigned_from: str | None = Query(default=None),
    resigned_to: str | None = Query(default=None),
    sort_by: str = Query(default="resigned_at"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    current_user: dict = Depends(get_current_user),
):
    if _current_role(current_user) not in {"admin", "auditor"}:
        return _admin_only_response()

    service = await _get_service(request)
    payload = await service.list_resigned_users(
        page=page,
        page_size=page_size,
        search=search,
        branch_id=branch_id,
        role=role,
        resignation_type=resignation_type,
        resigned_from=resigned_from,
        resigned_to=resigned_to,
        sort_by=sort_by if sort_by in RESIGNED_USERS_SORT_ALLOWLIST else "resigned_at",
        sort_dir=sort_dir,
    )
    return {
        **payload,
        "items": [_serialize_resigned_item(item) for item in payload.get("items", [])],
    }


@router.get("/resigned-users/export")
async def export_resigned_users(
    request: Request,
    search: str | None = Query(default=None),
    branch_id: str | None = Query(default=None),
    role: str | None = Query(default=None),
    resignation_type: str | None = Query(default=None),
    resigned_from: str | None = Query(default=None),
    resigned_to: str | None = Query(default=None),
    sort_by: str = Query(default="resigned_at"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    format: str = Query(default="excel", pattern="^(excel|csv)$"),
    current_user: dict = Depends(get_current_user),
):
    if _current_role(current_user) not in {"admin", "auditor"}:
        return _admin_only_response()

    service = await _get_service(request)
    rows = await service.get_resigned_users_export_rows(
        search=search,
        branch_id=branch_id,
        role=role,
        resignation_type=resignation_type,
        resigned_from=resigned_from,
        resigned_to=resigned_to,
        sort_by=sort_by if sort_by in RESIGNED_USERS_SORT_ALLOWLIST else "resigned_at",
        sort_dir=sort_dir,
    )

    export_rows = []
    for row in rows:
        item = _serialize_resigned_item(row)
        export_rows.append(
            {
                "Employee Name": item.get("employee_name"),
                "HR ID": item.get("hr_id"),
                "Username": item.get("username"),
                "Email": item.get("email"),
                "Branch Code": item.get("branch_code"),
                "Branch": item.get("branch_name"),
                "Role": item.get("role"),
                "Last Successful Login": item.get("last_login_at"),
                "Last Activity": item.get("last_activity_at"),
                "Resigned At": item.get("resigned_at"),
                "Inactivity Days": item.get("inactivity_days"),
                "Resignation Type": item.get("resignation_type"),
                "Resigned Reason": item.get("resigned_reason"),
                "Resigned By": item.get("resigned_by"),
            }
        )

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    if format == "csv":
        csv_bytes = pd.DataFrame(export_rows).to_csv(index=False).encode("utf-8-sig")
        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="resigned_users_{timestamp}.csv"'},
        )

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(export_rows).to_excel(writer, sheet_name="Resigned Users", index=False)
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="resigned_users_{timestamp}.xlsx"'},
    )


@router.post("/users/{employee_id}/reactivate")
async def reactivate_user(
    request: Request,
    employee_id: str,
    payload: ReactivateUserRequest,
    current_user: dict = Depends(get_current_user),
):
    if _current_role(current_user) not in {"admin", "auditor"}:
        return _admin_only_response()

    service = await _get_service(request)
    try:
        result = await service.reactivate_user(
            employee_id=employee_id,
            actor_email=str(current_user.get("email") or ""),
            actor_role=_current_role(current_user),
            note=payload.reason,
        )
    except ValueError as exc:
        return JSONResponse(
            content={"signal": "error", "message": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return {
        "signal": "success",
        "message": "User reactivated successfully",
        "data": _serialize_resigned_item(result),
    }


@router.post("/resigned-users/reactivate-all")
async def reactivate_all_resigned_users(
    request: Request,
    payload: BulkReactivateUsersRequest,
    current_user: dict = Depends(get_current_user),
):
    if _current_role(current_user) not in {"admin", "auditor"}:
        return _admin_only_response()

    service = await _get_service(request)
    result = await service.reactivate_resigned_users_bulk(
        actor_email=str(current_user.get("email") or ""),
        actor_role=_current_role(current_user),
        note=payload.reason,
        search=payload.search,
        branch_id=payload.branch_id,
        role=payload.role,
        resignation_type=payload.resignation_type,
        resigned_from=payload.resigned_from,
        resigned_to=payload.resigned_to,
        sort_by=payload.sort_by if payload.sort_by in RESIGNED_USERS_SORT_ALLOWLIST else "resigned_at",
        sort_dir=payload.sort_dir,
    )
    return {
        "signal": "success",
        "message": "Resigned users restored successfully",
        "updated_users": result.get("updated_users", 0),
        "reactivated_at": _serialize_datetime(result.get("reactivated_at")),
        "reactivated_by": result.get("reactivated_by"),
        "items": [_serialize_resigned_item(item) for item in result.get("items", [])],
    }


@router.post("/resigned-users/run-inactivity-check")
async def run_inactivity_check(
    request: Request,
    dry_run: bool = Query(default=True),
    current_user: dict = Depends(get_current_user),
):
    if _current_role(current_user) not in {"admin", "auditor"}:
        return _admin_only_response()

    service = await _get_service(request)
    report = await service.run_inactivity_check(
        dry_run=dry_run,
        actor_email=str(current_user.get("email") or ""),
        actor_role=_current_role(current_user),
        run_source="admin_manual",
        respect_feature_flag=False,
    )
    return {
        **report,
        "effective_from": _serialize_datetime(report.get("effective_from")),
        "cutoff_at": _serialize_datetime(report.get("cutoff_at")),
        "items": [serialize_run_item(item) for item in report.get("items", [])],
    }


@router.post("/resigned-users/backfill-login-history")
async def backfill_login_history(
    request: Request,
    dry_run: bool = Query(default=True),
    current_user: dict = Depends(get_current_user),
):
    if _current_role(current_user) not in {"admin", "auditor"}:
        return _admin_only_response()

    service = await _get_service(request)
    report = await service.run_login_history_backfill(
        dry_run=dry_run,
        actor_email=str(current_user.get("email") or ""),
        actor_role=_current_role(current_user),
    )
    serialized_items = []
    for item in report.get("items", []):
        serialized_item = dict(item)
        serialized_item["last_explicit_login"] = _serialize_datetime(serialized_item.get("last_explicit_login"))
        serialized_item["last_authenticated_activity"] = _serialize_datetime(
            serialized_item.get("last_authenticated_activity")
        )
        serialized_items.append(serialized_item)
    return {
        **report,
        "oldest_audit_record": _serialize_datetime(report.get("oldest_audit_record")),
        "newest_audit_record": _serialize_datetime(report.get("newest_audit_record")),
        "items": serialized_items,
    }
