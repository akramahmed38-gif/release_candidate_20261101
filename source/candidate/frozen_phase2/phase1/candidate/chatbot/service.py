from __future__ import annotations

import argparse
import json
import math
import re
import sys
import threading
import traceback
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

import tkinter as tk
from tkinter import messagebox, ttk

from .config import AppConfig, load_config
from .content_state import StaleSourceFilter
from .answer_relevance import align_answer_aspect
from .source_answers import grounded_source_answer
from .generation import (
    AnswerGenerator,
    GroundingValidationResult,
    GenerationResult,
    OllamaClient,
    clean_answer_preserve_formatting,
    clean_generation_context,
    validate_grounded_answer,
)
from .ingestion import MaterialIngestor
from .logging_utils import get_logger
from .normalization import normalize_text, tokenize_for_search
from .query_language import normalize_franco
from .ocr import OCRBackend
from .profiling import (
    activate_latency_profiler,
    get_latency_profiler,
    maybe_new_latency_profiler,
    record_timing,
    set_counter,
    set_metadata,
)
from .retrieval import HybridRetriever, RetrievalResult, RetrievedChunk
from .smalltalk import check_smalltalk, detect_smalltalk_type
from .vector_store import ChromaVectorStore


@dataclass
class IndexStats:
    files_indexed: int
    chunks_indexed: int
    rebuilt: bool
    manifest_path: str
    collection_name: str


class ReadWriteLock:
    def __init__(self) -> None:
        self._condition = threading.Condition(threading.Lock())
        self._reader_count = 0
        self._writer_active = False

    @contextmanager
    def read_lock(self):
        with self._condition:
            while self._writer_active:
                self._condition.wait()
            self._reader_count += 1
        try:
            yield
        finally:
            with self._condition:
                self._reader_count -= 1
                if self._reader_count == 0:
                    self._condition.notify_all()

    @contextmanager
    def write_lock(self):
        with self._condition:
            while self._writer_active or self._reader_count > 0:
                self._condition.wait()
            self._writer_active = True
        try:
            yield
        finally:
            with self._condition:
                self._writer_active = False
                self._condition.notify_all()

