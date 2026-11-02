from __future__ import annotations

import json
import logging
import re
import socket
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Sequence
from urllib.error import URLError

from .config import AppConfig
from .generation import OllamaClient
from .normalization import collapse_whitespace, normalize_text

_WORD_RE = re.compile(r"[A-Za-z0-9\u0600-\u06FF]+")
_QUESTION_MARKS = "?\u061F\uFF1F"
_CJK_CHAR_RE = re.compile(
    r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF\u3040-\u30FF\u31F0-\u31FF\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F\u3000-\u303F\uFF66-\uFF9F]"
)
_UNEXPECTED_CHAR_RE = re.compile(
    r"[^A-Za-z0-9\u0600-\u06FF\s\.,:;!\?\u061F،؛()\[\]\"'«»<>\-_/+%&*#=]"
)
_EXPECTED_PAYLOAD_KEYS = {"is_follow_up", "resolved_question"}

SYSTEM_PROMPT = (
    "You are a query rewriting assistant for an Arabic customer-support system. "
    "Your only job is follow-up resolution for retrieval. "
    "You must decide whether the current question depends on the active topic from the conversation, "
    "or whether it introduces its own standalone topic. "
    "If it is a follow-up, rewrite it into one clean standalone Arabic question that explicitly includes the active topic. "
    "Do not add facts that were not implied. "
    "Do not repeat words or concatenate previous questions. "
    "If it is standalone, return the current question exactly unchanged. "
    "Critical consistency rule: if you rewrite the question in any way, then is_follow_up must be true. "
    "The only time is_follow_up can be false is when resolved_question is exactly the same question unchanged. "
    "Short Arabic questions such as الشروط؟, الحد الأقصى؟, الرسوم كام؟, بيوصل امتى؟, or questions using pronouns like فيها or الغيها often depend on the active topic and should usually be rewritten as follow-ups when an active topic exists. "
    "Return only valid JSON with exactly these keys: is_follow_up, resolved_question."
)


@dataclass(frozen=True)
class ResolvedQuestion:
    is_follow_up: bool
    resolved_question: str
    used_llm: bool = False
    latency_ms: float = 0.0
    raw_response: str = ""
    failed_reason: str | None = None
    model_name: str | None = None


def _clean_string(value: Any) -> str:
    return collapse_whitespace(str(value or "").strip())


def _normalize(text: str) -> str:
    return normalize_text(text, for_search=True).lower().strip()


def _exception_reason(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, socket.timeout):
        return "timeout"
    if isinstance(exc, URLError) and isinstance(getattr(exc, "reason", None), socket.timeout):
        return "timeout"

    message = str(exc).strip().lower()
    if "timed out" in message or "timeout" in message:
        return "timeout"
    return "request_failed"


def _has_nearby_duplicate_words(text: str, window: int = 2) -> bool:
    tokens = [_normalize(token) for token in _WORD_RE.findall(text)]
    tokens = [token for token in tokens if token]
    for index, token in enumerate(tokens):
        lookahead = tokens[index + 1 : index + 1 + max(1, window)]
        if token and token in lookahead:
            return True
    return False


def _invalid_character_reason(text: str) -> str | None:
    if _CJK_CHAR_RE.search(text):
        return "cjk_characters_detected"
    if _UNEXPECTED_CHAR_RE.search(text):
        return "unexpected_characters"
    return None


def _max_reasonable_rewrite_length(original_question: str) -> int:
    original_length = len(_clean_string(original_question))
    return max(original_length * 3, original_length + 32, 56)


def _malformed_reason(original_question: str, resolved_question: str) -> str | None:
    normalized_original = _normalize(original_question)
    normalized_resolved = _normalize(resolved_question)
    if not normalized_resolved:
        return "empty_payload"
    if sum(resolved_question.count(marker) for marker in _QUESTION_MARKS) > 1:
        return "multiple_question_marks"
    if _has_nearby_duplicate_words(resolved_question):
        return "duplicate_words"
    if len(resolved_question) > _max_reasonable_rewrite_length(original_question):
        return "too_long"
    if normalized_resolved == normalized_original:
        return "unchanged_rewrite"
    return None


