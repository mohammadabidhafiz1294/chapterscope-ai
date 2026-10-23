"""Pluggable OCR interface for scanned PDFs (Phase 3).

No OCR engine is installed in this environment and none is a required
dependency. The default engine reports that OCR is required rather than
pretending extraction succeeded. A Tesseract adapter activates only when
``pytesseract``, ``pdf2image`` and the system ``tesseract`` / ``pdftoppm``
binaries are all present; installing them is documented and optional.

No paid OCR API is used or called anywhere.
"""

import importlib.util
import logging
import shutil
from abc import ABC, abstractmethod
from typing import Optional

from django.conf import settings

from .types import OCRPageResult

logger = logging.getLogger(__name__)


class OCREngine(ABC):
    """Interface for page-level OCR engines."""

    name: str = "abstract"

    @classmethod
    def is_available(cls) -> bool:  # pragma: no cover - interface default
        """Whether this engine's dependencies and binaries are present."""
        return False

    @abstractmethod
    def extract_page(self, file_path: str, page_number: int) -> OCRPageResult:
        """OCR a single 1-based page of a PDF file."""


class UnavailableOCREngine(OCREngine):
    """Placeholder engine used when no OCR backend is installed."""

    name = "unavailable"

    def extract_page(self, file_path: str, page_number: int) -> OCRPageResult:
        return OCRPageResult(
            text="",
            confidence=None,
            warnings=["ocr_engine_unavailable"],
        )


class TesseractOCREngine(OCREngine):
    """Local Tesseract OCR (optional).

    Requires ``pytesseract``, ``pdf2image`` and the system binaries
    ``tesseract`` and ``pdftoppm`` (poppler). Activated only when
    ``is_available()`` is True; otherwise the factory falls back to
    ``UnavailableOCREngine``.
    """

    name = "tesseract"

    @classmethod
    def is_available(cls) -> bool:
        if importlib.util.find_spec("pytesseract") is None:
            return False
        if importlib.util.find_spec("pdf2image") is None:
            return False
        if shutil.which("tesseract") is None:
            return False
        if shutil.which("pdftoppm") is None:
            return False
        return True

    def extract_page(self, file_path: str, page_number: int) -> OCRPageResult:
        import pytesseract
        from pdf2image import convert_from_path

        try:
            images = convert_from_path(
                file_path, first_page=page_number, last_page=page_number, dpi=200
            )
            if not images:
                return OCRPageResult(
                    text="", confidence=None, warnings=["ocr_page_render_failed"]
                )
            text = pytesseract.image_to_string(images[0])
            data = pytesseract.image_to_data(
                images[0], output_type=pytesseract.Output.DICT
            )
            confidences = [
                float(c) / 100.0
                for c in data.get("conf", [])
                if str(c).lstrip("-").replace(".", "", 1).isdigit()
                and float(c) >= 0
            ]
            avg_conf = (
                sum(confidences) / len(confidences) if confidences else None
            )
            return OCRPageResult(text=text.strip(), confidence=avg_conf)
        except Exception as exc:
            logger.warning("Tesseract OCR failed on page %s: %s", page_number, exc)
            return OCRPageResult(
                text="", confidence=None, warnings=["ocr_engine_error"]
            )


def get_ocr_engine() -> OCREngine:
    """Return the configured OCR engine, or an unavailable placeholder.

    Reads ``settings.OCR_ENGINE`` ('auto', 'none' or 'tesseract'). 'auto'
    uses Tesseract when installed, else the unavailable placeholder.
    """
    selector = (getattr(settings, "OCR_ENGINE", "auto") or "auto").lower()
    if selector == "none":
        return UnavailableOCREngine()
    if selector == "tesseract":
        if TesseractOCREngine.is_available():
            return TesseractOCREngine()
        logger.warning(
            "OCR_ENGINE=tesseract but Tesseract dependencies are not installed"
        )
        return UnavailableOCREngine()
    # auto
    if TesseractOCREngine.is_available():
        return TesseractOCREngine()
    return UnavailableOCREngine()


def ocr_page_if_needed(
    engine: OCREngine, file_path: str, page_number: int
) -> Optional[OCRPageResult]:
    """Run OCR on one page if the engine is available.

    Returns the OCRPageResult, or None when the engine is unavailable (the
    caller should then surface ``ocr_required`` honestly).
    """
    if not engine.is_available():
        return None
    return engine.extract_page(file_path, page_number)
