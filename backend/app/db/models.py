"""ORM models for ingested documents."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# JSONB on PostgreSQL; plain JSON elsewhere so the test suite can also run on SQLite.
JsonType = JSON().with_variant(JSONB(), "postgresql")


class DocumentSource(StrEnum):
    UPLOAD = "upload"
    PNCP = "pncp"


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ChunkKind(StrEnum):
    PREAMBLE = "preamble"  # text before the first numbered clause
    CLAUSE = "clause"  # body of the edital
    ANNEX = "annex"  # anything inside an "ANEXO" (contract draft, forms, ...)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(20))
    # Where the file came from when not uploaded (e.g. the PNCP control number).
    source_ref: Mapped[str | None] = mapped_column(String(500))
    filename: Mapped[str] = mapped_column(String(255))
    file_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 hex digest
    file_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=DocumentStatus.PENDING.value)
    error: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    # PDF metadata plus ingestion notes (pages that went through OCR, warnings).
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    pages: Mapped[list["Page"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="Page.number"
    )
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="Chunk.index"
    )


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("document_id", "number", name="uq_pages_document_number"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)  # 1-based, as shown by PDF viewers
    text: Mapped[str] = mapped_column(Text)  # normalized text
    ocr: Mapped[bool] = mapped_column(Boolean, default=False)

    document: Mapped[Document] = relationship(back_populates="pages")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("document_id", "index", name="uq_chunks_document_index"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    index: Mapped[int] = mapped_column(Integer)  # reading order within the document
    kind: Mapped[str] = mapped_column(String(20))
    heading: Mapped[str | None] = mapped_column(String(500))
    text: Mapped[str] = mapped_column(Text)
    page_start: Mapped[int] = mapped_column(Integer)
    page_end: Mapped[int] = mapped_column(Integer)
    # [[page number, character offset where that page begins in ``text``], ...]
    page_spans: Mapped[list[list[int]]] = mapped_column(JsonType, default=list)
    # Cached embedding (float32 bytes) and the model that produced it. A per-document
    # search covers a few hundred chunks at most, so it is done in memory.
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String(200))

    document: Mapped[Document] = relationship(back_populates="chunks")


class AnalysisStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Analysis(Base):
    """One extraction run over a document, with everything needed to audit it."""

    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default=AnalysisStatus.PENDING.value)
    error: Mapped[str | None] = mapped_column(Text)
    steps_done: Mapped[int] = mapped_column(Integer, default=0)
    steps_total: Mapped[int] = mapped_column(Integer, default=0)

    # Audit trail: what produced this result.
    strategy: Mapped[str] = mapped_column(String(50))
    prompt_version: Mapped[str] = mapped_column(String(100))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    llm_provider: Mapped[str] = mapped_column(String(50))
    llm_model: Mapped[str] = mapped_column(String(100))
    embedding_model: Mapped[str] = mapped_column(String(200))
    # Nullable: analyses created before the risk analysis existed have none.
    risk_prompt_version: Mapped[str | None] = mapped_column(String(100))
    risk_prompt_hash: Mapped[str | None] = mapped_column(String(64))

    # Result (EditalExtraction as JSON), risks (RiskReport as JSON) and per-call usage.
    result: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    risks: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    runs: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, default=list)
    citation_counts: Mapped[dict[str, int]] = mapped_column(JsonType, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JsonType, default=list)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[Document] = relationship()


# Output size of the embedding model the law index was built with (multilingual-e5-base).
# Changing EMBEDDING_MODEL to a model with another size requires a migration and re-indexing.
LAW_EMBEDDING_DIMENSIONS = 768


class LawProvision(Base):
    """One provision of a statute (article, paragraph, inciso, alínea), searchable.

    PostgreSQL-only: it relies on pgvector and on full-text search.
    """

    __tablename__ = "law_provisions"
    __table_args__ = (
        UniqueConstraint("law", "identifier", name="uq_law_provisions_law_identifier"),
        # No approximate (HNSW/IVFFlat) index on ``embedding`` on purpose: with a few
        # thousand rows an exact scan takes milliseconds and always returns the true
        # nearest neighbours, also when filtering by law or right after re-indexing.
        Index("ix_law_provisions_search", "search", postgresql_using="gin"),
        {"info": {"postgres_only": True}},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    law: Mapped[str] = mapped_column(String(50))  # e.g. "Lei 14.133/2021"
    identifier: Mapped[str] = mapped_column(String(100))  # e.g. "Art. 67, § 1º, II"
    kind: Mapped[str] = mapped_column(String(20))
    article: Mapped[int] = mapped_column(Integer, index=True)
    parent: Mapped[str | None] = mapped_column(String(100))
    position: Mapped[int] = mapped_column(Integer)  # reading order within the law
    heading: Mapped[str] = mapped_column(Text)  # chapter/section titles
    text: Mapped[str] = mapped_column(Text)  # the provision's own wording
    # Own text preceded by its section titles and enclosing provisions; this is
    # what gets embedded and indexed, so an inciso is searchable by its article's subject.
    context: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(LAW_EMBEDDING_DIMENSIONS))
    search: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('portuguese', context)", persisted=True)
    )


class CompanyProfile(Base):
    """A bidder's profile (``CompanyProfileData``), compared against editais."""

    __tablename__ = "company_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    # The whole profile as validated JSON. Its nested lists (attestations,
    # certificates) are only ever read together with the profile.
    data: Mapped[dict[str, Any]] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EligibilityCheck(Base):
    """One comparison of a profile with an analysis, kept as it was produced."""

    __tablename__ = "eligibility_checks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    # Kept when the profile is deleted: the snapshot below is what was compared.
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("company_profiles.id", ondelete="SET NULL"), index=True
    )
    profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JsonType)
    report: Mapped[dict[str, Any]] = mapped_column(JsonType)
    # Audit trail of the attestation comparison (the only LLM step).
    prompt_version: Mapped[str] = mapped_column(String(100))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    llm_model: Mapped[str | None] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
