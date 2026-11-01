from __future__ import annotations

import ast
import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from .config import AppConfig
from .generation import OllamaClient
from .normalization import keyword_overlap, normalize_text, tokenize_for_search
from .profiling import record_timing, set_counter, set_metadata
from .query_understanding import QueryUnderstandingEngine, QueryUnderstandingResult
from .vector_store import ChromaVectorStore
from .question_lookup import QuestionLookup


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    source_name: str
    source_path: str
    source_type: str
    location_type: str
    location_label: str
    location_value: str
    semantic_score: float
    keyword_score: float
    overlap_score: float
    overlap_count: int
    source_relevance: float
    final_score: float
    prompt_text: str | None = None
    qa_id: str | None = None
    category: str | None = None
    question_text: str | None = None
    answer_text: str | None = None
    alternate_questions: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    qa_match_score: float = 0.0
    source_sha256: str = ""
    extraction_quality: str = "unverified"
    answer_eligibility: str = ""
    verified_answer_passages: Any = field(default_factory=list)
    temporal_scope: str = ""

    def context_text(self) -> str:
        from .passage_quality import evidence_text
        return evidence_text(self.text,{'prompt_text':self.prompt_text,'answer_eligibility':self.answer_eligibility,
                'verified_answer_passages':self.verified_answer_passages,'temporal_scope':self.temporal_scope})

    def search_text(self) -> str:
        return self.text

    def to_prompt_chunk(self) -> dict[str, Any]:
        return {
            "id": self.chunk_id,
            "source_sha256": self.source_sha256,
            "extraction_quality": self.extraction_quality,
            "answer_eligibility": self.answer_eligibility,
            "temporal_scope": self.temporal_scope,
            "text": self.context_text(),
            "source_name": self.source_name,
            "source_path": self.source_path,
            "source_type": self.source_type,
            "location_type": self.location_type,
            "location_label": self.location_label,
            "location_value": self.location_value,
            "qa_id": self.qa_id,
            "category": self.category,
            "question_text": self.question_text,
            "semantic_score": round(self.semantic_score, 4),
            "keyword_score": round(self.keyword_score, 4),
            "overlap_score": round(self.overlap_score, 4),
            "overlap_count": self.overlap_count,
            "source_relevance": round(self.source_relevance, 4),
            "qa_match_score": round(self.qa_match_score, 4),
            "final_score": round(self.final_score, 4),
        }


@dataclass
class RetrievalResult:
    question: str
    normalized_question: str
    query_tokens: list[str]
    chunks: list[RetrievedChunk]
    fallback_reason: str | None = None
    ranked_chunks: list[RetrievedChunk] = field(default_factory=list)
    embedding_time_ms: float = 0.0
    chroma_search_time_ms: float = 0.0
    bm25_time_ms: float = 0.0
    rerank_time_ms: float = 0.0
    question_normalization_time_ms: float = 0.0
    query_tokenization_time_ms: float = 0.0
    fallback_decision_time_ms: float = 0.0
    total_time_ms: float = 0.0
    query_coverage: float = 0.0
    retrieval_confidence: float | None = None
    missing_query_tokens: list[str] = field(default_factory=list)
    semantic_candidate_count: int = 0
    keyword_candidate_count: int = 0
    merged_candidate_count: int = 0
    retrieval_query: str = ""
    original_normalized_query: str = ""
    original_normalized_question: str = ""
    original_query_tokens: list[str] = field(default_factory=list)
    rewritten_query: str = ""
    detected_intent: str = ""
    product_aliases: list[str] = field(default_factory=list)
    important_keywords: list[str] = field(default_factory=list)
    possible_meanings: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    query_understanding_used: bool = False
    query_understanding_failed_reason: str | None = None
    query_understanding_time_ms: float = 0.0

    @property
    def should_fallback(self) -> bool:
        return self.fallback_reason is not None

    @property
    def top_chunk(self) -> RetrievedChunk | None:
        return self.chunks[0] if self.chunks else None

    def prompt_chunks(self) -> list[dict[str, Any]]:
        return [chunk.to_prompt_chunk() for chunk in self.chunks]

    def ranked_prompt_chunks(self, limit: int = 10) -> list[dict[str, Any]]:
        return [chunk.to_prompt_chunk() for chunk in self.ranked_chunks[:limit]]


@dataclass
class ProductRetrievalSignal:
    has_fawry_yawmy: bool = False
    has_yellow_card: bool = False
    matched_aliases: list[str] = field(default_factory=list)
    expanded_terms: list[str] = field(default_factory=list)

    @property
    def exclusive_fawry_yawmy(self) -> bool:
        return self.has_fawry_yawmy and not self.has_yellow_card

    @property
    def exclusive_yellow_card(self) -> bool:
        return self.has_yellow_card and not self.has_fawry_yawmy

    @property
    def mixed_products(self) -> bool:
        return self.has_fawry_yawmy and self.has_yellow_card


