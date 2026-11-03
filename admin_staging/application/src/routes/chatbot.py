"""Portal routes that proxy chatbot requests to the Python 3.10 sidecar."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from chatbot.analytics import (
    build_analytics_payload,
    export_conversation_records_jsonl,
    filter_conversation_records,
    read_conversation_records,
)
from chatbot.profiling import create_request_id

try:
    from models.employee_model import EmployeeModel
    from models.exam_model import ExamModel
except Exception:  # pragma: no cover - import path and deps depend on app entrypoint
    try:
        from src.models.employee_model import EmployeeModel
        from src.models.exam_model import ExamModel
    except Exception:  # pragma: no cover - analytics/tests can run without DB model import
        EmployeeModel = None
        ExamModel = None

try:
    from routes.users.auth_utils import ACCESS_TOKEN_TYPE, _get_cookie_access_token, decode_token
except Exception:  # pragma: no cover - import path and deps depend on app entrypoint
    try:
        from src.routes.users.auth_utils import ACCESS_TOKEN_TYPE, _get_cookie_access_token, decode_token
    except Exception:  # pragma: no cover - analytics/tests can run without auth deps
        ACCESS_TOKEN_TYPE = "access"

        def _get_cookie_access_token(request: Request) -> str | None:
            return None

        def decode_token(token: str, expected_token_type: str | None = None) -> dict[str, Any]:
            raise RuntimeError("Authentication utilities are unavailable.")

from admin_knowledge import admin as staging_admin

logger = logging.getLogger("uvicorn")

chatbot_router = APIRouter(prefix="/api/v1/chatbot", tags=["api_v1", "chatbot"])
_sidecar_lock = asyncio.Lock()
SIDECAR_HOST = "127.0.0.1"
SIDECAR_PORT = 18011
SIDECAR_BASE_URL = f"http://{SIDECAR_HOST}:{SIDECAR_PORT}"
SIDECAR_STARTUP_TIMEOUT_SECONDS = 20.0
SIDECAR_REQUEST_TIMEOUT_SECONDS = 1800.0


class ChatbotAskRequest(BaseModel):
    knowledge_mode: str = "approved"
    selected_fact_ids: list[str] = Field(default_factory=list, max_length=21)
    question: str = Field(..., min_length=1, max_length=4000, description="User question for the chatbot.")
    debug: bool = Field(default=False, description="Include backend debug details in the response.")
    request_id: str | None = Field(default=None, max_length=200, description="Cross-layer tracing id.")
    session_id: str | None = Field(default=None, max_length=200, description="Stable browser session id.")
    conversation_id: str | None = Field(default=None, max_length=200, description="Current chat thread id.")
    message_id: str | None = Field(default=None, max_length=200, description="Current exchange id.")


class ChatbotFeedbackRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000, description="Original user question.")
    answer: str = Field(..., min_length=1, description="Answer shown to the user.")
    sources: list[dict[str, Any]] = Field(default_factory=list, description="Source metadata returned with the answer.")
    rating: str = Field(..., pattern="^(useful|wrong)$", description="User feedback rating.")
    timestamp: str = Field(..., min_length=1, max_length=100, description="Client-side feedback timestamp.")
    session_id: str | None = Field(default=None, max_length=200, description="Stable browser session id.")
    conversation_id: str | None = Field(default=None, max_length=200, description="Current chat thread id.")
    message_id: str | None = Field(default=None, max_length=200, description="Current exchange id.")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sidecar_python_path() -> Path:
    return _project_root() / "chatbot_venv" / "Scripts" / "python.exe"


def _sidecar_script_path() -> Path:
    return _project_root() / "chatbot_sidecar.py"


def _setup_message():
    return 'Staging chatbot integration is pending; no production action is required.'


def _normalize_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _read_response_payload(response, metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    read_started = time.perf_counter()
    raw_body = response.read().decode("utf-8")
    if metrics is not None:
        metrics["portal.sidecar_response_read_ms"] = round((time.perf_counter() - read_started) * 1000, 2)
    if not raw_body:
        return {}
    parse_started = time.perf_counter()
    try:
        payload = json.loads(raw_body)
        parsed_payload = payload if isinstance(payload, dict) else {"data": payload}
    except json.JSONDecodeError:
        parsed_payload = {"detail": raw_body}
    if metrics is not None:
        metrics["portal.sidecar_response_parse_ms"] = round((time.perf_counter() - parse_started) * 1000, 2)
    return parsed_payload


def _extract_request_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        return token or None

    refreshed_access_token = getattr(request.state, "refreshed_access_token", None)
    if refreshed_access_token:
        return refreshed_access_token

    return _get_cookie_access_token(request)


async def _resolve_chatbot_user_context(request: Request) -> dict[str, Any]:
    anonymous = {
        "username": "anonymous",
        "full_name": "",
        "employee_id": "",
        "role": "unknown",
    }
    token = _extract_request_token(request)
    if not token:
        return anonymous

    try:
        claims = decode_token(token, expected_token_type=ACCESS_TOKEN_TYPE)
    except Exception:
        return anonymous

    subject = _normalize_string(claims.get("sub"))
    email = _normalize_string(claims.get("email"))
    role = _normalize_string(claims.get("role")) or "unknown"
    username = email or subject or "anonymous"
    full_name = ""
    employee_id = subject or ""

    employee = await _resolve_request_employee(request, subject=subject, email=email)
    if employee is not None:
        username = _normalize_string(getattr(employee, "email", None)) or username
        full_name = _normalize_string(getattr(employee, "name", None)) or ""
        employee_id = _normalize_string(getattr(employee, "hr_id", None)) or employee_id
        role = _normalize_string(getattr(employee, "department", None)) or role

    return {
        "username": username,
        "full_name": full_name,
        "employee_id": employee_id,
        "role": role,
    }


async def _resolve_request_employee(
    request: Request,
    *,
    subject: str | None,
    email: str | None,
):
    db_client = getattr(request.app.state, "db_client", None)
    if db_client is None or EmployeeModel is None:
        return None

    try:
        employee_model = await EmployeeModel.create_instance(db_client=db_client)
        employee = await employee_model.get_user_by_hrid(subject) if subject else None
        if employee is None and email:
            exists, matched_employee = await employee_model.is_user_exists_by_email(email)
            employee = matched_employee if exists else None
        return employee
    except Exception as exc:  # pragma: no cover - defensive auth enrichment guard
        logger.warning("Could not resolve chatbot employee record: %s", exc)
        return None


async def _require_chatbot_test_access(request: Request) -> None:
    token = _extract_request_token(request)
    try:
        claims = decode_token(token, expected_token_type=ACCESS_TOKEN_TYPE) if token else {}
    except Exception:
        claims = {}
    if claims.get("role") != "admin" or claims.get("chatbot_test_access") is not True:
        raise HTTPException(status_code=403, detail="Chatbot is restricted to the system admin test login.")


chatbot_router.dependencies.append(Depends(_require_chatbot_test_access))


def _normalize_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _calculate_attempt_expiry_for_chat(exam, started_at: datetime | None) -> datetime | None:
    normalized_start = _normalize_utc_datetime(started_at)
    if normalized_start is None:
        return None

    duration_minutes = max(0, int(getattr(exam, "duration_minutes", 0) or 0))
    duration_deadline = normalized_start + timedelta(minutes=duration_minutes)
    exam_end = _normalize_utc_datetime(getattr(exam, "end_date", None))
    if exam_end is None:
        return duration_deadline
    return min(duration_deadline, exam_end)


async def _get_active_exam_chat_lock(request: Request) -> dict[str, Any] | None:
    token = _extract_request_token(request)
    if not token or ExamModel is None:
        return None

    try:
        claims = decode_token(token, expected_token_type=ACCESS_TOKEN_TYPE)
    except Exception:
        return None

    role = (_normalize_string(claims.get("role")) or "").lower()
    if role not in {"retail", "employee"}:
        return None

    subject = _normalize_string(claims.get("sub"))
    email = _normalize_string(claims.get("email"))
    employee = await _resolve_request_employee(request, subject=subject, email=email)
    if employee is None:
        return None

    employee_internal_id = _normalize_string(getattr(employee, "employee_id", None))
    if not employee_internal_id:
        return None

    db_client = getattr(request.app.state, "db_client", None)
    if db_client is None:
        return None

    exam_model = await ExamModel.create_instance(db_client=db_client)
    attempts = await exam_model.get_active_attempts_for_employee(employee_internal_id)
    now = datetime.now(timezone.utc)
    for attempt in attempts:
        exam = getattr(attempt, "exam", None)
        if exam is None:
            continue

        expires_at = _calculate_attempt_expiry_for_chat(exam, getattr(attempt, "started_at", None))
        if expires_at is not None and now >= expires_at:
            continue

        return {
            "exam_id": _normalize_string(getattr(exam, "exam_id", None)),
            "exam_title": _normalize_string(getattr(exam, "title", None)),
            "expires_at": expires_at.isoformat() if expires_at else None,
        }

    return None


def _request_sidecar(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
    metrics: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        serialize_started = time.perf_counter()
        data = json.dumps(payload).encode("utf-8")
        serialize_time_ms = round((time.perf_counter() - serialize_started) * 1000, 2)
        if metrics is not None:
            metrics["portal.sidecar_request_serialize_ms"] = serialize_time_ms

    request = UrlRequest(url=f"{SIDECAR_BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        roundtrip_started = time.perf_counter()
        with urlopen(request, timeout=timeout) as response:
            payload_data = _read_response_payload(response, metrics=metrics)
            roundtrip_time_ms = round((time.perf_counter() - roundtrip_started) * 1000, 2)
            if metrics is not None:
                metrics["portal.sidecar_request_roundtrip_ms"] = roundtrip_time_ms
            return response.getcode(), payload_data
    except HTTPError as exc:
        payload_data = _read_response_payload(exc, metrics=metrics)
        if metrics is not None:
            metrics["portal.sidecar_request_roundtrip_ms"] = None
        return exc.code, payload_data


def _probe_sidecar() -> dict[str, Any]:
    try:
        status_code, payload = _request_sidecar("/health", timeout=5.0)
        return {
            "running": status_code == 200,
            "status_code": status_code,
            "payload": payload,
        }
    except URLError as exc:
        return {"running": False, "error": str(exc)}
    except Exception as exc:  # pragma: no cover - defensive startup guard
        return {"running": False, "error": str(exc)}


def _wait_for_sidecar_health(timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        probe = _probe_sidecar()
        if probe.get("running"):
            return True
        time.sleep(1.0)
    return False


def _read_python_version(executable: Path) -> str | None:
    if not executable.exists():
        return None
    try:
        completed = subprocess.run(
            [str(executable), "-c", "import sys; print(sys.version)"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception:
        return None

    version = (completed.stdout or completed.stderr).strip()
    return version or None


def _start_sidecar_process() -> subprocess.Popen:
    sidecar_python = _sidecar_python_path()
    sidecar_script = _sidecar_script_path()

    if not sidecar_python.exists():
        raise RuntimeError(_setup_message())
    if not sidecar_script.exists():
        raise RuntimeError(f"Chatbot sidecar entrypoint is missing: {sidecar_script}")

    startup_env = os.environ.copy()
    startup_env.setdefault("PYTHONUTF8", "1")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    startup_log = _project_root() / "logs" / "chatbot_startup.log"
    startup_log.parent.mkdir(parents=True, exist_ok=True)
    # Keep interpreter/import failures, which happen before the service logger starts.
    with startup_log.open("a", encoding="utf-8") as startup_output:
        return subprocess.Popen(  # noqa: S603,S607 - controlled local executable and script
            [str(sidecar_python), str(sidecar_script)],
            cwd=str(_project_root()),
            env=startup_env,
            stdout=startup_output,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )


async def _ensure_sidecar_running():
    return {'running':False,'error':'Staging admin application is available; its isolated chatbot adapter is not connected yet. No production sidecar was contacted or started.'}


async def _sidecar_diagnostics_payload() -> tuple[bool, dict[str, Any], str | None]:
    try:
        probe = await _ensure_sidecar_running()
        if not probe.get("running"):
            return False, {}, probe.get("error") or "Chatbot sidecar is not running."

        status_code, payload = await run_in_threadpool(
            _request_sidecar,
            "/diagnostics",
            method="GET",
            timeout=SIDECAR_REQUEST_TIMEOUT_SECONDS,
        )
        if status_code != 200:
            detail = payload.get("detail") if isinstance(payload, dict) else None
            return False, payload, detail or "Chatbot sidecar diagnostics failed."
        return True, payload, None
    except Exception as exc:
        return False, {}, str(exc)


@chatbot_router.get("/diagnostics")
async def chatbot_diagnostics(user=Depends(staging_admin)) -> dict[str, Any]:
    # Read-only owned-worker probe. Never start a sidecar or inspect credentials.
    from staging_diagnostics import diagnostics
    return await run_in_threadpool(diagnostics)


@chatbot_router.post("/ask")
async def ask_chatbot(request: Request, payload: ChatbotAskRequest) -> dict[str, Any]:
    portal_started = time.perf_counter()
    request_id = payload.request_id or create_request_id("portal")
    payload = payload.model_copy(update={"request_id": request_id})
    question = payload.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question must not be empty.",
        )

    active_exam_lock = await _get_active_exam_chat_lock(request)
    if active_exam_lock is not None:
        logger.info(
            "Chatbot blocked during active exam request_id=%s exam_id=%s expires_at=%s",
            request_id,
            active_exam_lock.get("exam_id"),
            active_exam_lock.get("expires_at"),
        )
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                "The chatbot is unavailable while your exam attempt is in progress. "
                "Please submit the exam or wait for the session to end."
            ),
        )

    # Owned staging adapter: no production sidecar call or request-time spawn.
    from admin_knowledge import call_engine
    user_context = await _resolve_chatbot_user_context(request)
    result = await run_in_threadpool(call_engine, {
        'question': question, 'knowledge_mode': payload.knowledge_mode,
        'selected_fact_ids': payload.selected_fact_ids,
        'conversation_id': payload.conversation_id or payload.session_id or request_id,
    }, user_context)
    result.update(request_id=request_id, conversation_id=payload.conversation_id,
                  session_id=payload.session_id, message_id=payload.message_id)
    return result

    try:
        ensure_sidecar_started = time.perf_counter()
        await _ensure_sidecar_running()
        ensure_sidecar_time_ms = round((time.perf_counter() - ensure_sidecar_started) * 1000, 2)
        resolve_user_started = time.perf_counter()
        user_context = await _resolve_chatbot_user_context(request)
        resolve_user_time_ms = round((time.perf_counter() - resolve_user_started) * 1000, 2)
        sidecar_metrics: dict[str, Any] = {}
        status_code, response_payload = await run_in_threadpool(
            _request_sidecar,
            "/ask",
            method="POST",
            payload={
                "question": question,
                "debug": payload.debug,
                "request_id": request_id,
                "session_id": payload.session_id,
                "conversation_id": payload.conversation_id,
                "message_id": payload.message_id,
                "user": user_context,
            },
            timeout=SIDECAR_REQUEST_TIMEOUT_SECONDS,
            metrics=sidecar_metrics,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except URLError as exc:
        logger.exception("Chatbot sidecar connectivity failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chatbot sidecar is unavailable.",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive proxy guard
        logger.exception("Chatbot proxy failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chatbot sidecar is unavailable.",
        ) from exc

    if status_code != 200:
        detail = response_payload.get("detail", "Chatbot sidecar is unavailable.")
        raise HTTPException(status_code=status_code, detail=detail)

    portal_total_time_ms = round((time.perf_counter() - portal_started) * 1000, 2)
    portal_profile = {
        "request_id": request_id,
        "timings_ms": {
            "portal.total_ms": portal_total_time_ms,
            "portal.ensure_sidecar_running_ms": ensure_sidecar_time_ms,
            "portal.resolve_user_context_ms": resolve_user_time_ms,
            "portal.sidecar_request_serialize_ms": sidecar_metrics.get(
                "portal.sidecar_request_serialize_ms"
            ),
            "portal.sidecar_request_roundtrip_ms": sidecar_metrics.get(
                "portal.sidecar_request_roundtrip_ms"
            ),
            "portal.sidecar_response_read_ms": sidecar_metrics.get("portal.sidecar_response_read_ms"),
            "portal.sidecar_response_parse_ms": sidecar_metrics.get("portal.sidecar_response_parse_ms"),
        },
        "metadata": {
            "portal.sidecar_status_code": status_code,
        },
    }
    response_payload = dict(response_payload)
    response_payload["request_id"] = response_payload.get("request_id") or request_id
    if payload.debug:
        debug_payload = dict(response_payload.get("debug") or {})
        debug_payload["portal_latency_profile"] = portal_profile
        response_payload["debug"] = debug_payload
    return response_payload


@chatbot_router.post("/feedback")
async def submit_chatbot_feedback(request: Request, payload: ChatbotFeedbackRequest) -> dict[str, Any]:
    from catalog_store import db
    from admin_knowledge import hashlib
    actor = await _resolve_chatbot_user_context(request)
    event = {'request_id': payload.request_id, 'rating': payload.rating,
             'actor_hash': hashlib.sha256(str(actor.get('username')).encode()).hexdigest(),
             'question_sha256': hashlib.sha256(payload.question.encode()).hexdigest(),
             'answer_sha256': hashlib.sha256(payload.answer.encode()).hexdigest(),
             'source_references': [{'fact_id': x.get('fact_id')} for x in payload.sources],
             'environment': 'isolated_admin_staging'}
    with db() as connection:
        connection.execute('insert into event(at,kind,target,data) values(?,?,?,?)',
                           (time.time(),'answer_feedback',payload.conversation_id or '',json.dumps(event)))
    return {'saved': True, 'staging_only': True}
    try:
        await _ensure_sidecar_running()
        user_context = await _resolve_chatbot_user_context(request)
        status_code, response_payload = await run_in_threadpool(
            _request_sidecar,
            "/feedback",
            method="POST",
            payload={
                **payload.model_dump(),
                "user": user_context,
            },
            timeout=SIDECAR_REQUEST_TIMEOUT_SECONDS,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except URLError as exc:
        logger.exception("Chatbot feedback proxy failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chatbot sidecar is unavailable.",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive proxy guard
        logger.exception("Chatbot feedback proxy failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chatbot sidecar is unavailable.",
        ) from exc

    if status_code != 200:
        detail = response_payload.get("detail", "Chatbot sidecar is unavailable.")
        raise HTTPException(status_code=status_code, detail=detail)

    return response_payload


@chatbot_router.get("/analytics")
async def chatbot_analytics(
    username: str | None = Query(default=None),
    employee_id: str | None = Query(default=None),
    role: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    feedback: str | None = Query(default=None),
    day: str | None = Query(default=None),
    conversation_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    source_name: str | None = Query(default=None),
    question_contains: str | None = Query(default=None),
) -> dict[str, Any]:
    records = await run_in_threadpool(read_conversation_records)
    filtered_records = filter_conversation_records(
        records,
        username=username,
        employee_id=employee_id,
        role=role,
        status=status_filter,
        feedback=feedback,
        day=day,
        conversation_id=conversation_id,
        session_id=session_id,
        source_name=source_name,
        question_contains=question_contains,
    )
    return build_analytics_payload(
        filtered_records,
        applied_filters={
            "username": username,
            "employee_id": employee_id,
            "role": role,
            "status": status_filter,
            "feedback": feedback,
            "day": day,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "source_name": source_name,
            "question_contains": question_contains,
        },
    )


@chatbot_router.get("/analytics/export")
async def export_chatbot_analytics(
    username: str | None = Query(default=None),
    employee_id: str | None = Query(default=None),
    role: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    feedback: str | None = Query(default=None),
    day: str | None = Query(default=None),
    conversation_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    source_name: str | None = Query(default=None),
    question_contains: str | None = Query(default=None),
) -> StreamingResponse:
    records = await run_in_threadpool(read_conversation_records)
    filtered_records = filter_conversation_records(
        records,
        username=username,
        employee_id=employee_id,
        role=role,
        status=status_filter,
        feedback=feedback,
        day=day,
        conversation_id=conversation_id,
        session_id=session_id,
        source_name=source_name,
        question_contains=question_contains,
    )
    payload = export_conversation_records_jsonl(filtered_records)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        io.BytesIO(payload.encode("utf-8")),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="chatbot_conversations_{timestamp}.jsonl"',
        },
    )
