"""Document ingestion: store the file, then extract, normalize, chunk and persist."""

import hashlib
import logging
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import session as db_session
from app.db.models import Chunk, Document, DocumentSource, DocumentStatus, Page
from app.ingestion.chunking import chunk_pages
from app.ingestion.extract import InvalidPdfError, extract_pdf
from app.ingestion.normalize import normalize_pages
from app.ingestion.ocr import OcrEngine, OcrmypdfEngine

logger = logging.getLogger(__name__)

_MAX_FILENAME_CHARS = 255
_PDF_MAGIC = b"%PDF-"
# The PDF specification allows the header anywhere in the first 1024 bytes.
_PDF_MAGIC_WINDOW = 1024


class NotAPdfError(ValueError):
    pass


@dataclass(frozen=True)
class RegisteredDocument:
    document: Document
    created: bool  # False when the same file had already been ingested


def sanitize_filename(name: str) -> str:
    """A safe label for the client's file name; it is shown, never used as a path.

    Keeps only the last path segment, drops control and formatting characters
    (including the right-to-left override, U+202E, which can make "edital<U+202E>fdp.exe"
    display as "editalexe.pdf"), collapses whitespace and caps the length, keeping
    the extension.
    """
    name = unicodedata.normalize("NFC", name or "")
    name = re.split(r"[\\/]", name)[-1]
    name = "".join(ch for ch in name if unicodedata.category(ch) not in ("Cc", "Cf"))
    name = " ".join(name.split()).strip(" .")
    if not name:
        return "documento.pdf"
    if len(name) > _MAX_FILENAME_CHARS:
        stem, dot, extension = name.rpartition(".")
        if dot and 0 < len(extension) <= 10:
            name = f"{stem[: _MAX_FILENAME_CHARS - len(extension) - 1]}.{extension}"
        else:
            name = name[:_MAX_FILENAME_CHARS]
    return name


def file_path_for(file_hash: str) -> Path:
    return get_settings().storage_dir / f"{file_hash}.pdf"


def default_ocr_engine() -> OcrEngine:
    settings = get_settings()
    return OcrmypdfEngine(
        language=settings.ocr_language, timeout_seconds=settings.ocr_timeout_seconds
    )


def register_document(
    session: Session,
    content: bytes,
    filename: str,
    source: DocumentSource,
    source_ref: str | None = None,
) -> RegisteredDocument:
    """Store the file and create its Document row, deduplicating by content hash."""
    if _PDF_MAGIC not in content[:_PDF_MAGIC_WINDOW]:
        raise NotAPdfError("file does not look like a PDF")

    file_hash = hashlib.sha256(content).hexdigest()
    existing = session.scalar(select(Document).where(Document.file_hash == file_hash))
    if existing is not None:
        return RegisteredDocument(document=existing, created=False)

    path = file_path_for(file_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

    document = Document(
        source=source.value,
        source_ref=source_ref,
        # Kept only as a label for the user; it is never used to build a path.
        filename=sanitize_filename(filename),
        file_hash=file_hash,
        file_size=len(content),
        status=DocumentStatus.PENDING.value,
        meta={},
    )
    session.add(document)
    try:
        session.commit()
    except IntegrityError:
        # Another request stored the same file between our check and our insert.
        session.rollback()
        winner = session.scalar(select(Document).where(Document.file_hash == file_hash))
        if winner is None:
            raise
        return RegisteredDocument(document=winner, created=False)
    return RegisteredDocument(document=document, created=True)


def process_document(document_id: uuid.UUID, ocr_engine: OcrEngine | None = None) -> None:
    """Run the ingestion pipeline for one document. Meant to run in the background.

    Never raises: any failure is recorded on the document (status ``failed``).
    """
    session = db_session.new_session()
    try:
        document = session.get(Document, document_id)
        if document is None:
            logger.error("document not found", extra={"document_id": str(document_id)})
            return
        _ingest(session, document, ocr_engine or default_ocr_engine())
    finally:
        session.close()


def _ingest(session: Session, document: Document, ocr_engine: OcrEngine) -> None:
    started = time.perf_counter()
    log_context = {"document_id": str(document.id), "file_hash": document.file_hash}

    document.status = DocumentStatus.PROCESSING.value
    document.error = None
    session.commit()

    try:
        content = file_path_for(document.file_hash).read_bytes()
        extraction = extract_pdf(content, ocr_engine, get_settings().max_pdf_pages)
        texts = normalize_pages([page.text for page in extraction.pages])
        chunks = chunk_pages(texts, max_chars=get_settings().chunk_max_chars)

        # Reprocessing replaces whatever a previous (failed) attempt left behind.
        session.execute(delete(Chunk).where(Chunk.document_id == document.id))
        session.execute(delete(Page).where(Page.document_id == document.id))
        session.add_all(
            Page(document_id=document.id, number=page.number, text=text, ocr=page.ocr)
            for page, text in zip(extraction.pages, texts, strict=True)
        )
        session.add_all(
            Chunk(
                document_id=document.id,
                index=chunk.index,
                kind=chunk.kind.value,
                heading=chunk.heading[:500] if chunk.heading else None,
                text=chunk.text,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                page_spans=[list(span) for span in chunk.page_spans],
            )
            for chunk in chunks
        )
        document.page_count = len(extraction.pages)
        document.meta = {
            **(document.meta or {}),  # keeps what was known before, e.g. the PNCP origin
            "pdf": extraction.pdf_metadata,
            "ocr_pages": extraction.ocr_pages,
            "warnings": extraction.warnings,
        }
        document.status = DocumentStatus.READY.value
        session.commit()
    except InvalidPdfError as exc:
        session.rollback()
        _mark_failed(session, document, str(exc))
        logger.warning("ingestion rejected", extra={**log_context, "error": str(exc)})
        return
    except Exception:
        session.rollback()
        _mark_failed(session, document, "Erro inesperado ao processar o documento.")
        logger.exception("ingestion failed", extra=log_context)
        return

    logger.info(
        "ingestion completed",
        extra={
            **log_context,
            "pages": len(extraction.pages),
            "chunks": len(chunks),
            "ocr_pages": len(extraction.ocr_pages),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )


def _mark_failed(session: Session, document: Document, error: str) -> None:
    document.status = DocumentStatus.FAILED.value
    document.error = error
    session.commit()
