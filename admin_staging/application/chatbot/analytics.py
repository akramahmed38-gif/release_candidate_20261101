from __future__ import annotations

import json
import os
import time
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONVERSATION_LOG_PATH = PROJECT_ROOT / "logs" / "chatbot_conversations.jsonl"


class ConversationLogLock:
    def __init__(
        self,
        log_path: Path,
        *,
        timeout_seconds: float = 10.0,
        poll_interval_seconds: float = 0.1,
    ) -> None:
        self.log_path = Path(log_path)
        self.lock_path = self.log_path.with_name(f"{self.log_path.name}.lock")
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self._fd: int | None = None

    def __enter__(self) -> "ConversationLogLock":
        deadline = time.monotonic() + self.timeout_seconds
        payload = f"{os.getpid()}|{time.time()}".encode("utf-8")
        while True:
            try:
                self._fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.write(self._fd, payload)
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for log lock: {self.lock_path}")
                time.sleep(self.poll_interval_seconds)

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None
        try:
            if self.lock_path.exists():
                self.lock_path.unlink()
        except FileNotFoundError:
            pass


def conversation_log_path(path: Path | None = None) -> Path:
    return Path(path) if path is not None else CONVERSATION_LOG_PATH


def _normalize_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_role(value: Any) -> str:
    return (_normalize_string(value) or "unknown").lower()


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_timestamp_day(timestamp: Any) -> str | None:
    text = _normalize_string(timestamp)
    if not text:
        return None
    if "T" in text:
        return text.split("T", 1)[0]
    if len(text) >= 10:
        return text[:10]
    return text


