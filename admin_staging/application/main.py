"""
Main script for the application.
"""

import os
import asyncio
import json
import shutil
import time
from time import perf_counter
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from routes import base, material, exam, audit, chatbot, resigned_users, daily_brief, business_vocabulary, question_bank_groups
from routes.users import users_router
from routes.users.auth_utils import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    decode_token,
    extract_auth_claims,
)
from utils.config_utils import get_settings
from utils.audit_trail import append_audit_event, build_audit_event
from utils.logging_utils import setup_logger
from utils.resigned_users import (
    ResignedUsersService,
    auto_resign_scheduler,
    build_inactive_account_response,
    ensure_resigned_users_runtime_schema,
    is_employee_resigned,
)

from models.db_schemas import DailyBrief, Exam, Material, SQLAlchemyBase, VocabularyCategory, VocabularyItem

_init_lock = asyncio.Lock()
PUBLIC_API_PATHS = {
    "/api/v1/users/login",
    "/api/v1/users/login/request-otp",
    "/api/v1/users/refresh",
}
PUBLIC_FRONTEND_PATHS = {
    "/",
    "/login",
}
PUBLIC_FRONTEND_PREFIXES = (
    "/static/",
    "/favicon",
    "/manifest.json",
    "/asset-manifest.json",
    "/logo",
)
ADMIN_HR_ROLES = {"admin", "hr"}
MANAGER_ROLES = {"manager"}
EMPLOYEE_ROLES = {"retail", "employee"}
DASHBOARD_ROLES = ADMIN_HR_ROLES | MANAGER_ROLES
ALL_AUTH_ROLES = DASHBOARD_ROLES | EMPLOYEE_ROLES
DEFAULT_EXAM_LEVEL = "Entry Level"


async def _ensure_exam_level_column(conn, logger) -> None:
    result = await conn.exec_driver_sql("PRAGMA table_info(exams)")
    column_names = {row[1] for row in result.fetchall()}
    if "exam_level" not in column_names:
        await conn.exec_driver_sql(
            "ALTER TABLE exams ADD COLUMN exam_level VARCHAR(50) NOT NULL DEFAULT 'Entry Level'"
        )
        logger.info("Database migration applied: added exams.exam_level column")

    await conn.exec_driver_sql(
        f"UPDATE exams SET exam_level = '{DEFAULT_EXAM_LEVEL}' "
        "WHERE exam_level IS NULL OR TRIM(exam_level) = ''"
    )


async def _ensure_vocabulary_category_columns(conn, logger) -> None:
    result = await conn.exec_driver_sql("PRAGMA table_info(vocabulary_categories)")
    column_names = {row[1] for row in result.fetchall()}
    if "arabic_name" not in column_names:
        await conn.exec_driver_sql("ALTER TABLE vocabulary_categories ADD COLUMN arabic_name VARCHAR(120)")
        logger.info("Database migration applied: added vocabulary_categories.arabic_name")
    await conn.exec_driver_sql(
        "UPDATE vocabulary_categories SET arabic_name = CASE name "
        "WHEN 'Banking & Products' THEN 'الخدمات المصرفية والمنتجات' "
        "WHEN 'Daily Operations' THEN 'العمليات اليومية' ELSE name END "
        "WHERE arabic_name IS NULL OR TRIM(arabic_name) = ''"
    )


