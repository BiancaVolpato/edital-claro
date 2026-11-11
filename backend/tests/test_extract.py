import re
import shutil

import pymupdf
import pytest

from app.ingestion.chunking import chunk_pages
from app.ingestion.extract import InvalidPdfError, extract_pdf
from app.ingestion.normalize import normalize_pages
from app.ingestion.ocr import OcrError, OcrmypdfEngine
from tests.conftest import SAMPLES_DIR


class FakeOcr:
    """Stands in for Tesseract: records what it was asked and returns fixed text."""

    def __init__(self, available: bool = True, fail: bool = False) -> None:
        self.available = available
        self.fail = fail
        self.requested: list[list[int]] = []

    def is_available(self) -> bool:
        return self.available

    def ocr_pages(self, pdf_bytes: bytes, page_numbers: list[int]) -> dict[int, str]:
        self.requested.append(page_numbers)
        if self.fail:
            raise OcrError("boom")
        return {number: f"texto reconhecido da página {number}" for number in page_numbers}


def test_long_edital_is_extracted_with_correct_page_numbers(florianopolis_pdf: bytes) -> None:
    result = extract_pdf(florianopolis_pdf)
    pages = normalize_pages([page.text for page in result.pages])

    assert [page.number for page in result.pages] == list(range(1, 89))
    assert result.ocr_pages == []
    assert result.warnings == []
    # Landmarks checked by hand against the PDF opened in a viewer.
    assert "EDITAL DE CONCORRÊNCIA Nº 90330/2026" in pages[0]
    assert "R$ 22.549.875,04" in pages[1]
    assert "ANEXO I – TERMO DE REFERÊNCIA" in pages[20]
    assert "ANEXO II – MINUTA DO CONTRATO" in pages[63]
    assert pages[85].startswith("ANEXO III")
    # Invisible characters present in the raw file are gone.
    assert not any("\u200b" in page or "\u00a0" in page for page in pages)


def test_long_edital_chunks_carry_the_page_of_their_heading(florianopolis_pdf: bytes) -> None:
    pages = normalize_pages([page.text for page in extract_pdf(florianopolis_pdf).pages])

    first_page_of: dict[str | None, int] = {}
    for chunk in chunk_pages(pages):
        first_page_of.setdefault(chunk.heading, chunk.page_start)

    assert first_page_of["1- DA LICITAÇÃO"] == 2
    assert first_page_of["9- DOS DOCUMENTOS DE HABILITAÇÃO"] == 7
    assert first_page_of["11 - DAS IMPUGNAÇÕES E DOS RECURSOS ADMINISTRATIVOS"] == 12
    assert first_page_of["ANEXO I – TERMO DE REFERÊNCIA"] == 21
    assert first_page_of["ANEXO II – MINUTA DO CONTRATO"] == 64
    assert first_page_of["ANEXO II – MINUTA DO CONTRATO › 8.CLÁUSULA OITAVA – SUBCONTRATAÇÃO"] == 67
    assert all(chunk.page_start <= chunk.page_end for chunk in chunk_pages(pages))


def test_repeated_page_number_header_is_removed(lauro_muller_pdf: bytes) -> None:
    result = extract_pdf(lauro_muller_pdf)
    pages = normalize_pages([page.text for page in result.pages])

    # In this file every page starts with its own number on a separate line.
    assert result.pages[3].text.lstrip().startswith("4")
    assert not pages[3].startswith("4\n")
    assert "6. DO INÍCIO DA SESSÃO" in pages[3]


def test_ocr_runs_only_on_pages_without_text(mixed_scan_pdf: bytes) -> None:
    ocr = FakeOcr()

    result = extract_pdf(mixed_scan_pdf, ocr)

    assert ocr.requested == [[2]]
    assert [page.ocr for page in result.pages] == [False, True, False]
    assert result.pages[1].text == "texto reconhecido da página 2"
    assert "1. DO OBJETO" in result.pages[0].text  # native text untouched
    assert result.warnings == []


def test_ocr_is_not_called_when_every_page_has_text(lauro_muller_pdf: bytes) -> None:
    ocr = FakeOcr()

    extract_pdf(lauro_muller_pdf, ocr)

    assert ocr.requested == []


@pytest.mark.parametrize("ocr", [None, FakeOcr(available=False), FakeOcr(fail=True)])
def test_missing_or_failing_ocr_becomes_a_warning_not_an_error(
    mixed_scan_pdf: bytes, ocr: FakeOcr | None
) -> None:
    result = extract_pdf(mixed_scan_pdf, ocr)

    assert [page.ocr for page in result.pages] == [False, False, False]
    assert result.pages[1].text.strip() == ""
    assert len(result.warnings) == 1
    assert "(2)" in result.warnings[0]


@pytest.mark.parametrize("content", [b"", b"not a pdf at all", b"%PDF-1.7\ngarbage"])
def test_unreadable_files_raise_invalid_pdf(content: bytes) -> None:
    with pytest.raises(InvalidPdfError):
        extract_pdf(content)


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-zà-ÿ]{4,}", text.lower()))


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
def test_real_ocr_recovers_the_text_of_a_scanned_page(mixed_scan_pdf: bytes) -> None:
    """End-to-end OCR with ocrmypdf + Tesseract (runs in CI and in the Docker image)."""
    # The scanned page is a picture of page 4 of the original edital, whose
    # text layer is the ground truth.
    with pymupdf.open(SAMPLES_DIR / "lauro_muller_cc_233_2026.pdf") as original:
        expected = _words(str(original.load_page(3).get_text()))

    result = extract_pdf(mixed_scan_pdf, OcrmypdfEngine(language="por"))

    assert [page.ocr for page in result.pages] == [False, True, False]
    recognized = _words(result.pages[1].text)
    recall = len(expected & recognized) / len(expected)
    assert recall >= 0.9, f"OCR recovered only {recall:.0%} of the words"
    assert "sessão" in recognized
