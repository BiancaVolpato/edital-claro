"""Builds the eligibility report of a company profile against an analysed edital."""

import datetime as dt
from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.eligibility.attestations import compare_attestations
from app.eligibility.checks import (
    MANUAL_REASONS,
    CheckContext,
    Outcome,
    br_date,
    check_capital_or_net_worth,
    check_certificates,
    check_cnpj,
    check_company_purpose,
    check_company_size,
    check_registration,
)
from app.eligibility.profile import CERTIFICATE_LABELS, CompanyProfileData
from app.eligibility.prompts import EligibilityPrompt
from app.eligibility.requirements import Requirement, collect_requirements
from app.eligibility.schemas import (
    CriticalDeadline,
    EligibilityReport,
    EligibilitySummary,
    RequirementResult,
    RequirementStatus,
    Verdict,
)
from app.extraction.pipeline import GroupRun
from app.extraction.schemas import EditalExtraction, ExtractedField, ValidatedCitation
from app.llm.base import LLMProvider


@dataclass(frozen=True)
class EligibilityOutcome:
    report: EligibilityReport
    run: GroupRun | None


def _confirmed(extracted: ExtractedField[Any]) -> list[ValidatedCitation]:
    return [c for c in extracted.citations if c.status in ("valid", "wrong_page")]


def _supported(extracted: ExtractedField[Any]) -> bool:
    """Same rule as the risk rules: a value backed by at least one confirmed quote."""
    return extracted.value is not None and bool(_confirmed(extracted))


def _reference_date(extraction: EditalExtraction, today: dt.date, warnings: list[str]) -> dt.date:
    """The date certificates must be valid on: the opening session, if still ahead."""
    if not _supported(extraction.opening):
        warnings.append(
            "A data de abertura não foi extraída com citação confirmada; as validades foram "
            f"conferidas na data de hoje ({br_date(today)})."
        )
        return today
    opening: dt.date = extraction.opening.value.date  # type: ignore[union-attr]
    if opening < today:
        warnings.append(
            f"A sessão de abertura ({br_date(opening)}) já passou; as validades foram "
            f"conferidas na data de hoje ({br_date(today)})."
        )
        return today
    return opening


def _check(requirement: Requirement, context: CheckContext) -> Outcome:
    match requirement.kind:
        case "certidao":
            return check_certificates(requirement, context)
        case "registro_profissional":
            return check_registration(requirement, context)
        case "capital_ou_patrimonio":
            return check_capital_or_net_worth(requirement, context)
        case "cnpj":
            return check_cnpj(context)
        case "objeto_social":
            return check_company_purpose(context)
        case _:
            return Outcome(
                "nao_verificavel", MANUAL_REASONS.get(requirement.kind, MANUAL_REASONS["outro"])
            )


def _deadlines(
    extraction: EditalExtraction, profile: CompanyProfileData, reference: dt.date
) -> list[CriticalDeadline]:
    deadlines: list[CriticalDeadline] = []
    if _supported(extraction.opening):
        deadlines.append(
            CriticalDeadline(
                label="Sessão pública de abertura",
                date=extraction.opening.value.date,  # type: ignore[union-attr]
                source="edital",
                citations=_confirmed(extraction.opening),
            )
        )
    for label, extracted in (
        ("Prazo para impugnar o edital", extraction.impugnation_deadline),
        ("Prazo para pedir esclarecimentos", extraction.clarification_deadline),
    ):
        if _supported(extracted):
            deadlines.append(
                CriticalDeadline(
                    label=label,
                    date=extracted.value.date,  # type: ignore[union-attr]
                    rule=extracted.value.rule,  # type: ignore[union-attr]
                    source="edital",
                    citations=_confirmed(extracted),
                )
            )
    if _supported(extraction.site_visit) and extraction.site_visit.value == "obrigatoria":
        deadlines.append(
            CriticalDeadline(
                label="Visita técnica obrigatória: agende antes da abertura",
                date=None,
                source="edital",
                citations=_confirmed(extraction.site_visit),
            )
        )
    for certificate in profile.certificates:
        if certificate.valid_until <= reference:
            deadlines.append(
                CriticalDeadline(
                    label=f"Renovar: {CERTIFICATE_LABELS[certificate.kind]}",
                    date=certificate.valid_until,
                    source="perfil",
                )
            )
    registration = profile.registration
    if registration and registration.valid_until and registration.valid_until <= reference:
        deadlines.append(
            CriticalDeadline(
                label=f"Renovar a certidão de registro no {registration.council}",
                date=registration.valid_until,
                source="perfil",
            )
        )
    return sorted(deadlines, key=lambda d: (d.date is None, d.date or dt.date.max))


