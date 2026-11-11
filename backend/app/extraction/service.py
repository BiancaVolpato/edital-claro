"""Runs an analysis in the background and records result, usage and audit data."""

import logging
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import session as db_session
from app.db.models import Analysis, AnalysisStatus, Chunk, Document, Page
from app.embeddings.base import EmbeddingProvider, Vectors, get_embedding_provider
from app.extraction.pipeline import run_extraction
from app.extraction.prompts import load_prompt_set
from app.extraction.retrieval import ChunkData, embed_chunks
from app.llm.base import LLMProvider
from app.llm.factory import get_llm_provider

logger = logging.getLogger(__name__)

STRATEGY_SECTIONS = "sections"


def create_analysis(session: Session, document: Document, llm: LLMProvider) -> Analysis:
    """Register a pending analysis with its full audit trail."""
    settings = get_settings()
    prompt = load_prompt_set(settings.extraction_prompt_version)
    analysis = Analysis(
        document_id=document.id,
        status=AnalysisStatus.PENDING.value,
        strategy=STRATEGY_SECTIONS,
        prompt_version=prompt.version,
        prompt_hash=prompt.content_hash,
        llm_provider=llm.name,
        llm_model=llm.model,
        embedding_model=settings.embedding_model,
        steps_total=len(prompt.groups) + 1,  # +1 for locating the sections
        runs=[],
        citation_counts={},
        warnings=[],
    )
    session.add(analysis)
    session.commit()
    return analysis


def process_analysis(
    analysis_id: uuid.UUID,
    llm: LLMProvider | None = None,
    embedder: EmbeddingProvider | None = None,
) -> None:
    """Run one analysis. Meant for a background task: never raises."""
    session = db_session.new_session()
    try:
        analysis = session.get(Analysis, analysis_id)
        if analysis is None:
            logger.error("analysis not found", extra={"analysis_id": str(analysis_id)})
            return
        try:
            _analyze(session, analysis, llm, embedder)
        except Exception:
            session.rollback()
            logger.exception("analysis failed", extra={"analysis_id": str(analysis_id)})
            _finish(session, analysis, AnalysisStatus.FAILED, "unexpected error during analysis")
    finally:
        session.close()


def _finish(
    session: Session, analysis: Analysis, status: AnalysisStatus, error: str | None
) -> None:
    analysis.status = status.value
    analysis.error = error
    analysis.completed_at = datetime.now(UTC)
    session.commit()


def _chunk_vectors(session: Session, chunks: list[Chunk], embedder: EmbeddingProvider) -> Vectors:
    """Embeddings of all chunks, computing and caching the ones that are missing."""
    data = [_to_chunk_data(chunk) for chunk in chunks]
    stale = [
        position
        for position, chunk in enumerate(chunks)
        if chunk.embedding is None or chunk.embedding_model != embedder.model_name
    ]
    if stale:
        vectors = embed_chunks([data[position] for position in stale], embedder)
        for position, vector in zip(stale, vectors, strict=True):
            chunks[position].embedding = vector.astype(np.float32).tobytes()
            chunks[position].embedding_model = embedder.model_name
        session.commit()
    return np.stack([np.frombuffer(chunk.embedding or b"", dtype=np.float32) for chunk in chunks])


def _to_chunk_data(chunk: Chunk) -> ChunkData:
    # Chunks ingested before page spans existed fall back to their first page.
    spans = [(page, offset) for page, offset in chunk.page_spans] or [(chunk.page_start, 0)]
    return ChunkData(
        index=chunk.index, kind=chunk.kind, heading=chunk.heading, text=chunk.text, page_spans=spans
    )


def _analyze(
    session: Session,
    analysis: Analysis,
    llm: LLMProvider | None,
    embedder: EmbeddingProvider | None,
) -> None:
    started = time.perf_counter()
    log_context = {"analysis_id": str(analysis.id), "document_id": str(analysis.document_id)}

    analysis.status = AnalysisStatus.RUNNING.value
    session.commit()

    pages = dict(
        session.execute(
            select(Page.number, Page.text).where(Page.document_id == analysis.document_id)
        ).all()
    )
    chunks = list(
        session.scalars(
            select(Chunk).where(Chunk.document_id == analysis.document_id).order_by(Chunk.index)
        )
    )
    if not chunks:
        _finish(session, analysis, AnalysisStatus.FAILED, "document has no text to analyze")
        return

    llm = llm or get_llm_provider()
    embedder = embedder or get_embedding_provider()
    prompt = load_prompt_set(analysis.prompt_version)
    vectors = _chunk_vectors(session, chunks, embedder)

    analysis.steps_done = 1
    session.commit()

    def on_progress(done: int, total: int) -> None:
        analysis.steps_done = 1 + done
        session.commit()

    outcome = run_extraction(
        pages=pages,
        chunks=[_to_chunk_data(chunk) for chunk in chunks],
        chunk_vectors=vectors,
        prompt=prompt,
        llm=llm,
        embedder=embedder,
        max_concurrency=get_settings().llm_max_concurrency,
        on_progress=on_progress,
    )

    costs = [run.cost_usd for run in outcome.runs if not run.error]
    analysis.runs = [asdict(run) for run in outcome.runs]
    analysis.input_tokens = sum(run.input_tokens for run in outcome.runs)
    analysis.output_tokens = sum(run.output_tokens for run in outcome.runs)
    # The total is unknown if any call was served by a model without a known price.
    analysis.cost_usd = (
        None if any(cost is None for cost in costs) else round(sum(c for c in costs if c), 6)
    )
    analysis.latency_ms = round((time.perf_counter() - started) * 1000, 1)
    analysis.citation_counts = outcome.citation_counts
    analysis.warnings = [
        f"O grupo '{run.group}' não pôde ser extraído: {run.error}"
        for run in outcome.runs
        if run.error
    ]

    if len(outcome.failed_groups) == len(outcome.runs):
        # Nothing was extracted: do not present an empty result as an analysis.
        _finish(session, analysis, AnalysisStatus.FAILED, outcome.runs[0].error)
        logger.warning("analysis failed: every call failed", extra=log_context)
        return

    analysis.result = outcome.extraction.model_dump(mode="json")
    _finish(session, analysis, AnalysisStatus.COMPLETED, None)
    logger.info(
        "analysis completed",
        extra={
            **log_context,
            "prompt_version": analysis.prompt_version,
            "prompt_hash": analysis.prompt_hash,
            "llm_model": analysis.llm_model,
            "input_tokens": analysis.input_tokens,
            "output_tokens": analysis.output_tokens,
            "cost_usd": analysis.cost_usd,
            "latency_ms": analysis.latency_ms,
            "citations": analysis.citation_counts,
            "failed_groups": outcome.failed_groups,
        },
    )