async def ensure_runtime_ready(app: FastAPI) -> None:
    """Initialize app state for mounted mode where startup lifespan may be skipped."""
    if getattr(app.state, "db_client", None) is not None:
        return

    async with _init_lock:
        if getattr(app.state, "db_client", None) is not None:
            return

        settings = get_settings()
        logger = setup_logger(
            log_file=__file__,
            log_dir=settings.PATH_LOGS,
            log_to_console=True,
            file_mode="a",
        )
        logger.info("Application runtime initialization...")

        app.state.settings = settings
        Path(app.state.settings.PATH_LOGS).mkdir(parents=True, exist_ok=True)
        sqlite_path = Path(app.state.settings.SQLITE_DB_PATH)
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)

        legacy_sqlite_path = Path(__file__).resolve().parent / "assets" / "db" / "hr_learning_system.db"
        if not sqlite_path.exists() and legacy_sqlite_path.exists() and sqlite_path.resolve() != legacy_sqlite_path.resolve():
            shutil.copy2(legacy_sqlite_path, sqlite_path)

        sqlite_conn_url = f"sqlite+aiosqlite:///{app.state.settings.SQLITE_DB_PATH}"
        app.state.engine = create_async_engine(sqlite_conn_url)
        app.state.db_client = sessionmaker(
            app.state.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with app.state.engine.begin() as conn:
            await conn.run_sync(SQLAlchemyBase.metadata.create_all)
            await _ensure_exam_level_column(conn, logger)
            await _ensure_vocabulary_category_columns(conn, logger)
            await ensure_resigned_users_runtime_schema(conn, logger)
        await business_vocabulary.ensure_business_vocabulary_seed(app.state.db_client)
        await question_bank_groups.ensure_question_bank_groups(app.state.db_client)
        # Staging: no seeded identities.
        resigned_users_service = await ResignedUsersService.create_instance(app.state.db_client, app=app)
        # Staging: no production protected-account seeding.

        app.state.logger = logger
        app.state.resigned_users_service = resigned_users_service
        daily_brief.log_notification_runtime()
        logger.info("Database Connection Established")


@asynccontextmanager
async def lifespan(app: FastAPI):  # pylint: disable=[W0621]
    """Manage application startup and shutdown events."""

    await ensure_runtime_ready(app)
    app.state.auto_resign_scheduler_task = None  # Staging background jobs disabled

    yield  # The application runs here

    # Shutdown
    scheduler_task = getattr(app.state, "auto_resign_scheduler_task", None)
    if scheduler_task is not None:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
    logger = getattr(app.state, "logger", None)
    if logger:
        logger.info("Application is shutting down...")


app = FastAPI(lifespan=lifespan)

# app = FastAPI(
#     lifespan=lifespan,
#     docs_url="/api/docs",
#     redoc_url="/api/redoc",
#     openapi_url="/api/openapi.json"
# )


def _cors_allowed_origins():
    return ['http://127.0.0.1:'+os.environ['STAGING_PORT']]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)

app.include_router(base.base_router)
app.include_router(material.material_router)
app.include_router(exam.exam_router)
app.include_router(question_bank_groups.router)
app.include_router(audit.audit_router)
app.include_router(chatbot.chatbot_router)
app.include_router(users_router.router)
app.include_router(resigned_users.router)
app.include_router(daily_brief.router)
app.include_router(business_vocabulary.router)


@app.middleware("http")
async def ensure_training_app_ready(request: Request, call_next):
    await ensure_runtime_ready(request.app)
    return await call_next(request)


