"""Versioned, published dashboard source projections for the hourly refresh job.

This module is deliberately independent of the web-worker lifecycle. It never
rebuilds a snapshot during a request and never deserializes executable objects.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
import zlib
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

SNAPSHOT_SCHEMA_VERSION = 2
SNAPSHOT_MAX_AGE_SECONDS = 2 * 60 * 60
SNAPSHOT_GRACE_SECONDS = 120


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _datetime(value):
    return datetime.fromisoformat(value) if value else None


def project_sources(users, exams, attempts, hierarchy, audit_rows):
    """Retain the inputs consumed by the existing dashboard formulas."""
    from routes.exam import _normalize_topic_key, _resolve_management_topic_label

    projected_users = []
    for user in users:
        branch = getattr(user, "branch", None)
        projected_users.append({
            key: _iso(getattr(user, key, None)) for key in (
                "employee_id", "hr_id", "name", "email", "title", "department",
                "branch_code", "created_at", "last_login_at", "last_activity_at",
                "employment_status",
            )
        } | {"branch": {key: getattr(branch, key, None) for key in (
            "branch_code", "branch_name", "branch_region", "branch_area",
            "branch_division", "branch_sub_department",
        )} if branch is not None else None})

    projected_exams = []
    for exam in exams:
        projected_exams.append({
            key: _iso(getattr(exam, key, None)) for key in (
                "exam_id", "title", "exam_status", "start_date", "end_date",
                "created_at", "is_deleted",
            )
        } | {"employee_ids": [employee.employee_id for employee in (getattr(exam, "employees", None) or [])]})

    projected_attempts = []
    for attempt in attempts:
        projected_attempts.append({
            key: _iso(getattr(attempt, key, None)) for key in (
                "employee_id", "exam_id", "total_score", "max_score", "passed", "submitted_at",
            )
        } | {"answers": [{
            "is_correct": bool(getattr(answer, "is_correct", False)),
            "topic_label": label,
            "topic_key": _normalize_topic_key(label) if label else None,
        } for answer in (getattr(attempt, "answers", None) or [])
          if (label := _resolve_management_topic_label(getattr(getattr(answer, "question", None), "question_group", None)))]})

    # The builder needs membership evidence, not every individual audit event.
    login_emails, activity_emails = set(), set()
    for row in audit_rows:
        if str(row.get("ip_address") or "").lower() == "testclient" or "testclient" in str(row.get("user_agent") or "").lower():
            continue
        if int(row.get("status_code") or 0) >= 400:
            continue
        email = str(row.get("actor_email") or "").strip().lower()
        if not email or email == "anonymous":
            continue
        path = str(row.get("path") or "")
        if path == "/api/v1/users/login":
            login_emails.add(email)
        if path.startswith("/api/") and path not in {"/api/v1/users/login", "/api/v1/users/login/request-otp"}:
            activity_emails.add(email)

    return {
        "users": projected_users,
        "exams": projected_exams,
        "attempts": projected_attempts,
        "hierarchy": hierarchy,
        "login_emails": sorted(login_emails),
        "activity_emails": sorted(activity_emails),
    }


def restore_sources(payload):
    if not isinstance(payload, dict) or not all(key in payload for key in ("users", "exams", "attempts", "hierarchy")):
        raise ValueError("Incompatible dashboard snapshot payload")
    users = []
    for row in payload["users"]:
        user = SimpleNamespace(**{key: _datetime(value) if key in {"created_at", "last_login_at", "last_activity_at"} else value for key, value in row.items() if key != "branch"})
        user.branch = SimpleNamespace(**row["branch"]) if row.get("branch") else None
        users.append(user)
    by_id = {user.employee_id: user for user in users}
    exams = []
    for row in payload["exams"]:
        exam = SimpleNamespace(**{key: _datetime(value) if key in {"start_date", "end_date", "created_at"} else value for key, value in row.items() if key != "employee_ids"})
        exam.employees = [by_id[employee_id] for employee_id in row["employee_ids"] if employee_id in by_id]
        exams.append(exam)
    attempts = []
    for row in payload["attempts"]:
        attempt = SimpleNamespace(**{key: _datetime(value) if key == "submitted_at" else value for key, value in row.items() if key != "answers"})
        attempt.answers = [SimpleNamespace(is_correct=answer["is_correct"], question=SimpleNamespace(
            dashboard_topic_label=answer["topic_label"], dashboard_topic_key=answer["topic_key"])) for answer in row["answers"]]
        attempts.append(attempt)
    audit_rows = ([{"actor_email": email, "path": "/api/v1/users/login", "status_code": 200} for email in payload["login_emails"]]
                  + [{"actor_email": email, "path": "/api/v1/exams", "status_code": 200} for email in payload["activity_emails"]])
    return users, exams, attempts, payload["hierarchy"], audit_rows


def compute_kpi_overview(sources, filters, now, period_bounds):
    """Mirror management-kpis SQL semantics using a fixed source projection."""
    users, exams, attempts, _, _ = sources
    start, end, _ = period_bounds

    def eligible(user):
        department = str(user.department or "").lower()
        if department not in {"retail", "employee"} or (filters.get("role") and department != filters["role"]):
            return False
        branch = user.branch
        for field, attribute in (("region", "branch_region"), ("area", "branch_area"),
                                 ("division", "branch_division"), ("sub_department", "branch_sub_department")):
            if filters.get(field) and (getattr(branch, attribute, None) if branch else None) != filters[field]:
                return False
        return not filters.get("branch_code") or user.branch_code == filters["branch_code"]

    scoped = [user for user in users if eligible(user)]
    active = {user.employee_id: user for user in scoped if str(user.employment_status or "active").lower() != "resigned"}
    resigned_count = len(scoped) - len(active)
    assignments = {(exam.exam_id, employee.employee_id) for exam in exams if not exam.is_deleted
                   for employee in exam.employees if employee.employee_id in active}
    assigned_employees = {employee_id for _, employee_id in assignments}
    assigned_exam_ids = {exam_id for exam_id, _ in assignments}
    submitted = []
    for attempt in attempts:
        date = attempt.submitted_at
        if date is None or (attempt.exam_id, attempt.employee_id) not in assignments:
            continue
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        if date > end or (start is not None and date < start):
            continue
        submitted.append(attempt)
    participants = {attempt.employee_id for attempt in submitted}
    scores = []
    for attempt in submitted:
        if attempt.total_score is not None and attempt.max_score not in (None, 0):
            pct = Decimal(str(attempt.total_score)) * 100 / Decimal(str(attempt.max_score))
            scores.append(float(pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)))
    active_open = overdue_open = 0
    for exam in exams:
        if exam.exam_id not in assigned_exam_ids:
            continue
        status = str(exam.exam_status or "").lower()
        start_date = exam.start_date.replace(tzinfo=timezone.utc) if exam.start_date and exam.start_date.tzinfo is None else exam.start_date
        end_date = exam.end_date.replace(tzinfo=timezone.utc) if exam.end_date and exam.end_date.tzinfo is None else exam.end_date
        if status not in {"closed", "on hold"} and start_date and end_date and start_date <= now < end_date:
            active_open += 1
        if status == "open" and end_date and end_date <= now:
            overdue_open += 1
    login_emails = {str(row.get("actor_email") or "").lower() for row in sources[4] if row.get("path") == "/api/v1/users/login"}
    activity_emails = {str(row.get("actor_email") or "").lower() for row in sources[4] if str(row.get("path") or "").startswith("/api/") and row.get("path") != "/api/v1/users/login"}
    never_login = sum(user.last_login_at is None and str(user.email or "").lower() not in login_emails for user in active.values())
    never_active = sum(user.last_activity_at is None and str(user.email or "").lower() not in activity_emails for user in active.values())

    def rate(numerator, denominator):
        return round(numerator * 100 / denominator, 2) if denominator else 0.0

    return {
        "active_employees": len(active), "resigned_employees": resigned_count,
        "users_with_attempts": len(participants),
        "training_participation_rate": rate(len(participants), len(active)),
        "average_exam_score_pct": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "pass_rate_pct": rate(sum(bool(attempt.passed) for attempt in submitted), len(submitted)),
        "no_exam_attempts": len(assigned_employees - participants),
        "never_logged_in": never_login, "never_active": never_active,
        "active_open_exams": active_open, "overdue_open_exams": overdue_open,
    }


def prepare_default_responses(projection: dict, now: datetime):
    """Precompute the common unfiltered view; filtered views use the same projection."""
    from routes.exam import (_build_management_summary_bundle,
                             _get_management_summary_period_bounds,
                             _normalize_management_summary_filters)

    sources = restore_sources(projection)
    users, exams, attempts, hierarchy, audit_rows = sources
    filters = _normalize_management_summary_filters(period="all")
    overview = compute_kpi_overview(sources, filters, now,
                                    _get_management_summary_period_bounds(filters, now=now))
    defaults = {}
    for access_role in ("admin", "auditor", "hr", "manager"):
        bundle = _build_management_summary_bundle(
            users=users, active_exams=[exam for exam in exams if not exam.is_deleted],
            attempts=attempts, hierarchy=hierarchy, audit_rows=audit_rows,
            now=now, filters=filters, access_role=access_role)
        defaults[access_role] = {"kpi_overview": overview, "summary": bundle["summary"]}
    projection["defaults"] = defaults


def read_audit_prefix(path: Path):
    """Capture a file-size boundary and ignore a trailing partial JSONL line."""
    if not path.exists():
        return [], 0
    rows = []
    with path.open("rb") as stream:
        boundary = os.fstat(stream.fileno()).st_size
        while stream.tell() < boundary:
            line = stream.readline(boundary - stream.tell())
            if not line.endswith(b"\n"):
                break
            try:
                item = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows, boundary


def initialize_schema(connection):
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS dashboard_snapshot_runs (
            snapshot_id TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            source_as_of TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            audit_bytes INTEGER NOT NULL,
            retired_until TEXT,
            payload BLOB NOT NULL
        );
        CREATE TABLE IF NOT EXISTS dashboard_snapshot_pointer (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            snapshot_id TEXT NOT NULL REFERENCES dashboard_snapshot_runs(snapshot_id)
        );
        CREATE TABLE IF NOT EXISTS dashboard_snapshot_retired_ids (
            snapshot_id TEXT PRIMARY KEY,
            retired_at TEXT NOT NULL
        );
    """)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(dashboard_snapshot_runs)")}
    if "retired_until" not in columns:
        connection.execute("ALTER TABLE dashboard_snapshot_runs ADD COLUMN retired_until TEXT")


