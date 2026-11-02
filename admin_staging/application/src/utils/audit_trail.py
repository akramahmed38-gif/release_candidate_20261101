import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


CAIRO_TZ = ZoneInfo("Africa/Cairo")
AUDIT_FILE_NAME = "training_audit_trail.jsonl"
_AUDIT_LOCK = threading.Lock()


def _default_logs_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "logs"


def get_audit_log_path(app=None) -> Path:
    settings = getattr(getattr(app, "state", None), "settings", None) if app is not None else None
    if settings and getattr(settings, "PATH_LOGS", None):
        logs_dir = Path(settings.PATH_LOGS)
    else:
        logs_dir = _default_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / AUDIT_FILE_NAME


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_iso_utc(dt: datetime | None) -> str:
    if dt is None:
        dt = now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


def to_iso_cairo(dt: datetime | None) -> str:
    if dt is None:
        dt = now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CAIRO_TZ).isoformat()


def parse_datetime_value(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CAIRO_TZ).astimezone(timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


def build_audit_event(
    *,
    actor_email: str,
    actor_role: str,
    method: str,
    path: str,
    query: str,
    status_code: int,
    duration_ms: int,
    ip_address: str,
    user_agent: str,
    action: str | None = None,
    result: str | None = None,
    details: str | None = None,
    timestamp_utc: datetime | None = None,
) -> dict:
    ts = timestamp_utc or now_utc()
    return {
        "event_id": str(uuid.uuid4()),
        "timestamp_utc": to_iso_utc(ts),
        "timestamp_cairo": to_iso_cairo(ts),
        "actor_email": actor_email or "anonymous",
        "actor_role": actor_role or "anonymous",
        "method": method,
        "path": path,
        "query": query or "",
        "status_code": int(status_code),
        "duration_ms": int(duration_ms),
        "ip_address": ip_address or "-",
        "user_agent": user_agent or "-",
        "action": action or f"{method} {path}",
        "result": result or ("success" if 200 <= int(status_code) < 400 else "error"),
        "details": details or "",
    }


def append_audit_event(app, event: dict) -> None:
    path = get_audit_log_path(app)
    payload = {**event}
    with _AUDIT_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_audit_events(app) -> list[dict]:
    path = get_audit_log_path(app)
    if not path.exists():
        return []
    rows: list[dict] = []
    with _AUDIT_LOCK:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except Exception:
                    continue
                if isinstance(entry, dict):
                    rows.append(entry)
    return rows


def write_audit_events(app, rows: list[dict]) -> None:
    path = get_audit_log_path(app)
    with _AUDIT_LOCK:
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