@app.middleware("http")
async def enforce_authentication_and_roles(request: Request, call_next):
    normalized_path = _normalize_request_path(request)
    method_name = request.method.upper()

    if method_name == "OPTIONS":
        return await call_next(request)

    is_api_request = normalized_path.startswith("/api/")
    if is_api_request and normalized_path in PUBLIC_API_PATHS:
        return await call_next(request)

    if not is_api_request:
        is_public_frontend = (
            normalized_path in PUBLIC_FRONTEND_PATHS
            or any(normalized_path.startswith(prefix) for prefix in PUBLIC_FRONTEND_PREFIXES)
        )
        if is_public_frontend:
            return await call_next(request)

    allowed_roles = (
        _allowed_roles_for_api_path(normalized_path, method_name)
        if is_api_request
        else _allowed_roles_for_frontend_path(normalized_path)
    )

    requires_auth = is_api_request or allowed_roles is not None
    token = _extract_token_from_request(request)
    refresh_token = _extract_refresh_token_from_request(request)
    if requires_auth and not token and not refresh_token:
        if is_api_request:
            return JSONResponse(
                status_code=401,
                content={"signal": "error", "message": "Not authenticated"},
            )
        return RedirectResponse(url=_with_root(request, "/login"), status_code=307)

    payload: dict | None = None
    refreshed_access_token: str | None = None
    refreshed_refresh_token: str | None = None
    if token:
        try:
            payload = decode_token(token, expected_token_type="access")
        except Exception:
            payload = None

    if requires_auth and payload is None and refresh_token:
        try:
            refresh_payload = decode_token(refresh_token, expected_token_type="refresh")
            token_claims = extract_auth_claims(refresh_payload)
            if token_claims.get("sub") and token_claims.get("email"):
                refreshed_access_token = create_access_token(token_claims)
                refreshed_refresh_token = create_refresh_token(token_claims)
                request.state.refreshed_access_token = refreshed_access_token
                payload = decode_token(refreshed_access_token, expected_token_type="access")
        except Exception:
            payload = None

    if requires_auth and payload is None:
        if is_api_request:
            return JSONResponse(
                status_code=401,
                content={"signal": "error", "message": "Invalid or expired token"},
            )
        return RedirectResponse(url=_with_root(request, "/login"), status_code=307)

    if payload is not None and allowed_roles:
        role = _normalize_role_from_payload(payload)
        if role not in allowed_roles:
            if is_api_request:
                return JSONResponse(
                    status_code=403,
                    content={"signal": "Not authorized", "message": "Role access denied"},
                )
            return RedirectResponse(url=_with_root(request, _dashboard_fallback_by_role(role)), status_code=307)

    current_employee = None
    if payload is not None:
        current_employee = await _load_authenticated_employee(request, payload)
        if current_employee is not None:
            request.state.current_employee = current_employee
            if is_employee_resigned(current_employee):
                if is_api_request:
                    return JSONResponse(
                        status_code=403,
                        content=build_inactive_account_response(),
                    )
                response = RedirectResponse(url=_with_root(request, "/login"), status_code=307)
                cookie_path = _resolve_auth_cookie_path(request)
                response.delete_cookie("training_access_token", path=cookie_path)
                response.delete_cookie("training_refresh_token", path=cookie_path)
                response.delete_cookie("access_token", path=cookie_path)
                response.delete_cookie("refresh_token", path=cookie_path)
                return response

    response = await call_next(request)
    if refreshed_access_token:
        _set_auth_cookies(request, response, refreshed_access_token, refreshed_refresh_token)
    if (
        payload is not None
        and current_employee is not None
        and is_api_request
        and normalized_path not in PUBLIC_API_PATHS
        and getattr(response, "status_code", 500) < 400
    ):
        try:
            service = await _get_resigned_users_service(request)
            await service.maybe_touch_last_activity(payload.get("email"))
        except Exception:
            logger = getattr(request.app.state, "logger", None)
            if logger:
                logger.exception("Failed to update last_activity_at for %s", payload.get("email"))
    return response


async def _get_resigned_users_service(request: Request) -> ResignedUsersService:
    service = getattr(request.app.state, "resigned_users_service", None)
    if service is not None:
        return service
    service = await ResignedUsersService.create_instance(request.app.state.db_client, app=request.app)
    request.app.state.resigned_users_service = service
    return service


async def _load_authenticated_employee(request: Request, payload: dict | None):
    if payload is None:
        return None
    email = str(payload.get("email") or "").strip().lower()
    role = _normalize_role_from_payload(payload)
    if not email:
        return None
    if role == "admin" and email in {"admin", "admin@fawry.com"}:
        return None
    try:
        service = await _get_resigned_users_service(request)
        return await service.get_employee_by_email(email)
    except Exception:
        logger = getattr(request.app.state, "logger", None)
        if logger:
            logger.exception("Failed to load authenticated employee for %s", email)
        return None


