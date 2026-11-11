"""Document upload and retrieval endpoints."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Chunk, Document, DocumentSource, DocumentStatus, Page
from app.db.session import get_session
from app.ingestion.service import NotAPdfError, process_document, register_document

router = APIRouter(prefix="/documents", tags=["documents"])

SessionDep = Annotated[Session, Depends(get_session)]

_READ_BLOCK_BYTES = 1024 * 1024


class PageSummary(BaseModel):
    number: int
    ocr: bool
    char_count: int


class DocumentRead(BaseModel):
    # The ORM attribute is "meta" because SQLAlchemy reserves "metadata";
    # the API exposes it as "metadata".
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    source: str
    source_ref: str | None
    filename: str
    file_hash: str
    file_size: int
    status: str
    error: str | None
    page_count: int | None
    metadata: dict[str, Any] = Field(validation_alias="meta")
    created_at: datetime
    updated_at: datetime


class DocumentUploadResponse(DocumentRead):
    # True when this exact file had been uploaded before and was not processed again.
    duplicate: bool


class DocumentDetail(DocumentRead):
    chunk_count: int
    pages: list[PageSummary]


class PageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    number: int
    ocr: bool
    text: str


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    index: int
    kind: str
    heading: str | None
    text: str
    page_start: int
    page_end: int


async def _read_limited(file: UploadFile, max_bytes: int) -> bytes:
    """Read the upload in blocks, refusing files above the configured limit."""
    blocks: list[bytes] = []
    total = 0
    while block := await file.read(_READ_BLOCK_BYTES):
        total += len(block)
        if total > max_bytes:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"Arquivo maior que o limite de {max_bytes // (1024 * 1024)} MB.",
            )
        blocks.append(block)
    return b"".join(blocks)


def _get_document_or_404(session: Session, document_id: uuid.UUID) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado.")
    return document


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    responses={status.HTTP_200_OK: {"description": "File already ingested (duplicate)."}},
)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    response: Response,
    session: SessionDep,
) -> DocumentUploadResponse:
    """Upload an edital in PDF. Processing runs in the background; poll GET /documents/{id}."""
    content = await _read_limited(file, get_settings().max_upload_mb * 1024 * 1024)
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Arquivo vazio.")

    try:
        registered = register_document(
            session, content, filename=file.filename or "", source=DocumentSource.UPLOAD
        )
    except NotAPdfError:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "O arquivo enviado não é um PDF."
        ) from None

    document = registered.document
    # A duplicate whose earlier processing failed gets another attempt.
    needs_processing = registered.created or document.status == DocumentStatus.FAILED.value
    if needs_processing:
        background_tasks.add_task(process_document, document.id)
    if not registered.created:
        response.status_code = status.HTTP_200_OK

    return DocumentUploadResponse.model_validate(
        {**DocumentRead.model_validate(document).model_dump(), "duplicate": not registered.created}
    )


@router.get("/{document_id}")
def get_document(document_id: uuid.UUID, session: SessionDep) -> DocumentDetail:
    """Document status and metadata, with a per-page summary (no page text)."""
    document = _get_document_or_404(session, document_id)
    pages = session.execute(
        select(Page.number, Page.ocr, func.length(Page.text))
        .where(Page.document_id == document_id)
        .order_by(Page.number)
    ).all()
    chunk_count = session.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == document_id)
    )
    return DocumentDetail.model_validate(
        {
            **DocumentRead.model_validate(document).model_dump(),
            "chunk_count": chunk_count or 0,
            "pages": [
                PageSummary(number=number, ocr=ocr, char_count=char_count)
                for number, ocr, char_count in pages
            ],
        }
    )


@router.get("/{document_id}/pages/{number}")
def get_page(document_id: uuid.UUID, number: int, session: SessionDep) -> PageRead:
    """Normalized text of one page (1-based)."""
    _get_document_or_404(session, document_id)
    page = session.scalar(
        select(Page).where(Page.document_id == document_id, Page.number == number)
    )
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Página não encontrada.")
    return PageRead.model_validate(page)


@router.get("/{document_id}/chunks")
def list_chunks(document_id: uuid.UUID, session: SessionDep) -> list[ChunkRead]:
    """Chunks of the document in reading order."""
    _get_document_or_404(session, document_id)
    chunks = session.scalars(
        select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.index)
    ).all()
    return [ChunkRead.model_validate(chunk) for chunk in chunks]
