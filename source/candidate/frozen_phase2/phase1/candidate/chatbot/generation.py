from __future__ import annotations

import inspect
import json
import logging
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from .config import AppConfig
from .normalization import contains_arabic, normalize_text, tokenize_for_search
from .profiling import get_latency_profiler, record_timing, set_counter, set_metadata


CHINESE_CHAR_RE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]")
INLINE_WHITESPACE_RE = re.compile(r"[^\S\n]+")
RAW_QA_FIELD_RE = re.compile(r"^(id|category|question|alternate_questions|keywords|answer)\s*:\s*(.*)$", re.IGNORECASE)
RAW_QA_LIST_FIELDS = {"alternate_questions", "keywords"}
RAW_QA_SCALAR_FIELDS = {"id", "category", "question"}
LIST_PREFIX_RE = re.compile(r"^\s*(?:\d+[\.\)\-]\s*|[*\-•]\s*)")
GROUNDING_BRIDGE_TOKENS = {
    "خطوات",
    "الاجراء",
    "اجراء",
    "الإجراء",
    "إجراء",
    "الحل",
    "النتيجة",
    "ملاحظة",
    "اجابه",
    "الاجابه",
    "الاجراءات",
    "الخطوات",
    "التالي",
    "التاليه",
    "كالتالي",
    "اولا",
    "ثانيا",
    "ثالثا",
    "رابعا",
    "خامسا",
    "وفق",
    "وفقا",
    "للمصدر",
    "المتاح",
    "يمكن",
    "يجب",
    "يرجي",
    "يرجى",
    "يلزم",
    "عند",
    "بعد",
    "قبل",
    "ثم",
    "حاله",
    "حالة",
    "وجود",
    "عدم",
}


def _normalize_embedding_input(text: str) -> str:
    normalized = normalize_text(str(text or ""), for_search=True).lower().strip()
    if normalized:
        return normalized
    return " ".join(str(text or "").split()).strip().casefold()


def _embedding_input_preview(text: str, max_length: int = 120) -> str:
    preview = " ".join(str(text or "").split()).strip()
    if len(preview) <= max_length:
        return preview
    return preview[: max_length - 3].rstrip() + "..."


def _infer_embedding_call_site() -> str:
    frame = inspect.currentframe()
    caller = frame.f_back if frame is not None else None
    while caller is not None:
        module_name = str(caller.f_globals.get("__name__", "") or "")
        function_name = caller.f_code.co_name
        if module_name.startswith("chatbot.") and function_name not in {
            "embed_texts",
            "_infer_embedding_call_site",
        }:
            return f"{module_name}.{function_name}"
        caller = caller.f_back
    return "unknown"


def clean_answer_preserve_formatting(text: str) -> str:
    if not text:
        return ""

    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized_text:
        return ""

    cleaned_lines: list[str] = []
    for raw_line in normalized_text.split("\n"):
        line = INLINE_WHITESPACE_RE.sub(" ", raw_line).strip()
        if not line:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def clean_generation_context(text: str) -> str:
    if not text:
        return ""

    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned_lines: list[str] = []
    skip_list_items = False
    in_answer_block = False

    for raw_line in normalized_text.split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()

        field_match = RAW_QA_FIELD_RE.match(stripped)
        if field_match:
            field_name = field_match.group(1).lower()
            field_value = field_match.group(2).strip()
            skip_list_items = field_name in RAW_QA_LIST_FIELDS
            in_answer_block = field_name == "answer"

            if field_name in RAW_QA_SCALAR_FIELDS | RAW_QA_LIST_FIELDS:
                continue
            if field_name == "answer":
                if field_value and field_value not in {"|", ">"}:
                    cleaned_lines.append(field_value)
                continue

        if skip_list_items:
            if not stripped:
                skip_list_items = False
            elif re.match(r"^[*\-•]\s+.+$", stripped):
                continue
            else:
                continue
            continue

        if in_answer_block or stripped:
            cleaned_lines.append(line)
        elif cleaned_lines and cleaned_lines[-1] != "":
            cleaned_lines.append("")

    return clean_answer_preserve_formatting("\n".join(cleaned_lines))


class InferenceBusy(RuntimeError):
    inference_busy = True


_INFERENCE_SLOT = threading.BoundedSemaphore(1)


