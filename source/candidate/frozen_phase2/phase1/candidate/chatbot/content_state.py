"""Atomic publication and source invalidation for incremental learning refreshes."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import time
from uuid import uuid4

GENERATION_PATTERN = re.compile(r"^[a-f0-9]{24}$")


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + f".{os.getpid()}.{uuid4().hex}.pending")
    try:
        pending.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        for attempt in range(7):
            try:
                os.replace(pending, path)
                break
            except PermissionError:
                if os.name!='nt' or attempt==6:raise
                # Antivirus/indexing readers can briefly hold a Windows handle.
                time.sleep(.02*(2**attempt))
    finally:
        try:pending.unlink(missing_ok=True)
        except OSError:pass


def generation_directory(root, generation):
    if not isinstance(generation, str) or not GENERATION_PATTERN.fullmatch(generation):
        raise ValueError("Invalid content generation identifier")
    base = Path(root).resolve() / "data/chatbot_content/generations"
    target = (base / generation).resolve()
    target.relative_to(base.resolve())
    return target


def source_changes(previous, current_files, vocabulary_digest):
    old = {row["path"]: row for row in previous.get("files", [])}
    current = {value.path: value for value in current_files}
    deleted = sorted(set(old) - set(current))
    changed = sorted(path for path, value in current.items() if path not in old or old[path].get("size") != value.size or old[path].get("mtime_ns") != value.mtime_ns)
    return {"deleted": deleted, "changed": changed, "vocabulary_changed": previous.get("vocabulary_hash") != vocabulary_digest}


def publish_generation(root, generation, manifest, validate):
    target = generation_directory(root, generation)
    if not manifest.get("complete") or not manifest.get("validated"):
        raise ValueError("Incomplete or unvalidated content generation")
    if not target.is_dir(): raise ValueError("Generation directory does not exist")
    validate(target, manifest)
    atomic_json(Path(root) / "data/chatbot_content/active.json", {"generation": generation, "published_at": time.time(), "signature": manifest["signature"]})


def read_active_generation(root):
    pointer = Path(root) / "data/chatbot_content/active.json"
    if not pointer.exists(): return None
    value = json.loads(pointer.read_text(encoding="utf-8"))
    target = generation_directory(root, value["generation"])
    manifest = json.loads((target / "content_manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("complete") or not manifest.get("validated") or manifest.get("signature") != value.get("signature"):
        raise ValueError("Active content manifest failed validation")
    return value["generation"], target, manifest


class StaleSourceFilter:
    """Remove changed/deleted sources before they can answer from an older index."""
    def __init__(self, root, generation=None):
        self.path = Path(root) / "data/chatbot_content/stale_sources.json"
        self.blocked = set()
        self.vocabulary_stale = False
        self._stamp = None
        self.generation = generation
        self._snapshot = (frozenset(), False)

    def refresh(self):
        if not self.path.exists(): return
        stamp = self.path.stat().st_mtime_ns
        if stamp == self._stamp: return
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if self.generation is not None and 'blocked_generations' in value:
            entry=value['blocked_generations'].get(self.generation,{})
            self._snapshot=(frozenset(entry.get('paths',[])),bool(entry.get('vocabulary_stale')))
            self._stamp=stamp
            return
        already_current = self.generation is not None and self.generation == value.get('published_generation')
        self.blocked = set() if already_current else set(value.get("paths", []))
        self.vocabulary_stale = False if already_current else bool(value.get("vocabulary_stale"))
        self._snapshot = (frozenset(self.blocked), self.vocabulary_stale)
        self._stamp = stamp

    def allows(self, metadata):
        path = str(metadata.get("source_path", "")).replace("\\", "/")
        blocked, vocabulary_stale = self._snapshot
        return path not in blocked and not (vocabulary_stale and path.startswith("BusinessVocabulary/"))
