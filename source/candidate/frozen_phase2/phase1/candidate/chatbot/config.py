from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from .content_state import read_active_generation

PRIMARY_KNOWLEDGE_PATH = "KnowledgeBase"
LEGACY_MATERIAL_PATH = "material"
ENABLE_LATENCY_PROFILING = True
ENABLE_OCR_DURING_CHAT = False
ENABLE_LLM_QUERY_UNDERSTANDING = False
LLM_QUERY_UNDERSTANDING_TIMEOUT_SEC = 5
ENABLE_LLM_FOLLOW_UP_RESOLUTION = True
LLM_FOLLOW_UP_RESOLUTION_TIMEOUT_SEC = 3


@dataclass(frozen=True)
class AppConfig:
    project_path: Path
    knowledge_base_path: Path
    legacy_material_path: Path
    source_path: Path
    data_path: Path
    chroma_path: Path
    manifest_path: Path
    logs_path: Path
    log_file: Path
    collection_name: str
    index_version: str
    ollama_url: str
    llm_model: str
    fast_llm_model: str
    follow_up_llm_model: str
    enable_fast_mode: bool
    embedding_model: str
    fallback_text: str
    chunk_size: int
    chunk_overlap: int
    semantic_candidates: int
    keyword_candidates: int
    top_k: int
    min_semantic_score: float
    min_final_score: float
    min_keyword_overlap: int
    missing_key_terms_semantic_override: float
    missing_key_terms_final_override: float
    prompt_context_min_relative_score: float
    prompt_context_keep_adjacent_pages: bool
    enable_direct_qa_answer: bool
    direct_qa_min_score: float
    strict_grounded_mode: bool
    clarification_min_score: float
    clarification_score_margin: float
    clarification_min_query_coverage: float
    clarification_min_overlap: int
    clarification_max_options: int
    clarification_max_specificity_gap: float
    min_pdf_text_chars: int
    easyocr_langs: tuple[str, ...]
    render_scale: float
    temperature: float
    enable_latency_profiling: bool
    enable_ocr_during_chat: bool
    enable_llm_query_understanding: bool
    llm_query_understanding_timeout_sec: float
    enable_llm_follow_up_resolution: bool
    llm_follow_up_resolution_timeout_sec: float
    conversation_history_max_turns: int
    conversation_history_ttl_minutes: int
    generation_max_tokens: int = 192
    prefer_source_answers: bool = True
    generation_context_tokens: int = 4096
    generation_threads: int = 2
    generation_timeout_seconds: float = 30
    conversation_followup_max_topic_tokens: int = 8
    content_sync_enabled: bool = False
    content_generation: str | None = None


def load_config(base_path: Path | None = None) -> AppConfig:
    project_path = Path(base_path or Path(__file__).resolve().parents[1]).resolve()
    knowledge_base_path = project_path / PRIMARY_KNOWLEDGE_PATH
    legacy_material_path = project_path / LEGACY_MATERIAL_PATH
    data_path = project_path / "data"
    logs_path = project_path / "logs"

    # Optional pilot settings apply only to the chatbot sidecar, not the portal.
    settings_path = project_path / "chatbot_runtime.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8-sig")) if settings_path.exists() else {}
    generation_model = str(os.getenv("TRAINING_CHATBOT_MODEL") or settings.get("model") or "qwen2.5:7b")
    content_generation = None
    shared_content_index = False
    content_sync_enabled = bool(settings.get("enable_content_sync", False))
    if content_sync_enabled:
        active_content = read_active_generation(project_path)
        if active_content:
            content_generation, data_path, content_manifest = active_content
            shared_content_index = content_manifest.get('index_storage') == 'shared_collections'

    return AppConfig(
        project_path=project_path,
        knowledge_base_path=knowledge_base_path,
        legacy_material_path=legacy_material_path,
        source_path=knowledge_base_path,
        data_path=data_path,
        chroma_path=(project_path / 'data/chatbot_content/chroma') if shared_content_index else data_path / ("chroma" if content_generation else "chroma_hr_training"),
        manifest_path=data_path / "index_manifest.json",
        logs_path=logs_path,
        log_file=logs_path / "hr_training_chatbot.log",
        collection_name="hr_training_materials",
        index_version="qa_intent_index_v2",
        ollama_url="http://127.0.0.1:11434",
        llm_model=generation_model,
        fast_llm_model=generation_model,
        follow_up_llm_model=generation_model,
        enable_fast_mode=True,
        embedding_model="bge-m3",
        fallback_text="عذراً، هذه المعلومة غير متوفرة في الملفات المتاحة.",
        chunk_size=900,
        chunk_overlap=150,
        semantic_candidates=12,
        keyword_candidates=64,
        top_k=5,
        min_semantic_score=0.34,
        min_final_score=0.24,
        min_keyword_overlap=1,
        missing_key_terms_semantic_override=0.50,
        missing_key_terms_final_override=0.45,
        prompt_context_min_relative_score=0.75,
        prompt_context_keep_adjacent_pages=True,
        enable_direct_qa_answer=True,
        direct_qa_min_score=0.62,
        strict_grounded_mode=True,
        clarification_min_score=0.58,
        clarification_score_margin=0.05,
        clarification_min_query_coverage=0.35,
        clarification_min_overlap=1,
        clarification_max_options=3,
        clarification_max_specificity_gap=0.9,
        min_pdf_text_chars=20,
        easyocr_langs=("ar", "en"),
        render_scale=1.0,
        temperature=0.1,
        enable_latency_profiling=ENABLE_LATENCY_PROFILING,
        enable_ocr_during_chat=ENABLE_OCR_DURING_CHAT,
        enable_llm_query_understanding=ENABLE_LLM_QUERY_UNDERSTANDING,
        llm_query_understanding_timeout_sec=LLM_QUERY_UNDERSTANDING_TIMEOUT_SEC,
        enable_llm_follow_up_resolution=bool(settings.get("llm_follow_up", False)),
        llm_follow_up_resolution_timeout_sec=LLM_FOLLOW_UP_RESOLUTION_TIMEOUT_SEC,
        conversation_history_max_turns=12,
        conversation_history_ttl_minutes=120,
        conversation_followup_max_topic_tokens=8,
        generation_max_tokens=max(64, int(settings.get("max_output_tokens", 192))),
        prefer_source_answers=bool(settings.get("prefer_source_answers", True)),
        generation_context_tokens=max(2048, int(settings.get("context_tokens", 4096))),
        generation_threads=max(1, int(settings.get("threads", 2))),
        generation_timeout_seconds=max(5.0, float(settings.get("timeout_seconds", 30))),
        content_sync_enabled=content_sync_enabled,
        content_generation=content_generation,
    )
