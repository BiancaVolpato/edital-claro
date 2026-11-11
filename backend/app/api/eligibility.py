"""Eligibility endpoint: compares a company profile with an analysed edital."""

import datetime as dt
import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.profiles import get_profile_or_404
from app.core.config import get_settings
from app.db.models import Analysis, AnalysisStatus, EligibilityCheck
from app.db.session import get_session
from app.eligibility.profile import CompanyProfileData
from app.eligibility.prompts import load_eligibility_prompt
from app.eligibility.schemas import EligibilityReport
from app.eligibility.service import evaluate_eligibility
from app.extraction.schemas import EditalExtraction
from app.llm.base import LLMNotConfiguredError, LLMProvider
from app.llm.factory import get_llm_provider

logger = logging.getLogger(__name__)
router = APIRouter(tags=["eligibility"])

SessionDep = Annotated[Session, Depends(get_session)]


def optional_llm() -> LLMProvider | None:
    """Without credentials the check still runs; only the attestation comparison is skipped."""
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
    created_at: datetime


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
    profile = CompanyProfileData.model_validate(profile_row.data)
    prompt = load_eligibility_prompt(get_settings().eligibility_prompt_version)

    outcome = evaluate_eligibility(
        extraction=EditalExtraction.model_validate(analysis.result),
        profile=profile,
        llm=llm,
        prompt=prompt,
        today=reference_today,
    )
    run = outcome.run
    check = EligibilityCheck(
        analysis_id=analysis.id,
        profile_id=profile_row.id,
        profile_snapshot=profile.model_dump(mode="json"),
        report=outcome.report.model_dump(mode="json"),
        prompt_version=prompt.version,
        prompt_hash=prompt.content_hash,
        llm_model=run.model if run else None,
        input_tokens=run.input_tokens if run else 0,
        output_tokens=run.output_tokens if run else 0,
        cost_usd=run.cost_usd if run else 0.0,
    )
    session.add(check)
    session.commit()
    session.refresh(check)
    logger.info(
        "eligibility checked",
        extra={
            "analysis_id": str(analysis.id),
            "eligibility_id": str(check.id),
            "verdict": outcome.report.summary.verdict,
            "counts": outcome.report.summary.counts,
            "prompt_hash": prompt.content_hash,
            "input_tokens": check.input_tokens,
            "output_tokens": check.output_tokens,
            "cost_usd": check.cost_usd,
        },
    )
    return EligibilityRead(
        id=check.id,
        analysis_id=check.analysis_id,
        profile_id=check.profile_id,
        profile_snapshot=profile,
        report=outcome.report,
        prompt_version=check.prompt_version,
        prompt_hash=check.prompt_hash,
        llm_model=check.llm_model,
        input_tokens=check.input_tokens,
        output_tokens=check.output_tokens,
        cost_usd=check.cost_usd,
        created_at=check.created_at,
    )