def _resolve_actor_from_request(request: Request) -> tuple[str, str]:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        if token:
            try:
                payload = decode_token(token)
                actor_email = payload.get("email") or payload.get("sub") or "anonymous"
                actor_role = payload.get("role") or payload.get("department") or "anonymous"
                return str(actor_email), str(actor_role).lower()
            except Exception:
                return "anonymous", "anonymous"

    return "anonymous", "anonymous"


def _normalize_request_path(request: Request) -> str:
    """
    Normalize request path for mounted mode.
    When training app is mounted under `/training`, some environments may expose
    `/training/api/...` while others expose `/api/...`.
    """
    raw_path = request.url.path or request.scope.get("path") or "/"
    scope_path = request.scope.get("path") or raw_path
    root_path = request.scope.get("root_path") or ""

    normalized = scope_path
    if root_path and normalized.startswith(root_path):
        normalized = normalized[len(root_path):] or "/"
    elif root_path and raw_path.startswith(root_path):
        normalized = raw_path[len(root_path):] or "/"
    elif raw_path.startswith("/training/"):
        normalized = raw_path[len("/training"):] or "/"
    elif raw_path == "/training":
        normalized = "/"

    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


def _with_root(request: Request, path: str) -> str:
    root_path = request.scope.get("root_path") or ""
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{root_path}{path}"


