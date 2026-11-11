"""OCR fallback for pages without a text layer (scanned pages).

OCR is slow and less accurate than a native text layer, so it only ever sees
the pages that have no text. The engine sits behind a small protocol so tests
can replace it and so another OCR tool can be plugged in later.
"""

import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Protocol

import pymupdf

logger = logging.getLogger(__name__)


class OcrError(RuntimeError):
    pass


class OcrEngine(Protocol):
    def is_available(self) -> bool:
        """Whether the engine can run in this environment."""
        ...

    def ocr_pages(self, pdf_bytes: bytes, page_numbers: list[int]) -> dict[int, str]:
        """Return the recognized text for each requested 1-based page number."""
        ...


class OcrmypdfEngine:
    """Runs Tesseract through the ``ocrmypdf`` command-line tool."""

    def __init__(self, language: str = "por", timeout_seconds: int = 600) -> None:
        self._language = language
        self._timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        return shutil.which("tesseract") is not None

    def ocr_pages(self, pdf_bytes: bytes, page_numbers: list[int]) -> dict[int, str]:
        if not page_numbers:
            return {}

        with tempfile.TemporaryDirectory(prefix="edital-ocr-") as workdir:
            source = Path(workdir) / "input.pdf"
            target = Path(workdir) / "output.pdf"

            # Build a PDF holding only the pages that need OCR.
            with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
                document.select([number - 1 for number in page_numbers])
                document.save(source)

            # A subprocess keeps ocrmypdf's own worker processes away from the web
            # server and lets us enforce a timeout. The arguments are fixed values
            # and paths we created; nothing here comes from the uploaded file.
            command = [
                sys.executable,
                "-m",
                "ocrmypdf",
                "--force-ocr",
                "--language",
                self._language,
                "--output-type",
                "pdf",
                "--optimize",
                "0",
                "--quiet",
                str(source),
                str(target),
            ]
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise OcrError(f"OCR timed out after {self._timeout_seconds}s") from exc
            except subprocess.CalledProcessError as exc:
                raise OcrError(f"ocrmypdf failed: {exc.stderr.strip()[-500:]}") from exc

            with pymupdf.open(target) as recognized:
                return {
                    number: str(recognized.load_page(position).get_text())
                    for position, number in enumerate(page_numbers)
                }
