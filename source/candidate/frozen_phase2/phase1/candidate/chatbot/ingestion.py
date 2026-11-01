from __future__ import annotations

import json
import logging
import re
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable
from xml.etree import ElementTree as ET

import pdfplumber
import pypdfium2 as pdfium
from PIL import Image

from .config import AppConfig
from .normalization import contains_arabic, collapse_whitespace, normalize_text, repair_pdf_arabic_text
from .ocr import OCRBackend
from .profiling import mark_document_extraction_called

SUPPORTED_EXTENSIONS = {".pdf", ".pptx", ".docx", ".png", ".jpg", ".jpeg", ".md", ".txt"}
ARABIC_TOKEN_RE = re.compile(r"[\u0600-\u06FF]+")
KNOWN_CORRUPTED_ARABIC_PDF_PHRASES = (
    "قباس ريزو",
    "بزح سيئر",
    "دعاقتم قيرف",
    "بعش سلجم وضع",
    "خويش سلجم وضع",
    "ظفاحم",
    "قيرف",
    "لوا قيرف",
)
KNOWN_CORRUPTED_ARABIC_PDF_TOKENS = frozenset(
    {
        "قباس",
        "ريزو",
        "بزح",
        "سيئر",
        "دعاقتم",
        "بعش",
        "خويش",
        "سلجم",
        "ريفس",
        "ظفاحم",
        "قيرف",
        "لوا",
    }
)
MIN_SUSPICIOUS_ARABIC_PDF_TOKEN_CLUSTER = 3
MIN_SUSPICIOUS_ARABIC_PDF_TOKEN_RATIO = 0.12


@dataclass
class SourceFragment:
    source_path: str
    source_name: str
    source_type: str
    location_type: str
    location_value: str
    location_label: str
    content_type: str
    text: str
    prompt_text: str | None = None
    extraction_method: str | None = None
    extra_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OCRUsageReport:
    total_files: int = 0
    total_pages: int = 0
    pages_with_direct_text_extraction: int = 0
    pages_requiring_ocr: int = 0
    easyocr_success_pages: int = 0
    failed_ocr_pages: int = 0
    files_with_ocr_errors: list[str] = field(default_factory=list)
    page_errors: list[dict[str, str]] = field(default_factory=list)


@dataclass
class KnowledgeBaseQARecord:
    qa_id: str
    category: str
    question: str
    alternate_questions: list[str]
    keywords: list[str]
    answer: str