class HybridRetriever:
    STRICT_MIN_QUERY_COVERAGE = 0.5
    REWRITTEN_QUERY_WEIGHT = 0.6
    PRODUCT_ALIGNMENT_WEIGHT = 0.12
    MIXED_PRODUCT_BOOST = 0.04
    FAWRY_YAWMY_SOURCE_NAME = "fawry_youmy.md"
    YELLOW_CARD_SOURCE_NAME = "yellow_card.md"
    FAWRY_YAWMY_ALIASES = (
        "فوري يومي",
        "فوري يومى",
        "Fawry Yawmy",
        "fawry yawmy",
    )
    YELLOW_CARD_ALIASES = (
        "الكارت الأصفر",
        "الكارت الاصفر",
        "البطاقة الصفراء",
        "Yellow Card",
        "يلو كارد",
        "اليلو كارد",
        "يولو كارد",
        "اليولو كارد",
    )
    FAWRY_YAWMY_DEPOSIT_TERMS = (
        "ايداع",
        "إيداع",
        "الحد الاقصي للايداع",
        "حد الايداع",
        "اضيف فلوس",
        "احط فلوس",
    )
    FAWRY_YAWMY_DEPOSIT_EXPANSIONS = (
        "استثمار",
        "مبلغ الاستثمار",
        "حد الاستثمار",
        "الحد الأقصى للاستثمار",
        "500000",
        "500 ألف",
        "الاستثمار بالبطاقة",
    )

    def __init__(
        self,
        config: AppConfig,
        vector_store: ChromaVectorStore,
        ollama_client: OllamaClient,
        logger: logging.Logger,
    ) -> None:
        self.config = config
        self.vector_store = vector_store
        self.ollama_client = ollama_client
        self.logger = logger
        self.query_understanding = QueryUnderstandingEngine(config, ollama_client, logger)
        self.corpus: list[dict[str, Any]] = []
        self.doc_freq: Counter[str] = Counter()
        self.corpus_vocabulary: set[str] = set()
        self.avg_doc_len = 0.0
        self.qa_question_index: list[tuple[str, set[str]]] = []
        self.question_lookup = QuestionLookup([])
        self.source_filter = None

    def refresh(self) -> None:
        self.corpus = []
        rows = self.vector_store.fetch_all_chunks()
        for row in rows:
            metadata = row["metadata"]
            doc_tokens = tokenize_for_search(row["text"])
            source_tokens = tokenize_for_search(
                f"{metadata.get('source_name', '')} {metadata.get('location_label', '')}"
            )
            self.corpus.append(
                {
                    "id": row["id"],
                    "text": row["text"],
                    "metadata": metadata,
                    "doc_tokens": doc_tokens,
                    "source_tokens": source_tokens,
                }
            )
        self._rebuild_corpus_indexes()
        self.logger.info("Retriever refreshed with %s chunks.", len(self.corpus))

    def _rebuild_corpus_indexes(self) -> None:
        self.doc_freq = Counter()
        self.qa_question_index = []
        total_length = 0

        for row in self.corpus:
            metadata = row.get("metadata", {})
            doc_tokens = list(row.get("doc_tokens") or tokenize_for_search(str(row.get("text", ""))))
            source_tokens = list(
                row.get("source_tokens")
                or tokenize_for_search(
                    f"{metadata.get('source_name', '')} {metadata.get('location_label', '')}"
                )
            )
            row["doc_tokens"] = doc_tokens
            row["source_tokens"] = source_tokens
            question_text = str(metadata.get("question_text") or "").strip()
            normalized_question_text = normalize_text(question_text, for_search=True).lower() if question_text else ""
            question_tokens = tokenize_for_search(question_text)
            alternate_questions = self._metadata_list(metadata.get("alternate_questions"))
            if not alternate_questions:
                alternate_questions = self._extract_inline_field_items(
                    str(row.get("text", "")),
                    "Alternate Questions",
                    stop_labels=("Keywords",),
                )
            keywords = self._metadata_list(metadata.get("keywords"))
            if not keywords:
                keywords = self._extract_inline_field_items(str(row.get("text", "")), "Keywords")
            category_tokens = tokenize_for_search(str(metadata.get("category") or ""))
            alternate_question_tokens = [tokenize_for_search(item) for item in alternate_questions if item]
            keyword_tokens = self._dedupe_tokens(*[tokenize_for_search(item) for item in keywords if item])
            metadata["alternate_questions"] = alternate_questions
            metadata["keywords"] = keywords
            row["question_normalized"] = normalized_question_text
            row["question_tokens"] = question_tokens
            row["alternate_questions"] = alternate_questions
            row["alternate_question_tokens"] = alternate_question_tokens
            row["keywords"] = keywords
            row["keyword_tokens"] = keyword_tokens
            row["category_tokens"] = category_tokens
            total_length += len(doc_tokens)
            self.doc_freq.update(set(doc_tokens))
            if not question_text:
                continue

            question_token_set = set(question_tokens)
            if normalized_question_text or question_token_set:
                self.qa_question_index.append((normalized_question_text, question_token_set))

        self.corpus_vocabulary = set(self.doc_freq)
        self.avg_doc_len = (total_length / len(self.corpus)) if self.corpus else 0.0
        self.question_lookup = QuestionLookup(self.corpus)

    def _should_skip_query_understanding(self, normalized_question: str, query_tokens: list[str]) -> bool:
        if not normalized_question or not query_tokens:
            return True

        query_set = set(query_tokens)
        for question_text, question_tokens in self.qa_question_index:
            if normalized_question == question_text:
                return True
            if query_set and question_tokens and query_set == question_tokens:
                return True
            if query_set and question_tokens and query_set.issubset(question_tokens):
                if len(question_tokens) - len(query_set) <= 1:
                    return True
        return False

    @staticmethod
    def _combine_query_text(*parts: Any) -> str:
        segments: list[str] = []
        seen: set[str] = set()
        for part in parts:
            if isinstance(part, str):
                candidate_items = [part]
            elif isinstance(part, list):
                candidate_items = [str(item) for item in part]
            else:
                candidate_items = [str(part)]
            for item in candidate_items:
                cleaned = str(item).strip()
                normalized = cleaned.casefold()
                if not cleaned or normalized in seen:
                    continue
                seen.add(normalized)
                segments.append(cleaned)
        return " ".join(segments).strip()

    @staticmethod
    def _merge_unique_strings(*string_groups: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for string_group in string_groups:
            for item in string_group:
                cleaned = str(item).strip()
                normalized = cleaned.casefold()
                if not cleaned or normalized in seen:
                    continue
                seen.add(normalized)
                merged.append(cleaned)
        return merged

    @staticmethod
    def _matching_phrases(
        *,
        question: str,
        normalized_question: str,
        phrases: tuple[str, ...],
    ) -> list[str]:
        normalized_text = (normalized_question or "").casefold()
        raw_text = (question or "").casefold()
        matches: list[str] = []
        seen: set[str] = set()
        for phrase in phrases:
            raw_phrase = str(phrase).strip()
            if not raw_phrase:
                continue
            normalized_phrase = normalize_text(raw_phrase, for_search=True).casefold()
            if (
                (normalized_phrase and normalized_phrase in normalized_text)
                or raw_phrase.casefold() in raw_text
            ):
                key = raw_phrase.casefold()
                if key in seen:
                    continue
                seen.add(key)
                matches.append(raw_phrase)
        return matches

    def _product_retrieval_signal(
        self,
        *,
        question: str,
        normalized_question: str,
    ) -> ProductRetrievalSignal:
        fawry_yawmy_matches = self._matching_phrases(
            question=question,
            normalized_question=normalized_question,
            phrases=self.FAWRY_YAWMY_ALIASES,
        )
        yellow_card_matches = self._matching_phrases(
            question=question,
            normalized_question=normalized_question,
            phrases=self.YELLOW_CARD_ALIASES,
        )
        deposit_matches = self._matching_phrases(
            question=question,
            normalized_question=normalized_question,
            phrases=self.FAWRY_YAWMY_DEPOSIT_TERMS,
        )
        expanded_terms = list(self.FAWRY_YAWMY_DEPOSIT_EXPANSIONS) if fawry_yawmy_matches and deposit_matches else []
        return ProductRetrievalSignal(
            has_fawry_yawmy=bool(fawry_yawmy_matches),
            has_yellow_card=bool(yellow_card_matches),
            matched_aliases=self._merge_unique_strings(fawry_yawmy_matches, yellow_card_matches),
            expanded_terms=expanded_terms,
        )

    def _product_alignment_score(
        self,
        *,
        source_name: str,
        product_signal: ProductRetrievalSignal,
    ) -> float:
        source_key = str(source_name or "").strip().casefold()
        if not source_key:
            return 0.0

        is_fawry_yawmy_source = source_key == self.FAWRY_YAWMY_SOURCE_NAME.casefold()
        is_yellow_card_source = source_key == self.YELLOW_CARD_SOURCE_NAME.casefold()

        if product_signal.exclusive_fawry_yawmy:
            if is_fawry_yawmy_source:
                return 1.0
            if is_yellow_card_source:
                return -1.0
            return 0.0
        if product_signal.exclusive_yellow_card:
            if is_yellow_card_source:
                return 1.0
            if is_fawry_yawmy_source:
                return -1.0
            return 0.0
        if product_signal.mixed_products and (is_fawry_yawmy_source or is_yellow_card_source):
            return self.MIXED_PRODUCT_BOOST / self.PRODUCT_ALIGNMENT_WEIGHT
        return 0.0

    def search(self, question: str) -> RetrievalResult:
        source_filter = getattr(self, "source_filter", None)
        if source_filter is not None:
            source_filter.refresh()
        retrieval_started = perf_counter()
        question = question.strip()
        normalization_started = perf_counter()
        normalized_question = normalize_text(question, for_search=True)
        question_normalization_time_ms = round((perf_counter() - normalization_started) * 1000, 2)
        tokenization_started = perf_counter()
        query_tokens = tokenize_for_search(question)
        query_tokenization_time_ms = round((perf_counter() - tokenization_started) * 1000, 2)
        record_timing("preprocessing.normalize_question_ms", question_normalization_time_ms)
        record_timing("preprocessing.tokenize_and_expand_ms", query_tokenization_time_ms)
        set_counter("preprocessing.original_query_token_count", len(query_tokens))

        exact_rows = self.question_lookup.match(question)
        if source_filter is not None:
            exact_rows = [row for row in exact_rows if source_filter.allows(row.get("metadata", {}))]
        from .passage_quality import readability, evidence_text
        exact_rows = [row for row in exact_rows
                      if readability(evidence_text(row['text'], row['metadata']), row['metadata'], qa=True)['readable']
                      and readability(row['metadata'].get('answer_text') or row['text'], row['metadata'], qa=True)['readable']]
        if exact_rows:
            chunks = []
            for row in exact_rows[:self.config.top_k]:
                metadata = row["metadata"]
                chunks.append(RetrievedChunk(
                    chunk_id=row["id"], text=row["text"], source_name=metadata.get("source_name", ""),
                    source_path=metadata.get("source_path", ""), source_type=metadata.get("source_type", ""),
                    location_type=metadata.get("location_type", ""), location_label=metadata.get("location_label", ""),
                    location_value=str(metadata.get("location_value", "")), semantic_score=1.0,
                    keyword_score=1.0, overlap_score=1.0, overlap_count=len(query_tokens), source_relevance=1.0,
                    final_score=1.0, prompt_text=metadata.get("prompt_text"), qa_id=metadata.get("qa_id"),
                    category=metadata.get("category"), question_text=metadata.get("question_text"),
                    answer_text=metadata.get("answer_text"), qa_match_score=1.0,
                    alternate_questions=row.get("alternate_questions", []), keywords=row.get("keywords", []),
                    source_sha256=metadata.get("source_sha256", ""),
                    extraction_quality=metadata.get("extraction_quality", "unverified"),
                    answer_eligibility=metadata.get("answer_eligibility", ""),
                    verified_answer_passages=metadata.get("verified_answer_passages", []),
                    temporal_scope=metadata.get("temporal_scope", ""),
                ))
            ambiguous = len(exact_rows) > 1
            set_counter("retrieval.curated_question_lookup", 1)
            return RetrievalResult(
                question=question, normalized_question=normalized_question, query_tokens=query_tokens,
                chunks=chunks, ranked_chunks=chunks, query_coverage=1.0, retrieval_confidence=1.0,
                fallback_reason="ambiguous_curated_question" if ambiguous else None,
                needs_clarification=ambiguous, merged_candidate_count=len(chunks),
                total_time_ms=round((perf_counter()-retrieval_started)*1000, 2),
            )

        if not question:
            return RetrievalResult(
                question=question,
                normalized_question=normalized_question,
                query_tokens=query_tokens,
                retrieval_query=normalized_question or question,
                original_normalized_query=normalized_question or question,
                original_normalized_question=normalized_question,
                original_query_tokens=query_tokens,
                chunks=[],
                fallback_reason="empty",
                question_normalization_time_ms=question_normalization_time_ms,
                query_tokenization_time_ms=query_tokenization_time_ms,
            )
        if not query_tokens:
            return RetrievalResult(
                question=question,
                normalized_question=normalized_question,
                query_tokens=query_tokens,
                retrieval_query=normalized_question or question,
                original_normalized_query=normalized_question or question,
                original_normalized_question=normalized_question,
                original_query_tokens=query_tokens,
                chunks=[],
                fallback_reason="no_meaningful_tokens",
                question_normalization_time_ms=question_normalization_time_ms,
                query_tokenization_time_ms=query_tokenization_time_ms,
            )
        if not self.corpus:
            return RetrievalResult(
                question=question,
                normalized_question=normalized_question,
                query_tokens=query_tokens,
                retrieval_query=normalized_question or question,
                original_normalized_query=normalized_question or question,
                original_normalized_question=normalized_question,
                original_query_tokens=query_tokens,
                chunks=[],
                fallback_reason="empty_index",
                question_normalization_time_ms=question_normalization_time_ms,
                query_tokenization_time_ms=query_tokenization_time_ms,
            )

        original_normalized_query = normalized_question or question
        product_signal = self._product_retrieval_signal(
            question=question,
            normalized_question=normalized_question,
        )
        retrieval_query = question
        original_query_tokens = list(query_tokens)
        scoring_query_tokens = list(query_tokens)
        rewritten_query_tokens: list[str] = []
        rewritten_normalized_question = ""
        query_understanding = QueryUnderstandingResult()
        if product_signal.expanded_terms:
            retrieval_query = self._combine_query_text(question, product_signal.expanded_terms)
            rewritten_normalized_question = normalize_text(retrieval_query, for_search=True).lower()
            rewritten_query_tokens = tokenize_for_search(retrieval_query)
        set_metadata(
            "retrieval.product_signal",
            {
                "has_fawry_yawmy": product_signal.has_fawry_yawmy,
                "has_yellow_card": product_signal.has_yellow_card,
                "matched_aliases": product_signal.matched_aliases,
                "expanded_terms": product_signal.expanded_terms,
            },
        )
        if product_signal.matched_aliases or product_signal.expanded_terms:
            self.logger.info(
                'event="product_aware_retrieval" has_fawry_yawmy=%s has_yellow_card=%s matched_aliases=%s expanded_terms=%s',
                product_signal.has_fawry_yawmy,
                product_signal.has_yellow_card,
                product_signal.matched_aliases,
                product_signal.expanded_terms,
            )

        if not getattr(self.config, "enable_llm_query_understanding", False):
            query_understanding.failed_reason = "disabled"
        elif self._should_skip_query_understanding(normalized_question.lower(), query_tokens):
            query_understanding.failed_reason = "skipped_high_confidence_direct_match"
        else:
            query_understanding_started = perf_counter()
            query_understanding = self.query_understanding.understand(
                question=question,
                normalized_question=normalized_question,
                query_tokens=query_tokens,
            )
            query_understanding.latency_ms = round(
                (perf_counter() - query_understanding_started) * 1000,
                2,
            )

        record_timing("query_understanding_ms", query_understanding.latency_ms)
        set_counter("query_understanding.keyword_count", len(query_understanding.important_keywords))
        set_metadata("query_understanding.rewritten_query", query_understanding.rewritten_query or None)
        set_metadata("query_understanding.detected_intent", query_understanding.detected_intent or None)
        set_metadata("query_understanding.important_keywords", query_understanding.important_keywords)
        set_metadata("query_understanding.possible_meanings", query_understanding.possible_meanings)
        set_metadata("query_understanding.failed_reason", query_understanding.failed_reason)

        if query_understanding.used and query_understanding.rewritten_query:
            retrieval_query = self._combine_query_text(
                retrieval_query if rewritten_query_tokens else question,
                query_understanding.rewritten_query,
                query_understanding.important_keywords,
            )
            rewritten_normalized_question = normalize_text(
                query_understanding.rewritten_query,
                for_search=True,
            ).lower()
            rewritten_query_tokens = tokenize_for_search(retrieval_query)
            if not rewritten_query_tokens:
                retrieval_query = question
                rewritten_normalized_question = ""
                rewritten_query_tokens = []
                query_understanding.used = False
                query_understanding.failed_reason = "empty_rewritten_query_tokens"

        scoring_query_tokens = self._dedupe_tokens(original_query_tokens, rewritten_query_tokens)
        if not scoring_query_tokens:
            scoring_query_tokens = list(original_query_tokens)

        set_counter("preprocessing.query_token_count", len(scoring_query_tokens))
        set_counter("preprocessing.rewritten_query_token_count", len(rewritten_query_tokens))

        embedding_started = perf_counter()
        semantic_queries = [question]
        distinct_rewrite = self._is_distinct_rewrite(
            normalized_question=normalized_question.lower(),
            original_query_tokens=original_query_tokens,
            rewritten_normalized_question=rewritten_normalized_question,
            rewritten_query_tokens=rewritten_query_tokens,
        )
        if distinct_rewrite:
            semantic_queries.append(retrieval_query)
        query_embeddings = self.ollama_client.embed_texts(semantic_queries)
        embedding_time_ms = round((perf_counter() - embedding_started) * 1000, 2)

        chroma_started = perf_counter()
        semantic_maps: list[dict[str, float]] = []
        semantic_candidate_ids: set[str] = set()
        for query_embedding in query_embeddings:
            semantic_rows = self.vector_store.semantic_search(query_embedding, self.config.semantic_candidates)
            semantic_maps.append({row["id"]: float(row.get("semantic_score", 0.0) or 0.0) for row in semantic_rows})
            semantic_candidate_ids.update(row["id"] for row in semantic_rows)
        chroma_search_time_ms = round((perf_counter() - chroma_started) * 1000, 2)
        original_semantic_scores = semantic_maps[0] if semantic_maps else {}
        rewritten_semantic_scores = semantic_maps[1] if len(semantic_maps) > 1 else {}

        bm25_started = perf_counter()
        original_keyword_scores = {
            row["id"]: self._bm25_score(original_query_tokens, row["doc_tokens"]) for row in self.corpus
        }
        rewritten_keyword_scores = {
            row["id"]: self._bm25_score(rewritten_query_tokens, row["doc_tokens"]) for row in self.corpus
        }
        max_original_keyword_score = max(original_keyword_scores.values(), default=0.0)
        max_rewritten_keyword_score = max(rewritten_keyword_scores.values(), default=0.0)
        keyword_scores = {
            row["id"]: self._combine_query_scores(
                primary_score=self._normalize_score(
                    original_keyword_scores.get(row["id"], 0.0),
                    max_original_keyword_score,
                ),
                secondary_score=self._normalize_score(
                    rewritten_keyword_scores.get(row["id"], 0.0),
                    max_rewritten_keyword_score,
                ),
            )
            for row in self.corpus
        }

        keyword_ranked = sorted(
            (row for row in self.corpus if keyword_scores.get(row["id"], 0.0) > 0),
            key=lambda row: keyword_scores[row["id"]],
            reverse=True,
        )[: self.config.keyword_candidates]
        bm25_time_ms = round((perf_counter() - bm25_started) * 1000, 2)

        candidate_ids = set(semantic_candidate_ids)
        candidate_ids.update(row["id"] for row in keyword_ranked)
        semantic_candidate_count = len(semantic_candidate_ids)
        keyword_candidate_count = len(keyword_ranked)
        merged_candidate_count = len(candidate_ids)
        set_counter("retrieval.semantic_candidate_count", semantic_candidate_count)
        set_counter("retrieval.keyword_candidate_count", keyword_candidate_count)
        set_counter("retrieval.merged_candidate_count", merged_candidate_count)

        # Top-k truncation means an unreturned semantic score is unknown, not
        # zero. Score the merged candidates with existing stored vectors.
        for query_embedding, score_map in zip(query_embeddings, semantic_maps):
            missing=candidate_ids-set(score_map)
            score_map.update(self.vector_store.score_candidates(query_embedding,missing))
        rerank_started = perf_counter()
        ranked_chunks: list[RetrievedChunk] = []
        for row in self.corpus:
            chunk_id = row["id"]
            if chunk_id not in candidate_ids:
                continue
            if source_filter is not None and not source_filter.allows(row.get("metadata", {})):
                continue

            from .passage_quality import evidence_text,readability
            evidence=evidence_text(row['text'],row['metadata'])
            if not readability(evidence,row['metadata'],qa=bool(row['metadata'].get('qa_id')))['readable']:continue

            semantic_score = self._combine_query_scores(
                primary_score=original_semantic_scores.get(chunk_id, 0.0),
                secondary_score=rewritten_semantic_scores.get(chunk_id, 0.0),
            )
            keyword_score = keyword_scores.get(chunk_id, 0.0)
            overlap_count, overlap_ratio = keyword_overlap(scoring_query_tokens, row["doc_tokens"])
            source_overlap_count, source_overlap_ratio = keyword_overlap(
                scoring_query_tokens,
                row["source_tokens"],
            )
            source_relevance = min(1.0, source_overlap_ratio + (0.1 if source_overlap_count else 0.0))
            product_alignment_score = self._product_alignment_score(
                source_name=row["metadata"].get("source_name", ""),
                product_signal=product_signal,
            )
            qa_match_score = self._qa_match_score(
                row=row,
                query_tokens=scoring_query_tokens,
                original_normalized_question=normalized_question.lower(),
                rewritten_normalized_question=rewritten_normalized_question,
            )

            if row["metadata"].get("qa_id"):
                final_score = (
                    0.40 * semantic_score
                    + 0.16 * keyword_score
                    + 0.10 * overlap_ratio
                    + 0.04 * source_relevance
                    + 0.30 * qa_match_score
                    + self.PRODUCT_ALIGNMENT_WEIGHT * product_alignment_score
                )
            else:
                final_score = (
                    0.55 * semantic_score
                    + 0.25 * keyword_score
                    + 0.15 * overlap_ratio
                    + 0.05 * source_relevance
                    + self.PRODUCT_ALIGNMENT_WEIGHT * product_alignment_score
                )

            metadata = row["metadata"]
            ranked_chunks.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    text=row["text"],
                    source_name=metadata.get("source_name", ""),
                    source_path=metadata.get("source_path", ""),
                    source_type=metadata.get("source_type", ""),
                    location_type=metadata.get("location_type", ""),
                    location_label=metadata.get("location_label", ""),
                    location_value=str(metadata.get("location_value", "")),
                    semantic_score=semantic_score,
                    keyword_score=keyword_score,
                    overlap_score=overlap_ratio,
                    overlap_count=overlap_count,
                    source_relevance=source_relevance,
                    final_score=final_score,
                    prompt_text=metadata.get("prompt_text"),
                    qa_id=metadata.get("qa_id"),
                    category=metadata.get("category"),
                    question_text=metadata.get("question_text"),
                    answer_text=metadata.get("answer_text"),
                    alternate_questions=list(row.get("alternate_questions") or []),
                    keywords=list(row.get("keywords") or []),
                    qa_match_score=qa_match_score,
                    source_sha256=metadata.get("source_sha256", ""),
                    extraction_quality=metadata.get("extraction_quality", "unverified"),
                    answer_eligibility=metadata.get("answer_eligibility", ""),
                    verified_answer_passages=metadata.get("verified_answer_passages", []),
                    temporal_scope=metadata.get("temporal_scope", ""),
                )
            )

        from .answer_relevance import supported_aspect
        ranked_chunks.sort(key=lambda item: (
            supported_aspect(question, " ".join([item.source_name, item.context_text(), item.question_text or "", item.answer_text or ""])),
            item.final_score), reverse=True)
        top_chunks = ranked_chunks[: self.config.top_k]
        rerank_time_ms = round((perf_counter() - rerank_started) * 1000, 2)
        missing_query_tokens = [token for token in scoring_query_tokens if token not in self.corpus_vocabulary]
        query_coverage = self._query_coverage(scoring_query_tokens, top_chunks)
        retrieval_confidence = top_chunks[0].final_score if top_chunks else None
        fallback_decision_started = perf_counter()
        fallback_reason = self._fallback_reason(
            question=question,
            normalized_question=normalized_question,
            query_tokens=scoring_query_tokens,
            chunks=top_chunks,
            missing_query_tokens=missing_query_tokens,
            query_coverage=query_coverage,
        )
        fallback_decision_time_ms = round((perf_counter() - fallback_decision_started) * 1000, 2)
        total_time_ms = round((perf_counter() - retrieval_started) * 1000, 2)
        record_timing("retrieval.embedding_ms", embedding_time_ms)
        record_timing("retrieval.chroma_query_ms", chroma_search_time_ms)
        record_timing("retrieval.bm25_ms", bm25_time_ms)
        record_timing("retrieval.rerank_ms", rerank_time_ms)
        record_timing("retrieval.fallback_decision_ms", fallback_decision_time_ms)
        record_timing("retrieval.total_ms", total_time_ms)
        return RetrievalResult(
            question=question,
            normalized_question=normalized_question,
            query_tokens=scoring_query_tokens,
            retrieval_query=retrieval_query,
            original_normalized_query=original_normalized_query,
            original_normalized_question=normalized_question,
            original_query_tokens=original_query_tokens,
            rewritten_query=query_understanding.rewritten_query,
            detected_intent=query_understanding.detected_intent,
            product_aliases=self._merge_unique_strings(
                product_signal.matched_aliases,
                query_understanding.product_aliases,
            ),
            important_keywords=query_understanding.important_keywords,
            possible_meanings=query_understanding.possible_meanings,
            needs_clarification=query_understanding.needs_clarification,
            query_understanding_used=query_understanding.used,
            query_understanding_failed_reason=query_understanding.failed_reason,
            query_understanding_time_ms=query_understanding.latency_ms,
            chunks=top_chunks,
            fallback_reason=fallback_reason,
            ranked_chunks=ranked_chunks[:10],
            embedding_time_ms=embedding_time_ms,
            chroma_search_time_ms=chroma_search_time_ms,
            bm25_time_ms=bm25_time_ms,
            rerank_time_ms=rerank_time_ms,
            question_normalization_time_ms=question_normalization_time_ms,
            query_tokenization_time_ms=query_tokenization_time_ms,
            fallback_decision_time_ms=fallback_decision_time_ms,
            total_time_ms=total_time_ms,
            query_coverage=query_coverage,
            retrieval_confidence=retrieval_confidence,
            missing_query_tokens=missing_query_tokens,
            semantic_candidate_count=semantic_candidate_count,
            keyword_candidate_count=keyword_candidate_count,
            merged_candidate_count=merged_candidate_count,
        )

    @staticmethod
    def _dedupe_tokens(*token_groups: list[str]) -> list[str]:
        ordered_tokens: list[str] = []
        seen: set[str] = set()
        for token_group in token_groups:
            for token in token_group:
                normalized = str(token).strip().casefold()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                ordered_tokens.append(str(token).strip())
        return ordered_tokens

    @staticmethod
    def _normalize_score(score: float, max_score: float) -> float:
        if max_score <= 0:
            return 0.0
        return max(0.0, min(1.0, score / max_score))

    @classmethod
    def _combine_query_scores(cls, primary_score: float, secondary_score: float) -> float:
        primary = max(0.0, min(1.0, primary_score))
        secondary = max(0.0, min(1.0, secondary_score))
        if secondary <= 0:
            return primary
        return min(1.0, primary + (1.0 - primary) * secondary * cls.REWRITTEN_QUERY_WEIGHT)

    @staticmethod
    def _metadata_list(value: Any) -> list[str]:
        parsed_value = value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            parsed_value = stripped
            if stripped.startswith("[") and stripped.endswith("]"):
                for parser in (json.loads, ast.literal_eval):
                    try:
                        parsed_value = parser(stripped)
                        break
                    except (ValueError, SyntaxError, json.JSONDecodeError):
                        parsed_value = stripped
            if isinstance(parsed_value, str):
                return [parsed_value] if parsed_value else []

        if not isinstance(parsed_value, list):
            return []

        items: list[str] = []
        seen: set[str] = set()
        for item in parsed_value:
            cleaned = str(item).strip()
            if not cleaned:
                continue
            normalized = cleaned.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            items.append(cleaned)
        return items

    @staticmethod
    def _extract_inline_field_items(text: str, label: str, stop_labels: tuple[str, ...] = ()) -> list[str]:
        if not text:
            return []

        stop_clause = ""
        if stop_labels:
            joined_labels = "|".join(re.escape(item) for item in stop_labels)
            stop_clause = rf"(?=\s+(?:{joined_labels})\s*:|$)"
        else:
            stop_clause = r"$"
        match = re.search(rf"{re.escape(label)}\s*:\s*(.+?){stop_clause}", text, flags=re.IGNORECASE)
        if not match:
            return []

        field_text = match.group(1).strip()
        if not field_text:
            return []

        items = [item.strip(" -*") for item in re.split(r"\s+-\s+", field_text) if item.strip(" -*")]
        deduped_items: list[str] = []
        seen: set[str] = set()
        for item in items:
            normalized = item.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped_items.append(item)
        return deduped_items

    @staticmethod
    def _is_distinct_rewrite(
        *,
        normalized_question: str,
        original_query_tokens: list[str],
        rewritten_normalized_question: str,
        rewritten_query_tokens: list[str],
    ) -> bool:
        if not rewritten_query_tokens:
            return False
        return (
            rewritten_normalized_question != normalized_question
            or set(rewritten_query_tokens) != set(original_query_tokens)
        )

    def _qa_match_score(
        self,
        *,
        row: dict[str, Any],
        query_tokens: list[str],
        original_normalized_question: str,
        rewritten_normalized_question: str,
    ) -> float:
        question_tokens = list(row.get("question_tokens") or [])
        question_token_set = set(question_tokens)
        if not question_tokens:
            return 0.0

        question_normalized = str(row.get("question_normalized") or "")
        alternate_question_tokens = list(row.get("alternate_question_tokens") or [])
        keyword_tokens = list(row.get("keyword_tokens") or [])
        category_tokens = list(row.get("category_tokens") or [])
        query_token_set = set(query_tokens)

        question_overlap_ratio = keyword_overlap(query_tokens, question_tokens)[1]
        alternate_overlap_ratio = max(
            (keyword_overlap(query_tokens, alt_tokens)[1] for alt_tokens in alternate_question_tokens if alt_tokens),
            default=0.0,
        )
        keyword_overlap_ratio = keyword_overlap(query_tokens, keyword_tokens)[1] if keyword_tokens else 0.0
        category_overlap_ratio = keyword_overlap(query_tokens, category_tokens)[1] if category_tokens else 0.0
        exact_match = (
            question_normalized == original_normalized_question
            or (rewritten_normalized_question and question_normalized == rewritten_normalized_question)
        )
        subset_match = bool(query_token_set and query_token_set.issubset(question_token_set))

        score = (
            0.40 * question_overlap_ratio
            + 0.20 * alternate_overlap_ratio
            + 0.20 * keyword_overlap_ratio
            + 0.10 * category_overlap_ratio
            + 0.10 * float(exact_match or subset_match)
        )
        if exact_match:
            score = max(score, 0.95)
        elif subset_match and question_overlap_ratio >= 0.6:
            score = max(score, 0.82)
        return min(1.0, score)

    def _fallback_reason(
        self,
        *,
        question: str,
        normalized_question: str,
        query_tokens: list[str],
        chunks: list[RetrievedChunk],
        missing_query_tokens: list[str],
        query_coverage: float,
    ) -> str | None:
        if not chunks:
            self.logger.info(
                "Retriever fallback decision reason=no_chunks_found missing_query_tokens=%s",
                missing_query_tokens,
            )
            return "no_chunks_found"

        top_chunk = chunks[0]
        if (
            self.config.strict_grounded_mode
            and query_coverage < self.STRICT_MIN_QUERY_COVERAGE
            and top_chunk.overlap_count <= 1
        ):
            self.logger.info(
                "Retriever fallback decision reason=strict_low_query_coverage top_score=%.4f semantic_score=%.4f overlap_count=%s query_coverage=%.4f source=%s location=%s",
                top_chunk.final_score,
                top_chunk.semantic_score,
                top_chunk.overlap_count,
                query_coverage,
                top_chunk.source_name,
                top_chunk.location_label,
            )
            return "strict_low_query_coverage"
        if not self.config.strict_grounded_mode and self._high_confidence_override(top_chunk):
            self.logger.info(
                "Retriever accepted high_confidence_override=true top_score=%.4f semantic_score=%.4f overlap_count=%s source=%s location=%s missing_query_tokens=%s",
                top_chunk.final_score,
                top_chunk.semantic_score,
                top_chunk.overlap_count,
                top_chunk.source_name,
                top_chunk.location_label,
                missing_query_tokens,
            )
            return None
        if missing_query_tokens and top_chunk.overlap_count < 2:
            if not self.config.strict_grounded_mode and self._missing_key_terms_override(
                top_chunk,
                query_token_count=len(query_tokens),
            ):
                self.logger.info(
                    'event="retrieval_override_by_semantic_score" original_question=%r normalized_question=%r missing_terms=%s semantic_score=%.4f final_score=%.4f overlap_count=%s top_source=%s top_location=%s',
                    question,
                    normalized_question,
                    missing_query_tokens,
                    top_chunk.semantic_score,
                    top_chunk.final_score,
                    top_chunk.overlap_count,
                    top_chunk.source_name,
                    top_chunk.location_label,
                )
                return None
            self.logger.info(
                'event="retrieval_rejected_missing_key_terms" original_question=%r normalized_question=%r missing_terms=%s semantic_score=%.4f final_score=%.4f overlap_count=%s top_source=%s top_location=%s',
                question,
                normalized_question,
                missing_query_tokens,
                top_chunk.semantic_score,
                top_chunk.final_score,
                top_chunk.overlap_count,
                top_chunk.source_name,
                top_chunk.location_label,
            )
            self.logger.info(
                "Retriever fallback decision reason=missing_key_terms top_score=%.4f semantic_score=%.4f overlap_count=%s source=%s location=%s missing_query_tokens=%s",
                top_chunk.final_score,
                top_chunk.semantic_score,
                top_chunk.overlap_count,
                top_chunk.source_name,
                top_chunk.location_label,
                missing_query_tokens,
            )
            return "missing_key_terms"
        if top_chunk.semantic_score < self.config.min_semantic_score:
            self.logger.info(
                "Retriever fallback decision reason=low_similarity top_score=%.4f semantic_score=%.4f overlap_count=%s source=%s location=%s threshold=%.4f",
                top_chunk.final_score,
                top_chunk.semantic_score,
                top_chunk.overlap_count,
                top_chunk.source_name,
                top_chunk.location_label,
                self.config.min_semantic_score,
            )
            return "low_similarity"
        if top_chunk.overlap_count < self.config.min_keyword_overlap:
            self.logger.info(
                "Retriever fallback decision reason=low_keyword_overlap top_score=%.4f semantic_score=%.4f overlap_count=%s source=%s location=%s threshold=%s",
                top_chunk.final_score,
                top_chunk.semantic_score,
                top_chunk.overlap_count,
                top_chunk.source_name,
                top_chunk.location_label,
                self.config.min_keyword_overlap,
            )
            return "low_keyword_overlap"
        if top_chunk.final_score < self.config.min_final_score:
            self.logger.info(
                "Retriever fallback decision reason=low_final_score top_score=%.4f semantic_score=%.4f overlap_count=%s source=%s location=%s threshold=%.4f",
                top_chunk.final_score,
                top_chunk.semantic_score,
                top_chunk.overlap_count,
                top_chunk.source_name,
                top_chunk.location_label,
                self.config.min_final_score,
            )
            return "low_final_score"
        self.logger.info(
            "Retriever accepted chunks fallback_reason=None top_score=%.4f semantic_score=%.4f overlap_count=%s source=%s location=%s",
            top_chunk.final_score,
            top_chunk.semantic_score,
            top_chunk.overlap_count,
            top_chunk.source_name,
            top_chunk.location_label,
        )
        return None

    @staticmethod
    def _query_coverage(query_tokens: list[str], chunks: list[RetrievedChunk]) -> float:
        if not query_tokens or not chunks:
            return 0.0

        query_set = set(query_tokens)
        context_tokens: set[str] = set()
        for chunk in chunks:
            context_tokens.update(tokenize_for_search(chunk.search_text()))

        overlap_count = len(query_set & context_tokens)
        return overlap_count / max(len(query_set), 1)

    @staticmethod
    def _high_confidence_override(top_chunk: RetrievedChunk) -> bool:
        return top_chunk.final_score >= 0.60 and top_chunk.overlap_count >= 2

    def _missing_key_terms_override(self, top_chunk: RetrievedChunk, *, query_token_count: int) -> bool:
        return (
            top_chunk.overlap_count >= 1
            and query_token_count >= 3
            and (
                top_chunk.semantic_score >= self.config.missing_key_terms_semantic_override
                or top_chunk.final_score >= self.config.missing_key_terms_final_override
            )
        )

    def _bm25_score(self, query_tokens: list[str], doc_tokens: list[str]) -> float:
        if not query_tokens or not doc_tokens:
            return 0.0

        score = 0.0
        doc_counter = Counter(doc_tokens)
        doc_length = len(doc_tokens)
        corpus_size = max(len(self.corpus), 1)
        avg_doc_len = self.avg_doc_len or 1.0
        k1 = 1.5
        b = 0.75

        for token in query_tokens:
            term_frequency = doc_counter.get(token, 0)
            if term_frequency == 0:
                continue

            document_frequency = self.doc_freq.get(token, 0)
            idf = math.log(1 + (corpus_size - document_frequency + 0.5) / (document_frequency + 0.5))
            numerator = term_frequency * (k1 + 1)
            denominator = term_frequency + k1 * (1 - b + b * doc_length / avg_doc_len)
            score += idf * (numerator / denominator)

        return score