class OllamaClient:
    def __init__(self, config: AppConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self._embedding_cache = OrderedDict()
        self._embedding_cache_lock = threading.Lock()

    def _request(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        method: str = "POST",
        *,
        timeout_seconds: float = 180,
    ) -> dict[str, Any]:
        url = f"{self.config.ollama_url}{path}"
        data = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        request = Request(url=url, data=data, headers=headers, method=method)
        inference = path in {"/api/embed", "/api/generate", "/api/chat"}
        if inference and not _INFERENCE_SLOT.acquire(blocking=False):
            raise InferenceBusy("Inference capacity is busy")
        process_lock = None
        try:
            if inference and self.config.content_sync_enabled:
                from .content_sync import SyncLock, SyncAlreadyRunning
                process_lock = SyncLock(self.config.project_path / "data/chatbot_content/inference.lock")
                try:
                    process_lock.__enter__()
                except SyncAlreadyRunning:
                    raise InferenceBusy("Inference capacity is busy") from None
            with urlopen(request, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8")
        finally:
            if process_lock is not None:
                process_lock.__exit__(None, None, None)
            if inference: _INFERENCE_SLOT.release()
        return json.loads(body) if body else {}

    def status(self) -> dict[str, Any]:
        try:
            payload = self._request("/api/tags", payload=None, method="GET")
            models = [item.get("name", "") for item in payload.get("models", [])]
            return {"ok": True, "models": models}
        except URLError as exc:
            self.logger.warning("Could not reach Ollama; error_type=%s", type(exc).__name__)
            return {"ok": False, "models": [], "error": "Model service unavailable"}
        except Exception as exc:
            self.logger.warning("Unexpected Ollama error; error_type=%s", type(exc).__name__)
            return {"ok": False, "models": [], "error": "Model service unavailable"}

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        cache_key = (self.config.embedding_model, tuple(texts)) if len(texts) == 1 else None
        if cache_key is not None:
            with self._embedding_cache_lock:
                cached = self._embedding_cache.get(cache_key)
                if cached is not None:
                    self._embedding_cache.move_to_end(cache_key)
                    set_counter("embedding.cache_hit", 1)
                    return [list(vector) for vector in cached]

        call_site = _infer_embedding_call_site()
        started = perf_counter()
        payload = self._request(
            "/api/embed",
            payload={
                "model": self.config.embedding_model,
                "input": texts,
                "options": {"num_thread": self.config.generation_threads},
                "keep_alive": -1,
            },
            timeout_seconds=8 if len(texts) == 1 else 180,
        )
        elapsed_ms = round((perf_counter() - started) * 1000, 2)
        embeddings = payload.get("embeddings", [])
        if not embeddings:
            raise RuntimeError("Ollama did not return embeddings.")
        if cache_key is not None:
            with self._embedding_cache_lock:
                self._embedding_cache[cache_key] = [list(vector) for vector in embeddings]
                self._embedding_cache.move_to_end(cache_key)
                while len(self._embedding_cache) > 256:
                    self._embedding_cache.popitem(last=False)

        profiler = get_latency_profiler()
        if profiler is not None:
            profiler.record_timing("embedding.total_ms", elapsed_ms, accumulate=True)
            profiler.increment_counter("embedding_call_count", 1)
            profiler.increment_counter("embedding_input_count", len(texts))
            profiler.set_metadata("embedding_model", self.config.embedding_model)

            call_sources = list(profiler.metadata.get("embedding_call_sources", []) or [])
            if call_site not in call_sources:
                call_sources.append(call_site)
            profiler.set_metadata("embedding_call_sources", call_sources)

            embedding_calls = list(profiler.metadata.get("embedding_calls", []) or [])
            embedding_calls.append(
                {
                    "call_site": call_site,
                    "input_count": len(texts),
                    "time_ms": elapsed_ms,
                }
            )
            profiler.set_metadata("embedding_calls", embedding_calls)

            seen_inputs = profiler.scratchpad.setdefault("embedding_seen_inputs", set())
            duplicate_previews = list(profiler.metadata.get("duplicate_embedding_inputs", []) or [])
            duplicate_detected = bool(profiler.metadata.get("duplicate_embedding_detected", False))
            for text in texts:
                normalized_input = _normalize_embedding_input(text)
                if not normalized_input:
                    continue
                if normalized_input in seen_inputs:
                    duplicate_detected = True
                    preview = _embedding_input_preview(text)
                    if preview and preview not in duplicate_previews:
                        duplicate_previews.append(preview)
                    continue
                seen_inputs.add(normalized_input)

            profiler.set_metadata("duplicate_embedding_detected", duplicate_detected)
            profiler.set_metadata("duplicate_embedding_inputs", duplicate_previews[:5])

        return embeddings

    def generation_model(self) -> str:
        if self.config.enable_fast_mode:
            return self.config.fast_llm_model
        return self.config.llm_model

    def generate_payload(
        self,
        prompt: str,
        system_prompt: str,
        *,
        model_name: str | None = None,
        timeout_seconds: float | None = None,
        response_format: dict | None = None,
    ) -> dict[str, Any]:
        selected_model = model_name or self.generation_model()
        payload={
            "model": selected_model, "system": system_prompt, "prompt": prompt,
            "stream": False, "keep_alive": -1,
            "options": {"temperature": self.config.temperature,
                "num_predict": self.config.generation_max_tokens,
                "num_ctx": self.config.generation_context_tokens,
                "num_thread": self.config.generation_threads}}
        if response_format is not None:
            if not isinstance(response_format,dict):raise ValueError('Expected a JSON schema')
            payload['format']=response_format
        return self._request(
                "/api/generate",
            payload=payload,
            timeout_seconds=float(timeout_seconds or self.config.generation_timeout_seconds),
        )

    def generate_raw(
        self,
        prompt: str,
        system_prompt: str,
        *,
        model_name: str | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        payload = self.generate_payload(
            prompt=prompt,
            system_prompt=system_prompt,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
        )
        return payload.get("response", "")

    def generate(
        self,
        prompt: str,
        system_prompt: str,
        *,
        model_name: str | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        return clean_answer_preserve_formatting(
            self.generate_raw(
                prompt=prompt,
                system_prompt=system_prompt,
                model_name=model_name,
                timeout_seconds=timeout_seconds,
            )
        )


@dataclass
class GenerationResult:
    answer: str
    llm_called: bool
    qwen_response_time_ms: float = 0.0
    qwen_call_count: int = 0
    raw_answer: str = ""
    retry_used: bool = False
    fallback_reason: str | None = None
    model_name: str | None = None
    prompt_character_count: int = 0
    prompt_build_time_ms: float = 0.0
    system_prompt_build_time_ms: float = 0.0
    response_clean_time_ms: float = 0.0
    input_token_count: int | None = None
    output_token_count: int | None = None
    ollama_total_duration_ms: float = 0.0
    ollama_load_duration_ms: float = 0.0
    ollama_prompt_eval_duration_ms: float = 0.0
    ollama_eval_duration_ms: float = 0.0
    streaming: bool = False


@dataclass
class GroundingValidationResult:
    passed: bool
    unsupported_claim_detected: bool
    unsupported_claims: list[dict[str, Any]]
    checked_segments: list[str]
    reason: str | None = None


def validate_grounded_answer(
    answer: str,
    chunks: list[dict[str, Any]],
    fallback_text: str,
) -> GroundingValidationResult:
    normalized_answer = clean_answer_preserve_formatting(answer)
    if not normalized_answer or normalized_answer == fallback_text:
        return GroundingValidationResult(
            passed=False,
            unsupported_claim_detected=False,
            unsupported_claims=[],
            checked_segments=[],
            reason="empty_or_fallback_answer",
        )

    cleaned_contexts = [
        clean_generation_context(chunk.get("text", ""))
        for chunk in chunks
        if clean_generation_context(chunk.get("text", ""))
    ]
    if not cleaned_contexts:
        return GroundingValidationResult(
            passed=False,
            unsupported_claim_detected=False,
            unsupported_claims=[],
            checked_segments=[],
            reason="no_context_chunks",
        )

    normalized_contexts = [
        normalize_text(context, for_search=True).lower()
        for context in cleaned_contexts
        if normalize_text(context, for_search=True).lower()
    ]
    context_tokens: set[str] = set()
    for context in cleaned_contexts:
        context_tokens.update(tokenize_for_search(context))

    checked_segments: list[str] = []
    unsupported_claims: list[dict[str, Any]] = []
    for raw_line in normalized_answer.split("\n"):
        stripped_line = LIST_PREFIX_RE.sub("", raw_line.strip()).strip(" -:\t")
        if not stripped_line:
            continue

        checked_segments.append(stripped_line)
        normalized_segment = normalize_text(stripped_line, for_search=True).lower()
        if not normalized_segment:
            continue
        if any(normalized_segment in context for context in normalized_contexts):
            continue

        segment_tokens = [
            token
            for token in tokenize_for_search(stripped_line)
            if token not in GROUNDING_BRIDGE_TOKENS
        ]
        if not segment_tokens:
            continue

        unsupported_tokens = [
            token for token in segment_tokens if token not in context_tokens
        ]
        unsupported_ratio = len(unsupported_tokens) / max(len(segment_tokens), 1)

        # Allow small phrasing differences without failing grounding.
        if unsupported_ratio > 0.85:
            unsupported_claims.append(
                {
                    "segment": stripped_line,
                    "unsupported_tokens": unsupported_tokens[:8],
                    "unsupported_ratio": round(unsupported_ratio, 2),
                }
            )

    return GroundingValidationResult(
        passed=not unsupported_claims,
        unsupported_claim_detected=bool(unsupported_claims),
        unsupported_claims=unsupported_claims,
        checked_segments=checked_segments,
        reason=None if not unsupported_claims else "unsupported_claims_detected",
    )


class AnswerGenerator:
    SYSTEM_PROMPT = (
        "أجب فقط من السياق المقدم.\n"
        "لا تستخدم أي معرفة خارجية.\n"
        "لا تخترع أي معلومة.\n"
        "إذا كان السياق لا يحتوي على الإجابة، أعد هذه العبارة حرفياً:\n"
        '"عذراً، هذه المعلومة غير متوفرة في الملفات المتاحة."\n'
        "أجب بالعربية الواضحة.\n"
        "إذا احتاجت الإجابة إلى خطوات، استخدم خطوات مرقمة.\n"
        "اجعل الإجابة موجزة وكاملة."
    )

    def __init__(self, config: AppConfig, ollama_client: OllamaClient, logger: logging.Logger) -> None:
        self.config = config
        self.ollama_client = ollama_client
        self.logger = logger

    def fallback(self) -> GenerationResult:
        return GenerationResult(answer=self.config.fallback_text, llm_called=False)

    def generate_answer(self, question: str, chunks: list[dict[str, Any]]) -> GenerationResult:
        if not chunks:
            return self.fallback()

        prompt_started = perf_counter()
        prompt = self._build_prompt(question, chunks)
        prompt_build_time_ms = round((perf_counter() - prompt_started) * 1000, 2)
        system_prompt_started = perf_counter()
        system_prompt = self._build_system_prompt(question)
        system_prompt_build_time_ms = round((perf_counter() - system_prompt_started) * 1000, 2)
        model_name = self.ollama_client.generation_model()
        self.logger.info(
            "Generator started chunk_count=%s prompt_character_count=%s question_has_arabic=%s llm_model=%s",
            len(chunks),
            len(prompt),
            contains_arabic(question),
            model_name,
        )
        record_timing("prompt.build_prompt_ms", prompt_build_time_ms)
        record_timing("prompt.build_system_prompt_ms", system_prompt_build_time_ms)
        set_counter("prompt.prompt_chunk_count", len(chunks))
        set_counter("prompt.prompt_character_count", len(prompt))
        set_metadata("llm.streaming", False)
        started = perf_counter()
        if hasattr(self.ollama_client, "generate_payload"):
            ollama_payload = self.ollama_client.generate_payload(prompt=prompt, system_prompt=system_prompt)
        else:
            ollama_payload = {
                "response": self.ollama_client.generate_raw(prompt=prompt, system_prompt=system_prompt)
            }
        qwen_response_time_ms = round((perf_counter() - started) * 1000, 2)
        raw_answer = str(ollama_payload.get("response", "") or "")
        clean_started = perf_counter()
        answer = clean_answer_preserve_formatting(raw_answer)
        response_clean_time_ms = round((perf_counter() - clean_started) * 1000, 2)
        input_token_count = self._safe_int(ollama_payload.get("prompt_eval_count"))
        output_token_count = self._safe_int(ollama_payload.get("eval_count"))
        ollama_total_duration_ms = self._ollama_duration_ms(ollama_payload.get("total_duration"))
        ollama_load_duration_ms = self._ollama_duration_ms(ollama_payload.get("load_duration"))
        ollama_prompt_eval_duration_ms = self._ollama_duration_ms(
            ollama_payload.get("prompt_eval_duration")
        )
        ollama_eval_duration_ms = self._ollama_duration_ms(ollama_payload.get("eval_duration"))
        record_timing("llm.ollama_request_ms", qwen_response_time_ms)
        record_timing("llm.answer_clean_ms", response_clean_time_ms)
        set_counter("llm.input_token_count", input_token_count)
        set_counter("llm.output_token_count", output_token_count)
        set_metadata("llm.model_name", model_name)
        set_metadata("llm.streaming", False)
        set_counter("llm.ollama_total_duration_ms", ollama_total_duration_ms)
        set_counter("llm.ollama_load_duration_ms", ollama_load_duration_ms)
        set_counter("llm.ollama_prompt_eval_duration_ms", ollama_prompt_eval_duration_ms)
        set_counter("llm.ollama_eval_duration_ms", ollama_eval_duration_ms)

        if not answer:
            self.logger.warning(
                "Generation fallback triggered reason=empty_llm_response qwen_call_count=1 raw_preview=%r",
                raw_answer[:240],
            )
            return self._llm_fallback(
                reason="empty_llm_response",
                qwen_response_time_ms=qwen_response_time_ms,
                qwen_call_count=1,
                raw_answer=raw_answer,
                model_name=model_name,
                prompt_character_count=len(prompt),
                prompt_build_time_ms=prompt_build_time_ms,
                system_prompt_build_time_ms=system_prompt_build_time_ms,
                response_clean_time_ms=response_clean_time_ms,
                input_token_count=input_token_count,
                output_token_count=output_token_count,
                ollama_total_duration_ms=ollama_total_duration_ms,
                ollama_load_duration_ms=ollama_load_duration_ms,
                ollama_prompt_eval_duration_ms=ollama_prompt_eval_duration_ms,
                ollama_eval_duration_ms=ollama_eval_duration_ms,
            )
        if self.config.fallback_text in answer:
            partial_answer = clean_answer_preserve_formatting(
                answer.replace(self.config.fallback_text, "")
            )

            if partial_answer:
                self.logger.info(
                    "LLM returned useful partial answer with fallback text; fallback sentence removed qwen_call_count=1 raw_preview=%r",
                    raw_answer[:240],
                )
                answer = partial_answer
            else:
                self.logger.warning(
                    "Generation fallback triggered reason=llm_returned_fallback_text qwen_call_count=1 raw_preview=%r",
                    raw_answer[:240],
                )
                return GenerationResult(
                    answer=self.config.fallback_text,
                    llm_called=True,
                    qwen_response_time_ms=qwen_response_time_ms,
                    qwen_call_count=1,
                    raw_answer=raw_answer,
                    fallback_reason="llm_returned_fallback_text",
                    model_name=model_name,
                    prompt_character_count=len(prompt),
                    prompt_build_time_ms=prompt_build_time_ms,
                    system_prompt_build_time_ms=system_prompt_build_time_ms,
                    response_clean_time_ms=response_clean_time_ms,
                    input_token_count=input_token_count,
                    output_token_count=output_token_count,
                    ollama_total_duration_ms=ollama_total_duration_ms,
                    ollama_load_duration_ms=ollama_load_duration_ms,
                    ollama_prompt_eval_duration_ms=ollama_prompt_eval_duration_ms,
                    ollama_eval_duration_ms=ollama_eval_duration_ms,
                )
        if self._should_retry_in_arabic(question, answer):
            chinese_ratio = self._chinese_ratio(answer)
            self.logger.warning(
                "Generation guard retry triggered reason=arabic_or_chinese_answer chinese_ratio=%.3f raw_preview=%r",
                chinese_ratio,
                raw_answer[:240],
            )
            retry_started = perf_counter()
            remaining_timeout = self.config.generation_timeout_seconds - (retry_started - started)
            if remaining_timeout <= 0:
                raise TimeoutError("Answer generation deadline exceeded")
            retry_system_prompt = self._build_system_prompt(question, force_arabic_retry=True)
            if hasattr(self.ollama_client, "generate_payload"):
                retry_payload = self.ollama_client.generate_payload(
                    prompt=prompt,
                    system_prompt=retry_system_prompt,
                    timeout_seconds=remaining_timeout,
                )
            else:
                retry_payload = {
                    "response": self.ollama_client.generate_raw(
                        prompt=prompt,
                        system_prompt=retry_system_prompt,
                        timeout_seconds=remaining_timeout,
                    )
                }
            qwen_response_time_ms += round((perf_counter() - retry_started) * 1000, 2)
            retry_raw_answer = str(retry_payload.get("response", "") or "")
            retry_answer = clean_answer_preserve_formatting(retry_raw_answer)
            retry_input_token_count = self._safe_int(retry_payload.get("prompt_eval_count"))
            retry_output_token_count = self._safe_int(retry_payload.get("eval_count"))
            input_token_count = retry_input_token_count or input_token_count
            output_token_count = retry_output_token_count or output_token_count
            ollama_total_duration_ms += self._ollama_duration_ms(retry_payload.get("total_duration"))
            ollama_load_duration_ms += self._ollama_duration_ms(retry_payload.get("load_duration"))
            ollama_prompt_eval_duration_ms += self._ollama_duration_ms(
                retry_payload.get("prompt_eval_duration")
            )
            ollama_eval_duration_ms += self._ollama_duration_ms(retry_payload.get("eval_duration"))
            if not retry_answer:
                self.logger.warning(
                    "Generation fallback triggered reason=arabic_chinese_guard_fallback_empty_retry qwen_call_count=2 raw_preview=%r",
                    retry_raw_answer[:240],
                )
                return self._llm_fallback(
                    reason="arabic_chinese_guard_fallback",
                    qwen_response_time_ms=qwen_response_time_ms,
                    qwen_call_count=2,
                    raw_answer=retry_raw_answer,
                    retry_used=True,
                    model_name=model_name,
                    prompt_character_count=len(prompt),
                    prompt_build_time_ms=prompt_build_time_ms,
                    system_prompt_build_time_ms=system_prompt_build_time_ms,
                    response_clean_time_ms=response_clean_time_ms,
                    input_token_count=input_token_count,
                    output_token_count=output_token_count,
                    ollama_total_duration_ms=round(ollama_total_duration_ms, 2),
                    ollama_load_duration_ms=round(ollama_load_duration_ms, 2),
                    ollama_prompt_eval_duration_ms=round(ollama_prompt_eval_duration_ms, 2),
                    ollama_eval_duration_ms=round(ollama_eval_duration_ms, 2),
                )
            if self.config.fallback_text in retry_answer:
                self.logger.warning(
                    "Generation fallback triggered reason=arabic_chinese_guard_returned_fallback_text qwen_call_count=2 raw_preview=%r",
                    retry_raw_answer[:240],
                )
                return GenerationResult(
                    answer=self.config.fallback_text,
                    llm_called=True,
                    qwen_response_time_ms=qwen_response_time_ms,
                    qwen_call_count=2,
                    raw_answer=retry_raw_answer,
                    retry_used=True,
                    fallback_reason="arabic_chinese_guard_fallback",
                    model_name=model_name,
                    prompt_character_count=len(prompt),
                    prompt_build_time_ms=prompt_build_time_ms,
                    system_prompt_build_time_ms=system_prompt_build_time_ms,
                    response_clean_time_ms=response_clean_time_ms,
                    input_token_count=input_token_count,
                    output_token_count=output_token_count,
                    ollama_total_duration_ms=round(ollama_total_duration_ms, 2),
                    ollama_load_duration_ms=round(ollama_load_duration_ms, 2),
                    ollama_prompt_eval_duration_ms=round(ollama_prompt_eval_duration_ms, 2),
                    ollama_eval_duration_ms=round(ollama_eval_duration_ms, 2),
                )
            if self._should_retry_in_arabic(question, retry_answer):
                retry_ratio = self._chinese_ratio(retry_answer)
                self.logger.warning(
                    "Generation fallback triggered reason=arabic_chinese_guard_retry_invalid chinese_ratio=%.3f raw_preview=%r",
                    retry_ratio,
                    retry_raw_answer[:240],
                )
                return self._llm_fallback(
                    reason="arabic_chinese_guard_fallback",
                    qwen_response_time_ms=qwen_response_time_ms,
                    qwen_call_count=2,
                    raw_answer=retry_raw_answer,
                    retry_used=True,
                    model_name=model_name,
                    prompt_character_count=len(prompt),
                    prompt_build_time_ms=prompt_build_time_ms,
                    system_prompt_build_time_ms=system_prompt_build_time_ms,
                    response_clean_time_ms=response_clean_time_ms,
                    input_token_count=input_token_count,
                    output_token_count=output_token_count,
                    ollama_total_duration_ms=round(ollama_total_duration_ms, 2),
                    ollama_load_duration_ms=round(ollama_load_duration_ms, 2),
                    ollama_prompt_eval_duration_ms=round(ollama_prompt_eval_duration_ms, 2),
                    ollama_eval_duration_ms=round(ollama_eval_duration_ms, 2),
                )
            self.logger.info(
                "Generator completed after Arabic retry qwen_call_count=2 qwen_time_ms=%s llm_model=%s",
                qwen_response_time_ms,
                model_name,
            )
            return GenerationResult(
                answer=retry_answer,
                llm_called=True,
                qwen_response_time_ms=qwen_response_time_ms,
                qwen_call_count=2,
                raw_answer=retry_raw_answer,
                retry_used=True,
                model_name=model_name,
                prompt_character_count=len(prompt),
                prompt_build_time_ms=prompt_build_time_ms,
                system_prompt_build_time_ms=system_prompt_build_time_ms,
                response_clean_time_ms=response_clean_time_ms,
                input_token_count=input_token_count,
                output_token_count=output_token_count,
                ollama_total_duration_ms=round(ollama_total_duration_ms, 2),
                ollama_load_duration_ms=round(ollama_load_duration_ms, 2),
                ollama_prompt_eval_duration_ms=round(ollama_prompt_eval_duration_ms, 2),
                ollama_eval_duration_ms=round(ollama_eval_duration_ms, 2),
            )
        self.logger.info(
            "Generator completed successfully qwen_call_count=1 qwen_time_ms=%s llm_model=%s",
            qwen_response_time_ms,
            model_name,
        )
        return GenerationResult(
            answer=answer,
            llm_called=True,
            qwen_response_time_ms=qwen_response_time_ms,
            qwen_call_count=1,
            raw_answer=raw_answer,
            model_name=model_name,
            prompt_character_count=len(prompt),
            prompt_build_time_ms=prompt_build_time_ms,
            system_prompt_build_time_ms=system_prompt_build_time_ms,
            response_clean_time_ms=response_clean_time_ms,
            input_token_count=input_token_count,
            output_token_count=output_token_count,
            ollama_total_duration_ms=ollama_total_duration_ms,
            ollama_load_duration_ms=ollama_load_duration_ms,
            ollama_prompt_eval_duration_ms=ollama_prompt_eval_duration_ms,
            ollama_eval_duration_ms=ollama_eval_duration_ms,
        )

    def _build_prompt(self, question: str, chunks: list[dict[str, Any]]) -> str:
        context_blocks: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            context_text = clean_generation_context(chunk.get("text", ""))
            context_blocks.append(
                "\n".join(
                    [
                        f"[مقطع {index}]",
                        f"المصدر: {chunk['source_name']}",
                        f"الموضع: {chunk['location_label']}",
                        f"النص: {context_text}",
                    ]
                )
            )

        return "\n\n".join(
            [
                "السياق المسموح به فقط:",
                "\n\n".join(context_blocks),
                f"سؤال المستخدم: {question}",
                "الإجابة:",
            ]
        )

    def _build_system_prompt(self, question: str, force_arabic_retry: bool = False) -> str:
        prompt = self.SYSTEM_PROMPT
        if self.config.strict_grounded_mode:
            prompt = (
                f"{prompt}\n"
                "قواعد إلزامية للإجابة من السياق:\n"
                "\n"
                "أولاً: فهم السؤال\n"
                "1. افهم سؤال المستخدم حتى لو كان مكتوبًا بالعامية أو بصياغة غير دقيقة أو به أخطاء إملائية.\n"
                "2. اربط بين ألفاظ العامية والمعنى المقصود داخل السياق، مثل:\n"
                "   ينفع = يمكن، من غير = بدون، عايز = يريد، اعمل = أنفذ، مش ظاهر = غير ظاهر، فلوس = أموال، كارت = بطاقة.\n"
                "3. اربط بين الأسماء المختلفة لنفس المنتج أو الخدمة إذا كانت مذكورة في السياق، مثل:\n"
                "   الكارت الأصفر = الكارت الاصفر = البطاقة الصفراء = Yellow Card = اليلو كارد = يولو كارد.\n"
                "\n"
                "ثانياً: الالتزام بالسياق\n"
                "4. استخدم فقط المعلومات الموجودة صراحة أو بوضوح داخل السياق المقدم.\n"
                "5. لا تستخدم أي معرفة خارجية، ولا تضف شروطًا أو أسبابًا أو خطوات غير مذكورة في السياق.\n"
                "6. مسموح بتحويل المعلومة الواضحة في السياق إلى إجابة مباشرة بدون إضافة معلومة جديدة.\n"
                "   مثال: إذا كان السياق يقول إن الكارت الأصفر إجباري ولا يمكن عدم اختياره، وسأل المستخدم هل ينفع بدون الكارت الأصفر، فالإجابة تكون: لا، لا يمكن بدون الكارت الأصفر.\n"
                "7. إذا كان السياق يقول إن خدمة معينة إجبارية، فلا تعتبر باقي الخدمات المذكورة معها إجبارية إلا إذا قال السياق ذلك صراحة.\n"
                "   مثال: إذا كان السياق يقول إن الكارت الأصفر إجباري، فهذا لا يعني أن Azimut إجباري.\n"
                "\n"
                "ثالثاً: شكل الإجابة\n"
                "8. أجب على المستخدم مباشرة بدون شرح طريقة التفكير أو خطوات الوصول للإجابة.\n"
                "9. ممنوع كتابة عبارات مثل: خطوات الإجابة، بناءً على المقطع، من السياق، من المصدر، في الملف، حسب المستند.\n"
                "10. لا تذكر رقم المقطع أو اسم الملف أو مصدر المعلومة داخل الإجابة.\n"
                "11. لا تكتب عناوين عامة مثل: الإجابة، الحل، خطوات الإجراء، إلا إذا كان السؤال يطلب خطوات فعلية.\n"
                "12. اجعل الإجابة عملية ومباشرة وبنفس لغة سؤال المستخدم.\n"
                "13. إذا كان السؤال بسيطًا، اجعل الإجابة قصيرة وواضحة.\n"
                "14. إذا كان السؤال عن خطوات إجراء، اكتب الخطوات مرتبة وواضحة.\n"
                "15. إذا كان السؤال عن حد أو رسوم أو مدة أو رقم، اذكر الرقم كاملًا مع الوحدة أو العملة إذا كانت موجودة في السياق.\n"
                "   مثال: لا تقل 25 معاملة فقط إذا كان السياق يحتوي على 25 معاملة بإجمالي 60,000 جنيه يوميًا.\n"
                "16. استخدم ألفاظ دقيقة مثل: الحد الأقصى، حد التعاملات، رسوم السحب، مدة التفعيل، ولا تستخدم ألفاظ غير مناسبة مثل المدة القصوى بدل حد التعاملات.\n"
                "\n"
                "رابعاً: اكتمال الإجابة\n"
                "17. إذا كان السياق يحتوي على أكثر من جزء مفيد للإجابة، اجمع الأجزاء المهمة في إجابة واحدة مختصرة ومتكاملة.\n"
                "18. إذا كان السؤال عن مقارنة أو اختيار، وضّح الفرق بين الحالات المذكورة في السياق.\n"
                "19. إذا كان السؤال عن خدمة أو منتج، اذكر الحكم أو الإجراء الأساسي أولًا، ثم أي تفاصيل مهمة بعده.\n"
                "20. إذا كان السؤال عن مشكلة، اذكر سببها أو معناها إذا كان موجودًا في السياق، ثم الإجراء المطلوب.\n"
                "\n"
                "خامساً: عدم توفر المعلومة\n"
                "21. إذا كان السياق يحتوي على جزء مفيد من الإجابة، أجب بهذا الجزء فقط ولا تضف عبارة عدم التوفر.\n"
                "22. استخدم عبارة عدم التوفر فقط إذا لم تجد أي إجابة مفيدة في السياق بالكامل.\n"
                f"23. عبارة عدم التوفر المسموح بها هي فقط: \"{self.config.fallback_text}\"\n"
                "24. لا تخلط بين إجابة مفيدة وعبارة عدم التوفر في نفس الرد.\n"
                "25. يجب أن تكون الإجابة باللغة العربية فقط.\n"
                "26. ممنوع استخدام أي كلمات أو حروف صينية أو يابانية أو كورية أو أي لغة أخرى داخل الإجابة.\n"
                "27. وجود كلمات تقنية إنجليزية مثل POS أو ATM أو Yellow Card أو OTP مسموح فقط إذا كانت موجودة في السياق أو ضرورية لفهم الخدمة.\n"
                "28. إذا احتوت الإجابة على أي حروف غير عربية وغير إنجليزية تقنية، اعتبر الإجابة غير صالحة وأعد صياغتها باللغة العربية فقط.\n"
                "29. لا تبدأ الإجابة بجملة أجنبية. ابدأ دائمًا بإجابة عربية مباشرة.\n"
            )

        if not contains_arabic(question):
            return prompt

        prompt = (
            f"{prompt}\n"
            "قاعدة إلزامية: إذا كان سؤال المستخدم يحتوي على العربية، يجب أن تكون الإجابة النهائية بالعربية فقط.\n"
            "لا تكتب بالصينية أو بأي لغة أخرى إلا إذا كانت كلمة تقنية قصيرة موجودة في السياق.\n"
            f"إذا لم تستطع الإجابة بالعربية من السياق، أعد هذه العبارة حرفياً: \"{self.config.fallback_text}\""
        )
        if force_arabic_retry:
            prompt += (
                "\nالمحاولة السابقة لم تلتزم باللغة المطلوبة."
                "\nأعد الإجابة الآن بالعربية فقط."
                "\nإذا لم تستطع الالتزام بذلك، أعد عبارة عدم التوفر حرفياً."
            )
        return prompt

    def _should_retry_in_arabic(self, question: str, answer: str) -> bool:
        if not contains_arabic(question):
            return False
        if not answer:
            return True
        if not contains_arabic(answer):
            return True
        return self._chinese_ratio(answer) > 0.2

    @staticmethod
    def _chinese_ratio(text: str) -> float:
        visible_chars = [char for char in text if not char.isspace()]
        if not visible_chars:
            return 0.0
        chinese_chars = sum(1 for char in visible_chars if CHINESE_CHAR_RE.match(char))
        return chinese_chars / len(visible_chars)

    def _llm_fallback(
        self,
        reason: str,
        qwen_response_time_ms: float = 0.0,
        qwen_call_count: int = 0,
        raw_answer: str = "",
        retry_used: bool = False,
        model_name: str | None = None,
        prompt_character_count: int = 0,
        prompt_build_time_ms: float = 0.0,
        system_prompt_build_time_ms: float = 0.0,
        response_clean_time_ms: float = 0.0,
        input_token_count: int | None = None,
        output_token_count: int | None = None,
        ollama_total_duration_ms: float = 0.0,
        ollama_load_duration_ms: float = 0.0,
        ollama_prompt_eval_duration_ms: float = 0.0,
        ollama_eval_duration_ms: float = 0.0,
    ) -> GenerationResult:
        return GenerationResult(
            answer=self.config.fallback_text,
            llm_called=True,
            qwen_response_time_ms=qwen_response_time_ms,
            qwen_call_count=qwen_call_count,
            raw_answer=raw_answer,
            retry_used=retry_used,
            fallback_reason=reason,
            model_name=model_name,
            prompt_character_count=prompt_character_count,
            prompt_build_time_ms=prompt_build_time_ms,
            system_prompt_build_time_ms=system_prompt_build_time_ms,
            response_clean_time_ms=response_clean_time_ms,
            input_token_count=input_token_count,
            output_token_count=output_token_count,
            ollama_total_duration_ms=ollama_total_duration_ms,
            ollama_load_duration_ms=ollama_load_duration_ms,
            ollama_prompt_eval_duration_ms=ollama_prompt_eval_duration_ms,
            ollama_eval_duration_ms=ollama_eval_duration_ms,
        )

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _ollama_duration_ms(value: Any) -> float:
        try:
            if value is None:
                return 0.0
            return round(float(value) / 1_000_000, 2)
        except (TypeError, ValueError):
            return 0.0