def _extract_token_from_request(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        if token:
            return token

    cookie_token = request.cookies.get("training_access_token") or request.cookies.get("access_token")
    if cookie_token:
        return cookie_token
    return None


def _extract_refresh_token_from_request(request: Request) -> str | None:
    refresh_token = request.cookies.get("training_refresh_token") or request.cookies.get("refresh_token")
    if refresh_token:
        return refresh_token
    return None


def _resolve_auth_cookie_path(request: Request) -> str:
    root_path = request.scope.get("root_path") or ""
    if root_path:
        return root_path

    raw_path = request.url.path or request.scope.get("path") or "/"
    if raw_path.startswith("/training"):
        return "/training"
    return "/"


def _set_auth_cookies(request: Request, response: Response, access_token: str, refresh_token: str | None = None) -> None:
    cookie_path = _resolve_auth_cookie_path(request)
    response.set_cookie(
        "training_access_token",
        access_token,
        path=cookie_path,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )
    if refresh_token:
        response.set_cookie(
            "training_refresh_token",
            refresh_token,
            path=cookie_path,
            max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            samesite="lax",
        )


def _normalize_role_from_payload(payload: dict) -> str:
    return str(payload.get("role") or payload.get("department") or "").strip().lower()


def _dashboard_fallback_by_role(role: str) -> str:
    return "/employee/exams" if role in EMPLOYEE_ROLES else "/dashboard"


def _allowed_roles_for_frontend_path(path: str) -> set[str] | None:
    if path.startswith("/admin/resigned-users"):
        return {"admin"}
    if path.startswith("/admin/audit"):
        return {"admin"}
    if path == "/materials" or path.startswith("/materials/"):
        return ALL_AUTH_ROLES
    if path == "/daily-brief" or path.startswith("/daily-brief/"):
        return ALL_AUTH_ROLES
    if path == "/business-vocabulary" or path.startswith("/business-vocabulary/"):
        return ALL_AUTH_ROLES
    if path == "/script-book" or path.startswith("/script-book/"):
        return ALL_AUTH_ROLES
    if path == "/hr/materials" or path.startswith("/hr/materials/"):
        return ALL_AUTH_ROLES
    if path.startswith("/dashboard"):
        return DASHBOARD_ROLES
    if path.startswith("/admin/users") or path.startswith("/hr/"):
        return ADMIN_HR_ROLES
    if path.startswith("/employee/"):
        return ADMIN_HR_ROLES | EMPLOYEE_ROLES
    if path.startswith("/change-password"):
        return DASHBOARD_ROLES | EMPLOYEE_ROLES
    return None


def _allowed_roles_for_api_path(path: str, method: str) -> set[str] | None:
    method_name = method.upper()
    if path.startswith("/api/v1/admin/resigned-users") or path.startswith("/api/v1/admin/users/"):
        return {"admin"}
    if path.startswith("/api/v1/audit/"):
        return {"admin"}
    if path.startswith("/api/v1/chatbot/"):
        return {"admin"}

    if path.startswith("/api/v1/daily-brief/") or path == "/api/v1/daily-brief":
        if path == "/api/v1/daily-brief/upload" and method_name == "POST":
            return ADMIN_HR_ROLES
        if path in {"/api/v1/daily-brief/folder", "/api/v1/daily-brief/file"}:
            return {"admin"}
        return ALL_AUTH_ROLES

    if path.startswith("/api/v1/daily-briefs"):
        if (
            path in {"/api/v1/daily-briefs/current", "/api/v1/daily-briefs/history"}
            or path.startswith("/api/v1/daily-briefs/history/")
        ):
            return ALL_AUTH_ROLES
        if path.endswith("/read"):
            return EMPLOYEE_ROLES
        if path.endswith("/feedback") and method_name == "POST":
            return EMPLOYEE_ROLES
        if path.endswith("/images") or "/images/" in path:
            return ALL_AUTH_ROLES
        return ADMIN_HR_ROLES

    if path.startswith("/api/v1/business-vocabulary"):
        if method_name in {"POST", "PATCH", "PUT", "DELETE"}:
            return ADMIN_HR_ROLES
        return ALL_AUTH_ROLES

    if path in {
        "/api/v1/materials",
        "/api/v1/materials/search",
        "/api/v1/materials/open",
        "/api/v1/materials/stream",
    }:
        return ALL_AUTH_ROLES
    if path.startswith("/api/v1/materials/file/"):
        return ALL_AUTH_ROLES
    if path == "/api/v1/materials/folder" or path == "/api/v1/materials/file":
        return {"admin"}
    if path == "/api/v1/materials/upload" and method_name == "POST":
        return ADMIN_HR_ROLES
    if path.startswith("/api/v1/materials/"):
        return ADMIN_HR_ROLES

    if path.startswith("/api/v1/users/"):
        if path in PUBLIC_API_PATHS:
            return None
        if path == "/api/v1/users/change-password":
            return DASHBOARD_ROLES | EMPLOYEE_ROLES
        if path == "/api/v1/users/init-admin":
            return {"admin"}
        if (
            path.startswith("/api/v1/users/users")
            or path.startswith("/api/v1/users/user/")
            or path.startswith("/api/v1/users/bulkusers")
            or path.startswith("/api/v1/users/branches")
            or path.startswith("/api/v1/users/audience/")
        ):
            return ADMIN_HR_ROLES
        return ADMIN_HR_ROLES | EMPLOYEE_ROLES

    if path.startswith("/api/v1/exams/"):
        if path == "/api/v1/exams/student" or path.endswith("/submit"):
            return ADMIN_HR_ROLES | EMPLOYEE_ROLES
        if path == "/api/v1/exams/performance/me":
            return ADMIN_HR_ROLES | EMPLOYEE_ROLES
        if path.startswith("/api/v1/exams/dashboard/"):
            return DASHBOARD_ROLES
        if (
            path == "/api/v1/exams/create"
            or path == "/api/v1/exams/all"
            or path == "/api/v1/exams/analyze"
            or path == "/api/v1/exams/delete_all"
            or path.startswith("/api/v1/exams/performance")
            or "/results_details" in path
        ):
            return ADMIN_HR_ROLES
        if method_name in {"PUT", "DELETE"}:
            return ADMIN_HR_ROLES
        return ADMIN_HR_ROLES | EMPLOYEE_ROLES

    return None


def _is_audit_target(request: Request, normalized_path: str) -> bool:
    """
    Log all API calls and all mutating (non-GET) app actions.
    This keeps audit trail complete for create/update/delete flows.
    """
    if normalized_path.startswith("/api/"):
        return True
    return request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def audit_api_actions(request: Request, call_next):
    if _normalize_request_path(request) in PUBLIC_API_PATHS:
        return await call_next(request)
    normalized_path = _normalize_request_path(request)
    if not _is_audit_target(request, normalized_path):
        return await call_next(request)

    captured_email = None
    if normalized_path in {"/api/v1/users/login", "/api/v1/users/login/request-otp"}:
        try:
            if "application/json" in (request.headers.get("content-type") or "").lower():
                raw_body = await request.body()
                if raw_body:
                    payload = json.loads(raw_body.decode("utf-8"))
                    if isinstance(payload, dict):
                        captured_email = str(payload.get("email") or "").strip() or None
        except Exception:
            captured_email = None

    started = perf_counter()
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        try:
            duration_ms = int((perf_counter() - started) * 1000)
            actor_email, actor_role = _resolve_actor_from_request(request)
            if captured_email and actor_email == "anonymous":
                actor_email = captured_email
            query = request.url.query or ""
            ip_address = request.client.host if request.client else "-"
            user_agent = request.headers.get("user-agent", "-")
            status_code = getattr(response, "status_code", 500)
            event = build_audit_event(
                actor_email=actor_email,
                actor_role=actor_role,
                method=request.method,
                path=normalized_path,
                query=query,
                status_code=status_code,
                duration_ms=duration_ms,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            append_audit_event(request.app, event)
        except Exception:
            # Never break the request lifecycle because of audit failures.
            pass

FRONTEND_BUILD_DIR = Path(__file__).resolve().parent / "hr-training-frontend" / "build"
FRONTEND_INDEX_FILE = FRONTEND_BUILD_DIR / "index.html"
FRONTEND_BUILD_STAMP = str(int(time.time()))


def _frontend_response(path: Path, *, no_cache: bool = False) -> FileResponse:
    headers = {}
    if no_cache:
        headers = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    return FileResponse(path, headers=headers)


def _frontend_index_response() -> Response:
    if not FRONTEND_INDEX_FILE.is_file():
        return JSONResponse(
            status_code=404,
            content={"detail": "Frontend build not found. Run the React build step."},
        )
    html = FRONTEND_INDEX_FILE.read_text(encoding="utf-8")
    stamp = FRONTEND_BUILD_STAMP
    if "__BUILD_STAMP__" in html:
        html = html.replace("__BUILD_STAMP__", stamp)
    else:
        html = html.replace("</head>", f"<meta name=\"build-stamp\" content=\"{stamp}\" />\n</head>")
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    return Response(content=html, media_type="text/html", headers=headers)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Basic WebSocket endpoint for real-time features."""
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_text()
            await websocket.send_text(message)
    except WebSocketDisconnect:
        pass


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """Serve React build output from the same FastAPI server."""
    # if full_path.startswith("api/") or full_path == "api":
    #     return JSONResponse(status_code=404, content={"detail": "Not Found"})

    if (
        full_path.startswith("api/")
        or full_path in ["api", "docs", "redoc", "openapi.json"]
    ):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    if full_path == "":
        return _frontend_index_response()

    requested_path = (FRONTEND_BUILD_DIR / full_path).resolve()
    if FRONTEND_BUILD_DIR in requested_path.parents and requested_path.is_file():
        return _frontend_response(requested_path, no_cache=True)

    if FRONTEND_INDEX_FILE.is_file():
        return _frontend_index_response()

    return JSONResponse(
        status_code=404,
        content={"detail": "Frontend build not found. Run the React build step."},
    )


def main():
    """Entry Point for the Program."""
    print(
        f"Welcome from `{os.path.basename(__file__).split('.')[0]}` Module. Nothing to do ^_____^!"
    )


if __name__ == "__main__":
    main()
