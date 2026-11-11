"""Page-by-page text extraction from PDF files."""

import logging
from dataclasses import dataclass, field
from typing import Any

import pymupdf

from app.ingestion.ocr import OcrEngine, OcrError

logger = logging.getLogger(__name__)

# A page with fewer characters than this is treated as having no text layer.
# Scanned pages usually yield zero characters; the margin covers stray marks.
MIN_TEXT_CHARS = 20

_METADATA_KEYS = ("title", "author", "subject", "creator", "producer", "creationDate")


class InvalidPdfError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedPage:
    number: int  # 1-based
    text: str  # raw text, not yet normalized
    ocr: bool


@dataclass(frozen=True)
class ExtractionResult:
    pages: list[ExtractedPage]
    pdf_metadata: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    @property
    def ocr_pages(self) -> list[int]:
        return [page.number for page in self.pages if page.ocr]


def extract_pdf(pdf_bytes: bytes, ocr_engine: OcrEngine | None = None) -> ExtractionResult:
    """Extract the text of every page, running OCR only on pages without text."""
    try:
        document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises several unrelated exception types
        raise InvalidPdfError("file is not a readable PDF") from exc

    with document:
        if document.needs_pass:
            raise InvalidPdfError("PDF is password-protected")
        if document.page_count == 0:
            raise InvalidPdfError("PDF has no pages")

        texts = {
            index + 1: str(document.load_page(index).get_text())
            for index in range(document.page_count)
        }
        raw_metadata = document.metadata or {}

    pdf_metadata = {key: raw_metadata[key] for key in _METADATA_KEYS if raw_metadata.get(key)}
    textless = [number for number, text in texts.items() if len(text.strip()) < MIN_TEXT_CHARS]

    recognized: dict[int, str] = {}
    warnings: list[str] = []
    if textless:
        recognized, warnings = _run_ocr(pdf_bytes, textless, ocr_engine)

    pages = [
        ExtractedPage(
            number=number,
            text=recognized.get(number, text),
            ocr=number in recognized,
        )
        for number, text in sorted(texts.items())
    ]
    return ExtractionResult(pages=pages, pdf_metadata=pdf_metadata, warnings=warnings)


def _run_ocr(
    pdf_bytes: bytes, page_numbers: list[int], ocr_engine: OcrEngine | None
) -> tuple[dict[int, str], list[str]]:
    """Run OCR, degrading to a warning (never a failure) when it cannot run."""
    listed = ", ".join(str(number) for number in page_numbers)

    if ocr_engine is None or not ocr_engine.is_available():
        logger.warning("ocr unavailable", extra={"textless_pages": page_numbers})
        return {}, [f"OCR indisponível: páginas sem texto não foram lidas ({listed})."]

    try:
        recognized = ocr_engine.ocr_pages(pdf_bytes, page_numbers)
    except OcrError as exc:
        logger.warning("ocr failed", extra={"textless_pages": page_numbers, "error": str(exc)})
        return {}, [f"OCR falhou: páginas sem texto não foram lidas ({listed})."]

    logger.info("ocr completed", extra={"ocr_pages": page_numbers})
    return recognized, []
