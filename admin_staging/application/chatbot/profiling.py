from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Iterator
from uuid import uuid4

_ACTIVE_PROFILER: ContextVar["LatencyProfiler | None"] = ContextVar(
    "hr_training_chatbot_latency_profiler",
    default=None,
)


def create_request_id(prefix: str = "chatreq") -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


@dataclass
class LatencyProfiler:
    request_id: str
    enabled: bool = True
    started_at: str = field(default_factory=_now_iso)
    timings_ms: dict[str, float] = field(default_factory=dict)
    flags: dict[str, Any] = field(
        default_factory=lambda: {
            "ocr_called": False,
            "document_extraction_called": False,
            "ocr_references": [],
            "document_sources": [],
        }
    )
    counters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    scratchpad: dict[str, Any] = field(default_factory=dict, repr=False)

    @contextmanager
    def span(self, name: str, *, accumulate: bool = False) -> Iterator[None]:
        started = perf_counter()
        try:
            yield
        finally:
            elapsed_ms = round((perf_counter() - started) * 1000, 2)
            self.record_timing(name, elapsed_ms, accumulate=accumulate)

    def record_timing(self, name: str, value_ms: float | int | None, *, accumulate: bool = False) -> None:
        if not self.enabled or value_ms is None:
            return
        numeric_value = round(float(value_ms), 2)
        if accumulate:
            numeric_value = round(float(self.timings_ms.get(name, 0.0)) + numeric_value, 2)
        self.timings_ms[name] = numeric_value

    def set_counter(self, name: str, value: Any) -> None:
        if not self.enabled:
            return
        self.counters[name] = value

    def increment_counter(self, name: str, amount: int | float = 1) -> None:
        if not self.enabled:
            return
        current = self.counters.get(name, 0)
        self.counters[name] = current + amount

    def set_metadata(self, name: str, value: Any) -> None:
        if not self.enabled:
            return
        self.metadata[name] = value

    def add_note(self, note: str) -> None:
        if not self.enabled or not note:
            return
        self.notes.append(note)

    def mark_ocr_called(self, reference: str | None = None) -> None:
        if not self.enabled:
            return
        self.flags["ocr_called"] = True
        if reference:
            references = self.flags.setdefault("ocr_references", [])
            if reference not in references:
                references.append(reference)

    def mark_document_extraction_called(self, source_path: str | None = None) -> None:
        if not self.enabled:
            return
        self.flags["document_extraction_called"] = True
        if source_path:
            sources = self.flags.setdefault("document_sources", [])
            if source_path not in sources:
                sources.append(source_path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "started_at": self.started_at,
            "timings_ms": dict(self.timings_ms),
            "flags": dict(self.flags),
            "counters": dict(self.counters),
            "metadata": dict(self.metadata),
            "notes": list(self.notes),
        }


def get_latency_profiler() -> LatencyProfiler | None:
    return _ACTIVE_PROFILER.get()


@contextmanager
def activate_latency_profiler(profiler: LatencyProfiler | None) -> Iterator[LatencyProfiler | None]:
    token: Token[LatencyProfiler | None] | None = None
    if profiler is not None:
        token = _ACTIVE_PROFILER.set(profiler)
    try:
        yield profiler
    finally:
        if token is not None:
            _ACTIVE_PROFILER.reset(token)


def maybe_new_latency_profiler(
    *,
    enabled: bool,
    request_id: str | None = None,
) -> LatencyProfiler | None:
    if not enabled:
        return None
    return LatencyProfiler(request_id=request_id or create_request_id())


def record_timing(name: str, value_ms: float | int | None, *, accumulate: bool = False) -> None:
    profiler = get_latency_profiler()
    if profiler is not None:
        profiler.record_timing(name, value_ms, accumulate=accumulate)


def set_counter(name: str, value: Any) -> None:
    profiler = get_latency_profiler()
    if profiler is not None:
        profiler.set_counter(name, value)


def set_metadata(name: str, value: Any) -> None:
    profiler = get_latency_profiler()
    if profiler is not None:
        profiler.set_metadata(name, value)


def add_note(note: str) -> None:
    profiler = get_latency_profiler()
    if profiler is not None:
        profiler.add_note(note)


def mark_ocr_called(reference: str | None = None) -> None:
    profiler = get_latency_profiler()
    if profiler is not None:
        profiler.mark_ocr_called(reference=reference)


def mark_document_extraction_called(source_path: str | None = None) -> None:
    profiler = get_latency_profiler()
    if profiler is not None:
        profiler.mark_document_extraction_called(source_path=source_path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
