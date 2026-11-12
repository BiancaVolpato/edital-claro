"""Runs an analysis in the background and records result, usage and audit data."""

import logging
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import get_settings
from app.db import session as db_session
from app.db.models import Analysis, AnalysisStatus, Chunk, Document, Page
from app.embeddings.base import EmbeddingProvider, Vectors, get_embedding_provider
from app.extraction.pipeline import GroupRun, run_extraction
from app.extraction.prompts import load_prompt_set
from app.extraction.retrieval import ChunkData, embed_chunks
from app.llm.base import MAX_OUTPUT_TOKENS, LLMProvider
from app.llm.budget import BudgetedLLM
from app.llm.factory import get_llm_provider
from app.risks.assessment import assess_risks
from app.risks.law_repository import (
    DatabaseLawRepository,
    InMemoryLawRepository,
    LawRepository,
)
from app.risks.prompts import load_risk_prompt_set

logger = logging.getLogger(__name__)

STRATEGY_SECTIONS = "sections"


def create_analysis(session: Session, document: Document, llm: LLMProvider) -> Analysis:
    """Register a pending analysis with its full audit trail."""
    settings = get_settings()
    prompt = load_prompt_set(settings.extraction_prompt_version)
    risk_prompt = load_risk_prompt_set(settings.risk_prompt_version)
    analysis = Analysis(
        document_id=document.id,
        status=AnalysisStatus.PENDING.value,
        strategy=STRATEGY_SECTIONS,
        prompt_version=prompt.version,
        prompt_hash=prompt.content_hash,
        llm_provider=llm.name,
        llm_model=llm.model,
        embedding_model=settings.embedding_model,
        risk_prompt_version=risk_prompt.version,
        risk_prompt_hash=risk_prompt.content_hash,
        cost_limit_usd=settings.analysis_max_cost_usd or None,
        app_version=__version__,
        # Locating the sections, one step per extraction group, one per risk topic.
        steps_total=1 + len(prompt.groups) + len(risk_prompt.topics),
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


def get_law_repository(session: Session, embedder: EmbeddingProvider) -> LawRepository:
    """The indexed law in the database, or the law file when it is not indexed there."""
    database = DatabaseLawRepository(session, embedder)
    try:
        if database.is_indexed():
            return database
    except SQLAlchemyError:
        session.rollback()  # e.g. a database without the law table (tests on SQLite)
    logger.warning("law not indexed in the database; using the law file in memory")
    return InMemoryLawRepository(embedder)


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

    settings = get_settings()
    # Extraction and risk calls share one spending limit per analysis.
    llm = BudgetedLLM(llm or get_llm_provider(), settings.analysis_max_cost_usd, MAX_OUTPUT_TOKENS)
    embedder = embedder or get_embedding_provider()
    prompt = load_prompt_set(analysis.prompt_version)
    vectors = _chunk_vectors(session, chunks, embedder)

    analysis.steps_done = 1
    session.commit()

    def on_progress(done: int, total: int) -> None:
        analysis.steps_done = 1 + done
        session.commit()

    chunk_data = [_to_chunk_data(chunk) for chunk in chunks]
    outcome = run_extraction(
        pages=pages,
        chunks=chunk_data,
        chunk_vectors=vectors,
        prompt=prompt,
        llm=llm,
        embedder=embedder,
        max_concurrency=settings.llm_max_concurrency,
        on_progress=on_progress,
    )
    runs = list(outcome.runs)
    warnings = [
        f"O grupo '{run.group}' não pôde ser extraído: {run.error}"
        for run in outcome.runs
        if run.error
    ]

    if len(outcome.failed_groups) == len(outcome.runs):
        # Nothing was extracted: do not present an empty result as an analysis.
        _record_usage(analysis, runs, warnings, started)
        _finish(session, analysis, AnalysisStatus.FAILED, outcome.runs[0].error)
        logger.warning("analysis failed: every call failed", extra=log_context)
        return

    analysis.result = outcome.extraction.model_dump(mode="json")
    analysis.citation_counts = outcome.citation_counts
    session.commit()

    # Risks build on the extraction. A failure here keeps the extracted fields.
    risk_steps_start = 1 + len(prompt.groups)

    def on_risk_progress(done: int, total: int) -> None:
        analysis.steps_done = risk_steps_start + done
        session.commit()

    risk_count = 0
    if analysis.risk_prompt_version:
        try:
            risk_outcome = assess_risks(
                extraction=outcome.extraction,
                pages=pages,
                chunks=chunk_data,
                chunk_vectors=vectors,
                law=get_law_repository(session, embedder),
                prompt=load_risk_prompt_set(analysis.risk_prompt_version),
                llm=llm,
                embedder=embedder,
                max_concurrency=settings.llm_max_concurrency,
                on_progress=on_risk_progress,
            )
        except Exception:
            session.rollback()
            logger.exception("risk analysis failed", extra=log_context)
            warnings.append("A análise de riscos falhou; os campos extraídos foram mantidos.")
        else:
            runs += risk_outcome.runs
            warnings += risk_outcome.report.warnings
            analysis.risks = risk_outcome.report.model_dump(mode="json")
            risk_count = len(risk_outcome.report.risks)

    analysis.steps_done = analysis.steps_total
    _record_usage(analysis, runs, warnings, started)
    _finish(session, analysis, AnalysisStatus.COMPLETED, None)
    logger.info(
        "analysis completed",
        extra={
            **log_context,
            "prompt_version": analysis.prompt_version,
            "prompt_hash": analysis.prompt_hash,
            "risk_prompt_version": analysis.risk_prompt_version,
            "risk_prompt_hash": analysis.risk_prompt_hash,
            "llm_model": analysis.llm_model,
            "input_tokens": analysis.input_tokens,
            "output_tokens": analysis.output_tokens,
            "cost_usd": analysis.cost_usd,
            "latency_ms": analysis.latency_ms,
            "citations": analysis.citation_counts,
            "risks": risk_count,
            "failed_calls": [run.group for run in runs if run.error],
        },
    )


def _record_usage(
    analysis: Analysis, runs: list[GroupRun], warnings: list[str], started: float
) -> None:
    """Store the per-call records and their totals on the analysis."""
    costs = [run.cost_usd for run in runs if not run.error]
    analysis.runs = [asdict(run) for run in runs]
    analysis.input_tokens = sum(run.input_tokens for run in runs)
    analysis.output_tokens = sum(run.output_tokens for run in runs)
    # The total is unknown if any call was served by a model without a known price.
    analysis.cost_usd = (
        None if any(cost is None for cost in costs) else round(sum(c for c in costs if c), 6)
    )
    analysis.latency_ms = round((time.perf_counter() - started) * 1000, 1)
    analysis.warnings = warnings
