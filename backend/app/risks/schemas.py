"""Schemas of the risk analysis.

A risk is only reported when it is anchored at both ends: a validated quote
from the edital and a provision retrieved from the indexed law.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.extraction.schemas import Citation, ValidatedCitation

Severity = Literal["baixa", "media", "alta"]
RiskOrigin = Literal["rule", "llm"]
Audience = Literal["licitante", "orgao"]

SEVERITY_ORDER: dict[str, int] = {"alta": 0, "media": 1, "baixa": 2}


class LegalBasis(BaseModel):
    citation: str  # e.g. "Lei 14.133/2021, Art. 58, § 1º"
    identifier: str  # e.g. "Art. 58, § 1º"
    text: str  # wording of the provision, as indexed from the official text


class Risk(BaseModel):
    type: str  # stable code, e.g. "garantia_proposta_acima_do_limite"
    severity: Severity
    title: str
    description: str  # what was found and why it is a problem
    # The same finding matters differently to each side. A note is null when the
    # risk is not relevant to that audience.
    bidder_note: str | None  # "pay attention to this"
    agency_note: str | None  # "this may be challenged"
    citations: list[ValidatedCitation]  # where it is in the edital
    legal_basis: list[LegalBasis]
    origin: RiskOrigin


class DiscardedRisk(BaseModel):
    """A finding from the LLM that was dropped because it could not be grounded."""

    title: str
    reason: str


class RiskReport(BaseModel):
    risks: list[Risk]
    discarded: list[DiscardedRisk]
    warnings: list[str]


class AudienceRisk(BaseModel):
    """A risk as presented to one audience."""

    type: str
    severity: Severity
    title: str
    message: str  # the note written for this audience
    description: str
    citations: list[ValidatedCitation]
    legal_basis: list[LegalBasis]
    origin: RiskOrigin


def for_audience(report: RiskReport, audience: Audience) -> list[AudienceRisk]:
    """The risks that concern one audience, each with the note written for it."""
    view: list[AudienceRisk] = []
    for risk in report.risks:
        message = risk.bidder_note if audience == "licitante" else risk.agency_note
        if message:
            view.append(
                AudienceRisk(
                    type=risk.type,
                    severity=risk.severity,
                    title=risk.title,
                    message=message,
                    description=risk.description,
                    citations=risk.citations,
                    legal_basis=risk.legal_basis,
                    origin=risk.origin,
                )
            )
    return view


# --- What the LLM returns ----------------------------------------------------


class RiskFinding(BaseModel):
    type: str = Field(
        description="Rótulo curto em snake_case, ex.: 'atestado_com_limitacao_de_local'."
    )
    severity: Severity = Field(
        description="alta: contraria texto expresso da lei; media: provável restrição indevida, "
        "depende de justificativa; baixa: ponto de atenção."
    )
    title: str = Field(description="Título curto do risco, em uma linha.")
    description: str = Field(
        description="O que o edital exige e por que isso é um problema à luz do dispositivo citado."
    )
    bidder_note: str | None = Field(
        description="Orientação prática para a empresa licitante. Nulo se não se aplica."
    )
    agency_note: str | None = Field(
        description="Alerta para o órgão: por que a cláusula pode ser impugnada e como corrigir. "
        "Nulo se não se aplica."
    )
    citation: Citation = Field(description="Trecho literal do edital onde está a exigência.")
    legal_basis: list[str] = Field(
        description="Identificadores copiados exatamente da lista de dispositivos fornecida, "
        "ex.: 'Art. 67, § 2º'."
    )


class RiskFindings(BaseModel):
    risks: list[RiskFinding] = Field(description="Lista vazia se nenhum risco foi identificado.")
