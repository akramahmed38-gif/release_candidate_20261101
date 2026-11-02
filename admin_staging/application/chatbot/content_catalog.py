"""Allowlisted learning sources; never read account or authentication tables."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3

LIBRARIES = {"KnowledgeBase": "curated_knowledge", "material": "materials", "daily_brief": "script_book"}
DOCUMENT_TYPES = {".pdf", ".pptx", ".docx", ".xlsx", ".png", ".jpg", ".jpeg", ".md", ".txt", ".srt", ".vtt"}
MEDIA_TYPES = {".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm", ".mp3", ".wav", ".m4a"}
IGNORED_TYPES = {".db", ".db-shm", ".db-wal", ".tmp", ".bak", ".ini"}


@dataclass(frozen=True)
class ContentFile:
    path: str
    library: str
    size: int
    mtime_ns: int
    supported: bool


def discover_content(root: Path):
    files, ignored = [], 0
    root = root.resolve()
    for directory, library in LIBRARIES.items():
        base = root / directory
        if not base.is_dir(): continue
        for current, dirs, names in os.walk(base, followlinks=False):
            dirs[:] = [name for name in dirs if name not in {"__pycache__", ".git"} and not (Path(current) / name).is_symlink()]
            for name in sorted(names):
                path = Path(current) / name
                if path.is_symlink() or name.startswith("~$"): continue
                try: path.resolve().relative_to(base.resolve())
                except ValueError: continue
                if path.suffix.lower() in IGNORED_TYPES or name.lower() in {"thumbs.db", "desktop.ini"}:
                    ignored += 1
                    continue
                info = path.stat()
                files.append(ContentFile(path.relative_to(root).as_posix(), library, info.st_size, info.st_mtime_ns, path.suffix.lower() in DOCUMENT_TYPES | MEDIA_TYPES))
    return sorted(files, key=lambda value: value.path), ignored


def content_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()


def read_vocabulary(database):
    path = Path(database).resolve()
    uri = ("file://" + path.as_posix() if str(path).startswith("\\\\") else path.as_uri()) + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=3)) as connection:
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute("""SELECT i.vocabulary_id, i.english_text, i.arabic_text,
            i.speech_text, c.name, c.arabic_name FROM vocabulary_items i
            JOIN vocabulary_categories c ON c.category_id=i.category_id
            WHERE i.is_active=1 AND c.is_active=1 ORDER BY i.vocabulary_id""").fetchall()
    return [{"id": row[0], "english": row[1], "arabic": row[2], "speech": row[3] or "", "category": row[4], "category_arabic": row[5] or ""} for row in rows]


def vocabulary_hash(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def catalog_signature(files, vocabulary_digest):
    return hashlib.sha256(json.dumps({"files": [asdict(value) for value in files], "vocabulary": vocabulary_digest}, sort_keys=True).encode()).hexdigest()