def publish_snapshot(db_path: str, projection: dict, *, source_as_of: datetime, audit_bytes: int):
    snapshot_id = str(uuid.uuid4())
    generated_at = datetime.now(timezone.utc)
    encoded = zlib.compress(json.dumps(projection, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), level=6)
    with closing(sqlite3.connect(db_path, timeout=10)) as connection:
        initialize_schema(connection)
        # Serialization and compression are complete before the short write transaction.
        try:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute("SELECT snapshot_id FROM dashboard_snapshot_pointer WHERE id=1").fetchone()
            connection.execute(
                "INSERT INTO dashboard_snapshot_runs "
                "(snapshot_id,schema_version,source_as_of,generated_at,audit_bytes,retired_until,payload) "
                "VALUES (?,?,?,?,?,NULL,?)",
                (snapshot_id, SNAPSHOT_SCHEMA_VERSION, source_as_of.isoformat(), generated_at.isoformat(), audit_bytes, encoded),
            )
            connection.execute(
                "INSERT INTO dashboard_snapshot_pointer(id,snapshot_id) VALUES (1,?) "
                "ON CONFLICT(id) DO UPDATE SET snapshot_id=excluded.snapshot_id", (snapshot_id,),
            )
            if previous:
                retired_until = generated_at + timedelta(seconds=SNAPSHOT_GRACE_SECONDS)
                connection.execute("UPDATE dashboard_snapshot_runs SET retired_until=? WHERE snapshot_id=?",
                                   (retired_until.isoformat(), previous[0]))
                connection.execute(
                    "INSERT OR IGNORE INTO dashboard_snapshot_retired_ids(snapshot_id,retired_at) VALUES (?,?)",
                    (previous[0], generated_at.isoformat()),
                )
            _delete_expired_rows(connection, generated_at)
            _delete_expired_tombstones(connection, generated_at)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return snapshot_id, len(encoded)


