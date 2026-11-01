from __future__ import annotations
import json
import re
import socket
from dataclasses import dataclass, field
from typing import Any
from urllib.error import URLError
from .config import AppConfig
from .generation import OllamaClient

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
_CODE_FENCE_PREFIX_RE = re.compile(r"^\s*```(?:json)?\s*", re.IGNORECASE)
_CODE_FENCE_SUFFIX_RE = re.compile(r"\s*```\s*$", re.IGNORECASE)


def _clean_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        cleaned = _clean_string(item)
        if not cleaned:
            continue
        normalized = cleaned.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        items.append(cleaned)
    return items


def _clean_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def _extract_json_payload(raw_response: str) -> str:
    stripped = raw_response.strip()
    stripped = _CODE_FENCE_PREFIX_RE.sub("", stripped)
    stripped = _CODE_FENCE_SUFFIX_RE.sub("", stripped)
    match = _JSON_OBJECT_RE.search(stripped)
    return match.group(0).strip() if match else stripped


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


@dataclass
class QueryUnderstandingResult:
    rewritten_query: str = ""
    detected_intent: str = ""
    product_aliases: list[str] = field(default_factory=list)
    important_keywords: list[str] = field(default_factory=list)
    possible_meanings: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    used: bool = False
    failed_reason: str | None = None
    raw_response: str = ""
    latency_ms: float = 0.0


class QueryUnderstandingEngine:
    SYSTEM_PROMPT = (
        "You are a query understanding assistant for internal knowledge-base retrieval. "
        "Never answer the user. Never use outside knowledge. "
        "Your job is only to rewrite the user question into a clearer retrieval query and return structured hints. "
        "Return only valid JSON with exactly these keys: "
        "rewritten_query, detected_intent, product_aliases, important_keywords, "
        "possible_meanings, needs_clarification."
    )

    def __init__(self, config: AppConfig, ollama_client: OllamaClient, logger) -> None:
        self.config = config
        self.ollama_client = ollama_client
        self.logger = logger

    def understand(
        self,
        *,
        question: str,
        normalized_question: str,
        query_tokens: list[str],
    ) -> QueryUnderstandingResult:
        if not getattr(self.config, "enable_llm_query_understanding", False):
            return QueryUnderstandingResult(failed_reason="disabled")

        prompt = self._build_prompt(
            question=question,
            normalized_question=normalized_question,
            query_tokens=query_tokens,
        )
        timeout_seconds = float(getattr(self.config, "llm_query_understanding_timeout_sec", 5) or 5)

        try:
            raw_response = self.ollama_client.generate_raw(
                prompt=prompt,
                system_prompt=self.SYSTEM_PROMPT,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            reason = _exception_reason(exc)
            self.logger.warning("Query understanding failed reason=%s error=%s", reason, exc)
            return QueryUnderstandingResult(failed_reason=reason)

        return self._parse_response(raw_response)

    @staticmethod
    def _build_prompt(*, question: str, normalized_question: str, query_tokens: list[str]) -> str:
        query_token_text = ", ".join(query_tokens[:16])
        return (
            "Understand the user question only for retrieval.\n"
            "Do not answer the question.\n"
            "Rewrite the question into a clearer retrieval query.\n"
            "Use Egyptian Arabic synonyms, product aliases, and operational KB terms when useful.\n"
            "Return important_keywords that help retrieval.\n"
            "If the question is ambiguous, set needs_clarification to true and add possible_meanings.\n"
            "Return JSON only.\n\n"
            f"Original question: {question}\n"
            f"Normalized question: {normalized_question}\n"
            f"Expanded search tokens: {query_token_text}\n"
        )

    def _parse_response(self, raw_response: str) -> QueryUnderstandingResult:
        payload_text = _extract_json_payload(raw_response)
        if not payload_text:
            self.logger.warning("Query understanding returned empty response.")
            return QueryUnderstandingResult(raw_response=raw_response, failed_reason="empty_response")

        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            self.logger.warning("Query understanding returned invalid JSON: %r", raw_response)
            return QueryUnderstandingResult(raw_response=raw_response, failed_reason="invalid_json")

        if not isinstance(payload, dict):
            self.logger.warning("Query understanding returned non-object JSON: %r", payload)
            return QueryUnderstandingResult(raw_response=raw_response, failed_reason="invalid_json")

        result = QueryUnderstandingResult(
            rewritten_query=_clean_string(payload.get("rewritten_query")),
            detected_intent=_clean_string(payload.get("detected_intent")),
            product_aliases=_clean_string_list(payload.get("product_aliases")),
            important_keywords=_clean_string_list(payload.get("important_keywords")),
            possible_meanings=_clean_string_list(payload.get("possible_meanings")),
            needs_clarification=_clean_bool(payload.get("needs_clarification")),
            used=True,
            raw_response=raw_response,
        )

        if not result.rewritten_query:
            result.used = False
            result.failed_reason = "empty_payload"
            self.logger.warning("Query understanding returned no usable retrieval hints: %r", payload)
        return result