def _summary(
    results: list[RequirementResult], deadlines: list[CriticalDeadline]
) -> EligibilitySummary:
    counts: Counter[RequirementStatus] = Counter(result.status for result in results)
    missing = [
        f"{result.requirement} — {result.reason}"
        for result in results
        if result.status == "nao_atende"
    ]
    verdict: Verdict
    if not results:
        verdict = "apto_com_ressalvas"
        message = (
            "Nenhuma exigência de habilitação foi extraída do edital; não é possível concluir. "
            "Confira o edital manualmente."
        )
    elif counts["nao_atende"]:
        verdict = "inapto"
        message = (
            f"A empresa não atende {counts['nao_atende']} de {len(results)} exigências. "
            "Veja o que falta antes de participar."
        )
    elif counts["nao_verificavel"]:
        verdict = "apto_com_ressalvas"
        message = (
            "Nenhuma exigência conferida impede a participação, mas "
            f"{counts['nao_verificavel']} de {len(results)} precisam de conferência manual."
        )
    else:
        verdict = "apto"
        message = f"A empresa atende as {len(results)} exigências conferidas."
    return EligibilitySummary(
        verdict=verdict,
        message=message,
        counts={status: counts[status] for status in ("atende", "nao_atende", "nao_verificavel")},
        missing=missing,
        deadlines=deadlines,
    )


def evaluate_eligibility(
    *,
    extraction: EditalExtraction,
    profile: CompanyProfileData,
    llm: LLMProvider | None,
    prompt: EligibilityPrompt,
    today: dt.date,
) -> EligibilityOutcome:
    """Compare the profile with every extracted requirement, one result per requirement."""
    warnings: list[str] = []
    reference = _reference_date(extraction, today, warnings)
    context = CheckContext(
        profile=profile,
        reference_date=reference,
        estimated_value=(
            extraction.estimated_value.value if _supported(extraction.estimated_value) else None
        ),
    )
    requirements = collect_requirements(extraction)
    if not requirements:
        warnings.append("Nenhuma exigência de habilitação foi extraída do edital.")

    results: list[RequirementResult] = []
    if _supported(extraction.me_epp_exclusive) and extraction.me_epp_exclusive.value:
        outcome = check_company_size(context)
        results.append(
            RequirementResult(
                section="participacao",
                kind="porte",
                requirement="Licitação exclusiva para microempresas e empresas de pequeno porte.",
                citations=_confirmed(extraction.me_epp_exclusive),
                requirement_needs_review=extraction.me_epp_exclusive.needs_review,
                status=outcome.status,
                reason=outcome.reason,
                evidence=outcome.evidence,
            )
        )

    attestation = compare_attestations(
        [r for r in requirements if r.kind == "atestado"], profile.attestations, llm, prompt
    )
    warnings += attestation.warnings
    for requirement in requirements:
        by_llm = requirement.code in attestation.outcomes
        outcome = attestation.outcomes[requirement.code] if by_llm else _check(requirement, context)
        results.append(
            RequirementResult(
                section=requirement.section,
                kind=requirement.kind,
                requirement=requirement.text,
                citations=requirement.field.citations,
                requirement_needs_review=requirement.field.needs_review,
                status=outcome.status,
                reason=outcome.reason,
                evidence=outcome.evidence,
                origin="llm"
                if by_llm and attestation.run and not attestation.run.error
                else "code",
            )
        )

    report = EligibilityReport(
        summary=_summary(results, _deadlines(extraction, profile, reference)),
        reference_date=reference,
        results=results,
        warnings=warnings,
    )
    return EligibilityOutcome(report=report, run=attestation.run)