class TrainingChatbot:
    def __init__(self, base_path: Path | None = None) -> None:
        self.config: AppConfig = load_config(base_path=base_path)
        self.logger = get_logger(self.config.log_file)
        self.ollama_client = OllamaClient(self.config, self.logger)
        self.ocr_backend = OCRBackend(self.config, self.logger)
        self._active_index_lock = ReadWriteLock()
        manifest_payload = self._read_manifest_payload()
        active_collection_name = self._manifest_collection_name(manifest_payload)
        from .repair_overlay import vector_store_for_generation
        self.vector_store = vector_store_for_generation(
            self.config,
            self.logger,
            collection_name=active_collection_name,
        )
        self.ingestor = MaterialIngestor(self.config, self.ocr_backend, self.logger)
        self.retriever = HybridRetriever(self.config, self.vector_store, self.ollama_client, self.logger)
        if self.config.content_generation:
            self.retriever.source_filter = StaleSourceFilter(self.config.project_path, self.config.content_generation)
        from .repair_overlay import attach_overlay_filter
        attach_overlay_filter(self.retriever,self.vector_store)
        self.generator = AnswerGenerator(self.config, self.ollama_client, self.logger)
        self._last_index_stats = IndexStats(
            files_indexed=0,
            chunks_indexed=self.vector_store.count(),
            rebuilt=False,
            manifest_path=str(self.config.manifest_path),
            collection_name=self.vector_store.collection_name,
        )

    def _snapshot_active_index(self) -> tuple[ChromaVectorStore, HybridRetriever]:
        with self._active_index_lock.read_lock():
            return self.vector_store, self.retriever

    def _build_retriever_for_store(self, vector_store: ChromaVectorStore) -> HybridRetriever:
        retriever = HybridRetriever(self.config, vector_store, self.ollama_client, self.logger)
        if self.config.content_generation:
            retriever.source_filter = StaleSourceFilter(self.config.project_path, self.config.content_generation)
        from .repair_overlay import attach_overlay_filter
        attach_overlay_filter(retriever,vector_store)
        retriever.refresh()
        return retriever

    def ensure_index(
        self,
        force_reindex: bool = False,
        progress_callback: Callable[..., None] | None = None,
    ) -> IndexStats:
        if self.config.content_generation:
            raise RuntimeError("Expanded learning content is maintained by the background sync worker.")
        self._prepare_directories()
        files = self.ingestor.scan_source_files()
        current_manifest = self.ingestor.build_manifest(files)
        saved_manifest_payload = self._read_manifest_payload()
        saved_manifest = saved_manifest_payload.get("files", [])
        saved_index_version = str(saved_manifest_payload.get("index_version") or "").strip()

        rebuild_required = (
            force_reindex
            or self.vector_store.count() == 0
            or saved_manifest != current_manifest
            or saved_index_version != self.config.index_version
        )
        chunks_indexed = self.vector_store.count()
        active_collection_name = self.vector_store.collection_name

        if rebuild_required:
            self.logger.info("Index rebuild started.")
            temp_collection_name = self._next_collection_name()
            temp_store = self.vector_store.clone_for_collection(temp_collection_name)
            temp_store.reset_collection()
            workload = self.ingestor.estimate_workload(files)

            if progress_callback is not None:
                progress_callback(
                    current_file=None,
                    current_page=None,
                    current_location_label=None,
                    processed_pages=0,
                    total_pages=workload.get("total_pages", 0),
                )

            try:
                chunks = self.ingestor.build_chunks(
                    files,
                    progress_callback=progress_callback,
                    total_pages=workload.get("total_pages", 0),
                )

                if chunks:
                    embeddings = self._embed_chunk_texts([chunk["text"] for chunk in chunks])
                    temp_store.add_chunks(chunks, embeddings)
                    chunks_indexed = len(chunks)
                else:
                    chunks_indexed = 0

                new_retriever = self._build_retriever_for_store(temp_store)
                self._write_manifest(current_manifest, chunks_indexed, temp_collection_name)
                self._write_ocr_usage_report()
            except Exception:
                self._delete_collection(temp_store, temp_collection_name)
                raise

            with self._active_index_lock.write_lock():
                old_collection_name = self.vector_store.collection_name
                self.vector_store = temp_store
                self.retriever = new_retriever
            if old_collection_name != temp_collection_name:
                self._delete_collection(temp_store, old_collection_name)
            active_collection_name = temp_collection_name
            self.logger.info("Index rebuild finished.")
        else:
            active_vector_store, _ = self._snapshot_active_index()
            refreshed_retriever = self._build_retriever_for_store(active_vector_store)
            with self._active_index_lock.write_lock():
                if self.vector_store is active_vector_store:
                    self.retriever = refreshed_retriever
                else:
                    active_vector_store = self.vector_store
                    chunks_indexed = self.vector_store.count()
                active_collection_name = active_vector_store.collection_name

        self._last_index_stats = IndexStats(
            files_indexed=len(files),
            chunks_indexed=chunks_indexed,
            rebuilt=rebuild_required,
            manifest_path=str(self.config.manifest_path),
            collection_name=active_collection_name,
        )
        return self._last_index_stats

    def ask(self,question,debug=False,request_id=None):
        from .passage_quality import protect_answer
        canonical = getattr(self, 'canonical_runtime', None)
        raw = canonical.ask(question,debug=debug,request_id=request_id) if canonical else self._ask_core(question,debug=debug,request_id=request_id)
        result=protect_answer(raw)
        if isinstance(result,dict):result['knowledge_generation']=self.config.content_generation
        return result

    def _ask_core(
        self,
        question: str,
        debug: bool = False,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        question = normalize_franco(question)
        existing_profiler = get_latency_profiler()
        profiler = existing_profiler or maybe_new_latency_profiler(
            enabled=bool(getattr(self.config, "enable_latency_profiling", False)),
            request_id=request_id,
        )
        profiling_context = (
            activate_latency_profiler(profiler)
            if profiler is not None and existing_profiler is None
            else nullcontext(profiler)
        )

        with profiling_context:
            effective_request_id = profiler.request_id if profiler is not None else request_id
            question_length = len(question.strip())
            self.logger.info(
                "Chatbot ask started request_id=%s question_length=%s debug=%s",
                effective_request_id,
                question_length,
                debug,
            )
            set_metadata("request.request_id", effective_request_id)
            set_metadata("request.debug", debug)
            set_counter("request.question_length", question_length)
            started = perf_counter()
            smalltalk_started = perf_counter()
            smalltalk_type = detect_smalltalk_type(question)
            smalltalk_answer = check_smalltalk(question) if smalltalk_type is not None else None
            smalltalk_check_time_ms = round((perf_counter() - smalltalk_started) * 1000, 2)
            record_timing("service.smalltalk_check_ms", smalltalk_check_time_ms)
            if smalltalk_answer is not None:
                result = self._build_smalltalk_result(
                    question=question,
                    answer=smalltalk_answer,
                    request_id=effective_request_id,
                    smalltalk_type=smalltalk_type,
                    started=started,
                    smalltalk_check_time_ms=smalltalk_check_time_ms,
                    debug=debug,
                    profiler=profiler,
                )
                self.logger.info(
                    'event="smalltalk_handled" request_id=%s smalltalk_handled=True smalltalk_type=%s direct_qa_used=False qwen_call_count=0 ollama_generation_time_ms=0 total_response_time_ms=%s',
                    effective_request_id,
                    smalltalk_type,
                    result["total_response_time_ms"],
                )
                return result
            retrieval_started = perf_counter()
            with self._active_index_lock.read_lock():
                active_retriever = self.retriever
                retrieval = active_retriever.search(question)
            retrieval_time_ms = round((perf_counter() - retrieval_started) * 1000, 2)
            record_timing("service.retrieval_ms", retrieval_time_ms)
            direct_qa_promotion_started = perf_counter()
            self._maybe_promote_direct_qa_chunk(question, retrieval, retriever=active_retriever)
            align_answer_aspect(question, retrieval, self.config.direct_qa_min_score)
            direct_qa_promotion_time_ms = round((perf_counter() - direct_qa_promotion_started) * 1000, 2)
            record_timing("service.direct_qa_promotion_ms", direct_qa_promotion_time_ms)

            top_chunk = retrieval.top_chunk
            top_score = round(top_chunk.final_score, 4) if top_chunk is not None else None
            top_source = top_chunk.source_name if top_chunk is not None else None
            top_location = top_chunk.location_label if top_chunk is not None else None
            overlap_count = top_chunk.overlap_count if top_chunk is not None else 0
            embedding_time_ms = retrieval.embedding_time_ms
            chroma_search_time_ms = retrieval.chroma_search_time_ms
            bm25_time_ms = retrieval.bm25_time_ms
            rerank_time_ms = retrieval.rerank_time_ms
            selected_chunks = [
                {
                    "source_name": chunk.source_name,
                    "location_label": chunk.location_label,
                    "final_score": round(chunk.final_score, 4),
                }
                for chunk in retrieval.chunks
            ]
            top_5_retrieved_candidates = [chunk.to_prompt_chunk() for chunk in retrieval.ranked_chunks[:5]]
            set_counter("retrieval.selected_chunk_count", len(retrieval.chunks))
            set_counter("retrieval.ranked_chunk_count", len(retrieval.ranked_chunks))
            set_metadata("retrieval.top_5_candidates", top_5_retrieved_candidates)
            set_metadata("retrieval.selected_qa_id", top_chunk.qa_id if top_chunk is not None else None)
            self.logger.info(
                "Chatbot retrieval decision request_id=%s grounded_mode=%s fallback_used=%s fallback_reason=%s top_score=%s retrieval_confidence=%s query_coverage=%s keyword_overlap=%s qa_id=%s selected_chunks=%s",
                effective_request_id,
                self.config.strict_grounded_mode,
                retrieval.should_fallback,
                retrieval.fallback_reason,
                top_score,
                retrieval.retrieval_confidence,
                round(retrieval.query_coverage, 4),
                overlap_count,
                top_chunk.qa_id if top_chunk is not None else None,
                selected_chunks,
            )

            fallback_stage = "none"
            fallback_reason = None
            extractive_recovery_used = False
            prompt_context_filter_time_ms = 0.0
            extractive_recovery_time_ms = 0.0
            source_build_time_ms = 0.0
            prompt_character_count = 0
            number_of_prompt_chunks = 0
            grounding_validation_time_ms = 0.0
            direct_qa_answer_build_time_ms = 0.0
            clarification_payload_time_ms = 0.0
            llm_model_used = self.ollama_client.generation_model()
            direct_qa_decision_started = perf_counter()
            direct_qa_decision = self._direct_qa_decision(retrieval)
            direct_qa_decision_time_ms = round((perf_counter() - direct_qa_decision_started) * 1000, 2)
            record_timing("service.direct_qa_decision_ms", direct_qa_decision_time_ms)
            clarification_decision_started = perf_counter()
            clarification_decision = self._clarification_decision(
                question,
                retrieval,
                direct_qa_decision,
                retriever=active_retriever,
            )
            clarification_decision_time_ms = round(
                (perf_counter() - clarification_decision_started) * 1000,
                2,
            )
            record_timing("service.clarification_decision_ms", clarification_decision_time_ms)
            direct_qa_used = False
            clarification_payload: dict[str, Any] | None = None
            prompt_context_payload: list[dict[str, Any]] = []
            sources: list[dict[str, Any]] = []
            generation = GenerationResult(
                answer=self.config.fallback_text,
                llm_called=False,
            )
            grounding_validation = GroundingValidationResult(
                passed=False,
                unsupported_claim_detected=False,
                unsupported_claims=[],
                checked_segments=[],
                reason="retrieval_fallback" if retrieval.should_fallback else "not_checked",
            )
            if clarification_decision["should_clarify"]:
                clarification_payload_started = perf_counter()
                clarification_payload = self._build_clarification_payload(
                    question=question,
                    clarification_decision=clarification_decision,
                )
                clarification_payload_time_ms = round(
                    (perf_counter() - clarification_payload_started) * 1000,
                    2,
                )
                record_timing("service.clarification_payload_ms", clarification_payload_time_ms)
                fallback_stage = "clarification"
                fallback_reason = clarification_decision["reason"]
                llm_model_used = "clarification"
                generation = GenerationResult(
                    answer=clarification_payload["question"],
                    llm_called=False,
                    raw_answer=clarification_payload["question"],
                    model_name="clarification",
                )
                answer_text = clarification_payload["question"]
                self.logger.info(
                    'event="clarification_selected" question=%r reason=%s qa_ids=%s top_score=%s query_coverage=%s',
                    question,
                    fallback_reason,
                    [option.get("qa_id") for option in clarification_payload.get("options", [])],
                    top_score,
                    round(retrieval.query_coverage, 4),
                )
            elif retrieval.should_fallback:
                fallback_stage = "retrieval"
                fallback_reason = retrieval.fallback_reason
                self.logger.warning(
                    "Retrieval fallback selected stage=retrieval reason=%s grounded_mode=%s top_score=%s top_source=%s top_location=%s overlap_count=%s query_coverage=%s qa_id=%s",
                    fallback_reason,
                    self.config.strict_grounded_mode,
                    top_score,
                    top_source,
                    top_location,
                    overlap_count,
                    round(retrieval.query_coverage, 4),
                    top_chunk.qa_id if top_chunk is not None else None,
                )
                generation = self.generator.fallback()
                answer_text = generation.answer
            else:
                source_build_started = perf_counter()
                sources = self._unique_sources(retrieval)
                source_build_time_ms = round((perf_counter() - source_build_started) * 1000, 2)
                record_timing("context.source_build_ms", source_build_time_ms)

                direct_qa_answer_build_started = perf_counter()
                direct_qa_answer = self._build_direct_qa_answer(retrieval)
                direct_qa_answer_build_time_ms = round(
                    (perf_counter() - direct_qa_answer_build_started) * 1000,
                    2,
                )
                record_timing("service.direct_qa_answer_build_ms", direct_qa_answer_build_time_ms)
                if direct_qa_answer is not None and top_chunk is not None:
                    direct_qa_used = True
                    prompt_context_payload = [top_chunk.to_prompt_chunk()]
                    number_of_prompt_chunks = len(prompt_context_payload)
                    generation = GenerationResult(
                        answer=direct_qa_answer,
                        llm_called=False,
                        raw_answer=direct_qa_answer,
                        model_name="direct_qa_answer",
                    )
                    answer_text = direct_qa_answer
                    llm_model_used = "direct_qa_answer"
                    if direct_qa_decision["reason"] == "eligible_relaxed_strict_match":
                        direct_qa_decision["reason"] = "used_relaxed_strict_match"
                    else:
                        direct_qa_decision["reason"] = "used_standard_match"
                    grounding_validation = GroundingValidationResult(
                        passed=True,
                        unsupported_claim_detected=False,
                        unsupported_claims=[],
                        checked_segments=[],
                        reason="direct_qa_exact",
                    )
                    self.logger.info(
                        'event="direct_qa_answer_used" question=%r grounded_mode=%s qa_id=%s top_score=%s query_coverage=%s source=%s location=%s',
                        question,
                        self.config.strict_grounded_mode,
                        top_chunk.qa_id,
                        top_score,
                        round(retrieval.query_coverage, 4),
                        top_source,
                        top_location,
                    )
                else:
                    if direct_qa_decision["eligible"] and direct_qa_decision["reason"] == "eligible":
                        direct_qa_decision["reason"] = "empty_clean_answer_text"
                    prompt_filter_started = perf_counter()
                    prompt_context_chunks, removed_prompt_chunks = self._filter_prompt_context_chunks(
                        question,
                        retrieval,
                    )
                    prompt_context_filter_time_ms = round(
                        (perf_counter() - prompt_filter_started) * 1000,
                        2,
                    )
                    record_timing("context.prompt_context_filter_ms", prompt_context_filter_time_ms)
                    prompt_context_payload = [chunk.to_prompt_chunk() for chunk in prompt_context_chunks]
                    number_of_prompt_chunks = len(prompt_context_payload)
                    self.logger.info(
                        'event="prompt_context_filtered" question=%r top_score=%s original_chunk_count=%s filtered_chunk_count=%s removed_chunks=%s',
                        question,
                        top_score,
                        len(retrieval.chunks),
                        len(prompt_context_chunks),
                        removed_prompt_chunks,
                    )
                    source_answer = grounded_source_answer(retrieval, question) if self.config.prefer_source_answers else None
                    if source_answer:
                        generation = GenerationResult(
                            answer=source_answer, llm_called=False, raw_answer=source_answer,
                            model_name="grounded_source_quote",
                        )
                    else:
                        # A preference must not turn previously answerable
                        # questions into automatic clarification responses.
                        generation = self.generator.generate_answer(question, prompt_context_payload)
                    answer_text = generation.answer
                    llm_model_used = getattr(generation, "model_name", llm_model_used) or llm_model_used
                    prompt_character_count = getattr(generation, "prompt_character_count", 0)
                    generation_fallback_reason = getattr(generation, "fallback_reason", None)
                    if generation_fallback_reason:
                        fallback_stage = "generation"
                        fallback_reason = generation_fallback_reason
                        self.logger.warning(
                            "Generation fallback selected stage=generation reason=%s top_score=%s top_source=%s top_location=%s overlap_count=%s",
                            fallback_reason,
                            top_score,
                            top_source,
                            top_location,
                            overlap_count,
                        )
                        if self._should_use_extractive_recovery(retrieval, generation_fallback_reason):
                            extractive_started = perf_counter()
                            extractive_answer = self._build_extractive_recovery_answer(top_chunk)
                            extractive_recovery_time_ms = round(
                                (perf_counter() - extractive_started) * 1000,
                                2,
                            )
                            record_timing("service.extractive_recovery_ms", extractive_recovery_time_ms)
                            if extractive_answer != self.config.fallback_text:
                                answer_text = extractive_answer
                                extractive_recovery_used = True
                                self.logger.info(
                                    "Fallback-safe extractive answer applied reason=%s top_source=%s top_location=%s",
                                    generation_fallback_reason,
                                    top_source,
                                    top_location,
                                )
                            else:
                                self.logger.warning(
                                    "Fallback-safe extractive answer unavailable reason=%s top_source=%s top_location=%s",
                                    generation_fallback_reason,
                                    top_source,
                                    top_location,
                                )
                    elif self.config.strict_grounded_mode:
                        grounding_validation_started = perf_counter()
                        grounding_validation = validate_grounded_answer(
                            answer_text,
                            prompt_context_payload,
                            self.config.fallback_text,
                        )
                        grounding_validation_time_ms = round(
                            (perf_counter() - grounding_validation_started) * 1000,
                            2,
                        )
                        record_timing("grounding.validation_ms", grounding_validation_time_ms)
                        self.logger.info(
                            'event="grounding_validation" grounded_mode=%s passed=%s unsupported_claim_detected=%s qa_id=%s retrieval_confidence=%s reason=%s unsupported_claims=%s',
                            self.config.strict_grounded_mode,
                            grounding_validation.passed,
                            grounding_validation.unsupported_claim_detected,
                            top_chunk.qa_id if top_chunk is not None else None,
                            retrieval.retrieval_confidence,
                            grounding_validation.reason,
                            grounding_validation.unsupported_claims,
                        )
                        if not grounding_validation.passed:
                            fallback_stage = "generation"
                            fallback_reason = grounding_validation.reason or "grounding_validation_failed"
                            answer_text = self.config.fallback_text
                            self.logger.warning(
                                "Strict grounding rejected generated answer reason=%s top_score=%s top_source=%s top_location=%s",
                                fallback_reason,
                                top_score,
                                top_source,
                                top_location,
                            )

            total_response_time_ms = round((perf_counter() - started) * 1000, 2)
            record_timing("service.total_ms", total_response_time_ms)
            primary_source = next((source for source in sources if source.get("primary_source")), None)
            supporting_sources = [source for source in sources if not source.get("primary_source")]
            keyword_overlap = overlap_count
            answer_character_count = len(answer_text or "")
            answer_type = "clarification"
            if clarification_payload is None:
                if answer_text == self.config.fallback_text:
                    answer_type = "fallback"
                elif direct_qa_used:
                    answer_type = "direct_qa"
                elif llm_model_used == "grounded_source_quote":
                    answer_type = "source_quote"
                else:
                    answer_type = "generated"
            llm_called = bool(getattr(generation, "llm_called", False)) if generation is not None else False
            qwen_time_ms = float(getattr(generation, "qwen_response_time_ms", 0.0) or 0.0)
            prompt_build_time_ms = float(getattr(generation, "prompt_build_time_ms", 0.0) or 0.0)
            system_prompt_build_time_ms = float(
                getattr(generation, "system_prompt_build_time_ms", 0.0) or 0.0
            )
            answer_clean_time_ms = float(getattr(generation, "response_clean_time_ms", 0.0) or 0.0)
            llm_input_token_count = getattr(generation, "input_token_count", None)
            llm_output_token_count = getattr(generation, "output_token_count", None)
            ollama_total_duration_ms = float(
                getattr(generation, "ollama_total_duration_ms", 0.0) or 0.0
            )
            ollama_load_duration_ms = float(
                getattr(generation, "ollama_load_duration_ms", 0.0) or 0.0
            )
            ollama_prompt_eval_duration_ms = float(
                getattr(generation, "ollama_prompt_eval_duration_ms", 0.0) or 0.0
            )
            ollama_eval_duration_ms = float(
                getattr(generation, "ollama_eval_duration_ms", 0.0) or 0.0
            )
            llm_streaming = bool(getattr(generation, "streaming", False))
            qwen_call_count = int(getattr(generation, "qwen_call_count", 0) or 0)
            retry_used = bool(getattr(generation, "retry_used", False))
            embedding_call_count = int(
                (profiler.counters.get("embedding_call_count", 0) if profiler is not None else 0) or 0
            )
            embedding_input_count = int(
                (profiler.counters.get("embedding_input_count", 0) if profiler is not None else 0) or 0
            )
            embedding_total_time_ms = float(
                (profiler.timings_ms.get("embedding.total_ms", 0.0) if profiler is not None else 0.0) or 0.0
            )
            embedding_call_sources = list(
                (profiler.metadata.get("embedding_call_sources", []) if profiler is not None else []) or []
            )
            duplicate_embedding_detected = bool(
                (profiler.metadata.get("duplicate_embedding_detected", False) if profiler is not None else False)
            )
            duplicate_embedding_inputs = list(
                (profiler.metadata.get("duplicate_embedding_inputs", []) if profiler is not None else []) or []
            )
            set_metadata("answer.answer_type", answer_type)
            set_counter("answer.character_count", answer_character_count)
            set_counter("embedding.call_count", embedding_call_count)
            set_counter("embedding.input_count", embedding_input_count)
            set_metadata("embedding.call_sources", embedding_call_sources)
            set_metadata("embedding.duplicate_detected", duplicate_embedding_detected)

            result = {
                "request_id": effective_request_id,
                "type": "clarification" if clarification_payload is not None else "answer",
                "answer_type": answer_type,
                "question": question,
                "normalized_question": retrieval.normalized_question,
                "original_normalized_query": getattr(
                    retrieval,
                    "original_normalized_query",
                    getattr(retrieval, "original_normalized_question", retrieval.normalized_question),
                ),
                "retrieval_query": getattr(retrieval, "retrieval_query", question),
                "rewritten_query": getattr(retrieval, "rewritten_query", ""),
                "detected_intent": getattr(retrieval, "detected_intent", ""),
                "important_keywords": list(getattr(retrieval, "important_keywords", []) or []),
                "query_understanding_used": bool(getattr(retrieval, "query_understanding_used", False)),
                "query_understanding_failed_reason": getattr(
                    retrieval,
                    "query_understanding_failed_reason",
                    None,
                ),
                "query_understanding_time_ms": float(
                    getattr(retrieval, "query_understanding_time_ms", 0.0) or 0.0
                ),
                "answer": answer_text,
                "llm_called": llm_called,
                "fallback_used": answer_text == self.config.fallback_text,
                "fallback_stage": fallback_stage,
                "fallback_reason": fallback_reason,
                "sources": sources,
                "primary_source": primary_source,
                "supporting_sources": supporting_sources,
                "top_score": top_score,
                "top_source": top_source,
                "top_location": top_location,
                "keyword_overlap": keyword_overlap,
                "overlap_count": overlap_count,
                "selected_chunks": prompt_context_payload,
                "retrieved_chunks": [chunk.to_prompt_chunk() for chunk in retrieval.chunks],
                "top_5_retrieved_chunks": top_5_retrieved_candidates,
                "retrieved_candidate_count": len(retrieval.ranked_chunks),
                "llm_model": llm_model_used,
                "number_of_prompt_chunks": number_of_prompt_chunks,
                "prompt_character_count": prompt_character_count,
                "answer_character_count": answer_character_count,
                "retrieval_time_ms": retrieval_time_ms,
                "embedding_time_ms": embedding_time_ms,
                "embedding_call_count": embedding_call_count,
                "embedding_input_count": embedding_input_count,
                "embedding_total_time_ms": embedding_total_time_ms,
                "embedding_call_sources": embedding_call_sources,
                "duplicate_embedding_detected": duplicate_embedding_detected,
                "chroma_search_time_ms": chroma_search_time_ms,
                "bm25_time_ms": bm25_time_ms,
                "rerank_time_ms": rerank_time_ms,
                "question_normalization_time_ms": retrieval.question_normalization_time_ms,
                "query_tokenization_time_ms": retrieval.query_tokenization_time_ms,
                "retrieval_fallback_decision_time_ms": retrieval.fallback_decision_time_ms,
                "prompt_context_filter_time_ms": prompt_context_filter_time_ms,
                "qwen_time_ms": qwen_time_ms,
                "prompt_build_time_ms": prompt_build_time_ms,
                "system_prompt_build_time_ms": system_prompt_build_time_ms,
                "answer_clean_time_ms": answer_clean_time_ms,
                "llm_input_token_count": llm_input_token_count,
                "llm_output_token_count": llm_output_token_count,
                "ollama_total_duration_ms": ollama_total_duration_ms,
                "ollama_load_duration_ms": ollama_load_duration_ms,
                "ollama_prompt_eval_duration_ms": ollama_prompt_eval_duration_ms,
                "ollama_eval_duration_ms": ollama_eval_duration_ms,
                "llm_streaming": llm_streaming,
                "extractive_recovery_time_ms": extractive_recovery_time_ms,
                "source_build_time_ms": source_build_time_ms,
                "grounding_validation_time_ms": grounding_validation_time_ms,
                "direct_qa_promotion_time_ms": direct_qa_promotion_time_ms,
                "direct_qa_decision_time_ms": direct_qa_decision_time_ms,
                "clarification_decision_time_ms": clarification_decision_time_ms,
                "clarification_payload_time_ms": clarification_payload_time_ms,
                "direct_qa_answer_build_time_ms": direct_qa_answer_build_time_ms,
                "total_response_time_ms": total_response_time_ms,
                "extractive_recovery_used": extractive_recovery_used,
                "grounded_mode": self.config.strict_grounded_mode,
                "grounding_validation_passed": grounding_validation.passed,
                "unsupported_claim_detected": grounding_validation.unsupported_claim_detected,
                "retrieval_confidence": retrieval.retrieval_confidence,
                "qa_id": top_chunk.qa_id if top_chunk is not None else None,
                "selected_qa_id": top_chunk.qa_id if top_chunk is not None else None,
                "near_tie_clarification_triggered": clarification_decision["should_clarify"],
                "semantic_candidate_count": retrieval.semantic_candidate_count,
                "keyword_candidate_count": retrieval.keyword_candidate_count,
                "merged_candidate_count": retrieval.merged_candidate_count,
            }
            if clarification_payload is not None:
                result["clarification"] = clarification_payload
            filtered_selected_summary = [
                {
                    "source_name": chunk.get("source_name"),
                    "location_label": chunk.get("location_label"),
                    "final_score": chunk.get("final_score"),
                }
                for chunk in result["selected_chunks"]
            ]
            self.logger.info(
            'event="embedding_usage" request_id=%s embedding_model=%s embedding_call_count=%s embedding_input_count=%s embedding_total_time_ms=%s call_sites=%s',
            effective_request_id,
            self.config.embedding_model,
            embedding_call_count,
            embedding_input_count,
            embedding_total_time_ms,
            embedding_call_sources,
            )
            if duplicate_embedding_detected:
                self.logger.warning(
                    'event="duplicate_embedding_detected" request_id=%s embedding_model=%s duplicate_inputs=%s call_sites=%s',
                    effective_request_id,
                    self.config.embedding_model,
                    duplicate_embedding_inputs,
                    embedding_call_sources,
                )
            self.logger.info(
            'event="direct_qa_decision" question=%r grounded_mode=%s top_score=%s qa_id=%s answer_text_exists=%s direct_qa_eligible=%s direct_qa_threshold=%s direct_qa_used=%s selected_llm_model=%s total_response_time_ms=%s direct_qa_reason=%s query_coverage=%s',
            question,
            self.config.strict_grounded_mode,
            top_score,
            direct_qa_decision["qa_id"],
            direct_qa_decision["answer_text_exists"],
            direct_qa_decision["eligible"],
            direct_qa_decision["threshold"],
            direct_qa_used,
            llm_model_used,
            total_response_time_ms,
            direct_qa_decision["reason"],
            round(retrieval.query_coverage, 4),
            )
            self.logger.info(
            'event="ask_timing" total_time_ms=%s retrieval_time_ms=%s embedding_time_ms=%s chroma_search_time_ms=%s bm25_time_ms=%s rerank_time_ms=%s prompt_context_filter_time_ms=%s ollama_generation_time_ms=%s extractive_recovery_time_ms=%s source_build_time_ms=%s llm_model=%s number_of_prompt_chunks=%s prompt_character_count=%s answer_character_count=%s fallback_stage=%s fallback_used=%s grounded_mode=%s grounding_validation_passed=%s unsupported_claim_detected=%s retrieval_confidence=%s qa_id=%s',
            total_response_time_ms,
            retrieval_time_ms,
            embedding_time_ms,
            chroma_search_time_ms,
            bm25_time_ms,
            rerank_time_ms,
            prompt_context_filter_time_ms,
            qwen_time_ms,
            extractive_recovery_time_ms,
            source_build_time_ms,
            llm_model_used,
            number_of_prompt_chunks,
            prompt_character_count,
            answer_character_count,
            fallback_stage,
            result["fallback_used"],
            self.config.strict_grounded_mode,
            grounding_validation.passed,
            grounding_validation.unsupported_claim_detected,
            retrieval.retrieval_confidence,
            top_chunk.qa_id if top_chunk is not None else None,
            )
            self.logger.info(
            "Chatbot final result type=%s grounded_mode=%s fallback_used=%s fallback_stage=%s fallback_reason=%s top_score=%s top_source=%s top_location=%s overlap_count=%s retrieval_confidence=%s grounding_validation_passed=%s unsupported_claim_detected=%s extractive_recovery_used=%s selected_chunks=%s",
            result["type"],
            self.config.strict_grounded_mode,
            result["fallback_used"],
            fallback_stage,
            fallback_reason,
            top_score,
            top_source,
            top_location,
            overlap_count,
            retrieval.retrieval_confidence,
            grounding_validation.passed,
            grounding_validation.unsupported_claim_detected,
            extractive_recovery_used,
            filtered_selected_summary,
            )
            if debug:
                result["debug"] = {
                    "request_id": effective_request_id,
                    "normalized_question": retrieval.normalized_question,
                    "original_normalized_query": getattr(
                        retrieval,
                        "original_normalized_query",
                        getattr(retrieval, "original_normalized_question", retrieval.normalized_question),
                    ),
                    "query_tokens": retrieval.query_tokens,
                    "rewritten_query": getattr(retrieval, "rewritten_query", ""),
                    "detected_intent": getattr(retrieval, "detected_intent", ""),
                    "important_keywords": list(getattr(retrieval, "important_keywords", []) or []),
                    "product_aliases": list(getattr(retrieval, "product_aliases", []) or []),
                    "possible_meanings": list(getattr(retrieval, "possible_meanings", []) or []),
                    "needs_clarification": bool(getattr(retrieval, "needs_clarification", False)),
                    "query_understanding_used": bool(getattr(retrieval, "query_understanding_used", False)),
                    "query_understanding_failed_reason": getattr(
                        retrieval,
                        "query_understanding_failed_reason",
                        None,
                    ),
                    "query_understanding_time_ms": float(
                        getattr(retrieval, "query_understanding_time_ms", 0.0) or 0.0
                    ),
                    "retrieval_query": getattr(retrieval, "retrieval_query", question),
                    "top_10_retrieved_chunks": retrieval.ranked_prompt_chunks(limit=10),
                    "top_5_retrieved_chunks": top_5_retrieved_candidates,
                    "selected_top_chunks": prompt_context_payload,
                    "fallback_stage": fallback_stage,
                    "fallback_reason": fallback_reason,
                    "fallback_used": result["fallback_used"],
                    "qwen_response_time_ms": qwen_time_ms,
                    "qwen_call_count": qwen_call_count,
                    "retry_used": retry_used,
                    "llm_model": llm_model_used,
                    "clarification": clarification_payload,
                    "direct_qa": {
                        "top_score": top_score,
                        "qa_id": direct_qa_decision["qa_id"],
                        "answer_text_exists": direct_qa_decision["answer_text_exists"],
                        "direct_qa_eligible": direct_qa_decision["eligible"],
                        "direct_qa_threshold": direct_qa_decision["threshold"],
                        "direct_qa_used": direct_qa_used,
                        "selected_llm_model": llm_model_used,
                        "total_response_time_ms": total_response_time_ms,
                        "reason": direct_qa_decision["reason"],
                    },
                    "clarification_decision": {
                        "should_clarify": clarification_decision["should_clarify"],
                        "reason": clarification_decision["reason"],
                        "candidate_count": len(clarification_decision["candidates"]),
                    },
                    "number_of_prompt_chunks": number_of_prompt_chunks,
                    "prompt_character_count": prompt_character_count,
                    "answer_character_count": answer_character_count,
                    "top_score": top_score,
                    "top_source": top_source,
                    "top_location": top_location,
                    "keyword_overlap": keyword_overlap,
                    "overlap_count": overlap_count,
                    "retrieval_time_ms": retrieval_time_ms,
                    "embedding_time_ms": embedding_time_ms,
                    "embedding_call_count": embedding_call_count,
                    "embedding_input_count": embedding_input_count,
                    "embedding_total_time_ms": embedding_total_time_ms,
                    "embedding_call_sources": embedding_call_sources,
                    "duplicate_embedding_detected": duplicate_embedding_detected,
                    "duplicate_embedding_inputs": duplicate_embedding_inputs,
                    "chroma_search_time_ms": chroma_search_time_ms,
                    "bm25_time_ms": bm25_time_ms,
                    "rerank_time_ms": rerank_time_ms,
                    "question_normalization_time_ms": retrieval.question_normalization_time_ms,
                    "query_tokenization_time_ms": retrieval.query_tokenization_time_ms,
                    "retrieval_fallback_decision_time_ms": retrieval.fallback_decision_time_ms,
                    "prompt_context_filter_time_ms": prompt_context_filter_time_ms,
                    "prompt_build_time_ms": prompt_build_time_ms,
                    "system_prompt_build_time_ms": system_prompt_build_time_ms,
                    "answer_clean_time_ms": answer_clean_time_ms,
                    "llm_input_token_count": llm_input_token_count,
                    "llm_output_token_count": llm_output_token_count,
                    "ollama_total_duration_ms": ollama_total_duration_ms,
                    "ollama_load_duration_ms": ollama_load_duration_ms,
                    "ollama_prompt_eval_duration_ms": ollama_prompt_eval_duration_ms,
                    "ollama_eval_duration_ms": ollama_eval_duration_ms,
                    "llm_streaming": llm_streaming,
                    "extractive_recovery_time_ms": extractive_recovery_time_ms,
                    "source_build_time_ms": source_build_time_ms,
                    "grounding_validation_time_ms": grounding_validation_time_ms,
                    "direct_qa_promotion_time_ms": direct_qa_promotion_time_ms,
                    "direct_qa_decision_time_ms": direct_qa_decision_time_ms,
                    "clarification_decision_time_ms": clarification_decision_time_ms,
                    "clarification_payload_time_ms": clarification_payload_time_ms,
                    "direct_qa_answer_build_time_ms": direct_qa_answer_build_time_ms,
                    "total_response_time_ms": total_response_time_ms,
                    "extractive_recovery_used": extractive_recovery_used,
                    "grounded_mode": self.config.strict_grounded_mode,
                    "grounding_validation_passed": grounding_validation.passed,
                    "unsupported_claim_detected": grounding_validation.unsupported_claim_detected,
                    "grounding_validation_reason": grounding_validation.reason,
                    "unsupported_claims": grounding_validation.unsupported_claims,
                    "retrieval_confidence": retrieval.retrieval_confidence,
                    "query_coverage": retrieval.query_coverage,
                    "retrieved_candidate_count": len(retrieval.ranked_chunks),
                    "selected_qa_id": top_chunk.qa_id if top_chunk is not None else None,
                    "semantic_candidate_count": retrieval.semantic_candidate_count,
                    "keyword_candidate_count": retrieval.keyword_candidate_count,
                    "merged_candidate_count": retrieval.merged_candidate_count,
                    "qa_id": top_chunk.qa_id if top_chunk is not None else None,
                    "latency_profile": profiler.to_dict() if profiler is not None else None,
                }
            return result

    def _build_smalltalk_result(
        self,
        *,
        question: str,
        answer: str,
        request_id: str | None,
        smalltalk_type: str,
        started: float,
        smalltalk_check_time_ms: float,
        debug: bool,
        profiler: Any,
    ) -> dict[str, Any]:
        normalized_question = normalize_text(question, for_search=True)
        query_tokens = tokenize_for_search(question)
        answer_text = clean_answer_preserve_formatting(answer)
        total_response_time_ms = round((perf_counter() - started) * 1000, 2)
        answer_character_count = len(answer_text or "")

        record_timing("service.total_ms", total_response_time_ms)
        set_metadata("answer.answer_type", "smalltalk")
        set_metadata("smalltalk.handled", True)
        set_metadata("smalltalk.type", smalltalk_type)
        set_counter("answer.character_count", answer_character_count)

        result = {
            "request_id": request_id,
            "type": "answer",
            "answer_type": "smalltalk",
            "question": question,
            "normalized_question": normalized_question,
            "original_normalized_query": normalized_question or question,
            "retrieval_query": normalized_question or question,
            "rewritten_query": "",
            "detected_intent": "",
            "important_keywords": [],
            "query_understanding_used": False,
            "query_understanding_failed_reason": None,
            "query_understanding_time_ms": 0.0,
            "answer": answer_text,
            "llm_called": False,
            "fallback_used": False,
            "fallback_stage": "none",
            "fallback_reason": None,
            "sources": [],
            "primary_source": None,
            "supporting_sources": [],
            "top_score": None,
            "top_source": None,
            "top_location": None,
            "keyword_overlap": 0,
            "overlap_count": 0,
            "selected_chunks": [],
            "retrieved_chunks": [],
            "top_5_retrieved_chunks": [],
            "retrieved_candidate_count": 0,
            "llm_model": "smalltalk",
            "number_of_prompt_chunks": 0,
            "prompt_character_count": 0,
            "answer_character_count": answer_character_count,
            "retrieval_time_ms": 0.0,
            "embedding_time_ms": 0.0,
            "embedding_call_count": 0,
            "embedding_input_count": 0,
            "embedding_total_time_ms": 0.0,
            "embedding_call_sources": [],
            "duplicate_embedding_detected": False,
            "chroma_search_time_ms": 0.0,
            "bm25_time_ms": 0.0,
            "rerank_time_ms": 0.0,
            "question_normalization_time_ms": 0.0,
            "query_tokenization_time_ms": 0.0,
            "retrieval_fallback_decision_time_ms": 0.0,
            "prompt_context_filter_time_ms": 0.0,
            "qwen_time_ms": 0.0,
            "prompt_build_time_ms": 0.0,
            "system_prompt_build_time_ms": 0.0,
            "answer_clean_time_ms": 0.0,
            "llm_input_token_count": None,
            "llm_output_token_count": None,
            "ollama_total_duration_ms": 0.0,
            "ollama_load_duration_ms": 0.0,
            "ollama_prompt_eval_duration_ms": 0.0,
            "ollama_eval_duration_ms": 0.0,
            "llm_streaming": False,
            "extractive_recovery_time_ms": 0.0,
            "source_build_time_ms": 0.0,
            "grounding_validation_time_ms": 0.0,
            "direct_qa_promotion_time_ms": 0.0,
            "direct_qa_decision_time_ms": 0.0,
            "clarification_decision_time_ms": 0.0,
            "clarification_payload_time_ms": 0.0,
            "direct_qa_answer_build_time_ms": 0.0,
            "total_response_time_ms": total_response_time_ms,
            "extractive_recovery_used": False,
            "grounded_mode": self.config.strict_grounded_mode,
            "grounding_validation_passed": True,
            "unsupported_claim_detected": False,
            "retrieval_confidence": None,
            "qa_id": None,
            "selected_qa_id": None,
            "near_tie_clarification_triggered": False,
            "semantic_candidate_count": 0,
            "keyword_candidate_count": 0,
            "merged_candidate_count": 0,
            "smalltalk_handled": True,
            "smalltalk_type": smalltalk_type,
            "smalltalk_check_time_ms": smalltalk_check_time_ms,
        }
        if debug:
            result["debug"] = {
                "request_id": request_id,
                "normalized_question": normalized_question,
                "original_normalized_query": normalized_question or question,
                "query_tokens": query_tokens,
                "smalltalk_handled": True,
                "smalltalk_type": smalltalk_type,
                "retrieval_query": normalized_question or question,
                "top_10_retrieved_chunks": [],
                "top_5_retrieved_chunks": [],
                "selected_top_chunks": [],
                "fallback_stage": "none",
                "fallback_reason": None,
                "fallback_used": False,
                "qwen_response_time_ms": 0.0,
                "qwen_call_count": 0,
                "retry_used": False,
                "llm_model": "smalltalk",
                "clarification": None,
                "direct_qa": {
                    "top_score": None,
                    "qa_id": None,
                    "answer_text_exists": False,
                    "direct_qa_eligible": False,
                    "direct_qa_threshold": self.config.direct_qa_min_score,
                    "direct_qa_used": False,
                    "selected_llm_model": "smalltalk",
                    "total_response_time_ms": total_response_time_ms,
                    "reason": "smalltalk_fast_path",
                },
                "clarification_decision": {
                    "should_clarify": False,
                    "reason": "smalltalk_fast_path",
                    "candidate_count": 0,
                },
                "number_of_prompt_chunks": 0,
                "prompt_character_count": 0,
                "answer_character_count": answer_character_count,
                "top_score": None,
                "top_source": None,
                "top_location": None,
                "keyword_overlap": 0,
                "overlap_count": 0,
                "retrieval_time_ms": 0.0,
                "embedding_time_ms": 0.0,
                "embedding_call_count": 0,
                "embedding_input_count": 0,
                "embedding_total_time_ms": 0.0,
                "embedding_call_sources": [],
                "duplicate_embedding_detected": False,
                "duplicate_embedding_inputs": [],
                "chroma_search_time_ms": 0.0,
                "bm25_time_ms": 0.0,
                "rerank_time_ms": 0.0,
                "question_normalization_time_ms": 0.0,
                "query_tokenization_time_ms": 0.0,
                "retrieval_fallback_decision_time_ms": 0.0,
                "prompt_context_filter_time_ms": 0.0,
                "prompt_build_time_ms": 0.0,
                "system_prompt_build_time_ms": 0.0,
                "answer_clean_time_ms": 0.0,
                "llm_input_token_count": None,
                "llm_output_token_count": None,
                "ollama_total_duration_ms": 0.0,
                "ollama_load_duration_ms": 0.0,
                "ollama_prompt_eval_duration_ms": 0.0,
                "ollama_eval_duration_ms": 0.0,
                "llm_streaming": False,
                "extractive_recovery_time_ms": 0.0,
                "source_build_time_ms": 0.0,
                "grounding_validation_time_ms": 0.0,
                "direct_qa_promotion_time_ms": 0.0,
                "direct_qa_decision_time_ms": 0.0,
                "clarification_decision_time_ms": 0.0,
                "clarification_payload_time_ms": 0.0,
                "direct_qa_answer_build_time_ms": 0.0,
                "total_response_time_ms": total_response_time_ms,
                "extractive_recovery_used": False,
                "grounded_mode": self.config.strict_grounded_mode,
                "grounding_validation_passed": True,
                "grounding_validation_reason": "smalltalk_fast_path",
                "unsupported_claim_detected": False,
                "unsupported_claims": [],
                "retrieval_confidence": None,
                "query_coverage": 0.0,
                "retrieved_candidate_count": 0,
                "selected_qa_id": None,
                "semantic_candidate_count": 0,
                "keyword_candidate_count": 0,
                "merged_candidate_count": 0,
                "qa_id": None,
                "smalltalk_check_time_ms": smalltalk_check_time_ms,
                "latency_profile": profiler.to_dict() if profiler is not None else None,
            }
        return result

    def diagnostics(self) -> dict[str, Any]:
        ollama_status = self.ollama_client.status()
        return {
            "project_path": str(self.config.project_path),
            "source_path": str(self.config.source_path),
            "knowledge_base_path": str(self.config.knowledge_base_path),
            "legacy_material_path": str(self.config.legacy_material_path),
            "python_executable": sys.executable,
            "ollama_status": "running" if ollama_status.get("ok") else "unreachable",
            "llm_model": self.config.llm_model,
            "fast_llm_model": self.config.fast_llm_model,
            "follow_up_llm_model": self.config.follow_up_llm_model,
            "enable_fast_mode": self.config.enable_fast_mode,
            "active_generation_model": self.ollama_client.generation_model(),
            "embedding_model": self.config.embedding_model,
            "ocr_backend": self.ocr_backend.backend_name(),
            "files_indexed": self._last_index_stats.files_indexed,
            "chunks_indexed": self._last_index_stats.chunks_indexed,
            "materials_path": str(self.config.source_path),
            "chroma_path": str(self.config.chroma_path),
            "collection_name": self.vector_store.collection_name,
            "index_version": self.config.index_version,
            "top_k": self.config.top_k,
            "enable_direct_qa_answer": self.config.enable_direct_qa_answer,
            "direct_qa_min_score": self.config.direct_qa_min_score,
            "strict_grounded_mode": self.config.strict_grounded_mode,
            "clarification_min_score": self.config.clarification_min_score,
            "clarification_score_margin": self.config.clarification_score_margin,
            "available_models": ollama_status.get("models", []),
        }

    def _build_direct_qa_answer(self, retrieval: RetrievalResult) -> str | None:
        top_chunk = retrieval.top_chunk
        if not self._should_use_direct_qa_answer(retrieval):
            return None

        direct_answer = (top_chunk.answer_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not direct_answer or direct_answer == self.config.fallback_text:
            return None
        from .passage_quality import readability
        if not readability(direct_answer,qa=True)['readable']:return None
        return direct_answer

    def _maybe_promote_direct_qa_chunk(
        self,
        question: str,
        retrieval: RetrievalResult,
        *,
        retriever: Any | None = None,
    ) -> None:
        if not self.config.enable_direct_qa_answer or len(retrieval.chunks) < 2:
            return

        top_chunk = retrieval.top_chunk
        if top_chunk is None:
            return

        # Use the live question text for specificity scoring so promotion stays
        # accurate even if a synthetic retrieval fixture carries stale tokens.
        query_tokens = tokenize_for_search(question) or retrieval.query_tokens
        if not query_tokens:
            return

        qa_candidates = [chunk for chunk in retrieval.chunks if chunk.qa_id and chunk.answer_text]
        if len(qa_candidates) < 2:
            return

        score_margin = getattr(self.config, "direct_qa_candidate_margin", 0.03)
        near_top_candidates = [
            chunk for chunk in qa_candidates if (top_chunk.final_score - chunk.final_score) <= score_margin
        ]
        if len(near_top_candidates) < 2:
            return

        top_specificity = self._direct_qa_match_specificity(query_tokens, top_chunk, retriever=retriever)
        best_candidate = max(
            near_top_candidates,
            key=lambda chunk: (
                self._direct_qa_match_specificity(query_tokens, chunk, retriever=retriever),
                chunk.overlap_count,
                chunk.final_score,
            ),
        )
        best_specificity = self._direct_qa_match_specificity(query_tokens, best_candidate, retriever=retriever)
        if best_candidate.chunk_id == top_chunk.chunk_id or best_specificity <= top_specificity:
            return

        retrieval.chunks = [best_candidate] + [
            chunk for chunk in retrieval.chunks if chunk.chunk_id != best_candidate.chunk_id
        ]
        self.logger.info(
            'event="direct_qa_candidate_promoted" question=%r original_qa_id=%s promoted_qa_id=%s original_score=%s promoted_score=%s original_specificity=%s promoted_specificity=%s',
            question,
            top_chunk.qa_id,
            best_candidate.qa_id,
            round(top_chunk.final_score, 4),
            round(best_candidate.final_score, 4),
            round(top_specificity, 4),
            round(best_specificity, 4),
        )

    def _direct_qa_match_specificity(
        self,
        query_tokens: list[str],
        chunk: RetrievedChunk | None,
        *,
        retriever: Any | None = None,
    ) -> float:
        if chunk is None or not query_tokens:
            return 0.0

        retriever_state = retriever or self.retriever
        corpus_size = max(len(getattr(retriever_state, "corpus", [])), 1)
        doc_frequencies = getattr(retriever_state, "doc_freq", {})
        doc_tokens = set(tokenize_for_search(chunk.search_text()))
        specificity_score = 0.0
        for token in dict.fromkeys(query_tokens):
            if token not in doc_tokens:
                continue
            document_frequency = doc_frequencies.get(token, 0)
            specificity_score += math.log(
                1 + (corpus_size - document_frequency + 0.5) / (document_frequency + 0.5)
            )
        return specificity_score

    def _should_use_direct_qa_answer(self, retrieval: RetrievalResult) -> bool:
        top_chunk = retrieval.top_chunk
        if not self.config.enable_direct_qa_answer or top_chunk is None:
            return False
        if not top_chunk.qa_id or not top_chunk.answer_text:
            return False
        if self.config.strict_grounded_mode:
            if top_chunk.overlap_count < self.config.min_keyword_overlap:
                return False
            if retrieval.query_coverage < 0.5 and top_chunk.overlap_count <= 1:
                return False
        if top_chunk.final_score >= self.config.direct_qa_min_score:
            return True
        return self._is_relaxed_strict_direct_qa_match(retrieval)

    def _is_relaxed_strict_direct_qa_match(self, retrieval: RetrievalResult) -> bool:
        top_chunk = retrieval.top_chunk
        if not self.config.strict_grounded_mode or top_chunk is None:
            return False

        relaxed_min_score = getattr(self.config, "strict_direct_qa_min_score", 0.67)
        min_query_coverage = getattr(self.config, "strict_direct_qa_min_query_coverage", 0.50)
        min_overlap = max(getattr(self.config, "min_keyword_overlap", 1), 2)
        return (
            bool(top_chunk.qa_id)
            and bool(top_chunk.answer_text)
            and top_chunk.final_score >= relaxed_min_score
            and retrieval.query_coverage >= min_query_coverage
            and top_chunk.overlap_count >= min_overlap
        )

    def _direct_qa_decision(self, retrieval: RetrievalResult) -> dict[str, Any]:
        top_chunk = retrieval.top_chunk
        answer_text_exists = bool(top_chunk and top_chunk.answer_text and str(top_chunk.answer_text).strip())
        qa_id = top_chunk.qa_id if top_chunk is not None else None
        top_score = top_chunk.final_score if top_chunk is not None else None
        relaxed_min_score = getattr(self.config, "strict_direct_qa_min_score", 0.70)

        if not self.config.enable_direct_qa_answer:
            reason = "disabled"
            eligible = False
            threshold = self.config.direct_qa_min_score
        elif top_chunk is None:
            reason = "no_top_chunk"
            eligible = False
            threshold = self.config.direct_qa_min_score
        elif not qa_id:
            reason = "missing_qa_id"
            eligible = False
            threshold = self.config.direct_qa_min_score
        elif not answer_text_exists:
            reason = "missing_answer_text"
            eligible = False
            threshold = self.config.direct_qa_min_score
        elif top_score is not None and top_score >= self.config.direct_qa_min_score:
            reason = "eligible"
            eligible = True
            threshold = self.config.direct_qa_min_score
        elif self._is_relaxed_strict_direct_qa_match(retrieval):
            reason = "eligible_relaxed_strict_match"
            eligible = True
            threshold = relaxed_min_score
        elif top_score is None or top_score < relaxed_min_score:
            reason = "below_threshold"
            eligible = False
            threshold = relaxed_min_score if self.config.strict_grounded_mode else self.config.direct_qa_min_score
        elif self.config.strict_grounded_mode and top_chunk.overlap_count < self.config.min_keyword_overlap:
            reason = "insufficient_query_overlap"
            eligible = False
            threshold = relaxed_min_score
        elif (
            self.config.strict_grounded_mode
            and retrieval.query_coverage < 0.5
            and top_chunk.overlap_count <= 1
        ):
            reason = "strict_low_query_coverage"
            eligible = False
            threshold = relaxed_min_score
        else:
            reason = "below_strict_relaxed_requirements"
            eligible = False
            threshold = relaxed_min_score

        return {
            "qa_id": qa_id,
            "answer_text_exists": answer_text_exists,
            "eligible": eligible,
            "threshold": threshold,
            "reason": reason,
        }

    def _clarification_decision(
        self,
        question: str,
        retrieval: RetrievalResult,
        direct_qa_decision: dict[str, Any],
        *,
        retriever: Any | None = None,
    ) -> dict[str, Any]:
        decision = {
            "should_clarify": False,
            "reason": None,
            "candidates": [],
        }
        if retrieval.fallback_reason == "requested_aspect_not_supported":
            return {"should_clarify": True, "reason": "requested_aspect_not_supported", "candidates": []}
        if retrieval.fallback_reason == "ambiguous_curated_question":
            return {
                "should_clarify": True,
                "reason": "ambiguous_curated_question",
                "candidates": (retrieval.ranked_chunks or retrieval.chunks)[:self.config.clarification_max_options],
            }
        if direct_qa_decision.get("eligible") or retrieval.top_chunk is None:
            return decision

        ranked_chunks = retrieval.ranked_chunks or retrieval.chunks
        if len(ranked_chunks) < 2:
            return decision

        min_score = float(getattr(self.config, "clarification_min_score", 0.58))
        score_margin = float(getattr(self.config, "clarification_score_margin", 0.05))
        min_query_coverage = float(getattr(self.config, "clarification_min_query_coverage", 0.35))
        min_overlap = int(getattr(self.config, "clarification_min_overlap", 1))
        max_options = int(getattr(self.config, "clarification_max_options", 3))
        max_specificity_gap = float(getattr(self.config, "clarification_max_specificity_gap", 0.9))

        if retrieval.query_coverage < min_query_coverage:
            return decision

        query_tokens = tokenize_for_search(question) or retrieval.query_tokens
        if not query_tokens:
            return decision

        top_score = ranked_chunks[0].final_score
        candidates: list[RetrievedChunk] = []
        seen_qa_ids: set[str] = set()
        for chunk in ranked_chunks:
            if not chunk.qa_id or not chunk.answer_text or chunk.qa_id in seen_qa_ids:
                continue
            if chunk.final_score < min_score:
                continue
            if top_score - chunk.final_score > score_margin:
                continue
            if chunk.overlap_count < min_overlap:
                continue
            candidates.append(chunk)
            seen_qa_ids.add(chunk.qa_id)
            if len(candidates) >= max_options:
                break

        if len(candidates) < 2:
            return decision

        top_specificity = self._direct_qa_match_specificity(
            query_tokens,
            candidates[0],
            retriever=retriever,
        )
        second_specificity = self._direct_qa_match_specificity(
            query_tokens,
            candidates[1],
            retriever=retriever,
        )
        if (top_specificity - second_specificity) > max_specificity_gap:
            return decision

        top_label = self._clarification_label_for_chunk(candidates[0])
        if all(self._clarification_label_for_chunk(chunk) == top_label for chunk in candidates[1:]):
            return decision

        decision["should_clarify"] = True
        decision["reason"] = "near_tie_intent_candidates"
        decision["candidates"] = candidates
        return decision

    def _build_clarification_payload(
        self,
        *,
        question: str,
        clarification_decision: dict[str, Any],
    ) -> dict[str, Any]:
        if clarification_decision.get("reason") == "requested_aspect_not_supported":
            return {"question": "أي جانب تحديدًا تقصد؟ لم أجد تفاصيل كافية عن هذه النقطة في المصادر المسترجعة.",
                    "original_question": question, "attempts": 1,
                    "reason": "requested_aspect_not_supported", "options": []}
        options: list[dict[str, Any]] = []
        for index, chunk in enumerate(clarification_decision["candidates"], start=1):
            options.append(
                {
                    "id": f"option_{index}",
                    "label": self._clarification_label_for_chunk(chunk),
                    "question": self._clarification_label_for_chunk(chunk),
                    "source": chunk.source_name,
                    "page": chunk.location_label,
                    "qa_id": chunk.qa_id,
                    "category": chunk.category,
                }
            )

        prompt_lines = [
            "سؤالك ممكن يقصد أكتر من حالة. اختار الأقرب أو اكتب تفاصيل أكثر:",
        ]
        prompt_lines.extend(f"{index}. {option['label']}" for index, option in enumerate(options, start=1))

        return {
            "question": "\n".join(prompt_lines),
            "original_question": question,
            "attempts": 1,
            "reason": clarification_decision["reason"],
            "options": options,
        }

    @staticmethod
    def _clarification_label_for_chunk(chunk: RetrievedChunk) -> str:
        if chunk.question_text:
            return clean_answer_preserve_formatting(chunk.question_text)

        for raw_text in (chunk.prompt_text, chunk.text):
            label = TrainingChatbot._extract_question_label(raw_text)
            if label:
                return label
        return clean_answer_preserve_formatting(chunk.source_name or "اختيار مناسب")

    @staticmethod
    def _extract_question_label(text: str | None) -> str | None:
        normalized_text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized_text:
            return None

        field_match = re.search(r"(?im)^\s*(?:question|السؤال)\s*:\s*(.+)$", normalized_text)
        if field_match:
            return clean_answer_preserve_formatting(field_match.group(1))

        first_line = normalized_text.split("\n", 1)[0].strip()
        cleaned_line = clean_answer_preserve_formatting(first_line)
        return cleaned_line or None

    def _should_use_extractive_recovery(
        self,
        retrieval: RetrievalResult,
        generation_fallback_reason: str | None,
    ) -> bool:
        if self.config.strict_grounded_mode:
            return False
        top_chunk = retrieval.top_chunk
        if generation_fallback_reason is None or retrieval.should_fallback or top_chunk is None:
            return False
        recovery_text = top_chunk.answer_text or clean_generation_context(top_chunk.context_text())
        return bool(clean_answer_preserve_formatting(recovery_text))

    def _build_extractive_recovery_answer(self, top_chunk) -> str:
        if top_chunk is None:
            return self.config.fallback_text

        recovery_text = top_chunk.answer_text or clean_generation_context(top_chunk.context_text())
        clean_text = clean_answer_preserve_formatting(recovery_text)
        from .passage_quality import readability
        if not readability(clean_text,qa=bool(getattr(top_chunk,'qa_id',None)))['readable']:
            return self.config.fallback_text
        if not clean_text or clean_text == self.config.fallback_text:
            return self.config.fallback_text

        # A cut quote can lose an exception or condition. Prefer another answer path.
        excerpt = clean_text if len(clean_text)<=1400 else ''
        if not excerpt:
            return self.config.fallback_text
        if "\n" in excerpt:
            return f"وفقاً للمصدر المتاح:\n{excerpt}"
        return f"وفقاً للمصدر المتاح: {excerpt}"

    @staticmethod
    def _truncate_extractive_answer(text: str, max_chars: int = 420) -> str:
        if len(text) <= max_chars:
            return text

        excerpt = text[:max_chars].rstrip()
        boundaries = [
            excerpt.rfind("\n"),
            excerpt.rfind("؟"),
            excerpt.rfind("!"),
            excerpt.rfind("."),
            excerpt.rfind("،"),
            excerpt.rfind(";"),
        ]
        best_boundary = max(boundaries)
        if best_boundary >= int(max_chars * 0.6):
            excerpt = excerpt[: best_boundary + 1].rstrip()
        return excerpt.rstrip(" ،؛.!?") + "..."

    def _filter_prompt_context_chunks(
        self,
        question: str,
        retrieval: RetrievalResult,
    ) -> tuple[list[RetrievedChunk], list[dict[str, Any]]]:
        if not retrieval.chunks:
            return [], []

        prompt_chunks = retrieval.chunks[:3]
        removed_chunks = [
            {
                "source_name": chunk.source_name,
                "location_label": chunk.location_label,
                "page": chunk.location_value if chunk.location_type == "page" else None,
                "final_score": round(chunk.final_score, 4),
                "reason": "outside_top3_prompt_context",
            }
            for chunk in retrieval.chunks[3:]
        ]

        return prompt_chunks, removed_chunks

    def _should_keep_prompt_context_chunk(
        self,
        *,
        top_chunk: RetrievedChunk,
        candidate_chunk: RetrievedChunk,
        relative_threshold: float,
    ) -> bool:
        if candidate_chunk.final_score >= relative_threshold:
            return True
        return self._is_same_or_adjacent_prompt_context_chunk(top_chunk, candidate_chunk)

    def _is_same_or_adjacent_prompt_context_chunk(
        self,
        top_chunk: RetrievedChunk,
        candidate_chunk: RetrievedChunk,
    ) -> bool:
        if candidate_chunk.source_path != top_chunk.source_path:
            return False
        if candidate_chunk.location_type != top_chunk.location_type:
            return False
        if candidate_chunk.location_label == top_chunk.location_label:
            return True
        if not self.config.prompt_context_keep_adjacent_pages:
            return False
        if candidate_chunk.location_type not in {"page", "slide"}:
            return False

        top_location = self._parse_numeric_location(top_chunk.location_value)
        candidate_location = self._parse_numeric_location(candidate_chunk.location_value)
        if top_location is None or candidate_location is None:
            return False
        return abs(candidate_location - top_location) == 1

    @staticmethod
    def _parse_numeric_location(location_value: str) -> int | None:
        try:
            return int(str(location_value).strip())
        except (TypeError, ValueError):
            return None

    def print_startup_diagnostics(self) -> None:
        diagnostics = self.diagnostics()
        lines = [
            f"project path: {diagnostics['project_path']}",
            f"source path: {diagnostics['source_path']}",
            f"python executable: {diagnostics['python_executable']}",
            f"ollama status: {diagnostics['ollama_status']}",
            f"llm model: {diagnostics['llm_model']}",
            f"embedding model: {diagnostics['embedding_model']}",
            f"ocr backend: {diagnostics['ocr_backend']}",
            f"strict grounded mode: {diagnostics['strict_grounded_mode']}",
            f"number of files indexed: {diagnostics['files_indexed']}",
            f"number of chunks: {diagnostics['chunks_indexed']}",
            f"chroma path: {diagnostics['chroma_path']}",
            f"active collection: {diagnostics['collection_name']}",
        ]
        self._safe_console_print("\n".join(lines))

    @staticmethod
    def _safe_console_print(text: str) -> None:
        try:
            print(text)
        except UnicodeEncodeError:
            encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
            safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="ignore")
            print(safe_text)

    def _embed_chunk_texts(self, texts: list[str], batch_size: int = 12) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            embeddings.extend(self.ollama_client.embed_texts(batch))
        return embeddings

    def _prepare_directories(self) -> None:
        self.config.data_path.mkdir(parents=True, exist_ok=True)
        self.config.logs_path.mkdir(parents=True, exist_ok=True)
        self.config.chroma_path.mkdir(parents=True, exist_ok=True)

    def _read_manifest_payload(self) -> dict[str, Any]:
        if not self.config.manifest_path.exists():
            return {}
        try:
            payload = json.loads(self.config.manifest_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _manifest_collection_name(self, payload: dict[str, Any]) -> str:
        collection_name = payload.get("collection_name")
        if isinstance(collection_name, str) and collection_name.strip():
            return collection_name.strip()
        return self.config.collection_name

    def _next_collection_name(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"{self.config.collection_name}__{timestamp}_{uuid4().hex[:8]}"

    def _write_manifest(
        self,
        files_manifest: list[dict[str, Any]],
        chunk_count: int,
        collection_name: str,
    ) -> None:
        payload = {
            "indexed_at": datetime.now().isoformat(timespec="seconds"),
            "collection_name": collection_name,
            "index_version": self.config.index_version,
            "files": files_manifest,
            "chunk_count": chunk_count,
        }
        self.config.manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_ocr_usage_report(self) -> None:
        report = self.ingestor.last_report
        report_path = self.config.project_path / "ocr_usage_report.md"

        lines = [
            "# OCR Usage Report",
            "",
            f"Generated at: {datetime.now().isoformat(timespec='seconds')}",
            "",
            "Counts below use page-like units processed during indexing.",
            "For PDF this means pages. For PPTX/DOCX/image inputs it can also include slides, sections, and embedded image units.",
            "",
            f"- total files: {report.total_files}",
            f"- total pages: {report.total_pages}",
            f"- pages with direct text extraction: {report.pages_with_direct_text_extraction}",
            f"- pages requiring OCR: {report.pages_requiring_ocr}",
            f"- EasyOCR success pages: {report.easyocr_success_pages}",
            f"- failed OCR pages: {report.failed_ocr_pages}",
            "",
            "## Files With OCR Errors",
            "",
        ]

        if report.files_with_ocr_errors:
            lines.extend(f"- {source_name}" for source_name in report.files_with_ocr_errors)
        else:
            lines.append("- None")

        lines.extend(
            [
                "",
                "## Files/Pages With OCR Errors",
                "",
            ]
        )

        if report.page_errors:
            for item in report.page_errors:
                lines.append(
                    f"- {item['source_name']} | {item['location_label']} | {item['backend']} | {item['error']}"
                )
        else:
            lines.append("- None")

        report_path.write_text("\n".join(lines), encoding="utf-8")

    def _delete_collection(self, store: ChromaVectorStore, collection_name: str) -> None:
        try:
            store.delete_collection(collection_name)
        except Exception as exc:
            self.logger.warning("Could not delete Chroma collection %s: %s", collection_name, exc)

    @staticmethod
    def _source_from_prompt_chunk(chunk: dict[str, Any], is_primary: bool = True) -> dict[str, Any] | None:
        if not chunk:
            return None

        location_type = str(chunk.get("location_type", "") or "")
        location_value = chunk.get("location_value")
        score_value = chunk.get("final_score")
        try:
            score = round(float(score_value), 4) if score_value is not None else None
        except (TypeError, ValueError):
            score = None

        return {
            "source_name": chunk.get("source_name", ""),
            "source_path": chunk.get("source_path", ""),
            "location_label": chunk.get("location_label", ""),
            "final_score": score,
            "score": score,
            "page": location_value if location_type == "page" else None,
            "slide": location_value if location_type == "slide" else None,
            "section": location_value if location_type == "section" else None,
            "primary_source": is_primary,
            "role": "primary" if is_primary else "supporting",
        }

    @staticmethod
    def _unique_sources(retrieval: RetrievalResult) -> list[dict[str, Any]]:
        seen = set()
        sources: list[dict[str, Any]] = []
        for chunk in retrieval.chunks:
            key = (chunk.source_path, chunk.location_label)
            if key in seen:
                continue
            seen.add(key)
            is_primary = not sources
            source_payload = TrainingChatbot._source_from_prompt_chunk(chunk.to_prompt_chunk(), is_primary=is_primary)
            if source_payload is not None:
                sources.append(source_payload)
        return sources


class ChatbotGUI:
    def __init__(self, bot: TrainingChatbot) -> None:
        self.bot = bot
        self.root = tk.Tk()
        self.root.title("HR Training Arabic RAG Chatbot")
        self.root.geometry("980x720")
        self.status_var = tk.StringVar(value="جاهز")
        self._build_layout()

    def _build_layout(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)

        header = ttk.Label(frame, text="مساعد التدريب - بحث داخل ملفات المواد فقط", font=("Segoe UI", 15, "bold"))
        header.pack(anchor="e", pady=(0, 8))

        status = ttk.Label(frame, textvariable=self.status_var, font=("Segoe UI", 10))
        status.pack(anchor="e", pady=(0, 8))

        question_label = ttk.Label(frame, text="السؤال", font=("Segoe UI", 11, "bold"))
        question_label.pack(anchor="e")

        self.question_box = tk.Text(frame, height=5, wrap="word", font=("Segoe UI", 12))
        self.question_box.pack(fill="x", pady=(4, 10))

        button_row = ttk.Frame(frame)
        button_row.pack(fill="x", pady=(0, 10))

        self.ask_button = ttk.Button(button_row, text="اسأل", command=self.ask_question)
        self.ask_button.pack(side="right", padx=4)

        self.reindex_button = ttk.Button(button_row, text="إعادة الفهرسة", command=self.reindex)
        self.reindex_button.pack(side="right", padx=4)

        clear_button = ttk.Button(button_row, text="مسح", command=self.clear_output)
        clear_button.pack(side="right", padx=4)

        answer_label = ttk.Label(frame, text="الإجابة", font=("Segoe UI", 11, "bold"))
        answer_label.pack(anchor="e")

        self.answer_box = tk.Text(frame, height=15, wrap="word", font=("Segoe UI", 12))
        self.answer_box.pack(fill="both", expand=True, pady=(4, 10))
        self.answer_box.tag_configure("rtl", justify="right")

        source_label = ttk.Label(frame, text="المصادر", font=("Segoe UI", 11, "bold"))
        source_label.pack(anchor="e")

        self.sources_box = tk.Text(frame, height=8, wrap="word", font=("Segoe UI", 11))
        self.sources_box.pack(fill="both", expand=False, pady=(4, 0))
        self.sources_box.tag_configure("rtl", justify="right")

    def ask_question(self) -> None:
        question = self.question_box.get("1.0", "end").strip()
        if not question:
            messagebox.showwarning("تنبيه", "اكتب سؤالاً أولاً.")
            return

        self._set_busy("جاري البحث عن الإجابة...")
        threading.Thread(target=self._run_question, args=(question,), daemon=True).start()

    def reindex(self) -> None:
        self._set_busy("جاري إعادة الفهرسة...")
        threading.Thread(target=self._run_reindex, daemon=True).start()

    def clear_output(self) -> None:
        self.answer_box.delete("1.0", "end")
        self.sources_box.delete("1.0", "end")
        self.status_var.set("جاهز")

    def _run_question(self, question: str) -> None:
        try:
            result = self.bot.ask(question)
            self.root.after(0, lambda: self._display_result(result))
        except Exception as exc:
            self.root.after(0, lambda: self._display_error(exc))

    def _run_reindex(self) -> None:
        try:
            stats = self.bot.ensure_index(force_reindex=True)
            self.root.after(
                0,
                lambda: self.status_var.set(
                    f"تمت إعادة الفهرسة: {stats.files_indexed} ملف و {stats.chunks_indexed} مقطع"
                ),
            )
        except Exception as exc:
            self.root.after(0, lambda: self._display_error(exc))
        finally:
            self.root.after(0, self._set_ready)

    def _display_result(self, result: dict[str, Any]) -> None:
        self.answer_box.delete("1.0", "end")
        self.answer_box.insert("1.0", result["answer"])
        self.answer_box.tag_add("rtl", "1.0", "end")

        self.sources_box.delete("1.0", "end")
        if result["sources"]:
            lines = [
                f"{index}. {source['source_name']} - {source['location_label']}"
                for index, source in enumerate(result["sources"], start=1)
            ]
            self.sources_box.insert("1.0", "\n".join(lines))
        else:
            self.sources_box.insert("1.0", "لا توجد مصادر لأن الاسترجاع لم يجد سياقاً مناسباً.")
        self.sources_box.tag_add("rtl", "1.0", "end")

        self.status_var.set("تمت الإجابة")
        self._set_ready()

    def _display_error(self, exc: Exception) -> None:
        traceback.print_exc()
        messagebox.showerror("خطأ", str(exc))
        self.status_var.set("حدث خطأ")
        self._set_ready()

    def _set_busy(self, message: str) -> None:
        self.status_var.set(message)
        self.ask_button.configure(state="disabled")
        self.reindex_button.configure(state="disabled")

    def _set_ready(self) -> None:
        self.ask_button.configure(state="normal")
        self.reindex_button.configure(state="normal")

    def run(self) -> None:
        self.root.mainloop()


def build_chatbot(base_path: Path | None = None) -> TrainingChatbot:
    return TrainingChatbot(base_path=base_path)


def run_cli(bot: TrainingChatbot) -> None:
    print("اكتب سؤالك. للخروج اكتب exit أو quit أو خروج.")
    while True:
        question = input("> ").strip()
        if question.lower() in {"exit", "quit"} or question == "خروج":
            break
        if not question:
            continue

        result = bot.ask(question)
        print(result["answer"])
        if result["sources"]:
            print("المصادر:")
            for source in result["sources"]:
                print(f"- {source['source_name']} | {source['location_label']}")


def run_single_question(bot: TrainingChatbot, question: str) -> None:
    result = bot.ask(question)
    print(result["answer"])
    if result["sources"]:
        print("المصادر:")
        for source in result["sources"]:
            print(f"- {source['source_name']} | {source['location_label']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline Arabic RAG chatbot for HR training materials.")
    parser.add_argument("--mode", choices=["gui", "cli", "index"], default="gui")
    parser.add_argument("--question", help="Ask one question in CLI mode.")
    parser.add_argument("--reindex", action="store_true", help="Force a full reindex before answering.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bot = build_chatbot()
    bot.ensure_index(force_reindex=args.reindex)
    bot.print_startup_diagnostics()

    if args.question:
        run_single_question(bot, args.question)
        return

    if args.mode == "index":
        return
    if args.mode == "cli":
        run_cli(bot)
        return

    gui = ChatbotGUI(bot)
    gui.run()


if __name__ == "__main__":
    main()
