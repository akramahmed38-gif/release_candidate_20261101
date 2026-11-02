"""Extract learning content ahead of chat; reuse unchanged source results."""
from __future__ import annotations
from dataclasses import asdict, replace
import hashlib
import json
import logging
from pathlib import Path
import re
import time
import threading
import zipfile
import posixpath
from xml.etree import ElementTree as ET

from .content_catalog import MEDIA_TYPES, catalog_signature, content_hash, discover_content, read_vocabulary, vocabulary_hash
from .content_state import atomic_json

EXTRACTOR_VERSION = "learning-content-v3-pdf-ocr"
_PDF_RENDER_LOCK = threading.Lock()
_OCR_IMAGE_LOCK_GUARD = threading.Lock()
_OCR_IMAGE_LOCKS = {}


def _image_lock(key):
    with _OCR_IMAGE_LOCK_GUARD:
        return _OCR_IMAGE_LOCKS.setdefault(key,threading.Lock())


def extraction_cache_version(suffix):
    if suffix.lower() == '.pdf':
        return EXTRACTOR_VERSION
    return 'learning-content-v2' if suffix.lower() in {'.xlsx', '.pptx'} else 'learning-content-v1'


class PDFPageOCRIncomplete(RuntimeError):
    """A nonblank PDF page could not be read; never fall back to its text layer."""
_ASSIGNMENT = re.compile(r"(?im)((?:password|passwd|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|authorization|cookie|كلمة\s*المرور)\s*[:=]\s*)[^\r\n]+")


def safe_content(text):
    return _ASSIGNMENT.sub(r"\1[REDACTED]", str(text or ""))


def vocabulary_chunks(rows):
    result = []
    for item in rows:
        term, meaning = safe_content(item["english"]).strip(), safe_content(item["arabic"]).strip()
        if not term or not meaning: continue
        question, answer = f"ما معنى {term}؟", f"{term}: {meaning}"
        result.append({"id": "vocabulary-" + item["id"], "text": f"{question}\n{answer}", "metadata": {
            "source_name": "Business Vocabulary", "source_path": "BusinessVocabulary/" + item["id"],
            "source_type": "vocabulary", "location_type": "term", "location_value": item["id"],
            "location_label": term, "content_library": "vocabulary", "category": item["category"],
            "qa_id": "VOCABULARY_" + item["id"], "question_text": question, "answer_text": answer,
            "alternate_questions": [term, f"معنى {term}", f"يعني ايه {term}", f"ماذا يعني {term}", f"what does {term} mean", f"meaning of {term}"],
        }})
        base=result[-1]
        speech=safe_content(item.get('speech') or '').strip()
        category=safe_content(item.get('category_arabic') or item.get('category') or '').strip()
        english_category=safe_content(item.get('category') or '').strip()
        if english_category and english_category!=category:category+=f' ({english_category})'
        for suffix,prompt,response,aliases in [
            ('pronunciation',f'كيف ينطق {term}؟',f'{term}: {speech}',[f'طريقة نطق {term}',f'pronunciation of {term}']),
            ('category',f'ما تصنيف {term}؟',f'{term}: {category}',[f'فئة {term}',f'category of {term}']),
        ]:
            if not (speech if suffix=='pronunciation' else category):continue
            result.append({'id':base['id']+'-'+suffix,'text':prompt+'\n'+response,'metadata':{
                **base['metadata'],'qa_id':base['metadata']['qa_id']+'_'+suffix.upper(),
                'question_text':prompt,'answer_text':response,'alternate_questions':aliases}})
    return result


