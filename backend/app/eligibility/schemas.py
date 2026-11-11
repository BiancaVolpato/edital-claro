"""Schemas of the eligibility report and of the attestation comparison."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from app.extraction.schemas import ValidatedCitation

# atende: the profile meets the requirement; nao_atende: it does not;
# nao_verificavel: the profile lacks the data, or the requirement could not be read.
RequirementStatus = Literal["atende", "nao_atende", "nao_verificavel"]
Verdict = Literal["apto", "apto_com_ressalvas", "inapto"]
Section = Literal["participacao", "juridica", "fiscal", "tecnica", "economica"]
RequirementKind = Literal[
    "porte",
    "cnpj",
    "objeto_social",
    "certidao",
    "registro_profissional",
    "atestado",
    "capital_ou_patrimonio",
    "indices_contabeis",
    "balanco",
    "declaracao",
    "visita_tecnica",
    "outro",
]
# Whether the decision was made by code alone or used the LLM's comparison of
# attestation descriptions (the numbers are always compared in code).
DecisionOrigin = Literal["code", "llm"]

STATUS_ORDER: dict[RequirementStatus, int] = {"nao_atende": 0, "nao_verificavel": 1, "atende": 2}


class RequirementResult(BaseModel):
    section: Section
    kind: RequirementKind
    requirement: str
    citations: list[ValidatedCitation]
    # The requirement itself was extracted with low confidence: check it in the edital.
    requirement_needs_review: bool
    status: RequirementStatus
    reason: str
    evidence: list[str] = Field(default_factory=list)  # what in the profile was used
    origin: DecisionOrigin = "code"


class CriticalDeadline(BaseModel):
    label: str
    date: dt.date | None
    rule: str | None = None  # the deadline as written in the edital, when it has no date
    source: Literal["edital", "perfil"]
    citations: list[ValidatedCitation] = Field(default_factory=list)


class EligibilitySummary(BaseModel):
    verdict: Verdict
    message: str
    counts: dict[RequirementStatus, int]
    missing: list[str]  # one line per requirement not met
    deadlines: list[CriticalDeadline]


class EligibilityReport(BaseModel):
    summary: EligibilitySummary
    reference_date: dt.date  # date certificates must still be valid on
    results: list[RequirementResult]
    warnings: list[str]


# --- What the LLM returns (attestation comparison) ----------------------------


class ParcelMatch(BaseModel):
    parcel: str = Field(description="Código da parcela, ex.: 'R1.Q1'.")
    compatible_items: list[str] = Field(
        description="Códigos dos itens de atestado do mesmo serviço, ex.: ['A1.2']."
    )
    reason: str = Field(description="Por que esses itens são (ou nenhum é) do mesmo serviço.")


class RequirementMatch(BaseModel):
    requirement: str = Field(description="Código da exigência, ex.: 'R1'.")
    compatible_attestations: list[str] = Field(
        description="Códigos dos atestados compatíveis com a exigência, ex.: ['A1']."
    )
    parcels: list[ParcelMatch]
    reason: str = Field(description="Justificativa curta, em português.")


class AttestationMatches(BaseModel):
    requirements: list[RequirementMatch]
