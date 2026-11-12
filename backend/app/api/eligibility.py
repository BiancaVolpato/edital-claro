"""Eligibility endpoint: compares a company profile with an analysed edital."""

import datetime as dt
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.profiles import get_profile_or_404
from app.core.config import get_settings
from app.db.models import Analysis, AnalysisStatus, EligibilityCheck
from app.db.session import get_session
from app.eligibility.profile import CompanyProfileData
from app.eligibility.records import record_eligibility_check
from app.eligibility.schemas import EligibilityReport
from app.llm.base import LLMNotConfiguredError, LLMProvider
from app.llm.factory import get_llm_provider
from app.reports.markdown import render_eligibility

logger = logging.getLogger(__name__)
router = APIRouter(tags=["eligibility"])

SessionDep = Annotated[Session, Depends(get_session)]


def optional_llm() -> LLMProvider | None:
    """Without credentials the check still runs; only the attestation comparison is skipped.

    The public demo never calls the LLM, so visitors cannot spend money with it.
    """
    if get_settings().demo_mode:
        return None
    try:
        return get_llm_provider()
    except LLMNotConfiguredError:
        return None


def today() -> dt.date:
    return dt.date.today()


class EligibilityRequest(BaseModel):
    profile_id: uuid.UUID


class EligibilityRead(BaseModel):
    id: uuid.UUID
    analysis_id: uuid.UUID
    profile_id: uuid.UUID | None
    profile_snapshot: CompanyProfileData
    report: EligibilityReport
    prompt_version: str
    prompt_hash: str
    llm_model: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    cost_limit_usd: float | None
    app_version: str | None
    created_at: datetime


def _to_read(check: EligibilityCheck) -> EligibilityRead:
    return EligibilityRead(
        id=check.id,
        analysis_id=check.analysis_id,
        profile_id=check.profile_id,
        profile_snapshot=CompanyProfileData.model_validate(check.profile_snapshot),
        report=EligibilityReport.model_validate(check.report),
        prompt_version=check.prompt_version,
        prompt_hash=check.prompt_hash,
        llm_model=check.llm_model,
        input_tokens=check.input_tokens,
        output_tokens=check.output_tokens,
        cost_usd=check.cost_usd,
        cost_limit_usd=check.cost_limit_usd,
        app_version=check.app_version,
        created_at=check.created_at,
    )


def _get_check_or_404(session: Session, check_id: uuid.UUID) -> EligibilityCheck:
    check = session.get(EligibilityCheck, check_id)
    if check is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verificação de aptidão não encontrada.")
    return check


@router.post("/analyses/{analysis_id}/eligibility", status_code=status.HTTP_201_CREATED)
def check_eligibility(
    analysis_id: uuid.UUID,
    body: EligibilityRequest,
    session: SessionDep,
    llm: Annotated[LLMProvider | None, Depends(optional_llm)],
    reference_today: Annotated[dt.date, Depends(today)],
) -> EligibilityRead:
    """Compare a profile with the requirements of a completed analysis.

    Runs synchronously: at most one LLM call (the attestation comparison).
    """
    analysis = session.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Análise não encontrada.")
    if analysis.status != AnalysisStatus.COMPLETED.value or analysis.result is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A análise ainda não tem os campos extraídos (status: {analysis.status}).",
        )
    profile_row = get_profile_or_404(session, body.profile_id)
    check, outcome = record_eligibility_check(session, analysis, profile_row, llm, reference_today)
    logger.info(
        "eligibility checked",
        extra={
            "analysis_id": str(analysis.id),
            "eligibility_id": str(check.id),
            "verdict": outcome.report.summary.verdict,
            "counts": outcome.report.summary.counts,
            "prompt_hash": check.prompt_hash,
            "input_tokens": check.input_tokens,
            "output_tokens": check.output_tokens,
            "cost_usd": check.cost_usd,
        },
    )
    return _to_read(check)


@router.get("/analyses/{analysis_id}/eligibility")
def list_eligibility_checks(analysis_id: uuid.UUID, session: SessionDep) -> list[EligibilityRead]:
    """Checks already made on this analysis, newest first."""
    if session.get(Analysis, analysis_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Análise não encontrada.")
    checks = session.scalars(
        select(EligibilityCheck)
        .where(EligibilityCheck.analysis_id == analysis_id)
        .order_by(EligibilityCheck.created_at.desc())
    ).all()
    return [_to_read(check) for check in checks]


@router.get("/eligibility/{check_id}")
def get_eligibility(check_id: uuid.UUID, session: SessionDep) -> EligibilityRead:
    """A stored eligibility check, as it was produced."""
    return _to_read(_get_check_or_404(session, check_id))


@router.get("/eligibility/{check_id}/report.md", response_class=PlainTextResponse)
def export_eligibility(check_id: uuid.UUID, session: SessionDep) -> PlainTextResponse:
    """The eligibility report as a Markdown file."""
    check = _get_check_or_404(session, check_id)
    analysis = session.get(Analysis, check.analysis_id)
    content = render_eligibility(
        filename=analysis.document.filename if analysis else "edital",
        company=str(check.profile_snapshot.get("name", "empresa")),
        report=EligibilityReport.model_validate(check.report),
        generated_at=datetime.now(UTC),
    )
    return PlainTextResponse(
        content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="aptidao-{check.id}.md"'},
    )
