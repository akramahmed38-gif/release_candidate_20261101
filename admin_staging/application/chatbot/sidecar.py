from __future__ import annotations
import asyncio
import importlib
import inspect
import json
import logging
import re
import threading
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from importlib import metadata as importlib_metadata
from importlib import util as importlib_util
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.error import URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .analytics import (
    append_conversation_record,
    conversation_log_path,
    update_conversation_feedback,
)
from .conversation_memory import (
    ConversationStore,
    FollowUpResolution,
    conversation_store_key,
    conversation_owner,
    detect_topic_alias,
    resolve_follow_up_question,
    starts_with_question_wording,
)
from .config import load_config
from .admission import AdmissionBusy, RequestAdmission
from .query_language import franco_clarification
from .content_runtime import watch_content_generations
from .question_lookup import question_key
from .follow_up_resolution import resolve_follow_up_via_llm
from .profiling import (
    activate_latency_profiler,
    create_request_id,
    maybe_new_latency_profiler,
    record_timing,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(base_path=PROJECT_ROOT)
SIDECAR_HOST = "127.0.0.1"
SIDECAR_PORT = 18011
REQUIRED_PACKAGES = ("pdfplumber", "chromadb", "ollama", "easyocr", "fastapi", "uvicorn")
SERVICE_LOGGER_NAME = "hr_training_chatbot_sidecar"
CLARIFICATION_PROMPT = "محتاج توضحلي أكتر تقصد إيه بالضبط؟"
CLARIFICATION_TTL_MINUTES = 10
CLARIFICATION_STATUS_PENDING = "pending"
CLARIFICATION_STATUS_FAILED = "failed"

def _configure_logger() -> logging.Logger:
    CONFIG.logs_path.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(SERVICE_LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler = logging.FileHandler(CONFIG.logs_path / "chatbot_sidecar.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


LOGGER = _configure_logger()
_service_lock = asyncio.Lock()


class IndexingAlreadyRunningError(Exception):
    pass


class IndexingInProgressError(Exception):
    pass


class ChatbotAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    debug: bool = False
    request_id: str | None = Field(default=None, max_length=200)
    session_id: str | None = Field(default=None, max_length=200)
    conversation_id: str | None = Field(default=None, max_length=200)
    message_id: str | None = Field(default=None, max_length=200)
    user: dict[str, Any] = Field(default_factory=dict)


class ChatbotFeedbackRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    answer: str = Field(..., min_length=1)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    rating: str = Field(..., pattern="^(useful|wrong)$")
    timestamp: str = Field(..., min_length=1, max_length=100)
    session_id: str | None = Field(default=None, max_length=200)
    conversation_id: str | None = Field(default=None, max_length=200)
    message_id: str | None = Field(default=None, max_length=200)
    user: dict[str, Any] = Field(default_factory=dict)



def _sidecar_error_message(exc: Exception) -> str:
    if isinstance(exc, ModuleNotFoundError):
        package_name = getattr(exc, "name", None) or str(exc)
        return f"Missing Python package: {package_name}. Run setup_chatbot_sidecar.bat"
    return str(exc)


def _timestamp_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _manifest_payload() -> dict[str, Any]:
    if not CONFIG.manifest_path.exists():
        return {}
    try:
        payload = json.loads(CONFIG.manifest_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _manifest_collection_name() -> str:
    payload = _manifest_payload()
    collection_name = payload.get("collection_name")
    if isinstance(collection_name, str) and collection_name.strip():
        return collection_name.strip()
    return CONFIG.collection_name


def _current_chunks_count(app: FastAPI) -> int:
    chatbot_service = getattr(app.state, "chatbot_service", None)
    if chatbot_service is not None:
        try:
            return chatbot_service.vector_store.count()
        except Exception:
            return int(getattr(app.state, "chunks_count", 0) or 0)
    return int(getattr(app.state, "chunks_count", 0) or 0)


def _indexing_state_payload(app: FastAPI) -> dict[str, Any]:
    return {
        "status": getattr(app.state, "indexing_status", "idle"),
        "indexing_status": getattr(app.state, "indexing_status", "idle"),
        "started_at": getattr(app.state, "indexing_started_at", None),
        "indexing_started_at": getattr(app.state, "indexing_started_at", None),
        "finished_at": getattr(app.state, "indexing_finished_at", None),
        "indexing_finished_at": getattr(app.state, "indexing_finished_at", None),
        "last_error": getattr(app.state, "last_index_error", None),
        "last_index_error": getattr(app.state, "last_index_error", None),
        "current_file": getattr(app.state, "current_file", None),
        "current_page": getattr(app.state, "current_page", None),
        "current_location_label": getattr(app.state, "current_location_label", None),
        "processed_pages": getattr(app.state, "processed_pages", 0),
        "total_pages": getattr(app.state, "total_pages", 0),
        "chunks_count": _current_chunks_count(app),
    }


def _set_indexing_state(app: FastAPI, **values: Any) -> None:
    for key, value in values.items():
        setattr(app.state, key, value)


def _feedback_log_path() -> Path:
    return CONFIG.logs_path / "chatbot_feedback.jsonl"


def _conversation_log_path() -> Path:
    return conversation_log_path(CONFIG.logs_path / "chatbot_conversations.jsonl")


def _append_feedback(payload: dict[str, Any]) -> None:
    CONFIG.logs_path.mkdir(parents=True, exist_ok=True)
    with _feedback_log_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _sanitize_user_context(user: dict[str, Any] | None) -> dict[str, Any]:
    payload = user or {}
    username = str(payload.get("username") or payload.get("email") or payload.get("employee_id") or "anonymous").strip()
    full_name = str(payload.get("full_name") or payload.get("name") or "").strip()
    employee_id = str(payload.get("employee_id") or payload.get("hr_id") or "").strip()
    role = str(payload.get("role") or "unknown").strip() or "unknown"
    return {
        "username": username or "anonymous",
        "full_name": full_name,
        "employee_id": employee_id,
        "role": role,
    }


def _clarification_key(conversation_id: str | None, session_id: str | None) -> str | None:
    return conversation_store_key(conversation_id, session_id)


def _clarification_expiry() -> str:
    return (datetime.now() + timedelta(minutes=CLARIFICATION_TTL_MINUTES)).isoformat(timespec="seconds")


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _clarification_options(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    clarification_payload = (result or {}).get("clarification")
    if not isinstance(clarification_payload, dict):
        return []
    raw_options = clarification_payload.get("options")
    if not isinstance(raw_options, list):
        return []
    return [option for option in raw_options if isinstance(option, dict)]


def _normalize_clarification_reply(reply: str) -> str:
    return str(reply or "").strip().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")).lower()


def _looks_like_standalone_question(text: str) -> bool:
    candidate = str(text or "").strip()
    if not candidate:
        return False
    if candidate.endswith(("?", "ØŸ")):
        return True
    if starts_with_question_wording(candidate):
        return True
    if detect_topic_alias(candidate) is not None:
        return True
    return False


def _match_clarification_option(entry: dict[str, Any], clarification_reply: str) -> dict[str, Any] | None:
    options = entry.get("clarification_options")
    if not isinstance(options, list) or not options:
        return None

    normalized_reply = _normalize_clarification_reply(clarification_reply)
    if not normalized_reply:
        return None

    if re.fullmatch(r"\d+", normalized_reply):
        selected_index = int(normalized_reply) - 1
        if 0 <= selected_index < len(options):
            selected_option = options[selected_index]
            return dict(selected_option) if isinstance(selected_option, dict) else None

    for option in options:
        if not isinstance(option, dict):
            continue
        option_id = _normalize_clarification_reply(str(option.get("id") or ""))
        option_label = _normalize_clarification_reply(str(option.get("label") or ""))
        if normalized_reply and normalized_reply in {option_id, option_label}:
            return dict(option)
    return None


def _resolve_clarification_question(
    entry: dict[str, Any],
    clarification_reply: str,
) -> tuple[str, dict[str, Any] | None, bool]:
    original_question = str(entry.get("original_question") or clarification_reply).strip() or clarification_reply
    selected_option = _match_clarification_option(entry, clarification_reply)
    if selected_option is not None:
        selected_question = str(
            selected_option.get("question")
            or selected_option.get("label")
            or original_question
        ).strip()
        return selected_question or original_question, selected_option, False

    normalized_original = _normalize_clarification_reply(original_question)
    normalized_reply = _normalize_clarification_reply(clarification_reply)
    standalone_new_question = (
        normalized_reply == normalized_original
        or detect_topic_alias(clarification_reply) is not None
        or _looks_like_standalone_question(clarification_reply)
    )
    if standalone_new_question:
        return clarification_reply.strip() or original_question, None, True

    enhanced_question = " ".join(
        part for part in [original_question, clarification_reply.strip()] if part
    ).strip()
    return enhanced_question or original_question, None, False


def _mark_clarification_attempt_failed(result: dict[str, Any]) -> dict[str, Any]:
    failed_result = dict(result)
    failed_result["type"] = "answer"
    failed_result["answer_type"] = "fallback"
    failed_result["answer"] = CONFIG.fallback_text
    failed_result["fallback_used"] = True
    failed_result["fallback_stage"] = "clarification"
    failed_result["fallback_reason"] = "clarification_attempt_failed"
    failed_result["sources"] = failed_result.get("sources", []) or []
    failed_result.pop("clarification", None)
    return failed_result


def _log_clarification_event(
    event_name: str,
    *,
    conversation_id: str | None = None,
    session_id: str | None = None,
    original_question: str | None = None,
    clarification_reply: str | None = None,
    enhanced_question: str | None = None,
    fallback_stage: str | None = None,
    fallback_reason: str | None = None,
) -> None:
    LOGGER.info(
        "%s conversation_id=%s session_id=%s original_question=%r clarification_reply=%r enhanced_question=%r fallback_stage=%s fallback_reason=%s",
        event_name,
        conversation_id,
        session_id,
        original_question,
        clarification_reply,
        enhanced_question,
        fallback_stage,
        fallback_reason,
    )


def _cleanup_expired_clarifications(app: FastAPI) -> None:
    entries_to_log: list[dict[str, Any]] = []
    with app.state.clarification_state_lock:
        for key, entry in list(app.state.clarification_state.items()):
            expires_at = _parse_timestamp(entry.get("expires_at"))
            if expires_at is None or expires_at > datetime.now():
                continue
            entries_to_log.append(dict(entry))
            del app.state.clarification_state[key]

    for entry in entries_to_log:
        _log_clarification_event(
            "clarification_expired",
            conversation_id=entry.get("conversation_id"),
            session_id=entry.get("session_id"),
            original_question=entry.get("original_question"),
            fallback_stage=entry.get("fallback_stage"),
            fallback_reason=entry.get("fallback_reason"),
        )


def _get_clarification_entry(app: FastAPI, conversation_id: str | None, session_id: str | None) -> dict[str, Any] | None:
    _cleanup_expired_clarifications(app)
    key = _clarification_key(conversation_id, session_id)
    if not key:
        return None

    with app.state.clarification_state_lock:
        entry = app.state.clarification_state.get(key)
        return dict(entry) if entry is not None else None


def _set_clarification_entry(
    app: FastAPI,
    conversation_id: str | None,
    session_id: str | None,
    entry: dict[str, Any],
) -> None:
    key = _clarification_key(conversation_id, session_id)
    if not key:
        return

    with app.state.clarification_state_lock:
        app.state.clarification_state[key] = dict(entry)


def _pop_clarification_entry(app: FastAPI, conversation_id: str | None, session_id: str | None) -> dict[str, Any] | None:
    _cleanup_expired_clarifications(app)
    key = _clarification_key(conversation_id, session_id)
    if not key:
        return None

    with app.state.clarification_state_lock:
        entry = app.state.clarification_state.pop(key, None)
        return dict(entry) if entry is not None else None


def _create_pending_clarification_entry(
    payload: ChatbotAskRequest,
    question: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    clarification_payload = result.get("clarification") if isinstance(result.get("clarification"), dict) else {}
    return {
        "status": CLARIFICATION_STATUS_PENDING,
        "conversation_id": payload.conversation_id,
        "session_id": payload.session_id,
        "original_question": question,
        "clarification_question": clarification_payload.get("question") or CLARIFICATION_PROMPT,
        "clarification_options": _clarification_options(result),
        "created_at": _timestamp_now(),
        "expires_at": _clarification_expiry(),
        "attempts": int(clarification_payload.get("attempts", 1) or 1),
        "fallback_stage": result.get("fallback_stage"),
        "fallback_reason": result.get("fallback_reason"),
        "top_source": result.get("top_source"),
        "top_score": result.get("top_score"),
    }


def _create_failed_clarification_entry(
    payload: ChatbotAskRequest,
    original_question: str,
    result: dict[str, Any],
    attempts: int,
) -> dict[str, Any]:
    return {
        "status": CLARIFICATION_STATUS_FAILED,
        "conversation_id": payload.conversation_id,
        "session_id": payload.session_id,
        "original_question": original_question,
        "created_at": _timestamp_now(),
        "expires_at": _clarification_expiry(),
        "attempts": attempts,
        "fallback_stage": result.get("fallback_stage"),
        "fallback_reason": "clarification_attempt_failed",
        "top_source": result.get("top_source"),
        "top_score": result.get("top_score"),
    }


def _is_repeat_failed_clarification(
    app: FastAPI,
    conversation_id: str | None,
    session_id: str | None,
    question: str,
) -> bool:
    entry = _get_clarification_entry(app, conversation_id, session_id)
    if not entry or entry.get("status") != CLARIFICATION_STATUS_FAILED:
        return False
    return str(entry.get("original_question") or "").strip() == question.strip()


def _build_clarification_response(
    payload: ChatbotAskRequest,
    question: str,
    result: dict[str, Any],
    attempts: int,
) -> dict[str, Any]:
    question_prompt = CLARIFICATION_PROMPT
    if result.get("fallback_reason") == "requested_aspect_not_supported":
        question_prompt = "تقصد أي جانب تحديدًا؟ وضّح النقطة المطلوبة لأبحث عنها في المادة التدريبية."
    response = {
        "type": "clarification",
        "answer_type": "clarification",
        "answer": question_prompt,
        "clarification": {
            "question": question_prompt,
            "reason": result.get("fallback_reason"),
            "original_question": question,
            "attempts": attempts,
        },
        "sources": [],
        "fallback_used": False,
        "fallback_stage": "clarification",
        "fallback_reason": "fallback_answer_replaced_by_clarification",
        "top_score": result.get("top_score"),
        "top_source": result.get("top_source"),
        "top_location": result.get("top_location"),
        "overlap_count": result.get("overlap_count", 0),
        "extractive_recovery_used": False,
        "conversation_id": payload.conversation_id,
        "session_id": payload.session_id,
        "message_id": payload.message_id,
        "follow_up_detected": bool(result.get("follow_up_detected", False)),
        "conversation_history_used": bool(result.get("conversation_history_used", False)),
        "resolved_question": result.get("resolved_question", question),
    }
    if payload.debug and "debug" in result:
        debug_payload = dict(result.get("debug") or {})
        debug_payload["fallback_stage"] = "clarification"
        debug_payload["fallback_reason"] = "fallback_answer_replaced_by_clarification"
        debug_payload["clarification"] = {
            "question": CLARIFICATION_PROMPT,
            "original_question": question,
            "attempts": attempts,
        }
        response["debug"] = debug_payload
    return response


def _build_conversation_record(
    *,
    request_payload: ChatbotAskRequest,
    question: str,
    timestamp: str,
    result: dict[str, Any] | None = None,
    status_value: str,
    error_message: str | None = None,
) -> dict[str, Any]:
    user_context = _sanitize_user_context(request_payload.user)
    clarification_payload = (result or {}).get("clarification") if isinstance((result or {}).get("clarification"), dict) else {}
    sources = (result or {}).get("sources", []) or []
    primary_source = (result or {}).get("primary_source")
    if primary_source is None:
        primary_source = next(
            (source for source in sources if isinstance(source, dict) and source.get("primary_source")),
            sources[0] if sources else None,
        )
    supporting_sources = (result or {}).get("supporting_sources")
    if supporting_sources is None:
        supporting_sources = [
            source
            for source in sources
            if isinstance(source, dict) and source is not primary_source
        ]

    return {
        "request_id": request_payload.request_id,
        "conversation_id": request_payload.conversation_id,
        "session_id": request_payload.session_id,
        "message_id": request_payload.message_id,
        "timestamp": timestamp,
        "username": user_context["username"],
        "full_name": user_context["full_name"],
        "employee_id": user_context["employee_id"],
        "role": user_context["role"],
        "question": question,
        "resolved_question": (result or {}).get("resolved_question", question),
        "normalized_question": (result or {}).get("normalized_question", question),
        "answer": (result or {}).get("answer", ""),
        "fallback_used": bool((result or {}).get("fallback_used", False)),
        "fallback_stage": (result or {}).get("fallback_stage"),
        "fallback_reason": (result or {}).get("fallback_reason"),
        "primary_source": primary_source,
        "supporting_sources": supporting_sources or [],
        "top_score": (result or {}).get("top_score"),
        "top_source": (result or {}).get("top_source"),
        "top_location": (result or {}).get("top_location"),
        "overlap_count": (result or {}).get("overlap_count"),
        "selected_chunks": (result or {}).get("selected_chunks") or [],
        "retrieval_time_ms": (result or {}).get("retrieval_time_ms"),
        "qwen_time_ms": (result or {}).get("qwen_time_ms"),
        "total_response_time_ms": (result or {}).get("total_response_time_ms"),
        "extractive_recovery_used": bool((result or {}).get("extractive_recovery_used", False)),
        "feedback": None,
        "status": status_value,
        "error_message": error_message,
        "clarification_triggered": (result or {}).get("type") == "clarification",
        "clarification_options": clarification_payload.get("options", []),
        "conversation_history_used": bool((result or {}).get("conversation_history_used", False)),
        "follow_up_detected": bool((result or {}).get("follow_up_detected", False)),
        "follow_up_reason": (result or {}).get("follow_up_reason"),
        "conversation_history_turn_count": (result or {}).get("conversation_history_turn_count"),
    }


def _append_conversation_log(record: dict[str, Any]) -> None:
    append_conversation_record(record, _conversation_log_path())


def _persist_conversation_record(record: dict[str, Any]) -> float:
    started = perf_counter()
    try:
        _append_conversation_log(record)
    except Exception as exc:  # pragma: no cover - defensive logging guard
        LOGGER.exception("Failed to persist conversation record: %s", exc)
    return round((perf_counter() - started) * 1000, 2)


def _resolve_follow_up_from_history(
    app: FastAPI,
    *,
    question: str,
    conversation_id: str | None,
    session_id: str | None,
    chatbot_service: Any | None,
) -> FollowUpResolution:
    store_key = conversation_store_key(conversation_id, session_id)
    conversation_store = getattr(app.state, "conversation_store", None)
    if conversation_store is None:
        return FollowUpResolution(
            resolved_question=question,
            used_history=False,
            follow_up_detected=False,
            reason="store_unavailable",
            store_key=store_key,
            turn_count=0,
        )

    snapshot = conversation_store.get_snapshot(conversation_id, session_id)
    # Some canonical business questions contain words also used in follow-ups.
    # Their complete, curated wording must not require a previous chat turn.
    lookup = getattr(getattr(chatbot_service, "retriever", None), "question_lookup", None)
    if lookup is not None:
        matches = lookup.match(question)
        if any(question_key(question) == question_key(row.get("metadata", {}).get("question_text", "")) for row in matches):
            return FollowUpResolution(
                resolved_question=question, used_history=False, follow_up_detected=False,
                reason="curated_standalone_question", store_key=store_key,
                turn_count=snapshot.turn_count if snapshot else 0,
            )
    return resolve_follow_up_question(
        question,
        snapshot,
        max_topic_tokens=CONFIG.conversation_followup_max_topic_tokens,
        llm_resolver=(
            None
            if chatbot_service is None
            else lambda current_question, active_topic, recent_turns: resolve_follow_up_via_llm(
                current_question,
                active_topic,
                recent_turns,
                ollama_client=chatbot_service.ollama_client,
                config=chatbot_service.config,
                logger=LOGGER,
            )
        ),
    )


def _conversation_history_trace_state(
    app: FastAPI,
    *,
    conversation_id: str | None,
    session_id: str | None,
) -> dict[str, Any]:
    store_key = conversation_store_key(conversation_id, session_id)
    conversation_store = getattr(app.state, "conversation_store", None)
    if conversation_store is None:
        return {
            "history_store_hit": False,
            "history_turn_count": 0,
            "active_topic_before": None,
            "conversation_store_key": store_key,
        }

    snapshot = conversation_store.get_snapshot(conversation_id, session_id)
    active_topic_before = None
    if snapshot is not None:
        anchor_turn = snapshot.latest_topical_user_turn()
        if anchor_turn is not None:
            active_topic_before = anchor_turn.resolved_topic_label()

    return {
        "history_store_hit": snapshot is not None,
        "history_turn_count": snapshot.turn_count if snapshot is not None else 0,
        "active_topic_before": active_topic_before,
        "conversation_store_key": store_key,
    }


def _save_conversation_exchange(
    app: FastAPI,
    *,
    payload: ChatbotAskRequest,
    original_question: str,
    resolved_question: str,
    response_payload: dict[str, Any],
    request_id: str,
    timestamp: str,
    question_text: str | None = None,
) -> None:
    conversation_store = getattr(app.state, "conversation_store", None)
    if conversation_store is None:
        return

    conversation_store.save_exchange(
        conversation_id=payload.conversation_id,
        session_id=payload.session_id,
        request_id=request_id,
        user_question=original_question,
        resolved_question=resolved_question,
        assistant_answer=str(response_payload.get("answer", "") or ""),
        answer_type=response_payload.get("answer_type"),
        message_id=payload.message_id,
        qa_id=response_payload.get("selected_qa_id"),
        source_name=response_payload.get("top_source"),
        question_text=question_text,
        timestamp=timestamp,
    )


def _import_for_diagnostics(package_name: str) -> None:
    if package_name == "easyocr":
        importlib.import_module("torch")
    importlib.import_module(package_name)


def _package_diagnostics() -> tuple[dict[str, dict[str, Any]], list[str]]:
    packages: dict[str, dict[str, Any]] = {}
    missing_packages: list[str] = []

    for package_name in REQUIRED_PACKAGES:
        installed = importlib_util.find_spec(package_name) is not None
        version: str | None = None
        importable = False
        error: str | None = None

        if installed:
            try:
                version = importlib_metadata.version(package_name)
            except Exception:
                version = None

            try:
                _import_for_diagnostics(package_name)
                importable = True
            except Exception as exc:  # pragma: no cover - depends on local environment
                error = str(exc)
        else:
            missing_packages.append(package_name)

        if installed and not importable:
            missing_packages.append(package_name)

        packages[package_name] = {
            "installed": installed,
            "importable": importable,
            "version": version,
            "error": error,
        }

    return packages, missing_packages


def _ollama_status() -> dict[str, Any]:
    def model_present(expected: str, available_models: list[str]) -> bool:
        return any(
            model_name == expected
            or model_name == f"{expected}:latest"
            or model_name.split(":", 1)[0] == expected
            for model_name in available_models
        )

    request = UrlRequest(url=f"{CONFIG.ollama_url}/api/tags", method="GET")
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
        models = [item.get("name", "") for item in payload.get("models", [])]
        return {
            "ok": True,
            "status_code": 200,
            "models": models,
            "required_models_present": {
                CONFIG.llm_model: model_present(CONFIG.llm_model, models),
                CONFIG.embedding_model: model_present(CONFIG.embedding_model, models),
            },
        }
    except URLError as exc:
        return {
            "ok": False,
            "status_code": None,
            "models": [],
            "required_models_present": {
                CONFIG.llm_model: False,
                CONFIG.embedding_model: False,
            },
            "error": str(exc),
        }
    except Exception as exc:  # pragma: no cover - defensive diagnostics guard
        return {
            "ok": False,
            "status_code": None,
            "models": [],
            "required_models_present": {
                CONFIG.llm_model: False,
                CONFIG.embedding_model: False,
            },
            "error": str(exc),
        }


def _chroma_status(app: FastAPI | None = None) -> dict[str, Any]:
    chatbot_service = getattr(app.state, "chatbot_service", None) if app is not None else None
    if chatbot_service is not None:
        try:
            return {
                "ok": True,
                "path": str(chatbot_service.config.chroma_path),
                "collection_name": chatbot_service.vector_store.collection_name,
                "chunks_count": chatbot_service.vector_store.count(),
            }
        except Exception as exc:
            return {
                "ok": False,
                "path": str(chatbot_service.config.chroma_path),
                "collection_name": getattr(chatbot_service.vector_store, "collection_name", chatbot_service.config.collection_name),
                "chunks_count": None,
                "error": str(exc),
            }

    try:
        import chromadb
        from chromadb.config import Settings
    except Exception as exc:  # pragma: no cover - depends on local environment
        return {
            "ok": False,
            "path": str(CONFIG.chroma_path),
            "collection_name": CONFIG.collection_name,
            "chunks_count": None,
            "error": str(exc),
        }

    try:
        client = chromadb.PersistentClient(
            path=str(CONFIG.chroma_path),
            settings=Settings(anonymized_telemetry=False),
        )
        collection_name = _manifest_collection_name()
        collection = client.get_collection(name=collection_name)
        return {
            "ok": True,
            "path": str(CONFIG.chroma_path),
            "collection_name": collection_name,
            "chunks_count": collection.count(),
        }
    except Exception as exc:  # pragma: no cover - depends on local environment
        return {
            "ok": False,
            "path": str(CONFIG.chroma_path),
            "collection_name": _manifest_collection_name(),
            "chunks_count": None,
            "error": str(exc),
        }


def _manifest_index_status() -> dict[str, Any]:
    payload = _manifest_payload()
    status_payload = {
        "manifest_path": str(CONFIG.manifest_path),
        "manifest_exists": CONFIG.manifest_path.exists(),
        "collection_name": _manifest_collection_name(),
        "files_indexed": 0,
        "chunks_count": 0,
        "last_indexed_at": None,
        "service_initialized": False,
        "service_error": None,
    }
    if not payload:
        return status_payload

    try:
        status_payload["files_indexed"] = len(payload.get("files", []))
        status_payload["chunks_count"] = int(payload.get("chunk_count", 0) or 0)
        status_payload["last_indexed_at"] = payload.get("indexed_at")
    except Exception as exc:
        status_payload["service_error"] = f"Could not read manifest: {exc}"
    return status_payload


def _build_chatbot_service():
    from .service import build_chatbot

    return build_chatbot(PROJECT_ROOT)


async def _run_index_job(app: FastAPI, chatbot_service, force_reindex: bool):
    indexing_lock = app.state.indexing_job_lock
    if not indexing_lock.acquire(blocking=False):
        raise IndexingAlreadyRunningError()

    def progress_callback(**payload: Any) -> None:
        _set_indexing_state(app, **payload)

    _set_indexing_state(
        app,
        indexing_status="running",
        indexing_started_at=_timestamp_now(),
        indexing_finished_at=None,
        last_index_error=None,
        current_file=None,
        current_page=None,
        current_location_label=None,
        processed_pages=0,
        total_pages=0,
        chunks_count=chatbot_service.vector_store.count(),
    )

    try:
        stats = await run_in_threadpool(
            chatbot_service.ensure_index,
            force_reindex,
            progress_callback,
        )
    except Exception as exc:
        _set_indexing_state(
            app,
            indexing_status="failed",
            indexing_finished_at=_timestamp_now(),
            last_index_error=_sidecar_error_message(exc),
            current_file=None,
            current_page=None,
            current_location_label=None,
            chunks_count=chatbot_service.vector_store.count(),
        )
        raise
    else:
        app.state.index_initialized = True
        _set_indexing_state(
            app,
            indexing_status="succeeded",
            indexing_finished_at=_timestamp_now(),
            last_index_error=None,
            current_file=None,
            current_page=None,
            current_location_label=None,
            chunks_count=stats.chunks_indexed,
        )
        return stats
    finally:
        indexing_lock.release()


async def _ensure_index_ready(app: FastAPI, chatbot_service) -> None:
    if getattr(app.state, "index_initialized", False):
        return

    if app.state.indexing_job_lock.locked():
        raise IndexingInProgressError()

    # Chat traffic only reads the existing trained collection. Indexing is explicit.
    if chatbot_service.vector_store.count() <= 0 and not getattr(getattr(chatbot_service, "config", None), "content_generation", None):
        raise RuntimeError("The existing knowledge index is empty; chat will not rebuild it automatically.")
    retriever = await run_in_threadpool(
        chatbot_service._build_retriever_for_store, chatbot_service.vector_store
    )
    with chatbot_service._active_index_lock.write_lock():
        chatbot_service.retriever = retriever
    app.state.index_initialized = True


async def _ensure_service(app: FastAPI):
    chatbot_service = getattr(app.state, "chatbot_service", None)
    if chatbot_service is not None:
        return chatbot_service

    async with _service_lock:
        chatbot_service = getattr(app.state, "chatbot_service", None)
        if chatbot_service is not None:
            return chatbot_service

        try:
            chatbot_service = await run_in_threadpool(_build_chatbot_service)
            app.state.chatbot_service = chatbot_service
            app.state.chatbot_error = None
            app.state.chunks_count = chatbot_service.vector_store.count()
            LOGGER.info("Chatbot sidecar service initialized.")
            return chatbot_service
        except Exception as exc:
            message = _sidecar_error_message(exc)
            app.state.chatbot_service = None
            app.state.chatbot_error = message
            LOGGER.exception("Chatbot sidecar initialization failed: %s", message)
            raise


def _service_index_status(app: FastAPI) -> dict[str, Any]:
    chatbot_service = getattr(app.state, "chatbot_service", None)
    if chatbot_service is None:
        manifest_status = _manifest_index_status()
        manifest_status["service_error"] = getattr(app.state, "chatbot_error", None)
        return manifest_status

    return {
        "manifest_path": str(chatbot_service.config.manifest_path),
        "manifest_exists": chatbot_service.config.manifest_path.exists(),
        "collection_name": chatbot_service.vector_store.collection_name,
        "files_indexed": chatbot_service._last_index_stats.files_indexed,
        "chunks_count": chatbot_service.vector_store.count(),
        "last_indexed_at": None,
        "service_initialized": True,
        "service_error": getattr(app.state, "chatbot_error", None),
    }


def _invoke_chatbot_ask(chatbot_service, question: str, debug: bool, request_id: str):
    try:
        parameters = inspect.signature(chatbot_service.ask).parameters
    except (TypeError, ValueError):
        parameters = {}

    if "request_id" in parameters:
        return chatbot_service.ask(question, debug, request_id=request_id)
    return chatbot_service.ask(question, debug)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.request_admission = RequestAdmission()
    app.state.chatbot_service = None
    app.state.chatbot_error = None
    app.state.indexing_job_lock = threading.Lock()
    app.state.clarification_state_lock = threading.Lock()
    app.state.clarification_state = {}
    app.state.conversation_store = ConversationStore(
        max_turns=CONFIG.conversation_history_max_turns,
        ttl_minutes=CONFIG.conversation_history_ttl_minutes,
    )
    app.state.indexing_status = "idle"
    app.state.indexing_started_at = None
    app.state.indexing_finished_at = None
    app.state.last_index_error = None
    app.state.current_file = None
    app.state.current_page = None
    app.state.current_location_label = None
    app.state.processed_pages = 0
    app.state.total_pages = 0
    app.state.chunks_count = 0
    app.state.index_initialized = False
    # Load the existing corpus once before readiness, never on a user's greeting.
    service = await _ensure_service(app)
    await _ensure_index_ready(app, service)
    refresh_task = asyncio.create_task(watch_content_generations(app, PROJECT_ROOT, LOGGER))
    try:
        yield
    finally:
        refresh_task.cancel()
        try:
            await refresh_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="HR Training Chatbot Sidecar", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service_initialized": getattr(app.state, "chatbot_service", None) is not None,
        "service_error": getattr(app.state, "chatbot_error", None),
    }


@app.get("/diagnostics")
async def diagnostics() -> dict[str, Any]:
    try:
        await _ensure_service(app)
    except Exception:
        pass

    packages, missing_packages = _package_diagnostics()
    return {
        "python_executable": sys.executable,
        "python_version": sys.version,
        "project_path": str(PROJECT_ROOT),
        "source_path": str(CONFIG.source_path),
        "knowledge_base_path": str(CONFIG.knowledge_base_path),
        "legacy_material_path": str(CONFIG.legacy_material_path),
        "materials_path": str(CONFIG.source_path),
        "chroma_path": str(CONFIG.chroma_path),
        "ocr_usage_report_path": str(PROJECT_ROOT / "ocr_usage_report.md"),
        "feedback_log_path": str(_feedback_log_path()),
        "conversation_log_path": str(_conversation_log_path()),
        "packages": packages,
        "missing_packages": missing_packages,
        "ollama_status": _ollama_status(),
        "chroma_status": _chroma_status(app),
        "index_status": _service_index_status(app),
        "indexing_state": _indexing_state_payload(app),
        "service_error": getattr(app.state, "chatbot_error", None),
    }


@app.get("/index-status")
async def index_status() -> dict[str, Any]:
    try:
        await _ensure_service(app)
    except Exception:
        pass

    return {
        **_indexing_state_payload(app),
        "index_status": _service_index_status(app),
        "chroma_status": _chroma_status(app),
    }


def _get_admission():
    controller = getattr(app.state, "request_admission", None)
    if controller is None:
        controller = RequestAdmission()
        app.state.request_admission = controller
    return controller


def _chatbot_request_failure(exc: Exception) -> HTTPException:
    if getattr(exc, "inference_busy", False):
        return HTTPException(status_code=503, detail="The assistant is busy. Please try again shortly.", headers={"Retry-After": "5"})
    timed_out = isinstance(exc, TimeoutError) or (isinstance(exc, URLError) and isinstance(exc.reason, TimeoutError))
    message = (
        "The assistant took too long to respond. Your previous conversation is saved; please try again."
        if timed_out else "The assistant could not complete this request. Please try again shortly."
    )
    return HTTPException(status_code=504 if timed_out else 503, detail=message)


@app.post("/ask")
async def ask(payload: ChatbotAskRequest):
    user = payload.user or {}
    identity = str(user.get("employee_id") or user.get("username") or "").strip()
    if not identity or identity.casefold() == "anonymous":
        raise HTTPException(status_code=401, detail="Please sign in before using the assistant.")
    try:
        async with _get_admission().acquire(identity):
            with conversation_owner(identity):
                response = franco_clarification(payload.question)
                if response is None:response = await _ask_impl(payload)
                return await _localize_reply(payload, response)
    except AdmissionBusy:
        return JSONResponse(status_code=503, content={"detail": "The assistant is busy. Please try again shortly."}, headers={"Retry-After": "5"})
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("Chatbot request failed")
        raise _chatbot_request_failure(exc) from exc


async def _localize_reply(payload, response):
    from .reply_language import localize_response
    from .citation_policy import apply_citation_policy
    service = getattr(app.state, 'chatbot_service', None)
    started=perf_counter()
    response=await run_in_threadpool(apply_citation_policy, response, PROJECT_ROOT)
    result=await run_in_threadpool(localize_response, response, payload.question, getattr(service, 'ollama_client', None))
    if isinstance(result,dict):
        result['reply_localization_time_ms']=round((perf_counter()-started)*1000,2)
        LOGGER.info('Chatbot reply language=%s translation_status=%s translation_model_call_count=%s localization_ms=%s',
                    result.get('reply_language'),result.get('translation_status','not_required'),
                    result.get('translation_model_call_count',0),result['reply_localization_time_ms'])
    return result


async def _ask_impl(payload: ChatbotAskRequest) -> dict[str, Any]:
    effective_request_id = payload.request_id or create_request_id("sidecar")
    payload = payload.model_copy(update={"request_id": effective_request_id})
    profiler = maybe_new_latency_profiler(
        enabled=CONFIG.enable_latency_profiling,
        request_id=effective_request_id,
    )

    with activate_latency_profiler(profiler):
        sidecar_started = perf_counter()
        validation_started = perf_counter()
        from .query_language import normalize_conversation_query
        question = normalize_conversation_query(payload.question.strip())
        validation_time_ms = round((perf_counter() - validation_started) * 1000, 2)
        record_timing("sidecar.request_validation_ms", validation_time_ms)
        if not question:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Question must not be empty.",
            )

        request_timestamp = _timestamp_now()
        total_response_time_ms = None
        clarification_lookup_started = perf_counter()
        clarification_entry = _get_clarification_entry(app, payload.conversation_id, payload.session_id)
        clarification_lookup_time_ms = round((perf_counter() - clarification_lookup_started) * 1000, 2)
        record_timing("sidecar.clarification_lookup_ms", clarification_lookup_time_ms)
        clarification_reply = None
        selected_option = None
        original_question = question
        enhanced_question = None
        clarification_attempts = 0
        question_for_rag = question
        resolving_pending_clarification = False
        clarification_resolution_time_ms = 0.0
        follow_up_resolution = FollowUpResolution(
            resolved_question=question,
            used_history=False,
            follow_up_detected=False,
            reason="not_checked",
            store_key=conversation_store_key(payload.conversation_id, payload.session_id),
            turn_count=0,
        )
        chatbot_service = None
        pending_clarification_entry = (
            clarification_entry
            if clarification_entry and clarification_entry.get("status") == CLARIFICATION_STATUS_PENDING
            else None
        )

        if pending_clarification_entry is not None:
            clarification_resolution_started = perf_counter()
            preview_selected_option = _match_clarification_option(pending_clarification_entry, question)
            if preview_selected_option is not None:
                popped_entry = _pop_clarification_entry(app, payload.conversation_id, payload.session_id)
                if popped_entry and popped_entry.get("status") == CLARIFICATION_STATUS_PENDING:
                    pending_clarification_entry = None
                    resolving_pending_clarification = True
                    clarification_attempts = int(popped_entry.get("attempts", 1) or 1)
                    original_question = str(popped_entry.get("original_question") or question).strip() or question
                    clarification_reply = question
                    enhanced_question, selected_option, clarification_standalone_new_question = _resolve_clarification_question(
                        popped_entry,
                        clarification_reply,
                    )
                    question_for_rag = enhanced_question or question
                    if clarification_standalone_new_question:
                        resolving_pending_clarification = False
                    _log_clarification_event(
                        "clarification_abandoned_new_question"
                        if clarification_standalone_new_question
                        else "clarification_reply",
                        conversation_id=payload.conversation_id,
                        session_id=payload.session_id,
                        original_question=original_question,
                        clarification_reply=clarification_reply,
                        enhanced_question=enhanced_question,
                        fallback_stage=popped_entry.get("fallback_stage"),
                        fallback_reason=popped_entry.get("fallback_reason"),
                    )
            clarification_resolution_time_ms += round(
                (perf_counter() - clarification_resolution_started) * 1000,
                2,
            )

        if not resolving_pending_clarification:
            ensure_service_started = perf_counter()
            chatbot_service = await _ensure_service(app)
            ensure_service_time_ms = round((perf_counter() - ensure_service_started) * 1000, 2)
            record_timing("sidecar.ensure_service_ms", ensure_service_time_ms)
            follow_up_resolution_started = perf_counter()
            try:
                follow_up_resolution = await run_in_threadpool(
                    _resolve_follow_up_from_history,
                    app,
                    question=question,
                    conversation_id=payload.conversation_id,
                    session_id=payload.session_id,
                    chatbot_service=chatbot_service,
                )
                question_for_rag = follow_up_resolution.resolved_question or question
            except Exception as exc:  # pragma: no cover - defensive guard
                LOGGER.warning(
                    "Conversation follow-up resolution failed request_id=%s conversation_id=%s session_id=%s error=%s",
                    effective_request_id,
                    payload.conversation_id,
                    payload.session_id,
                    exc,
                )
                follow_up_resolution = FollowUpResolution(
                    resolved_question=question,
                    used_history=False,
                    follow_up_detected=False,
                    reason="history_resolution_failed",
                    store_key=conversation_store_key(payload.conversation_id, payload.session_id),
                    turn_count=0,
                )
                question_for_rag = question
            follow_up_resolution_time_ms = round(
                (perf_counter() - follow_up_resolution_started) * 1000,
                2,
            )
            record_timing("sidecar.follow_up_resolution_ms", follow_up_resolution_time_ms)
            if follow_up_resolution.llm_used:
                record_timing("follow_up_llm_resolution_ms", follow_up_resolution.llm_resolution_time_ms)
            LOGGER.info(
                'event="conversation_follow_up_resolution" request_id=%s conversation_id=%s session_id=%s used_history=%s follow_up_detected=%s reason=%s llm_used=%s llm_failed_reason=%s llm_resolution_ms=%s original_question=%r resolved_question=%r turn_count=%s',
                effective_request_id,
                payload.conversation_id,
                payload.session_id,
                follow_up_resolution.used_history,
                follow_up_resolution.follow_up_detected,
                follow_up_resolution.reason,
                follow_up_resolution.llm_used,
                follow_up_resolution.llm_failed_reason,
                follow_up_resolution.llm_resolution_time_ms,
                question,
                question_for_rag,
                follow_up_resolution.turn_count,
            )

        if follow_up_resolution.needs_clarification:
            response = _build_clarification_response(payload, question, {}, 1)
            response["answer"] = follow_up_resolution.clarification_question or CLARIFICATION_PROMPT
            response["clarification"]["question"] = response["answer"]
            response["request_id"] = effective_request_id
            response["follow_up_detected"] = follow_up_resolution.follow_up_detected
            entry = _create_pending_clarification_entry(payload, question, response)
            _set_clarification_entry(app, payload.conversation_id, payload.session_id, entry)
            _persist_conversation_record(_build_conversation_record(
                request_payload=payload, question=question, timestamp=request_timestamp,
                result=response, status_value="clarification",
            ))
            return response

        if pending_clarification_entry is not None and not resolving_pending_clarification:
            clarification_resolution_started = perf_counter()
            should_abandon_pending_clarification = (
                follow_up_resolution.used_history
                or follow_up_resolution.follow_up_detected
                or detect_topic_alias(question) is not None
                or _looks_like_standalone_question(question)
            )
            if should_abandon_pending_clarification:
                popped_entry = _pop_clarification_entry(app, payload.conversation_id, payload.session_id)
                if popped_entry and popped_entry.get("status") == CLARIFICATION_STATUS_PENDING:
                    _log_clarification_event(
                        "clarification_abandoned_history_follow_up"
                        if follow_up_resolution.used_history or follow_up_resolution.follow_up_detected
                        else "clarification_abandoned_new_question",
                        conversation_id=payload.conversation_id,
                        session_id=payload.session_id,
                        original_question=str(popped_entry.get("original_question") or question).strip() or question,
                        clarification_reply=question,
                        enhanced_question=question_for_rag,
                        fallback_stage=popped_entry.get("fallback_stage"),
                        fallback_reason=popped_entry.get("fallback_reason"),
                    )
                pending_clarification_entry = None
            else:
                popped_entry = _pop_clarification_entry(app, payload.conversation_id, payload.session_id)
                if popped_entry and popped_entry.get("status") == CLARIFICATION_STATUS_PENDING:
                    pending_clarification_entry = None
                    resolving_pending_clarification = True
                    clarification_attempts = int(popped_entry.get("attempts", 1) or 1)
                    original_question = str(popped_entry.get("original_question") or question).strip() or question
                    clarification_reply = question
                    enhanced_question, selected_option, clarification_standalone_new_question = _resolve_clarification_question(
                        popped_entry,
                        clarification_reply,
                    )
                    question_for_rag = enhanced_question or question
                    if clarification_standalone_new_question:
                        resolving_pending_clarification = False
                    _log_clarification_event(
                        "clarification_abandoned_new_question"
                        if clarification_standalone_new_question
                        else "clarification_reply",
                        conversation_id=payload.conversation_id,
                        session_id=payload.session_id,
                        original_question=original_question,
                        clarification_reply=clarification_reply,
                        enhanced_question=enhanced_question,
                        fallback_stage=popped_entry.get("fallback_stage"),
                        fallback_reason=popped_entry.get("fallback_reason"),
                    )
            clarification_resolution_time_ms += round(
                (perf_counter() - clarification_resolution_started) * 1000,
                2,
            )

        if clarification_resolution_time_ms > 0:
            record_timing("sidecar.clarification_resolution_ms", clarification_resolution_time_ms)


        try:
            service_started = perf_counter()
            if chatbot_service is None:
                ensure_service_started = perf_counter()
                chatbot_service = await _ensure_service(app)
                ensure_service_time_ms = round((perf_counter() - ensure_service_started) * 1000, 2)
                record_timing("sidecar.ensure_service_ms", ensure_service_time_ms)
            if not getattr(app.state, "index_initialized", False):
                ensure_index_started = perf_counter()
                try:
                    await _ensure_index_ready(app, chatbot_service)
                except IndexingInProgressError:
                    _persist_conversation_record(
                        _build_conversation_record(
                            request_payload=payload,
                            question=question,
                            timestamp=request_timestamp,
                            status_value="error",
                            error_message="indexing_in_progress",
                        )
                    )
                    return JSONResponse(
                        status_code=status.HTTP_409_CONFLICT,
                        content={"status": "indexing_in_progress", "request_id": effective_request_id},
                    )
                finally:
                    ensure_index_time_ms = round((perf_counter() - ensure_index_started) * 1000, 2)
                    record_timing("sidecar.ensure_index_ready_ms", ensure_index_time_ms)
            history_trace_state = _conversation_history_trace_state(
                app,
                conversation_id=payload.conversation_id,
                session_id=payload.session_id,
            )
            user_context = _sanitize_user_context(payload.user)
            pending_clarification_found = bool(
                clarification_entry and clarification_entry.get("status") == CLARIFICATION_STATUS_PENDING
            )
            pre_ask_trace = {
                "conversation_store_key": history_trace_state["conversation_store_key"],
                "conversation_id": payload.conversation_id,
                "session_id": payload.session_id,
                "user_identifier": user_context.get("username"),
                "history_store_hit": history_trace_state["history_store_hit"],
                "history_turn_count": history_trace_state["history_turn_count"],
                "active_topic_before": history_trace_state["active_topic_before"],
                "original_question": question,
                "resolved_question": question_for_rag,
                "follow_up_detected": follow_up_resolution.follow_up_detected,
                "follow_up_reason": follow_up_resolution.reason,
                "follow_up_llm_used": follow_up_resolution.llm_used,
                "follow_up_llm_failed_reason": follow_up_resolution.llm_failed_reason,
                "follow_up_llm_resolution_ms": follow_up_resolution.llm_resolution_time_ms,
                "pending_clarification_found": pending_clarification_found,
                "clarification_resolution_used": resolving_pending_clarification,
                "final_question_passed_to_chatbot_ask": question_for_rag,
            }
            LOGGER.info(
                'event="pre_chatbot_ask_trace" %s',
                json.dumps(pre_ask_trace, ensure_ascii=False),
            )
            service_call_started = perf_counter()
            result = await run_in_threadpool(
                _invoke_chatbot_ask,
                chatbot_service,
                question_for_rag,
                payload.debug,
                effective_request_id,
            )
            service_call_time_ms = round((perf_counter() - service_call_started) * 1000, 2)
            record_timing("sidecar.service_call_ms", service_call_time_ms)
            total_response_time_ms = round((perf_counter() - service_started) * 1000, 2)
        except HTTPException:
            raise
        except Exception as exc:
            _persist_conversation_record(
                _build_conversation_record(
                    request_payload=payload,
                    question=question,
                    timestamp=request_timestamp,
                    status_value="error",
                    error_message=_sidecar_error_message(exc),
                )
            )
            raise _chatbot_request_failure(exc) from exc

        result = dict(result)
        result.setdefault("request_id", effective_request_id)
        result.setdefault("total_response_time_ms", total_response_time_ms)
        top_question_text = None
        for chunk in (result.get("retrieved_chunks") or []):
            if isinstance(chunk, dict) and chunk.get("question_text"):
                top_question_text = str(chunk.get("question_text") or "").strip() or None
                if top_question_text:
                    break
        result["top_question_text"] = top_question_text
        result["original_question"] = question
        result["resolved_question"] = question_for_rag
        result["conversation_history_used"] = follow_up_resolution.used_history
        result["follow_up_detected"] = follow_up_resolution.follow_up_detected
        result["follow_up_reason"] = follow_up_resolution.reason
        result["conversation_history_turn_count"] = follow_up_resolution.turn_count
        result["conversation_history_store_key"] = follow_up_resolution.store_key
        result["conversation_history_anchor_question"] = follow_up_resolution.anchor_question
        result["conversation_history_anchor_tokens"] = list(follow_up_resolution.anchor_tokens)
        result["follow_up_llm_used"] = follow_up_resolution.llm_used
        result["follow_up_llm_resolution_ms"] = follow_up_resolution.llm_resolution_time_ms
        result["follow_up_llm_failed_reason"] = follow_up_resolution.llm_failed_reason
        LOGGER.info(
            "Clarification trace pre-replacement request_id=%s conversation_id=%s session_id=%s answer=%r fallback_used=%s fallback_stage=%s fallback_reason=%s result_type=%s",
            effective_request_id,
            payload.conversation_id,
            payload.session_id,
            result.get("answer", ""),
            bool(result.get("fallback_used")),
            result.get("fallback_stage", "none"),
            result.get("fallback_reason"),
            result.get("type", "answer"),
        )
        if resolving_pending_clarification and (
            result.get("fallback_used") or result.get("type", "answer") == "clarification"
        ):
            if result.get("type", "answer") == "clarification":
                result = _mark_clarification_attempt_failed(result)
            else:
                result = dict(result)
                result["fallback_reason"] = "clarification_attempt_failed"
            result = dict(result)
            _set_clarification_entry(
                app,
                payload.conversation_id,
                payload.session_id,
                _create_failed_clarification_entry(
                    payload=payload,
                    original_question=original_question,
                    result=result,
                    attempts=clarification_attempts,
                ),
            )
            _log_clarification_event(
                "clarification_attempt_failed",
                conversation_id=payload.conversation_id,
                session_id=payload.session_id,
                original_question=original_question,
                clarification_reply=clarification_reply,
                enhanced_question=enhanced_question,
                fallback_stage=result.get("fallback_stage"),
                fallback_reason=result.get("fallback_reason"),
            )
        elif resolving_pending_clarification:
            _log_clarification_event(
                "pending_clarification_resolved",
                conversation_id=payload.conversation_id,
                session_id=payload.session_id,
                original_question=original_question,
                clarification_reply=clarification_reply,
                enhanced_question=enhanced_question,
                fallback_stage=result.get("fallback_stage"),
                fallback_reason=result.get("fallback_reason"),
            )

        is_repeat_failed_clarification = _is_repeat_failed_clarification(
            app,
            payload.conversation_id,
            payload.session_id,
            question,
        )
        response_type = result.get("type", "answer")
        should_store_service_clarification = (
            not resolving_pending_clarification
            and response_type == "clarification"
        )
        should_replace_fallback_with_clarification = (
            not resolving_pending_clarification
            and response_type == "answer"
            and bool(result.get("fallback_used"))
            and not is_repeat_failed_clarification
        )
        LOGGER.info(
            "Clarification trace decision request_id=%s conversation_id=%s session_id=%s service_clarification=%s should_replace=%s resolving_pending=%s result_type=%s fallback_used=%s repeat_failed=%s fallback_stage=%s fallback_reason=%s",
            effective_request_id,
            payload.conversation_id,
            payload.session_id,
            should_store_service_clarification,
            should_replace_fallback_with_clarification,
            resolving_pending_clarification,
            response_type,
            bool(result.get("fallback_used")),
            is_repeat_failed_clarification,
            result.get("fallback_stage", "none"),
            result.get("fallback_reason"),
        )
        if should_store_service_clarification:
            pending_entry = _create_pending_clarification_entry(payload, question, result)
            _set_clarification_entry(app, payload.conversation_id, payload.session_id, pending_entry)
            LOGGER.info(
                "Clarification state created from service request_id=%s conversation_id=%s session_id=%s original_question=%r attempts=%s fallback_stage=%s fallback_reason=%s",
                effective_request_id,
                payload.conversation_id,
                payload.session_id,
                question,
                pending_entry.get("attempts", 1),
                pending_entry.get("fallback_stage"),
                pending_entry.get("fallback_reason"),
            )
            _log_clarification_event(
                "service_clarification_created",
                conversation_id=payload.conversation_id,
                session_id=payload.session_id,
                original_question=question,
                fallback_stage=result.get("fallback_stage"),
                fallback_reason=result.get("fallback_reason"),
            )
        elif should_replace_fallback_with_clarification:
            pending_entry = _create_pending_clarification_entry(payload, question, result)
            _set_clarification_entry(app, payload.conversation_id, payload.session_id, pending_entry)
            LOGGER.info(
                "Clarification state created request_id=%s conversation_id=%s session_id=%s original_question=%r attempts=%s fallback_stage=%s fallback_reason=%s",
                effective_request_id,
                payload.conversation_id,
                payload.session_id,
                question,
                pending_entry.get("attempts", 1),
                pending_entry.get("fallback_stage"),
                pending_entry.get("fallback_reason"),
            )
            _log_clarification_event(
                "fallback_replaced_with_clarification",
                conversation_id=payload.conversation_id,
                session_id=payload.session_id,
                original_question=question,
                fallback_stage=result.get("fallback_stage"),
                fallback_reason=result.get("fallback_reason"),
            )
            _log_clarification_event(
                "pending_clarification_created",
                conversation_id=payload.conversation_id,
                session_id=payload.session_id,
                original_question=question,
                fallback_stage=result.get("fallback_stage"),
                fallback_reason=result.get("fallback_reason"),
            )
            result = _build_clarification_response(
                payload=payload,
                question=question,
                result=result,
                attempts=int(pending_entry.get("attempts", 1) or 1),
            )
            result["request_id"] = effective_request_id

        response_type = result.get("type", "answer")
        if response_type == "clarification":
            status_value = "clarification"
        else:
            status_value = "fallback" if result.get("fallback_used") else "success"
        conversation_persist_time_ms = _persist_conversation_record(
            _build_conversation_record(
                request_payload=payload,
                question=question,
                timestamp=request_timestamp,
                result=result,
                status_value=status_value,
            )
        )
        record_timing("sidecar.conversation_persist_ms", conversation_persist_time_ms)

        response_build_started = perf_counter()
        response_payload = {
            "request_id": effective_request_id,
            "type": response_type,
            "answer": result.get("answer", ""),
            "answer_type": result.get("answer_type"),
            "sources": result.get("sources", []) or [],
            "fallback_used": bool(result.get("fallback_used", False)),
            "fallback_stage": result.get("fallback_stage", "none"),
            "fallback_reason": result.get("fallback_reason"),
            "top_score": result.get("top_score"),
            "top_source": result.get("top_source"),
            "top_location": result.get("top_location"),
            "overlap_count": result.get("overlap_count", 0),
            "extractive_recovery_used": bool(result.get("extractive_recovery_used", False)),
            "conversation_id": payload.conversation_id,
            "session_id": payload.session_id,
            "message_id": payload.message_id,
            "selected_qa_id": result.get("selected_qa_id"),
            "follow_up_detected": bool(result.get("follow_up_detected", False)),
            "conversation_history_used": bool(result.get("conversation_history_used", False)),
            "resolved_question": result.get("resolved_question", question),
        }
        if response_type == "clarification":
            response_payload["clarification"] = result.get("clarification", {})
        response_build_time_ms = round((perf_counter() - response_build_started) * 1000, 2)
        record_timing("sidecar.response_build_ms", response_build_time_ms)

        if payload.debug and "debug" in result:
            debug_payload = dict(result["debug"])
            debug_payload.setdefault("total_response_time_ms", total_response_time_ms)
            debug_payload["request_id"] = effective_request_id
            debug_payload["ocr_called"] = bool(
                (profiler.to_dict() if profiler is not None else {}).get("flags", {}).get("ocr_called", False)
            )
            debug_payload["document_extraction_called"] = bool(
                (profiler.to_dict() if profiler is not None else {})
                .get("flags", {})
                .get("document_extraction_called", False)
            )
            debug_payload.update(follow_up_resolution.to_debug_dict())
            debug_payload["original_question"] = question
            debug_payload["resolved_question"] = question_for_rag
            debug_payload["clarification_resolution_used"] = resolving_pending_clarification
            response_payload["debug"] = debug_payload

        conversation_history_save_started = perf_counter()
        try:
            _save_conversation_exchange(
                app,
                payload=payload,
                original_question=question,
                resolved_question=question_for_rag,
                response_payload=response_payload,
                request_id=effective_request_id,
                timestamp=request_timestamp,
                question_text=top_question_text,
            )
        except Exception as exc:  # pragma: no cover - defensive logging guard
            LOGGER.warning(
                "Failed to save conversation history request_id=%s conversation_id=%s session_id=%s error=%s",
                effective_request_id,
                payload.conversation_id,
                payload.session_id,
                exc,
            )
        conversation_history_save_time_ms = round(
            (perf_counter() - conversation_history_save_started) * 1000,
            2,
        )
        record_timing("sidecar.conversation_history_save_ms", conversation_history_save_time_ms)

        final_latency_profile = profiler.to_dict() if profiler is not None else None
        if payload.debug and "debug" in response_payload:
            response_payload["debug"]["latency_profile"] = final_latency_profile
        json_serialize_started = perf_counter()
        json.dumps(response_payload, ensure_ascii=False)
        json_serialize_time_ms = round((perf_counter() - json_serialize_started) * 1000, 2)
        record_timing("response.json_serialize_ms", json_serialize_time_ms)
        total_sidecar_time_ms = round((perf_counter() - sidecar_started) * 1000, 2)
        record_timing("sidecar.total_ms", total_sidecar_time_ms)
        final_latency_profile = profiler.to_dict() if profiler is not None else None
        if payload.debug and "debug" in response_payload:
            response_payload["debug"]["latency_profile"] = final_latency_profile
        LOGGER.info(
            "Clarification trace response request_id=%s conversation_id=%s session_id=%s response_type=%s fallback_used=%s fallback_stage=%s fallback_reason=%s",
            effective_request_id,
            payload.conversation_id,
            payload.session_id,
            response_payload.get("type", "answer"),
            bool(response_payload.get("fallback_used", False)),
            response_payload.get("fallback_stage", "none"),
            response_payload.get("fallback_reason"),
        )
        return response_payload


@app.post("/feedback")
async def feedback(payload: ChatbotFeedbackRequest) -> dict[str, Any]:
    feedback_payload = {
        "question": payload.question.strip(),
        "answer": payload.answer,
        "sources": payload.sources,
        "rating": payload.rating,
        "timestamp": payload.timestamp,
        "session_id": payload.session_id,
        "conversation_id": payload.conversation_id,
        "message_id": payload.message_id,
        "user": _sanitize_user_context(payload.user),
    }
    await run_in_threadpool(_append_feedback, feedback_payload)
    update_result = await run_in_threadpool(
        update_conversation_feedback,
        message_id=payload.message_id,
        feedback=payload.rating,
        timestamp=payload.timestamp,
        path=_conversation_log_path(),
        conversation_id=payload.conversation_id,
        session_id=payload.session_id,
        question=payload.question.strip(),
        answer=payload.answer,
    )
    return {
        "status": "saved",
        "feedback_log_path": str(_feedback_log_path()),
        "conversation_log_path": str(_conversation_log_path()),
        "conversation_updated": bool(update_result.get("updated")),
    }




@app.post("/reindex")
async def reindex() -> dict[str, Any]:
    try:
        chatbot_service = await _ensure_service(app)
        stats = await _run_index_job(app, chatbot_service, True)
    except IndexingAlreadyRunningError:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"status": "already_running"},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_sidecar_error_message(exc),
        ) from exc

    return {
        "status": "succeeded",
        "files_indexed": stats.files_indexed,
        "chunks_count": stats.chunks_indexed,
        "rebuilt": stats.rebuilt,
        "manifest_path": stats.manifest_path,
        "collection_name": stats.collection_name,
    }


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=SIDECAR_HOST, port=SIDECAR_PORT, log_level="info")


if __name__ == "__main__":
    main()