def _delete_expired_rows(connection, now: datetime):
    # Legacy unretired rows are historical, not a grace-period predecessor.
    return connection.execute(
        "DELETE FROM dashboard_snapshot_runs WHERE snapshot_id NOT IN "
        "(SELECT snapshot_id FROM dashboard_snapshot_pointer WHERE id=1) "
        "AND (retired_until IS NULL OR retired_until <= ?)",
        (now.isoformat(),),
    ).rowcount


def _delete_expired_tombstones(connection, now: datetime):
    cutoff = now - timedelta(days=7)
    return connection.execute(
        "DELETE FROM dashboard_snapshot_retired_ids WHERE retired_at < ? "
        "AND snapshot_id NOT IN (SELECT snapshot_id FROM dashboard_snapshot_pointer WHERE id=1)",
        (cutoff.isoformat(),),
    ).rowcount


def cleanup_retired_snapshots(db_path: str, *, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    with closing(sqlite3.connect(db_path, timeout=10)) as connection:
        initialize_schema(connection)
        try:
            connection.execute("BEGIN IMMEDIATE")
            deleted = _delete_expired_rows(connection, now)
            _delete_expired_tombstones(connection, now)
            connection.commit()
            return deleted
        except Exception:
            connection.rollback()
            raise


def requested_snapshot_expired(db_path: str, requested_id: str) -> bool:
    """A tombstone proves prior issuance; an unknown ID is not an expiry signal."""
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=2)) as connection:
        try:
            row = connection.execute(
                "SELECT 1 FROM dashboard_snapshot_retired_ids t "
                "JOIN dashboard_snapshot_pointer p ON p.id=1 "
                "JOIN dashboard_snapshot_runs r ON r.snapshot_id=p.snapshot_id "
                "WHERE t.snapshot_id=? AND t.snapshot_id!=p.snapshot_id AND r.schema_version=?",
                (requested_id, SNAPSHOT_SCHEMA_VERSION),
            ).fetchone()
        except sqlite3.OperationalError as error:
            if "no such table" in str(error).lower():
                return False
            raise
    if row is None:
        return False
    try:
        current = read_snapshot(db_path)
    except (ValueError, sqlite3.Error, zlib.error):
        return False
    if current is None or not isinstance(current.get("payload"), dict):
        return False
    defaults = current["payload"].get("defaults")
    return isinstance(defaults, dict) and all(
        isinstance(defaults.get(role), dict) and {"summary", "kpi_overview"} <= defaults[role].keys()
        for role in ("admin", "auditor", "hr", "manager")
    )


