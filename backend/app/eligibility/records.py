"""Runs an eligibility check and stores it with its audit trail."""

import datetime as dt

from sqlalchemy.orm import Session

from app import __version__
from app.core.config import get_settings
from app.db.models import Analysis, CompanyProfile, EligibilityCheck
from app.eligibility.profile import CompanyProfileData
from app.eligibility.prompts import load_eligibility_prompt
from app.eligibility.service import EligibilityOutcome, evaluate_eligibility
from app.extraction.schemas import EditalExtraction
from app.llm.base import MAX_OUTPUT_TOKENS, LLMProvider
from app.llm.budget import BudgetedLLM


def record_eligibility_check(
    session: Session,
    analysis: Analysis,
    profile_row: CompanyProfile,
    llm: LLMProvider | None,
    today: dt.date,
) -> tuple[EligibilityCheck, EligibilityOutcome]:
    """Compare the profile with a completed analysis and store the result."""
    settings = get_settings()
    profile = CompanyProfileData.model_validate(profile_row.data)
    prompt = load_eligibility_prompt(settings.eligibility_prompt_version)
    budgeted = (
        BudgetedLLM(llm, settings.eligibility_max_cost_usd, MAX_OUTPUT_TOKENS) if llm else None
    )
    outcome = evaluate_eligibility(
        extraction=EditalExtraction.model_validate(analysis.result),
        profile=profile,
        llm=budgeted,
        prompt=prompt,
        today=today,
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
        cost_limit_usd=settings.eligibility_max_cost_usd or None,
        app_version=__version__,
    )
    session.add(check)
    session.commit()
    session.refresh(check)
    return check, outcome
