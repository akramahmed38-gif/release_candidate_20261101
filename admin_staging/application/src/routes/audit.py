import io
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from routes.users.auth_utils import get_current_user
from utils.audit_trail import parse_datetime_value, read_audit_events, write_audit_events


audit_router = APIRouter(prefix="/api/v1/audit", tags=["api_v1", "audit"])


def _require_admin(current_user: dict):
    role = str(current_user.get("role") or current_user.get("department") or "").lower()
    if role != "admin":
        return JSONResponse(
            content={
                "signal": "Not authorized",
                "message": "Only admin can access audit trail",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return None


def _apply_filters(
    rows: list[dict],
    *,
    search: str | None,
    actor_email: str | None,
    actor_role: str | None,
    method: str | None,
    path_contains: str | None,
    status_code: int | None,
    from_ts: str | None,
    to_ts: str | None,
) -> list[dict]:
    result = rows

    if actor_email:
        actor_email_lower = actor_email.strip().lower()
        result = [row for row in result if str(row.get("actor_email") or "").lower() == actor_email_lower]

    if actor_role:
        actor_role_lower = actor_role.strip().lower()
        result = [row for row in result if str(row.get("actor_role") or "").lower() == actor_role_lower]

    if method:
        method_upper = method.strip().upper()
        result = [row for row in result if str(row.get("method") or "").upper() == method_upper]

    if path_contains:
        needle = path_contains.strip().lower()
        result = [row for row in result if needle in str(row.get("path") or "").lower()]

    if status_code is not None:
        result = [row for row in result if int(row.get("status_code") or 0) == int(status_code)]

    from_dt = parse_datetime_value(from_ts)
    to_dt = parse_datetime_value(to_ts)
    if from_dt:
        result = [
            row
            for row in result
            if (parse_datetime_value(row.get("timestamp_utc")) or datetime.min.replace(tzinfo=timezone.utc)) >= from_dt
        ]
    if to_dt:
        result = [
            row
            for row in result
            if (parse_datetime_value(row.get("timestamp_utc")) or datetime.min.replace(tzinfo=timezone.utc)) <= to_dt
        ]

    if search:
        token = search.strip().lower()

        def _matches(row: dict) -> bool:
            haystack = " ".join(
                [
                    str(row.get("actor_email") or ""),
                    str(row.get("actor_role") or ""),
                    str(row.get("method") or ""),
                    str(row.get("path") or ""),
                    str(row.get("query") or ""),
                    str(row.get("action") or ""),
                    str(row.get("result") or ""),
                    str(row.get("details") or ""),
                    str(row.get("ip_address") or ""),
                    str(row.get("status_code") or ""),
                ]
            ).lower()
            return token in haystack

        result = [row for row in result if _matches(row)]

    return result


def _sort_rows(rows: list[dict], sort_by: str, sort_dir: str) -> list[dict]:
    reverse = sort_dir.lower() == "desc"
    key_name = sort_by if sort_by else "timestamp_utc"

    if key_name == "timestamp_utc":
        return sorted(
            rows,
            key=lambda row: parse_datetime_value(row.get("timestamp_utc")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=reverse,
        )

    return sorted(
        rows,
        key=lambda row: str(row.get(key_name) or "").lower(),
        reverse=reverse,
    )


@audit_router.get("/logs")
async def get_audit_logs(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: str | None = Query(None),
    actor_email: str | None = Query(None),
    actor_role: str | None = Query(None),
    method: str | None = Query(None),
    path_contains: str | None = Query(None),
    status_code: int | None = Query(None),
    from_ts: str | None = Query(None),
    to_ts: str | None = Query(None),
    sort_by: str = Query("timestamp_utc"),
    sort_dir: str = Query("desc"),
    current_user: dict = Depends(get_current_user),
):
    unauthorized = _require_admin(current_user)
    if unauthorized:
        return unauthorized

    rows = read_audit_events(request.app)
    rows = _apply_filters(
        rows,
        search=search,
        actor_email=actor_email,
        actor_role=actor_role,
        method=method,
        path_contains=path_contains,
        status_code=status_code,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    rows = _sort_rows(rows, sort_by=sort_by, sort_dir=sort_dir)

    total = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    sliced = rows[start:end]

    return JSONResponse(
        content={
            "signal": "success",
            "total": total,
            "page": page,
            "page_size": page_size,
            "logs": sliced,
        },
        status_code=status.HTTP_200_OK,
    )


@audit_router.get("/logs/export")
async def export_audit_logs(
    request: Request,
    search: str | None = Query(None),
    actor_email: str | None = Query(None),
    actor_role: str | None = Query(None),
    method: str | None = Query(None),
    path_contains: str | None = Query(None),
    status_code: int | None = Query(None),
    from_ts: str | None = Query(None),
    to_ts: str | None = Query(None),
    sort_by: str = Query("timestamp_utc"),
    sort_dir: str = Query("desc"),
    current_user: dict = Depends(get_current_user),
):
    unauthorized = _require_admin(current_user)
    if unauthorized:
        return unauthorized

    rows = read_audit_events(request.app)
    rows = _apply_filters(
        rows,
        search=search,
        actor_email=actor_email,
        actor_role=actor_role,
        method=method,
        path_contains=path_contains,
        status_code=status_code,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    rows = _sort_rows(rows, sort_by=sort_by, sort_dir=sort_dir)

    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="AuditLogs")
    output.seek(0)

    filename = f"audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        io.BytesIO(output.getvalue()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@audit_router.delete("/logs/purge")
async def purge_audit_logs(
    request: Request,
    before_ts: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    unauthorized = _require_admin(current_user)
    if unauthorized:
        return unauthorized

    rows = read_audit_events(request.app)
    original_count = len(rows)

    if before_ts:
        before_dt = parse_datetime_value(before_ts)
        if before_dt is None:
            return JSONResponse(
                content={
                    "signal": "error",
                    "message": "Invalid before_ts format. Use ISO datetime.",
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        kept = []
        for row in rows:
            row_dt = parse_datetime_value(row.get("timestamp_utc"))
            if row_dt is None or row_dt > before_dt:
                kept.append(row)
        rows = kept
    else:
        rows = []

    write_audit_events(request.app, rows)

    return JSONResponse(
        content={
            "signal": "success",
            "deleted_count": original_count - len(rows),
            "remaining_count": len(rows),
        },
        status_code=status.HTTP_200_OK,
    )