def read_snapshot(db_path: str, snapshot_id: str | None = None, *, now: datetime | None = None,
                  decode: bool = True):
    now = now or datetime.now(timezone.utc)
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=2)) as connection:
        try:
            if snapshot_id:
                row = connection.execute(
                    "SELECT r.snapshot_id,r.schema_version,r.source_as_of,r.generated_at,r.audit_bytes,r.payload,"
                    "r.retired_until,p.snapshot_id FROM dashboard_snapshot_runs r "
                    "LEFT JOIN dashboard_snapshot_pointer p ON p.id=1 WHERE r.snapshot_id=?",
                    (snapshot_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT r.snapshot_id,r.schema_version,r.source_as_of,r.generated_at,r.audit_bytes,r.payload,"
                    "r.retired_until,p.snapshot_id FROM dashboard_snapshot_pointer p "
                    "JOIN dashboard_snapshot_runs r ON r.snapshot_id=p.snapshot_id WHERE p.id=1",
                ).fetchone()
        except sqlite3.OperationalError as error:
            if "no such table" in str(error).lower():
                return None
            raise
    if row is None:
        return None
    if row[0] != row[7] and (not row[6] or now >= datetime.fromisoformat(row[6])):
        return None
    if row[1] != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("Dashboard snapshot schema version is incompatible")
    return {"snapshot_id": row[0], "source_as_of": row[2], "generated_at": row[3], "audit_bytes": row[4],
            "is_stale": (datetime.now(timezone.utc) - datetime.fromisoformat(row[2])).total_seconds() > SNAPSHOT_MAX_AGE_SECONDS,
            "payload": json.loads(zlib.decompress(row[5])) if decode else row[5]}


@lru_cache(maxsize=2)
def _decoded_version(snapshot_id: str, encoded: bytes):
    return json.loads(zlib.decompress(encoded))


@lru_cache(maxsize=2)
def _restored_version(snapshot_id: str, encoded: bytes):
    return restore_sources(_decoded_version(snapshot_id, encoded))


def load_published_sources(db_path: str, requested_id: str | None = None, *, include_sources: bool = True):
    # Fetch authorization and payload in one SQLite read. Cleanup may run after
    # this fetch without invalidating an already-admitted response.
    record = read_snapshot(db_path, requested_id, decode=False)
    if record is None:
        return None
    version = record["snapshot_id"]
    encoded = record["payload"]
    payload = _decoded_version(version, encoded)
    sources = _restored_version(version, encoded) if include_sources else None
    is_stale = (datetime.now(timezone.utc) - datetime.fromisoformat(record["source_as_of"])).total_seconds() > SNAPSHOT_MAX_AGE_SECONDS
    return {key: value for key, value in record.items() if key != "payload"} | {
        "is_stale": is_stale, "refresh_status": "stale" if is_stale else "current",
    }, sources, payload.get("defaults", {})