def _payload_schema_is_valid(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if set(payload.keys()) != _EXPECTED_PAYLOAD_KEYS:
        return False
    if not isinstance(payload.get("is_follow_up"), bool):
        return False
    if not isinstance(payload.get("resolved_question"), str):
        return False
    return True


def _recent_turn_text(turn: Any) -> str:
    if isinstance(turn, dict):
        role = _clean_string(turn.get("role"))
        content = _clean_string(turn.get("content"))
    else:
        role = _clean_string(getattr(turn, "role", ""))
        content = _clean_string(getattr(turn, "content", ""))

    if not role and not content:
        return ""
    if len(content) > 220:
        content = content[:217].rstrip() + "..."
    return f"{role or 'unknown'}: {content}"


def _render_recent_turns(recent_turns: Sequence[Any], max_turns: int = 6) -> str:
    rendered_turns = []
    for turn in list(recent_turns)[-max(1, int(max_turns or 6)) :]:
        rendered = _recent_turn_text(turn)
        if rendered:
            rendered_turns.append(rendered)

    if not rendered_turns:
        return "none"
    return "\n".join(f"- {row}" for row in rendered_turns)


def _build_prompt(*, question: str, active_topic: str | None, recent_turns: Sequence[Any]) -> str:
    active_topic_text = _clean_string(active_topic) or "none"
    recent_turns_text = _render_recent_turns(recent_turns)
    return (
        "Recent conversation turns:\n"
        f"{recent_turns_text}\n\n"
        f"Active topic from the conversation: {active_topic_text}\n"
        f"Current user question: {question}\n\n"
        "Task: Determine if the current question is a follow-up that depends on the active topic "
        "(missing an explicit subject, using a pronoun, or an elliptical question), "
        "OR if it introduces its own explicit new topic and should be treated standalone.\n\n"
        "Rules:\n"
        "- If it is a follow-up depending on the active topic, rewrite it into ONE clean, complete standalone Arabic question that explicitly includes the active topic.\n"
        "- Do not add information not implied by the original question.\n"
        "- Do not repeat or duplicate wording.\n"
        "- If the question already contains an explicit topic/product name of its own, or there is no active topic, output it exactly unchanged.\n"
        "- If resolved_question is different from the current question, then is_follow_up MUST be true.\n"
        "- If is_follow_up is false, resolved_question MUST equal the current question exactly.\n"
        "- Treat short elliptical Arabic questions as follow-ups when they clearly depend on the active topic.\n"
        "\nExamples:\n"
        '- Active topic: "معاشي" | Current user question: "اي شروط الالغاء" -> {"is_follow_up": true, "resolved_question": "ما شروط إلغاء معاشي؟"}\n'
        '- Active topic: "معاشي" | Current user question: "هل أقدر أعمل فيها أكتر من وثيقة؟" -> {"is_follow_up": true, "resolved_question": "هل أقدر أعمل أكتر من وثيقة معاشي؟"}\n'
        '- Active topic: "قرشك الأبيض" | Current user question: "الشروط؟" -> {"is_follow_up": true, "resolved_question": "ما شروط قرشك الأبيض؟"}\n'
        '- Active topic: "صحتك فوري" | Current user question: "بيوصل امتى؟" -> {"is_follow_up": true, "resolved_question": "وثيقة صحتك فوري بتوصل امتى؟"}\n'
        '- Active topic: "معاشي" | Current user question: "اشرحلي قرشك الأبيض." -> {"is_follow_up": false, "resolved_question": "اشرحلي قرشك الأبيض."}\n'
        '- Output ONLY valid JSON: {"is_follow_up": true/false, "resolved_question": "..."}\n'
        "- No explanation. No extra text.\n"
    )


def _json_parse_failure_result(
    *,
    cleaned_question: str,
    latency_ms: float,
    raw_response: str,
    model_name: str | None,
    logger: logging.Logger,
    cleaned_topic: str,
) -> ResolvedQuestion:
    logger.warning(
        "Follow-up LLM resolution rejected reason=follow_up_llm_json_parse_failed active_topic=%r question=%r raw=%r",
        cleaned_topic,
        cleaned_question,
        raw_response,
    )
    return ResolvedQuestion(
        is_follow_up=False,
        resolved_question=cleaned_question,
        used_llm=True,
        latency_ms=latency_ms,
        raw_response=raw_response,
        failed_reason="follow_up_llm_json_parse_failed",
        model_name=model_name,
    )


def resolve_follow_up_via_llm(
    question: str,
    active_topic: str | None,
    recent_turns: Sequence[Any],
    *,
    ollama_client: OllamaClient,
    config: AppConfig,
    logger: logging.Logger,
) -> ResolvedQuestion:
    cleaned_question = _clean_string(question)
    cleaned_topic = _clean_string(active_topic)
    model_name = getattr(config, "follow_up_llm_model", config.fast_llm_model)

    if not cleaned_question:
        return ResolvedQuestion(
            is_follow_up=False,
            resolved_question=cleaned_question,
            used_llm=False,
            failed_reason="empty_question",
            model_name=model_name,
        )

    if not getattr(config, "enable_llm_follow_up_resolution", False):
        return ResolvedQuestion(
            is_follow_up=False,
            resolved_question=cleaned_question,
            used_llm=False,
            failed_reason="disabled",
            model_name=model_name,
        )

    if not cleaned_topic:
        return ResolvedQuestion(
            is_follow_up=False,
            resolved_question=cleaned_question,
            used_llm=False,
            failed_reason="no_active_topic",
            model_name=model_name,
        )

    prompt = _build_prompt(
        question=cleaned_question,
        active_topic=cleaned_topic,
        recent_turns=recent_turns,
    )
    timeout_seconds = float(getattr(config, "llm_follow_up_resolution_timeout_sec", 3) or 3)

    started = perf_counter()
    try:
        raw_response = ollama_client.generate_raw(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        reason = _exception_reason(exc)
        logger.warning(
            "Follow-up LLM resolution failed reason=%s active_topic=%r question=%r error=%s",
            reason,
            cleaned_topic,
            cleaned_question,
            exc,
        )
        return ResolvedQuestion(
            is_follow_up=False,
            resolved_question=cleaned_question,
            used_llm=True,
            latency_ms=round((perf_counter() - started) * 1000, 2),
            failed_reason=reason,
            model_name=model_name,
        )

    latency_ms = round((perf_counter() - started) * 1000, 2)
    payload_text = raw_response.strip()
    if not payload_text:
        logger.warning(
            "Follow-up LLM resolution returned empty response active_topic=%r question=%r",
            cleaned_topic,
            cleaned_question,
        )
        return ResolvedQuestion(
            is_follow_up=False,
            resolved_question=cleaned_question,
            used_llm=True,
            latency_ms=latency_ms,
            raw_response=raw_response,
            failed_reason="empty_response",
            model_name=model_name,
        )

    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return _json_parse_failure_result(
            cleaned_question=cleaned_question,
            latency_ms=latency_ms,
            raw_response=raw_response,
            model_name=model_name,
            logger=logger,
            cleaned_topic=cleaned_topic,
        )

    if not _payload_schema_is_valid(payload):
        return _json_parse_failure_result(
            cleaned_question=cleaned_question,
            latency_ms=latency_ms,
            raw_response=raw_response,
            model_name=model_name,
            logger=logger,
            cleaned_topic=cleaned_topic,
        )

    is_follow_up = payload["is_follow_up"]
    resolved_question = _clean_string(payload["resolved_question"]) or cleaned_question
    invalid_character_reason = _invalid_character_reason(resolved_question)
    if invalid_character_reason is not None:
        logger.warning(
            "Follow-up LLM resolution rejected reason=%s active_topic=%r question=%r resolved_question=%r",
            invalid_character_reason,
            cleaned_topic,
            cleaned_question,
            resolved_question,
        )
        return ResolvedQuestion(
            is_follow_up=False,
            resolved_question=cleaned_question,
            used_llm=True,
            latency_ms=latency_ms,
            raw_response=raw_response,
            failed_reason=invalid_character_reason,
            model_name=model_name,
        )

    if not is_follow_up:
        if _normalize(resolved_question) != _normalize(cleaned_question):
            return ResolvedQuestion(
                is_follow_up=False,
                resolved_question=cleaned_question,
                used_llm=True,
                latency_ms=latency_ms,
                raw_response=raw_response,
                failed_reason="standalone_mutated",
                model_name=model_name,
            )
        return ResolvedQuestion(
            is_follow_up=False,
            resolved_question=cleaned_question,
            used_llm=True,
            latency_ms=latency_ms,
            raw_response=raw_response,
            model_name=model_name,
        )

    normalized_topic = _normalize(cleaned_topic)
    normalized_resolved = _normalize(resolved_question)
    if normalized_topic and normalized_topic not in normalized_resolved:
        return ResolvedQuestion(
            is_follow_up=False,
            resolved_question=cleaned_question,
            used_llm=True,
            latency_ms=latency_ms,
            raw_response=raw_response,
            failed_reason="missing_active_topic",
            model_name=model_name,
        )

    malformed_reason = _malformed_reason(cleaned_question, resolved_question)
    if malformed_reason is not None:
        return ResolvedQuestion(
            is_follow_up=False,
            resolved_question=cleaned_question,
            used_llm=True,
            latency_ms=latency_ms,
            raw_response=raw_response,
            failed_reason=malformed_reason,
            model_name=model_name,
        )

    return ResolvedQuestion(
        is_follow_up=True,
        resolved_question=resolved_question,
        used_llm=True,
        latency_ms=latency_ms,
        raw_response=raw_response,
        model_name=model_name,
    )