def _ensure_log_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_records_without_lock(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def read_conversation_records(path: Path | None = None) -> list[dict[str, Any]]:
    log_path = conversation_log_path(path)
    if not log_path.exists():
        return []
    with ConversationLogLock(log_path):
        return _read_records_without_lock(log_path)


def append_conversation_record(record: dict[str, Any], path: Path | None = None) -> Path:
    log_path = conversation_log_path(path)
    _ensure_log_parent(log_path)
    with ConversationLogLock(log_path):
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return log_path


def _write_records_without_lock(path: Path, records: list[dict[str, Any]]) -> None:
    _ensure_log_parent(path)
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    content = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
    if content:
        content += "\n"
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def update_conversation_feedback(
    *,
    message_id: str | None,
    feedback: str,
    timestamp: str,
    path: Path | None = None,
    conversation_id: str | None = None,
    session_id: str | None = None,
    question: str | None = None,
    answer: str | None = None,
) -> dict[str, Any]:
    log_path = conversation_log_path(path)
    _ensure_log_parent(log_path)

    with ConversationLogLock(log_path):
        records = _read_records_without_lock(log_path)
        match_index: int | None = None

        for index in range(len(records) - 1, -1, -1):
            record = records[index]
            if message_id and record.get("message_id") == message_id:
                match_index = index
                break

        if match_index is None:
            for index in range(len(records) - 1, -1, -1):
                record = records[index]
                if conversation_id and record.get("conversation_id") != conversation_id:
                    continue
                if session_id and record.get("session_id") != session_id:
                    continue
                if question and record.get("question") != question:
                    continue
                if answer and record.get("answer") != answer:
                    continue
                match_index = index
                break

        if match_index is None:
            return {
                "updated": False,
                "message_id": message_id,
                "conversation_id": conversation_id,
                "session_id": session_id,
                "feedback": feedback,
                "timestamp": timestamp,
            }

        records[match_index]["feedback"] = feedback
        records[match_index]["feedback_timestamp"] = timestamp
        _write_records_without_lock(log_path, records)
        return {
            "updated": True,
            "message_id": records[match_index].get("message_id"),
            "conversation_id": records[match_index].get("conversation_id"),
            "session_id": records[match_index].get("session_id"),
            "feedback": feedback,
            "timestamp": timestamp,
        }


def filter_conversation_records(
    records: list[dict[str, Any]],
    *,
    username: str | None = None,
    employee_id: str | None = None,
    role: str | None = None,
    status: str | None = None,
    feedback: str | None = None,
    day: str | None = None,
    conversation_id: str | None = None,
    session_id: str | None = None,
    source_name: str | None = None,
    question_contains: str | None = None,
) -> list[dict[str, Any]]:
    normalized_username = (_normalize_string(username) or "").lower()
    normalized_employee_id = (_normalize_string(employee_id) or "").lower()
    normalized_role = (_normalize_string(role) or "").lower()
    normalized_status = (_normalize_string(status) or "").lower()
    normalized_feedback = (_normalize_string(feedback) or "").lower()
    normalized_day = _normalize_string(day)
    normalized_conversation_id = _normalize_string(conversation_id)
    normalized_session_id = _normalize_string(session_id)
    normalized_source_name = (_normalize_string(source_name) or "").lower()
    normalized_question_contains = (_normalize_string(question_contains) or "").lower()

    filtered: list[dict[str, Any]] = []
    for record in records:
        record_username = (_normalize_string(record.get("username")) or "").lower()
        record_employee_id = (_normalize_string(record.get("employee_id")) or "").lower()
        record_role = (_normalize_string(record.get("role")) or "").lower()
        record_status = (_normalize_string(record.get("status")) or "").lower()
        record_feedback = (_normalize_string(record.get("feedback")) or "").lower()
        record_day = _safe_timestamp_day(record.get("timestamp"))
        record_conversation_id = _normalize_string(record.get("conversation_id"))
        record_session_id = _normalize_string(record.get("session_id"))
        record_question = (_normalize_string(record.get("question")) or "").lower()

        if normalized_username and record_username != normalized_username:
            continue
        if normalized_employee_id and record_employee_id != normalized_employee_id:
            continue
        if normalized_role and record_role != normalized_role:
            continue
        if normalized_status and record_status != normalized_status:
            continue
        if normalized_feedback and record_feedback != normalized_feedback:
            continue
        if normalized_day and record_day != normalized_day:
            continue
        if normalized_conversation_id and record_conversation_id != normalized_conversation_id:
            continue
        if normalized_session_id and record_session_id != normalized_session_id:
            continue
        if normalized_question_contains and normalized_question_contains not in record_question:
            continue
        if normalized_source_name:
            flattened_sources = []
            primary_source = record.get("primary_source")
            if isinstance(primary_source, dict):
                flattened_sources.append(primary_source)
            supporting_sources = record.get("supporting_sources") or []
            if isinstance(supporting_sources, list):
                flattened_sources.extend(item for item in supporting_sources if isinstance(item, dict))
            if not any(
                normalized_source_name in ((_normalize_string(source.get("source_name")) or "").lower())
                for source in flattened_sources
            ):
                continue

        filtered.append(record)

    return filtered


def _top_users(records: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    conversation_sets: defaultdict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    for record in records:
        key = (
            _normalize_string(record.get("username")) or "anonymous",
            _normalize_string(record.get("full_name")) or "",
            _normalize_string(record.get("employee_id")) or "",
            _normalize_string(record.get("role")) or "unknown",
        )
        item = grouped.setdefault(
            key,
            {
                "username": key[0],
                "full_name": key[1],
                "employee_id": key[2],
                "role": key[3],
                "request_count": 0,
                "success_count": 0,
                "fallback_count": 0,
                "error_count": 0,
            },
        )
        item["request_count"] += 1
        status_value = (_normalize_string(record.get("status")) or "").lower()
        item[f"{status_value}_count"] = item.get(f"{status_value}_count", 0) + 1
        conversation_id = _normalize_string(record.get("conversation_id"))
        if conversation_id:
            conversation_sets[key].add(conversation_id)

    ranked = sorted(
        grouped.values(),
        key=lambda item: (item["request_count"], item.get("success_count", 0)),
        reverse=True,
    )
    for item in ranked:
        key = (
            item["username"],
            item["full_name"],
            item["employee_id"],
            item["role"],
        )
        item["conversation_count"] = len(conversation_sets[key])
    return ranked[:limit]


def _top_roles(records: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    users_by_role: defaultdict[str, set[str]] = defaultdict(set)
    for record in records:
        role = _normalize_role(record.get("role"))
        item = grouped.setdefault(
            role,
            {
                "role": role,
                "request_count": 0,
                "success_count": 0,
                "fallback_count": 0,
                "error_count": 0,
            },
        )
        item["request_count"] += 1
        status_value = (_normalize_string(record.get("status")) or "").lower()
        item[f"{status_value}_count"] = item.get(f"{status_value}_count", 0) + 1
        users_by_role[role].add(_normalize_string(record.get("username")) or "anonymous")

    ranked = sorted(grouped.values(), key=lambda item: item["request_count"], reverse=True)
    for item in ranked:
        item["user_count"] = len(users_by_role[item["role"]])
    return ranked[:limit]


def _top_questions(records: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    grouped: Counter[str] = Counter()
    for record in records:
        question = _normalize_string(record.get("question"))
        if question:
            grouped[question] += 1
    return [{"question": question, "count": count} for question, count in grouped.most_common(limit)]


def _failed_questions(records: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        status_value = (_normalize_string(record.get("status")) or "").lower()
        if status_value not in {"fallback", "error"}:
            continue
        key = (
            _normalize_string(record.get("question")) or "",
            _normalize_string(record.get("fallback_reason") or record.get("error_message")) or status_value,
        )
        item = grouped.setdefault(
            key,
            {
                "question": key[0],
                "reason": key[1],
                "count": 0,
                "status": status_value,
            },
        )
        item["count"] += 1
    ranked = sorted(grouped.values(), key=lambda item: item["count"], reverse=True)
    return ranked[:limit]


def _source_usage(records: list[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        sources: list[tuple[dict[str, Any], str]] = []
        primary_source = record.get("primary_source")
        if isinstance(primary_source, dict):
            sources.append((primary_source, "primary"))
        supporting_sources = record.get("supporting_sources")
        if isinstance(supporting_sources, list):
            sources.extend((source, "supporting") for source in supporting_sources if isinstance(source, dict))

        for source, role in sources:
            key = (
                _normalize_string(source.get("source_name")) or "Unknown source",
                _normalize_string(
                    source.get("location_label")
                    or source.get("page")
                    or source.get("slide")
                    or source.get("section")
                )
                or "",
                role,
            )
            item = grouped.setdefault(
                key,
                {
                    "source_name": key[0],
                    "location_label": key[1],
                    "role": role,
                    "count": 0,
                    "avg_score": 0.0,
                    "_scores": [],
                },
            )
            item["count"] += 1
            score_value = _safe_float(source.get("score") or source.get("final_score"))
            if score_value is not None:
                item["_scores"].append(score_value)

    ranked = sorted(grouped.values(), key=lambda item: item["count"], reverse=True)
    for item in ranked:
        scores = item.pop("_scores", [])
        item["avg_score"] = round(mean(scores), 4) if scores else None
    return ranked[:limit]


def _daily_activity(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        day = _safe_timestamp_day(record.get("timestamp"))
        if not day:
            continue
        item = grouped.setdefault(
            day,
            {
                "date": day,
                "total": 0,
                "success": 0,
                "fallback": 0,
                "error": 0,
                "feedback_useful": 0,
                "feedback_wrong": 0,
            },
        )
        item["total"] += 1
        status_value = (_normalize_string(record.get("status")) or "").lower()
        if status_value in {"success", "fallback", "error"}:
            item[status_value] += 1
        feedback_value = (_normalize_string(record.get("feedback")) or "").lower()
        if feedback_value == "useful":
            item["feedback_useful"] += 1
        elif feedback_value == "wrong":
            item["feedback_wrong"] += 1
    return [grouped[key] for key in sorted(grouped)]


def _performance_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    retrieval_times = [value for value in (_safe_float(item.get("retrieval_time_ms")) for item in records) if value is not None]
    qwen_times = [value for value in (_safe_float(item.get("qwen_time_ms")) for item in records) if value is not None]
    total_times = [value for value in (_safe_float(item.get("total_response_time_ms")) for item in records) if value is not None]
    fallback_count = sum(1 for item in records if (_normalize_string(item.get("status")) or "").lower() == "fallback")
    success_count = sum(1 for item in records if (_normalize_string(item.get("status")) or "").lower() == "success")
    error_count = sum(1 for item in records if (_normalize_string(item.get("status")) or "").lower() == "error")
    count = len(records)

    def percentile(values: list[float], rank: float) -> float | None:
        if not values:
            return None
        sorted_values = sorted(values)
        index = min(max(int(round((len(sorted_values) - 1) * rank)), 0), len(sorted_values) - 1)
        return round(sorted_values[index], 2)

    return {
        "avg_retrieval_time_ms": round(mean(retrieval_times), 2) if retrieval_times else None,
        "avg_qwen_time_ms": round(mean(qwen_times), 2) if qwen_times else None,
        "avg_total_response_time_ms": round(mean(total_times), 2) if total_times else None,
        "p95_total_response_time_ms": percentile(total_times, 0.95),
        "success_rate": round(success_count / count, 4) if count else 0.0,
        "fallback_rate": round(fallback_count / count, 4) if count else 0.0,
        "error_rate": round(error_count / count, 4) if count else 0.0,
    }


def build_analytics_payload(
    records: list[dict[str, Any]],
    *,
    applied_filters: dict[str, Any] | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    status_counter = Counter(
        (_normalize_string(record.get("status")) or "unknown").lower() for record in records
    )
    feedback_counter = Counter(
        (_normalize_string(record.get("feedback")) or "none").lower() for record in records
    )
    fallback_reasons = Counter(
        (_normalize_string(record.get("fallback_reason")) or "none")
        for record in records
        if (_normalize_string(record.get("status")) or "").lower() == "fallback"
    )

    unique_users = {
        (
            _normalize_string(record.get("username")) or "anonymous",
            _normalize_string(record.get("employee_id")) or "",
        )
        for record in records
    }
    unique_conversations = {
        _normalize_string(record.get("conversation_id"))
        for record in records
        if _normalize_string(record.get("conversation_id"))
    }

    return {
        "log_path": str(conversation_log_path(log_path)),
        "filters": applied_filters or {},
        "summary": {
            "total_records": len(records),
            "total_conversations": len(unique_conversations),
            "unique_users": len(unique_users),
            "average_questions_per_user": round(len(records) / len(unique_users), 2) if unique_users else 0.0,
            "status_breakdown": dict(status_counter),
            "feedback_breakdown": dict(feedback_counter),
            "top_fallback_reasons": [
                {"reason": reason, "count": count}
                for reason, count in fallback_reasons.most_common(10)
            ],
        },
        "top_users": _top_users(records),
        "top_roles": _top_roles(records),
        "top_questions": _top_questions(records),
        "failed_questions": _failed_questions(records),
        "top_sources": _source_usage(records),
        "daily_activity": _daily_activity(records),
        "performance": _performance_summary(records),
    }


def export_conversation_records_jsonl(records: list[dict[str, Any]]) -> str:
    if not records:
        return ""
    return "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