class ContentPreparer:
    def __init__(self, root, output, database, allow_model_download=False):
        self.root, self.output, self.database = Path(root), Path(output), Path(database)
        self.allow_model_download = allow_model_download
        self.logger = logging.getLogger("learning_content_preparation")
        self.logger.addHandler(logging.NullHandler())
        self.logger.disabled = True
        self._ingestor = self._speech_model = None
        self.output.mkdir(parents=True, exist_ok=True)

    @property
    def ingestor(self):
        if self._ingestor is None:
            from .config import load_config
            from .ingestion import MaterialIngestor
            from .ocr import OCRBackend
            outer = self
            class OfflineOCR(OCRBackend):
                def ocr_image(self, image, reference=""):
                    converted=self._to_image(image)
                    key=hashlib.sha256(("offline-ocr-v1:"+str(converted.size)).encode()+converted.tobytes()).hexdigest()
                    cache=outer.output/'ocr_cache'/(key+'.json')
                    with _image_lock(key):
                        if cache.exists():
                            saved=json.loads(cache.read_text(encoding='utf-8'))
                            self.last_result=saved['result']
                            self.last_backend='EasyOCR (cached)'
                            return saved['text']
                        text=super().ocr_image(converted,reference)
                        if self.last_result.get('easyocr_attempted') and not self.last_result.get('easyocr_error'):
                            atomic_json(cache,{'text':safe_content(text),'result':{k:v for k,v in self.last_result.items() if k!='reference'}})
                        return text

                def _init_easyocr(self):
                    if self._easy_attempted: return self._easy
                    self._easy_attempted = True
                    try:
                        import easyocr
                        import torch
                        torch.set_num_threads(2)
                        location = outer.root / "models/easyocr"
                        if outer.allow_model_download and not location.exists(): location = Path.home() / ".EasyOCR/model"
                        self._easy = easyocr.Reader(list(self.config.easyocr_langs), gpu=False, verbose=False, model_storage_directory=str(location), download_enabled=outer.allow_model_download)
                    except Exception:
                        self._easy = None
                    return self._easy
            config = replace(load_config(self.root), generation_threads=1)
            self._ingestor = MaterialIngestor(config, OfflineOCR(config, self.logger), self.logger)
        return self._ingestor

    def text_rows(self, source, text, location_type, location, label):
        return [{"id": str(number), "text": part, "metadata": {
            "source_name": Path(source.path).name, "source_path": source.path,
            "source_type": Path(source.path).suffix.lstrip("."), "location_type": location_type,
            "location_value": str(location), "location_label": label,
        }} for number, part in enumerate(self.ingestor._split_text(text), 1)]

    def spreadsheet(self, source):
        import openpyxl
        book = openpyxl.load_workbook(self.root / source.path, read_only=True, data_only=True, keep_links=False)
        formulas = None
        rows = []
        try:
            formulas = openpyxl.load_workbook(self.root / source.path, read_only=True, data_only=False, keep_links=False)
            for sheet in book:
                headers = None
                formula_rows=formulas[sheet.title].iter_rows(values_only=True)
                for index, (values, expressions) in enumerate(zip(sheet.iter_rows(values_only=True),formula_rows), 1):
                    values = [str(value).strip() if value is not None else "" for value in values]
                    for column,expression in enumerate(expressions):
                        if isinstance(expression,str) and expression.startswith('='):
                            values[column]=(values[column]+' | ' if values[column] else '')+'Formula: '+expression
                    if not any(values): continue
                    if headers is None: headers = values
                    cells = [f"{headers[i] if i < len(headers) and headers[i] else 'Column ' + str(i+1)}: {value}" for i, value in enumerate(values) if value]
                    rows.extend(self.text_rows(source, f"{sheet.title} | " + " | ".join(cells), "sheet_row", f"{sheet.title}:{index}", f"{sheet.title}, row {index}"))
        finally:
            book.close()
            if formulas is not None:formulas.close()
        return rows

    def pdf(self, source, digest):
        """OCR every rendered page; never consume potentially corrupt PDF text."""
        import pypdfium2 as pdfium
        from PIL import ImageStat
        rows, pages = [], []
        audit = self.output/'pdf_ocr_audits'/(hashlib.sha256(source.path.encode()).hexdigest()+'.json')
        with _PDF_RENDER_LOCK:
            document = pdfium.PdfDocument(str(self.root/source.path))
            page_count=len(document)
        try:
            for index in range(page_count):
                image = None
                try:
                    # PDFium calls remain serialized; CPU OCR runs in parallel
                    # on detached images, never concurrently inside PDFium.
                    with _PDF_RENDER_LOCK:
                        page=document[index]
                        bitmap=None
                        try:
                            bitmap = page.render(scale=max(2.5, self.ingestor.config.render_scale))
                            image = bitmap.to_pil().copy()
                        finally:
                            if bitmap is not None:bitmap.close()
                            page.close()
                    gray = image.convert('L')
                    # Only nearly uniform white pages can be skipped as blank.
                    stat = ImageStat.Stat(gray)
                    blank = stat.mean[0] >= 254.5 and stat.stddev[0] < 1
                    gray.close()
                    text = '' if blank else self.ingestor.ocr_backend.ocr_image(image, reference=f'PDF page {index+1}')
                    result = self.ingestor.ocr_backend.last_result if not blank else {}
                    state = 'blank' if blank else ('ocr_ready' if text.strip() and not result.get('easyocr_error') else 'ocr_failed')
                    pages.append({'page':index+1,'status':state,'characters':len(text)})
                    if text.strip():
                        chunks = self.text_rows(source,text,'page',index+1,f'Page {index+1}')
                        for chunk in chunks:
                            chunk['metadata'].update(extraction_method='easyocr_full_page',content_type='ocr_text')
                        rows.extend(chunks)
                    atomic_json(audit,{'source_sha256':digest,'pages_expected':page_count,'pages_processed':len(pages),'complete':False,'pages':pages})
                finally:
                    if image is not None:image.close()
        finally:
            with _PDF_RENDER_LOCK:document.close()
        complete = bool(pages) and not any(page['status']=='ocr_failed' for page in pages)
        atomic_json(audit,{'source_sha256':digest,'pages_expected':len(pages),'pages_processed':len(pages),'complete':complete,'pages':pages})
        if not complete:
            raise PDFPageOCRIncomplete()
        return rows

    @staticmethod
    def presentation_slides(archive):
        if 'ppt/presentation.xml' not in archive.namelist():return None
        root=ET.fromstring(archive.read('ppt/presentation.xml'))
        relations=ET.fromstring(archive.read('ppt/_rels/presentation.xml.rels'))
        targets={relation.get('Id'):relation.get('Target','') for relation in relations if relation.get('Type','').endswith('/slide') and relation.get('TargetMode')!='External'}
        ordered={}
        for element in root.findall('.//{http://schemas.openxmlformats.org/presentationml/2006/main}sldId'):
            target=targets.get(element.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'))
            if not target:continue
            target=target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('ppt',target))
            if target.startswith('ppt/slides/') and target in archive.namelist():ordered[target]=len(ordered)+1
        return ordered

    def presentation_notes(self,source):
        rows=[]
        namespaces={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
        with zipfile.ZipFile(self.root/source.path) as archive:
            active=self.presentation_slides(archive)
            for name in sorted(archive.namelist()):
                match=re.fullmatch(r'ppt/slides/_rels/slide(\d+)\.xml\.rels',name)
                if not match:continue
                slide=f'ppt/slides/slide{match.group(1)}.xml'
                if active is not None and slide not in active:continue
                number=active[slide] if active is not None else int(match.group(1))
                for relation in ET.fromstring(archive.read(name)):
                    if not relation.get('Type','').endswith('/notesSlide') or relation.get('TargetMode')=='External':continue
                    target=relation.get('Target','')
                    target=target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('ppt/slides',target))
                    if not target.startswith('ppt/notesSlides/') or target not in archive.namelist():continue
                    root=ET.fromstring(archive.read(target));parts=[]
                    for shape in root.findall('.//p:sp',namespaces):
                        placeholder=shape.find('.//p:ph',namespaces)
                        if placeholder is not None and placeholder.get('type') in {'sldNum','dt','ftr','hdr','sldImg'}:continue
                        text=' '.join(node.text or '' for node in shape.findall('.//a:t',namespaces)).strip()
                        if text:parts.append(text)
                    if parts:rows.extend(self.text_rows(source,'\n'.join(parts),'slide',str(number),f'Slide {number} speaker notes'))
        return rows

    def media(self, source):
        import av
        rows = []
        with av.open(str(self.root / source.path)) as container:
            has_audio, has_video = bool(container.streams.audio), bool(container.streams.video)
        if has_audio:
            from faster_whisper import WhisperModel
            if self._speech_model is None:
                model_root = self.root / "models/speech/small"
                if not model_root.exists():
                    if not self.allow_model_download: raise RuntimeError("offline_speech_model_missing")
                    from huggingface_hub import snapshot_download
                    model_root = Path(snapshot_download("Systran/faster-whisper-small", local_dir=self.output / "speech_model", token=False, allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"]))
                self._speech_model = WhisperModel(str(model_root), device="cpu", compute_type="int8", cpu_threads=2, num_workers=1, local_files_only=True)
            segments, _ = self._speech_model.transcribe(str(self.root / source.path), beam_size=1, vad_filter=True, condition_on_previous_text=False)
            buffer=[]
            buffer_start=buffer_end=0
            for segment in segments:
                if not segment.text.strip(): continue
                if not buffer:buffer_start=int(segment.start)
                buffer_end=int(segment.end)
                buffer.append(segment.text.strip())
                if buffer_end-buffer_start>=40 or sum(map(len,buffer))>=800:
                    label=f"{buffer_start // 60:02d}:{buffer_start % 60:02d}–{buffer_end // 60:02d}:{buffer_end % 60:02d}"
                    rows.extend(self.text_rows(source,' '.join(buffer),'timestamp',buffer_start,label))
                    buffer=[]
            if buffer:
                label=f"{buffer_start // 60:02d}:{buffer_start % 60:02d}–{buffer_end // 60:02d}:{buffer_end % 60:02d}"
                rows.extend(self.text_rows(source,' '.join(buffer),'timestamp',buffer_start,label))
        if has_video:
            # Capture on-screen teaching text as well as speech. Sampling is
            # reported explicitly; it cannot prove every transient frame read.
            seen, previous_thumbnail, last_time = set(), None, -10
            with av.open(str(self.root / source.path)) as container:
                container.streams.video[0].codec_context.thread_count = 1
                for frame in container.decode(video=0):
                    stamp = float(frame.time or 0)
                    if stamp - last_time < 5: continue
                    last_time = stamp
                    image = frame.to_image()
                    thumbnail = list(image.convert("L").resize((16, 16)).getdata())
                    if previous_thumbnail is not None and sum(abs(a-b) for a,b in zip(thumbnail,previous_thumbnail)) / 256 < 3: continue
                    previous_thumbnail = thumbnail
                    text = self.ingestor.ocr_backend.ocr_image(image, reference="video-frame")
                    if len(text.strip()) < 15: continue
                    key = " ".join(text.split())
                    if key in seen: continue
                    seen.add(key)
                    second = int(stamp)
                    rows.extend(self.text_rows(source, text, "timestamp", second, f"{second // 60:02d}:{second % 60:02d} (screen text)"))
        return rows

    def finalize_chunks(self, source, digest, chunks):
        for number, chunk in enumerate(chunks):
            metadata = chunk["metadata"]
            metadata.update(content_library=source.library, source_sha256=digest, source_path=source.path)
            chunk["text"] = safe_content(chunk["text"])
            for field in ["prompt_text", "answer_text", "question_text"]:
                if field in metadata: metadata[field] = safe_content(metadata[field])
            if not metadata.get('qa_id') and source.library!='curated_knowledge':
                metadata.setdefault('prompt_text',chunk['text'])
                subject=' / '.join(Path(source.path).parts[-4:])
                chunk['text']=safe_content(subject)+'\n'+chunk['text']
            chunk["id"] = "learning-" + hashlib.sha256(f"{source.path}\0{number}\0{chunk['text']}".encode()).hexdigest()
        return chunks

    def prepare(self, include_media=True):
        files, ignored = discover_content(self.root)
        vocabulary = read_vocabulary(self.database)
        voc_hash = vocabulary_hash(vocabulary)
        signature = hashlib.sha256((EXTRACTOR_VERSION + catalog_signature(files, voc_hash)).encode()).hexdigest()
        manifest_path = self.output / "preparation_manifest.json"
        previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        previous_files = {row["path"]: row for row in previous.get("files", [])}
        status = []
        for index, source in enumerate(files):
            atomic_json(self.output / "preparation_progress.json", {"processed":index,"total":len(files),"phase":"extracting","source_id":hashlib.sha256(source.path.encode()).hexdigest()[:16],"extension":Path(source.path).suffix.lower(),"started_at":time.time()})
            row, old = asdict(source), previous_files.get(source.path, {})
            if not source.supported: row.update(status="unsupported", chunks=0)
            elif Path(source.path).suffix.lower() in MEDIA_TYPES and not include_media: row.update(status="pending_media", chunks=0)
            else:
                try:
                    digest = old.get("sha256") if old.get("size") == source.size and old.get("mtime_ns") == source.mtime_ns else None
                    digest = digest or content_hash(self.root / source.path)
                    suffix=Path(source.path).suffix.lower()
                    cache_version=extraction_cache_version(suffix)
                    key = hashlib.sha256((cache_version + source.path + digest).encode()).hexdigest()
                    part = self.output / "parts" / (key + ".json")
                    if part.exists(): chunks = json.loads(part.read_text(encoding="utf-8"))
                    else:
                        suffix = Path(source.path).suffix.lower()
                        if suffix == '.pdf': chunks = self.pdf(source,digest)
                        elif suffix == ".xlsx": chunks = self.spreadsheet(source)
                        elif suffix in {'.srt','.vtt'}:
                            text=(self.root/source.path).read_text(encoding='utf-8-sig')
                            chunks=self.text_rows(source,text,'captions','1','Captions with timestamps')
                        elif suffix in MEDIA_TYPES: chunks = self.media(source)
                        else:
                            self.ingestor.embedded_asset_issues = []
                            chunks = self.ingestor.build_chunks([self.root / source.path])
                            issues = self.ingestor.embedded_asset_issues
                            if issues:
                                audit_name = hashlib.sha256(source.path.encode()).hexdigest() + '.json'
                                atomic_json(self.output / 'embedded_asset_audits' / audit_name,
                                            {'source_path': source.path, 'issues': issues})
                                for chunk in chunks:
                                    chunk['metadata']['embedded_asset_omissions'] = len(issues)
                            if suffix=='.pptx':
                                with zipfile.ZipFile(self.root/source.path) as archive:active=self.presentation_slides(archive)
                                if active is not None:
                                    visible=[]
                                    for chunk in chunks:
                                        metadata=chunk['metadata']
                                        if metadata.get('location_type')=='slide':
                                            slide=f"ppt/slides/slide{metadata.get('location_value')}.xml"
                                            if slide not in active:continue
                                            metadata['location_value']=str(active[slide])
                                            metadata['location_label']=f'Slide {active[slide]}'
                                        visible.append(chunk)
                                    chunks=visible
                                chunks.extend(self.presentation_notes(source))
                        chunks=self.finalize_chunks(source,digest,chunks)
                        if chunks: atomic_json(part, chunks)
                    current = (self.root / source.path).stat()
                    if current.st_size != source.size or current.st_mtime_ns != source.mtime_ns: row.update(status="changed_during_extraction", chunks=0)
                    else: row.update(status="ready" if chunks else "empty_extraction", chunks=len(chunks), sha256=digest, part=part.relative_to(self.output).as_posix())
                except Exception as exc: row.update(status="extraction_failed", chunks=0, error_type=type(exc).__name__)
            status.append(row)
            atomic_json(self.output / "preparation_progress.json", {"processed": index+1, "total": len(files), "last_status": row["status"], "library": source.library})
        ready = [row for row in status if row["status"] == "ready"]
        total = 0
        pending = self.output / "chunks.pending"
        with pending.open("w", encoding="utf-8") as stream:
            for row in ready:
                for chunk in json.loads((self.output / row["part"]).read_text(encoding="utf-8")):
                    stream.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                    total += 1
            for chunk in vocabulary_chunks(vocabulary):
                stream.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                total += 1
        import os
        os.replace(pending, self.output / "chunks.jsonl")
        missing_libraries = [name for name in ["KnowledgeBase", "material", "daily_brief"] if not (self.root / name).is_dir()]
        manifest = {"extractor_version": EXTRACTOR_VERSION, "signature": signature, "complete": len(ready)==len(files) and not missing_libraries, "missing_libraries": missing_libraries, "source_files": len(files), "ready_files": len(ready), "vocabulary_items": len(vocabulary), "vocabulary_hash": voc_hash, "chunks": total, "ignored_non_content_files": ignored, "files": status, "prepared_at": time.time(), "media_extraction": "speech transcription plus changed-frame OCR sampled every five seconds"}
        atomic_json(manifest_path, manifest)
        return manifest