class MaterialIngestor:
    def __init__(self, config: AppConfig, ocr_backend: OCRBackend, logger: logging.Logger) -> None:
        self.config = config
        self.ocr_backend = ocr_backend
        self.logger = logger
        self.last_report = OCRUsageReport()

    def scan_source_files(self) -> list[Path]:
        if not self.config.source_path.exists():
            return []
        files = [
            path
            for path in self.config.source_path.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        return sorted(files)

    def scan_material_files(self) -> list[Path]:
        return self.scan_source_files()

    def build_manifest(self, files: Iterable[Path]) -> list[dict[str, str | int]]:
        manifest: list[dict[str, str | int]] = []
        for path in files:
            stat = path.stat()
            manifest.append(
                {
                    "path": self._display_source_path(path),
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
        return manifest

    def estimate_workload(self, files: Iterable[Path]) -> dict[str, int]:
        total_pages = 0
        total_files = 0

        for path in files:
            total_files += 1
            suffix = path.suffix.lower()
            try:
                if suffix == ".pdf":
                    with pdfplumber.open(path) as pdf:
                        total_pages += len(pdf.pages)
                elif suffix == ".pptx":
                    with zipfile.ZipFile(path) as archive:
                        slide_count = sum(
                            1
                            for name in archive.namelist()
                            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
                        )
                        image_count = len(self._iter_all_pptx_images(archive))
                        total_pages += slide_count + image_count
                elif suffix == ".docx":
                    with zipfile.ZipFile(path) as archive:
                        image_count = len(
                            [name for name in archive.namelist() if name.startswith("word/media/")]
                        )
                        total_pages += 1 if self._is_knowledge_base_file(path) else 1 + image_count
                elif suffix in {".md", ".txt"}:
                    total_pages += 1
                elif suffix in {".png", ".jpg", ".jpeg"}:
                    total_pages += 1
            except Exception as exc:
                self.logger.warning("Could not estimate workload for %s: %s", path.name, exc)
                total_pages += 1

        return {"total_files": total_files, "total_pages": total_pages}

    def build_chunks(
        self,
        files: list[Path],
        progress_callback: Callable[..., None] | None = None,
        total_pages: int | None = None,
    ) -> list[dict]:
        self.last_report = OCRUsageReport(
            total_files=len(files),
            total_pages=max(total_pages or 0, 0),
        )
        progress_state = {
            "processed_pages": 0,
            "total_pages": max(total_pages or 0, 0),
        }
        chunks: list[dict] = []
        for path in files:
            self.logger.info("Extracting content from %s", path.name)
            fragments = self.extract_fragments(
                path,
                progress_callback=progress_callback,
                progress_state=progress_state,
            )
            for fragment in fragments:
                for chunk_index, chunk_text in enumerate(self._split_text(fragment.text), start=1):
                    chunk_id = self._build_chunk_id(fragment, chunk_index)
                    chunks.append(
                        {
                            "id": chunk_id,
                            "text": chunk_text,
                            "metadata": {
                                "source_path": fragment.source_path,
                                "source_name": fragment.source_name,
                                "source_type": fragment.source_type,
                                "location_type": fragment.location_type,
                                "location_value": fragment.location_value,
                                "location_label": fragment.location_label,
                                "content_type": fragment.content_type,
                                "chunk_index": chunk_index,
                            },
                        }
                    )
                    if fragment.prompt_text:
                        chunks[-1]["metadata"]["prompt_text"] = fragment.prompt_text
                    if fragment.extraction_method:
                        chunks[-1]["metadata"]["extraction_method"] = fragment.extraction_method
                    if fragment.extra_metadata:
                        chunks[-1]["metadata"].update(fragment.extra_metadata)
        self.logger.info("Built %s chunks from %s files.", len(chunks), len(files))
        return chunks

    def extract_fragments(
        self,
        path: Path,
        progress_callback: Callable[..., None] | None = None,
        progress_state: dict[str, int] | None = None,
    ) -> list[SourceFragment]:
        mark_document_extraction_called(self._display_source_path(path))
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self._extract_pdf_fragments(path, progress_callback, progress_state)
        if suffix == ".pptx":
            return self._extract_pptx_fragments(path, progress_callback, progress_state)
        if suffix == ".docx":
            return self._extract_docx_fragments(path, progress_callback, progress_state)
        if suffix in {".md", ".txt"}:
            return self._extract_knowledge_base_text_fragments(path, progress_callback, progress_state)
        if suffix in {".png", ".jpg", ".jpeg"}:
            return self._extract_image_fragments(path, progress_callback, progress_state)
        return []

    def _notify_progress(
        self,
        progress_callback: Callable[..., None] | None,
        progress_state: dict[str, int] | None,
        *,
        current_file: str,
        current_page: str,
        current_location_label: str,
        finished: bool,
    ) -> None:
        if progress_state is None:
            return

        if finished:
            progress_state["processed_pages"] = progress_state.get("processed_pages", 0) + 1

        if progress_callback is None:
            return

        progress_callback(
            current_file=current_file,
            current_page=current_page,
            current_location_label=current_location_label,
            processed_pages=progress_state.get("processed_pages", 0),
            total_pages=progress_state.get("total_pages", 0),
        )

    def _record_ocr_outcome(self, path: Path, location_label: str) -> None:
        self.last_report.pages_requiring_ocr += 1
        last_result = getattr(self.ocr_backend, "last_result", {}) or {}
        backend = last_result.get("backend")
        if backend == "EasyOCR" and last_result.get("success"):
            self.last_report.easyocr_success_pages += 1
            if last_result.get("easyocr_error"):
                self._add_ocr_error(
                    path=path,
                    location_label=location_label,
                    backend="EasyOCR",
                    error=str(last_result["easyocr_error"]),
                )
        else:
            self.last_report.failed_ocr_pages += 1
            error_message = str(
                last_result.get("easyocr_error")
                or "OCR returned no text."
            )
            self._add_ocr_error(
                path=path,
                location_label=location_label,
                backend=str(backend or "None"),
                error=error_message,
            )

    def _add_ocr_error(self, path: Path, location_label: str, backend: str, error: str) -> None:
        source_name = path.name
        if source_name not in self.last_report.files_with_ocr_errors:
            self.last_report.files_with_ocr_errors.append(source_name)
        self.last_report.page_errors.append(
            {
                "source_name": source_name,
                "source_path": self._display_source_path(path),
                "location_label": location_label,
                "backend": backend,
                "error": error,
            }
        )

    def _extract_pdf_fragments(
        self,
        path: Path,
        progress_callback: Callable[..., None] | None = None,
        progress_state: dict[str, int] | None = None,
    ) -> list[SourceFragment]:
        fragments: list[SourceFragment] = []
        pdfium_doc = pdfium.PdfDocument(str(path))
        with pdfplumber.open(path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                location_label = f"صفحة {page_number}"
                self._notify_progress(
                    progress_callback,
                    progress_state,
                    current_file=path.name,
                    current_page=str(page_number),
                    current_location_label=location_label,
                    finished=False,
                )
                extracted_text = repair_pdf_arabic_text(page.extract_text() or "")
                extracted_text = collapse_whitespace(extracted_text.replace("\x00", " "))
                content_type = "pdf_text"
                extraction_method = "pdfplumber_text"
                is_corrupted, bad_tokens = self.is_corrupted_arabic_pdf_text(extracted_text)

                if is_corrupted:
                    self.logger.warning(
                        'event="pdf_text_quality_gate_failed" source_name=%r page=%s reason=%s sample_bad_tokens=%s pdf_text_chars=%s',
                        path.name,
                        page_number,
                        "known_corrupted_tokens" if bad_tokens else "suspicious_arabic_pdf_text",
                        bad_tokens[:5],
                        len(extracted_text),
                    )
                    extracted_text, content_type, extraction_method = self._replace_pdf_text_with_ocr(
                        pdfium_doc=pdfium_doc,
                        page_number=page_number,
                        path=path,
                        location_label=location_label,
                        original_pdf_text_chars=len(extracted_text),
                    )
                elif len(extracted_text) < self.config.min_pdf_text_chars:
                    original_pdf_text_chars = len(extracted_text)
                    ocr_text = self._ocr_pdf_page(pdfium_doc, page_number, path)
                    self._record_ocr_outcome(path, location_label)
                    if len(ocr_text) > len(extracted_text):
                        extracted_text = ocr_text
                        content_type = "ocr_text"
                        extraction_method = "easyocr_page_render"
                        self.logger.info(
                            'event="pdf_text_replaced_by_ocr" source_name=%r page=%s ocr_chars=%s original_pdf_text_chars=%s',
                            path.name,
                            page_number,
                            len(ocr_text),
                            original_pdf_text_chars,
                        )
                    elif extracted_text:
                        self.last_report.pages_with_direct_text_extraction += 1
                        self.logger.info(
                            'event="pdf_text_quality_gate_passed" source_name=%r page=%s pdf_text_chars=%s',
                            path.name,
                            page_number,
                            len(extracted_text),
                        )
                elif extracted_text:
                    self.last_report.pages_with_direct_text_extraction += 1
                    self.logger.info(
                        'event="pdf_text_quality_gate_passed" source_name=%r page=%s pdf_text_chars=%s',
                        path.name,
                        page_number,
                        len(extracted_text),
                    )

                self._notify_progress(
                    progress_callback,
                    progress_state,
                    current_file=path.name,
                    current_page=str(page_number),
                    current_location_label=location_label,
                    finished=True,
                )

                if not extracted_text:
                    continue

                fragments.append(
                    SourceFragment(
                        source_path=self._display_source_path(path),
                        source_name=path.name,
                        source_type="pdf",
                        location_type="page",
                        location_value=str(page_number),
                        location_label=location_label,
                        content_type=content_type,
                        text=extracted_text,
                        extraction_method=extraction_method,
                    )
                )
        pdfium_doc.close()
        return fragments

    def is_corrupted_arabic_pdf_text(self, text: str) -> tuple[bool, list[str]]:
        clean_text = collapse_whitespace((text or "").replace("\x00", " "))
        if not clean_text or not contains_arabic(clean_text):
            return False, []

        normalized_text = normalize_text(clean_text, for_search=True)
        matched_phrases = [
            phrase
            for phrase in KNOWN_CORRUPTED_ARABIC_PDF_PHRASES
            if normalize_text(phrase, for_search=True) in normalized_text
        ]
        if matched_phrases:
            return True, matched_phrases[:5]

        arabic_tokens = ARABIC_TOKEN_RE.findall(normalized_text)
        if not arabic_tokens:
            return False, []

        suspicious_tokens = [token for token in arabic_tokens if token in KNOWN_CORRUPTED_ARABIC_PDF_TOKENS]
        suspicious_ratio = len(suspicious_tokens) / max(len(arabic_tokens), 1)
        unique_suspicious_tokens = list(dict.fromkeys(suspicious_tokens))

        if (
            len(suspicious_tokens) >= MIN_SUSPICIOUS_ARABIC_PDF_TOKEN_CLUSTER
            and len(unique_suspicious_tokens) >= 2
            and suspicious_ratio >= MIN_SUSPICIOUS_ARABIC_PDF_TOKEN_RATIO
        ):
            return True, unique_suspicious_tokens[:5]

        return False, []

    def _replace_pdf_text_with_ocr(
        self,
        pdfium_doc: pdfium.PdfDocument,
        page_number: int,
        path: Path,
        location_label: str,
        original_pdf_text_chars: int,
    ) -> tuple[str, str, str]:
        ocr_text = self._ocr_pdf_page(pdfium_doc, page_number, path)
        self._record_ocr_outcome(path, location_label)
        self.logger.info(
            'event="pdf_text_replaced_by_ocr" source_name=%r page=%s ocr_chars=%s original_pdf_text_chars=%s',
            path.name,
            page_number,
            len(ocr_text),
            original_pdf_text_chars,
        )
        return ocr_text, "ocr_text", "easyocr_page_render"

    def _extract_pptx_fragments(
        self,
        path: Path,
        progress_callback: Callable[..., None] | None = None,
        progress_state: dict[str, int] | None = None,
    ) -> list[SourceFragment]:
        fragments: list[SourceFragment] = []
        with zipfile.ZipFile(path) as archive:
            slide_names = sorted(
                (
                    name
                    for name in archive.namelist()
                    if name.startswith("ppt/slides/slide") and name.endswith(".xml")
                ),
                key=self._extract_numeric_suffix,
            )

            for slide_name in slide_names:
                slide_number = self._extract_numeric_suffix(slide_name)
                slide_label = f"شريحة {slide_number}"
                self._notify_progress(
                    progress_callback,
                    progress_state,
                    current_file=path.name,
                    current_page=str(slide_number),
                    current_location_label=slide_label,
                    finished=False,
                )
                slide_text = self._extract_xml_text(archive.read(slide_name))
                if slide_text:
                    self.last_report.pages_with_direct_text_extraction += 1
                    fragments.append(
                        SourceFragment(
                            source_path=self._display_source_path(path),
                            source_name=path.name,
                            source_type="pptx",
                            location_type="slide",
                            location_value=str(slide_number),
                            location_label=slide_label,
                            content_type="slide_text",
                            text=slide_text,
                        )
                    )

                for image_index, image_bytes in enumerate(
                    self._iter_pptx_slide_images(archive, slide_number),
                    start=1,
                ):
                    image_label = f"{slide_label} - صورة {image_index}"
                    self._notify_progress(
                        progress_callback,
                        progress_state,
                        current_file=path.name,
                        current_page=f"{slide_number}.image_{image_index}",
                        current_location_label=image_label,
                        finished=False,
                    )
                    ocr_text = self.ocr_backend.ocr_image(
                        image_bytes,
                        reference=f"{path.name} slide {slide_number} image {image_index}",
                    )
                    self._record_ocr_outcome(path, image_label)
                    self._notify_progress(
                        progress_callback,
                        progress_state,
                        current_file=path.name,
                        current_page=f"{slide_number}.image_{image_index}",
                        current_location_label=image_label,
                        finished=True,
                    )
                    if not ocr_text:
                        continue
                    fragments.append(
                        SourceFragment(
                            source_path=self._display_source_path(path),
                            source_name=path.name,
                            source_type="pptx",
                            location_type="slide",
                            location_value=str(slide_number),
                            location_label=slide_label,
                            content_type=f"slide_image_{image_index}",
                            text=ocr_text,
                        )
                    )
                self._notify_progress(
                    progress_callback,
                    progress_state,
                    current_file=path.name,
                    current_page=str(slide_number),
                    current_location_label=slide_label,
                    finished=True,
                )
        return fragments

    def _extract_docx_fragments(
        self,
        path: Path,
        progress_callback: Callable[..., None] | None = None,
        progress_state: dict[str, int] | None = None,
    ) -> list[SourceFragment]:
        if self._is_knowledge_base_file(path):
            return self._extract_knowledge_base_docx_fragments(path, progress_callback, progress_state)

        fragments: list[SourceFragment] = []
        with zipfile.ZipFile(path) as archive:
            self._notify_progress(
                progress_callback,
                progress_state,
                current_file=path.name,
                current_page="main",
                current_location_label="القسم الرئيسي",
                finished=False,
            )
            text_parts: list[str] = []
            for xml_name in archive.namelist():
                if xml_name in {"word/document.xml"} or (
                    xml_name.startswith("word/header") and xml_name.endswith(".xml")
                ) or (xml_name.startswith("word/footer") and xml_name.endswith(".xml")):
                    text_parts.append(self._extract_xml_text(archive.read(xml_name)))

            merged_text = collapse_whitespace("\n".join(part for part in text_parts if part))
            if merged_text:
                self.last_report.pages_with_direct_text_extraction += 1
                fragments.append(
                    SourceFragment(
                        source_path=self._display_source_path(path),
                        source_name=path.name,
                        source_type="docx",
                        location_type="section",
                        location_value="main",
                        location_label="القسم الرئيسي",
                        content_type="doc_text",
                        text=merged_text,
                    )
                )
            self._notify_progress(
                progress_callback,
                progress_state,
                current_file=path.name,
                current_page="main",
                current_location_label="القسم الرئيسي",
                finished=True,
            )

            image_names = sorted(name for name in archive.namelist() if name.startswith("word/media/"))
            for image_index, image_name in enumerate(image_names, start=1):
                image_label = f"صورة مضمّنة {image_index}"
                self._notify_progress(
                    progress_callback,
                    progress_state,
                    current_file=path.name,
                    current_page=f"image_{image_index}",
                    current_location_label=image_label,
                    finished=False,
                )
                ocr_text = self.ocr_backend.ocr_image(
                    archive.read(image_name),
                    reference=f"{path.name} image {image_index}",
                )
                self._record_ocr_outcome(path, image_label)
                self._notify_progress(
                    progress_callback,
                    progress_state,
                    current_file=path.name,
                    current_page=f"image_{image_index}",
                    current_location_label=image_label,
                    finished=True,
                )
                if not ocr_text:
                    continue
                fragments.append(
                    SourceFragment(
                        source_path=self._display_source_path(path),
                        source_name=path.name,
                        source_type="docx",
                        location_type="section",
                        location_value=f"image_{image_index}",
                        location_label=image_label,
                        content_type=f"doc_image_{image_index}",
                        text=ocr_text,
                    )
                )
        return fragments

    def _extract_knowledge_base_docx_fragments(
        self,
        path: Path,
        progress_callback: Callable[..., None] | None = None,
        progress_state: dict[str, int] | None = None,
    ) -> list[SourceFragment]:
        with zipfile.ZipFile(path) as archive:
            self._notify_progress(
                progress_callback,
                progress_state,
                current_file=path.name,
                current_page="main",
                current_location_label="Knowledge Base",
                finished=False,
            )

            text_parts: list[str] = []
            for xml_name in archive.namelist():
                if xml_name == "word/document.xml" or (
                    xml_name.startswith("word/header") and xml_name.endswith(".xml")
                ) or (xml_name.startswith("word/footer") and xml_name.endswith(".xml")):
                    text_parts.append(self._extract_xml_text(archive.read(xml_name)))

            merged_text = collapse_whitespace("\n".join(part for part in text_parts if part))
            self._notify_progress(
                progress_callback,
                progress_state,
                current_file=path.name,
                current_page="main",
                current_location_label="Knowledge Base",
                finished=True,
            )
            if not merged_text:
                return []

            self.last_report.pages_with_direct_text_extraction += 1
            return self._extract_knowledge_base_fragments_from_text(
                path=path,
                raw_text=merged_text,
                extraction_method="docx_text",
            )

    def _extract_knowledge_base_text_fragments(
        self,
        path: Path,
        progress_callback: Callable[..., None] | None = None,
        progress_state: dict[str, int] | None = None,
    ) -> list[SourceFragment]:
        self._notify_progress(
            progress_callback,
            progress_state,
            current_file=path.name,
            current_page="main",
            current_location_label="Knowledge Base",
            finished=False,
        )
        raw_text = self._read_text_file(path)
        sections = self._split_knowledge_base_sections(raw_text)
        self._notify_progress(
            progress_callback,
            progress_state,
            current_file=path.name,
            current_page="main",
            current_location_label="Knowledge Base",
            finished=True,
        )
        if not sections:
            return []

        self.last_report.pages_with_direct_text_extraction += 1
        extraction_method = f"{path.suffix.lower().lstrip('.')}_text"
        return self._extract_knowledge_base_fragments_from_text(
            path=path,
            raw_text="\n\n---\n\n".join(sections),
            extraction_method=extraction_method,
        )

    def _extract_knowledge_base_fragments_from_text(
        self,
        *,
        path: Path,
        raw_text: str,
        extraction_method: str,
    ) -> list[SourceFragment]:
        sections = self._split_knowledge_base_sections(raw_text)
        fragments: list[SourceFragment] = []
        for section_index, section_text in enumerate(sections, start=1):
            qa_record = self._parse_knowledge_base_qa_record(section_text)
            if qa_record is not None:
                fragments.append(
                    SourceFragment(
                        source_path=self._display_source_path(path),
                        source_name=path.name,
                        source_type="knowledge_base",
                        location_type="section",
                        location_value=str(section_index),
                        location_label=f"Section {section_index}",
                        content_type="knowledge_base_text",
                        text=self._build_qa_search_text(qa_record),
                        prompt_text=self._build_qa_prompt_text(qa_record),
                        extraction_method=extraction_method,
                        extra_metadata={
                            "qa_id": qa_record.qa_id,
                            "category": qa_record.category,
                            "question_text": qa_record.question,
                            "answer_text": qa_record.answer,
                            "alternate_questions": json.dumps(qa_record.alternate_questions, ensure_ascii=False),
                            "keywords": json.dumps(qa_record.keywords, ensure_ascii=False),
                        },
                    )
                )
                continue
            fragments.append(
                SourceFragment(
                    source_path=self._display_source_path(path),
                    source_name=path.name,
                    source_type="knowledge_base",
                    location_type="section",
                    location_value=str(section_index),
                    location_label=f"Section {section_index}",
                    content_type="knowledge_base_text",
                    text=section_text,
                    extraction_method=extraction_method,
                )
            )
        return fragments

    def _extract_image_fragments(
        self,
        path: Path,
        progress_callback: Callable[..., None] | None = None,
        progress_state: dict[str, int] | None = None,
    ) -> list[SourceFragment]:
        self._notify_progress(
            progress_callback,
            progress_state,
            current_file=path.name,
            current_page="image",
            current_location_label="الصورة",
            finished=False,
        )
        image = Image.open(path).convert("RGB")
        text = self.ocr_backend.ocr_image(image, reference=path.name)
        self._record_ocr_outcome(path, "الصورة")
        self._notify_progress(
            progress_callback,
            progress_state,
            current_file=path.name,
            current_page="image",
            current_location_label="الصورة",
            finished=True,
        )
        if not text:
            return []
        return [
            SourceFragment(
                source_path=self._display_source_path(path),
                source_name=path.name,
                source_type="image",
                location_type="section",
                location_value="image",
                location_label="الصورة",
                content_type="image_ocr",
                text=text,
            )
        ]

    def _ocr_pdf_page(self, pdfium_doc: pdfium.PdfDocument, page_number: int, path: Path) -> str:
        page = pdfium_doc[page_number - 1]
        bitmap = page.render(scale=self.config.render_scale)
        image = bitmap.to_pil()
        return self.ocr_backend.ocr_image(image, reference=f"{path.name} page {page_number}")

    @staticmethod
    def _split_knowledge_base_sections(text: str) -> list[str]:
        normalized_text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
        raw_sections = re.split(r"(?m)^\s*-{3,}\s*$", normalized_text)
        sections = [section.strip() for section in raw_sections if section and section.strip()]
        return sections

    @staticmethod
    def _parse_knowledge_base_qa_record(section_text: str) -> KnowledgeBaseQARecord | None:
        normalized_text = (section_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized_text:
            return None

        fields: dict[str, Any] = {
            "id": "",
            "category": "",
            "question": "",
            "alternate_questions": [],
            "keywords": [],
            "answer": [],
        }
        current_field: str | None = None
        answer_started = False

        for raw_line in normalized_text.split("\n"):
            line = raw_line.rstrip()
            stripped = line.strip()

            if not stripped:
                if current_field == "answer":
                    fields["answer"].append("")
                continue

            field_match = re.match(
                r"^(id|category|question|alternate_questions|keywords|answer)\s*:\s*(.*)$",
                stripped,
                flags=re.IGNORECASE,
            )
            if field_match:
                field_name = field_match.group(1).lower()
                field_value = field_match.group(2).strip()
                current_field = field_name
                if field_name in {"id", "category", "question"}:
                    fields[field_name] = collapse_whitespace(field_value)
                    continue
                if field_name in {"alternate_questions", "keywords"}:
                    if field_value and field_value not in {"|", ">"}:
                        fields[field_name].append(collapse_whitespace(field_value.lstrip("-*•").strip()))
                    continue
                if field_name == "answer":
                    answer_started = True
                    if field_value and field_value not in {"|", ">"}:
                        fields["answer"].append(field_value)
                    continue

            if current_field in {"alternate_questions", "keywords"}:
                bullet_match = re.match(r"^[*\-•]\s*(.+)$", stripped)
                if bullet_match:
                    item_text = collapse_whitespace(bullet_match.group(1))
                    if item_text:
                        fields[current_field].append(item_text)
                    continue
                if fields[current_field]:
                    fields[current_field][-1] = collapse_whitespace(f"{fields[current_field][-1]} {stripped}")
                else:
                    fields[current_field].append(collapse_whitespace(stripped))
                continue

            if current_field == "answer":
                fields["answer"].append(line)
                continue

            return None

        answer_text = MaterialIngestor._normalize_multiline_answer(fields["answer"])
        if not (fields["id"] and fields["category"] and fields["question"] and answer_started and answer_text):
            return None

        return KnowledgeBaseQARecord(
            qa_id=str(fields["id"]),
            category=str(fields["category"]),
            question=str(fields["question"]),
            alternate_questions=[item for item in fields["alternate_questions"] if item],
            keywords=[item for item in fields["keywords"] if item],
            answer=answer_text,
        )

    @staticmethod
    def _normalize_multiline_answer(lines: list[str]) -> str:
        if not lines:
            return ""

        cleaned_lines: list[str] = []
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                if cleaned_lines and cleaned_lines[-1] != "":
                    cleaned_lines.append("")
                continue
            cleaned_lines.append(re.sub(r"[^\S\n]+", " ", line))

        return "\n".join(cleaned_lines).strip()

    @staticmethod
    def _build_qa_search_text(record: KnowledgeBaseQARecord) -> str:
        lines = [
            f"Question: {record.question}",
            f"Category: {record.category}",
        ]
        if record.alternate_questions:
            lines.append("Alternate Questions:")
            lines.extend(f"- {question}" for question in record.alternate_questions)
        if record.keywords:
            lines.append("Keywords:")
            lines.extend(f"- {keyword}" for keyword in record.keywords)
        return collapse_whitespace("\n".join(lines))

    @staticmethod
    def _build_qa_prompt_text(record: KnowledgeBaseQARecord) -> str:
        answer_text = record.answer.strip()
        if not answer_text:
            return f"السؤال: {record.question}"
        return "\n".join(
            [
                f"السؤال: {record.question}",
                "الإجابة:",
                answer_text,
            ]
        ).strip()

    @staticmethod
    def _read_text_file(path: Path) -> str:
        for encoding in ("utf-8-sig", "utf-8", "cp1256"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        return path.read_text(encoding="utf-8", errors="ignore")

    def _is_knowledge_base_file(self, path: Path) -> bool:
        try:
            return path.resolve().is_relative_to(self.config.knowledge_base_path.resolve())
        except ValueError:
            return False

    def _iter_pptx_slide_images(self, archive: zipfile.ZipFile, slide_number: int) -> Iterable[bytes]:
        rel_name = f"ppt/slides/_rels/slide{slide_number}.xml.rels"
        if rel_name not in archive.namelist():
            return []

        rel_root = ET.fromstring(archive.read(rel_name))
        base_dir = PurePosixPath("ppt/slides")
        images: list[bytes] = []

        for relation in rel_root:
            relation_type = relation.attrib.get("Type", "")
            if not relation_type.endswith("/image"):
                continue
            target = relation.attrib.get("Target", "")
            resolved = (base_dir / target).as_posix()
            normalized = str(PurePosixPath(resolved))
            normalized = normalized.replace("ppt/slides/../", "ppt/")
            if normalized in archive.namelist():
                from .embedded_images import decode_office_asset
                try:
                    decoded, reason = decode_office_asset(archive.read(normalized), PurePosixPath(normalized).suffix)
                    if reason:
                        issues = getattr(self, 'embedded_asset_issues', [])
                        issues.append({'slide': slide_number, 'asset': normalized, 'reason': reason})
                        self.embedded_asset_issues = issues
                    if decoded is not None:
                        images.append(decoded)
                except Exception as exc:
                    issues = getattr(self, 'embedded_asset_issues', [])
                    issues.append({'slide': slide_number, 'asset': normalized, 'reason': type(exc).__name__})
                    self.embedded_asset_issues = issues
        return images

    def _iter_all_pptx_images(self, archive: zipfile.ZipFile) -> list[str]:
        rel_names = sorted(
            (
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/_rels/slide") and name.endswith(".xml.rels")
            ),
            key=self._extract_numeric_suffix,
        )
        images: list[str] = []
        for rel_name in rel_names:
            rel_root = ET.fromstring(archive.read(rel_name))
            base_dir = PurePosixPath("ppt/slides")
            for relation in rel_root:
                relation_type = relation.attrib.get("Type", "")
                if not relation_type.endswith("/image"):
                    continue
                target = relation.attrib.get("Target", "")
                resolved = (base_dir / target).as_posix()
                normalized = str(PurePosixPath(resolved)).replace("ppt/slides/../", "ppt/")
                if normalized in archive.namelist():
                    images.append(normalized)
        return images

    @staticmethod
    def _extract_xml_text(xml_bytes: bytes) -> str:
        root = ET.fromstring(xml_bytes)
        texts = [node.text or "" for node in root.iter() if node.tag.endswith("}t") and node.text]
        return collapse_whitespace("\n".join(texts))

    @staticmethod
    def _extract_numeric_suffix(name: str) -> int:
        match = re.search(r"(\d+)", Path(name).stem)
        return int(match.group(1)) if match else 0

    def _split_text(self, text: str) -> list[str]:
        from .document_structure import structured_chunks
        return structured_chunks(text,self.config.chunk_size,self.config.chunk_overlap)

    def _build_chunk_id(self, fragment: SourceFragment, chunk_index: int) -> str:
        source_key = normalize_text(fragment.source_name, for_search=True)
        source_key = re.sub(r"[^A-Za-z0-9\u0600-\u06FF]+", "-", source_key).strip("-")
        location_key = f"{fragment.location_type}-{fragment.location_value}"
        return f"{source_key}-{location_key}-{chunk_index}"

    def _display_source_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.config.project_path))
        except ValueError:
            return str(path)
