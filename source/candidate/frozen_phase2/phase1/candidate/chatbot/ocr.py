from __future__ import annotations

import io
import logging

import numpy as np
from PIL import Image

from .config import AppConfig
from .normalization import collapse_whitespace
from .profiling import add_note, mark_ocr_called


class OCRBackend:
    def __init__(self, config: AppConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self._easy = None
        self._torch_ready = False
        self._easy_attempted = False
        self._torch_attempted = False
        self.last_backend = "غير متاح"
        self.last_result: dict[str, object] = {
            "reference": "",
            "backend": None,
            "success": False,
            "easyocr_attempted": False,
            "easyocr_success": False,
            "easyocr_error": None,
            "text_length": 0,
        }

    def backend_name(self) -> str:
        return self.last_backend

    def _warmup_torch(self) -> bool:
        if self._torch_attempted:
            return self._torch_ready

        self._torch_attempted = True
        try:
            import torch

            _ = torch.__version__
            self._torch_ready = True
            self.logger.info("Torch runtime initialized for OCR.")
        except Exception as exc:
            self._torch_ready = False
            self.logger.warning("Torch runtime initialization failed (%s).", type(exc).__name__)
        return self._torch_ready

    def _init_easyocr(self):
        if self._easy_attempted:
            return self._easy

        self._easy_attempted = True
        try:
            self._warmup_torch()
            import easyocr

            self._easy = easyocr.Reader(list(self.config.easyocr_langs), gpu=False, verbose=False)
            self.logger.info("EasyOCR initialized as the only OCR backend.")
        except Exception as exc:
            self.logger.warning("EasyOCR initialization failed (%s).", type(exc).__name__)
            self._easy = None
        return self._easy

    @staticmethod
    def _to_image(image: Image.Image | bytes) -> Image.Image:
        if isinstance(image, Image.Image):
            return image.convert("RGB")
        return Image.open(io.BytesIO(image)).convert("RGB")

    def ocr_image(self, image: Image.Image | bytes, reference: str = "") -> str:
        mark_ocr_called(reference=reference or None)
        if not self.config.enable_ocr_during_chat:
            add_note(
                "OCR path was reached while ENABLE_OCR_DURING_CHAT is False. "
                "This usually indicates indexing or a document-processing path rather than normal text chat."
            )
        pil_image = self._to_image(image)
        image_array = np.array(pil_image)
        self.last_result = {
            "reference": reference,
            "backend": None,
            "success": False,
            "easyocr_attempted": False,
            "easyocr_success": False,
            "easyocr_error": None,
            "text_length": 0,
        }

        easy = self._init_easyocr()
        if easy is not None:
            self.last_result["easyocr_attempted"] = True
            try:
                from .ocr_layout import summarize_layout
                layout = summarize_layout(easy.readtext(image_array, detail=1, paragraph=False))
                layout['geometry_version']='ocr-blocks-v1'
                self.last_result.update(layout)
                text = layout["text"]
                if text:
                    self.last_backend = "EasyOCR"
                    self.last_result["backend"] = "EasyOCR"
                    self.last_result["success"] = True
                    self.last_result["easyocr_success"] = True
                    self.last_result["text_length"] = len(text)
                    return text
            except Exception as exc:
                self.logger.warning("EasyOCR failed (%s).", type(exc).__name__)
                self.last_result["easyocr_error"] = type(exc).__name__

        self.last_backend = "غير متاح"
        return ""
