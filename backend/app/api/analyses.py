"""Analysis endpoints: start an analysis and read its status, fields and risks."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Analysis, Document, DocumentStatus
from app.db.session import get_session
from app.extraction.schemas import EditalExtraction
from app.extraction.service import create_analysis, process_analysis
from app.llm.base import LLMNotConfiguredError
from app.llm.factory import get_llm_provider
from app.reports.markdown import render_analysis
from app.risks.schemas import Audience, AudienceRisk, RiskReport, for_audience

router = APIRouter(tags=["analyses"])

SessionDep = Annotated[Session, Depends(get_session)]


class AnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    status: str
    error: str | None
    steps_done: int
    steps_total: int
    # Audit trail
    strategy: str
    prompt_version: str
    prompt_hash: str
    llm_provider: str
    llm_model: str
    embedding_model: str
    risk_prompt_version: str | None
    risk_prompt_hash: str | None
    # Result and usage
    result: EditalExtraction | None
    risks: RiskReport | None
    runs: list[dict[str, Any]]
    citation_counts: dict[str, int]
    warnings: list[str]
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    latency_ms: float | None
    created_at: datetime
    completed_at: datetime | None


@router.post("/documents/{document_id}/analyze", status_code=status.HTTP_202_ACCEPTED)
def analyze_document(
    document_id: uuid.UUID, background_tasks: BackgroundTasks, session: SessionDep
) -> AnalysisRead:
    """Start the extraction of a processed document. Poll GET /analyses/{id} for the result."""
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento não encontrado.")
    if document.status != DocumentStatus.READY.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"O documento ainda não está pronto para análise (status: {document.status}).",
        )

    try:
        llm = get_llm_provider()
    except LLMNotConfiguredError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "A análise com IA não está configurada neste servidor (falta a chave da API).",
        ) from None

    analysis = create_analysis(session, document, llm)
    background_tasks.add_task(process_analysis, analysis.id, llm)
    return AnalysisRead.model_validate(analysis)


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: uuid.UUID, session: SessionDep) -> AnalysisRead:
    """Status, progress and (when completed) the extracted fields with citations and cost."""
    analysis = session.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Análise não encontrada.")
    return AnalysisRead.model_validate(analysis)


class AudienceRisksRead(BaseModel):
    analysis_id: uuid.UUID
    audience: Audience
    risks: list[AudienceRisk]


@router.get("/analyses/{analysis_id}/risks")
def get_risks(
    analysis_id: uuid.UUID,
    session: SessionDep,
    audience: Annotated[
        Audience,
        Query(description="licitante: pontos de atenção; orgao: o que pode gerar impugnação"),
    ] = "licitante",
) -> AudienceRisksRead:
    """The risks of a completed analysis, written for one audience, most severe first."""
    analysis = session.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Análise não encontrada.")
    if analysis.risks is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Esta análise não tem riscos disponíveis (status: {analysis.status}).",
        )
    report = RiskReport.model_validate(analysis.risks)
    return AudienceRisksRead(
        analysis_id=analysis.id, audience=audience, risks=for_audience(report, audience)
    )


class AnalysisSummary(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    status: str
    steps_done: int
    steps_total: int
    object: str | None  # extracted object of the edital, when available
    agency: str | None
    created_at: datetime
    completed_at: datetime | None


def _extracted(analysis: Analysis, name: str) -> str | None:
    value = ((analysis.result or {}).get(name) or {}).get("value")
    return value if isinstance(value, str) else None


@router.get("/analyses")
def list_analyses(
    session: SessionDep,
    document_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[AnalysisSummary]:
    """Most recent analyses first, optionally of one document."""
    query = select(Analysis, Document.filename).join(Document)
    if document_id is not None:
        query = query.where(Analysis.document_id == document_id)
    rows = session.execute(query.order_by(Analysis.created_at.desc()).limit(limit)).all()
    return [
        AnalysisSummary(
            id=analysis.id,
            document_id=analysis.document_id,
            filename=filename,
            status=analysis.status,
            steps_done=analysis.steps_done,
            steps_total=analysis.steps_total,
            object=_extracted(analysis, "object"),
            agency=_extracted(analysis, "agency"),
            created_at=analysis.created_at,
            completed_at=analysis.completed_at,
        )
        for analysis, filename in rows
    ]


@router.get("/analyses/{analysis_id}/report.md", response_class=PlainTextResponse)
def export_analysis(
    analysis_id: uuid.UUID,
    session: SessionDep,
    audience: Audience = "licitante",
) -> PlainTextResponse:
    """The analysis as a Markdown file: fields, checklist and risks, with their citations."""
    analysis = session.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Análise não encontrada.")
    if analysis.result is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Esta análise ainda não tem resultado (status: {analysis.status}).",
        )
    content = render_analysis(
        filename=analysis.document.filename,
        extraction=EditalExtraction.model_validate(analysis.result),
        risks=RiskReport.model_validate(analysis.risks) if analysis.risks else None,
        audience=audience,
        generated_at=datetime.now(UTC),
    )
    return PlainTextResponse(
        content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="analise-{analysis.id}.md"'},
    )
