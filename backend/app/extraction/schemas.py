"""Schemas for the structured extraction of an edital.

``EditalExtraction`` is the single source of truth for which fields exist.
The schema sent to the LLM for each group of fields is derived from it
(``raw_group_model``), so a field is declared only once.

Field names are in English (code); enum values and descriptions are in
Portuguese because they are domain terms of Brazilian procurement law and are
read by the model alongside Portuguese text.
"""

import datetime as dt
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel, Field, create_model

ConfidenceLevel = Literal["alta", "media", "baixa"]
CitationStatus = Literal["valid", "wrong_page", "not_found", "too_short"]

Modality = Literal[
    "concorrencia",
    "pregao",
    "concurso",
    "leilao",
    "dialogo_competitivo",
    "dispensa",
    "inexigibilidade",
    "outra",
]
JudgmentCriterion = Literal[
    "menor_preco",
    "maior_desconto",
    "melhor_tecnica_ou_conteudo_artistico",
    "tecnica_e_preco",
    "maior_lance",
    "maior_retorno_economico",
    "outro",
]
ExecutionRegime = Literal[
    "empreitada_por_preco_unitario",
    "empreitada_por_preco_global",
    "empreitada_integral",
    "contratacao_por_tarefa",
    "contratacao_integrada",
    "contratacao_semi_integrada",
    "fornecimento_e_prestacao_de_servico_associado",
    "outro",
]
SiteVisit = Literal["obrigatoria", "facultativa", "nao_exigida"]


# --- Value types -----------------------------------------------------------


class OpeningSession(BaseModel):
    date: dt.date
    time: str | None = Field(description="Horário no formato HH:MM (24h), se informado.")


class Deadline(BaseModel):
    date: dt.date | None = Field(
        description="Data limite, somente se o edital a indicar por extenso."
    )
    rule: str | None = Field(
        description="Regra do prazo como escrita no edital, "
        "ex.: 'até 3 dias úteis antes da data de abertura'."
    )


class Duration(BaseModel):
    amount: int
    unit: Literal["dias", "meses", "anos"]


class Guarantee(BaseModel):
    required: bool
    percent: float | None = Field(
        description="Percentual exigido, ex.: 5 para 5%. Nulo se não houver percentual."
    )


# --- What the LLM returns ----------------------------------------------------


class Citation(BaseModel):
    page: int = Field(description="Número da página, como aparece no marcador [página N].")
    quote: str = Field(
        description="Trecho literal e contínuo copiado do edital, sem reticências nem alterações."
    )


class RawField[T](BaseModel):
    """A field as returned by the model, before citation validation."""

    value: T | None = Field(description="Nulo quando a informação não está nos trechos fornecidos.")
    citations: list[Citation]
    confidence: ConfidenceLevel


# --- What the system stores and serves ---------------------------------------


class ValidatedCitation(BaseModel):
    page: int  # page where the quote was actually found (corrected when needed)
    quote: str
    status: CitationStatus
    cited_page: int  # page the model pointed to
    match_score: float  # 0-100 similarity between the quote and the page text


class ExtractedField[T](BaseModel):
    value: T | None
    citations: list[ValidatedCitation]
    confidence: float = Field(description="0 to 1, after citation validation.")
    needs_review: bool


class EditalExtraction(BaseModel):
    # identification
    number: ExtractedField[str] = Field(
        description="Número do edital/licitação, ex.: 'Concorrência nº 233/2026'."
    )
    modality: ExtractedField[Modality] = Field(description="Modalidade da licitação.")
    agency: ExtractedField[str] = Field(description="Órgão ou entidade que promove a licitação.")
    object: ExtractedField[str] = Field(description="Objeto da licitação, resumido em uma frase.")
    estimated_value: ExtractedField[float] = Field(
        description="Valor total estimado ou máximo da contratação, em reais (número, sem R$)."
    )
    judgment_criterion: ExtractedField[JudgmentCriterion] = Field(
        description="Critério de julgamento das propostas."
    )
    execution_regime: ExtractedField[ExecutionRegime] = Field(
        description="Regime de execução da obra ou serviço."
    )
    # dates and periods
    publication_date: ExtractedField[dt.date] = Field(
        description="Data de publicação ou de assinatura do edital."
    )
    opening: ExtractedField[OpeningSession] = Field(
        description="Data e horário da sessão pública de abertura."
    )
    impugnation_deadline: ExtractedField[Deadline] = Field(
        description="Prazo para impugnar o edital."
    )
    clarification_deadline: ExtractedField[Deadline] = Field(
        description="Prazo para pedir esclarecimentos."
    )
    execution_period: ExtractedField[Duration] = Field(
        description="Prazo de execução da obra ou serviço (não o de vigência do contrato)."
    )
    # guarantees and participation
    bid_guarantee: ExtractedField[Guarantee] = Field(
        description="Garantia de proposta exigida dos licitantes."
    )
    contract_guarantee: ExtractedField[Guarantee] = Field(
        description="Garantia de execução contratual exigida do vencedor."
    )
    site_visit: ExtractedField[SiteVisit] = Field(description="Visita ou vistoria técnica.")
    consortium_allowed: ExtractedField[bool] = Field(
        description="Se a participação de empresas em consórcio é permitida."
    )
    me_epp_exclusive: ExtractedField[bool] = Field(
        description="Se a licitação é exclusiva para microempresas e empresas de pequeno porte."
    )
    # qualification requirements: one item per requirement
    qualification_legal: list[ExtractedField[str]] = Field(
        description="Exigências de habilitação jurídica, uma por item."
    )
    qualification_fiscal: list[ExtractedField[str]] = Field(
        description="Exigências de regularidade fiscal, social e trabalhista, uma por item."
    )
    qualification_technical: list[ExtractedField[str]] = Field(
        description="Exigências de qualificação técnica, uma por item, com quantitativos."
    )
    qualification_economic: list[ExtractedField[str]] = Field(
        description="Exigências de qualificação econômico-financeira, uma por item, com índices."
    )
    annexes: list[ExtractedField[str]] = Field(
        description="Anexos do edital, um por item, com número e título."
    )


def is_list_field(name: str) -> bool:
    return get_origin(EditalExtraction.model_fields[name].annotation) is list


def _value_type(annotation: Any) -> Any:
    """``ExtractedField[X]`` -> ``X``."""
    return annotation.__pydantic_generic_metadata__["args"][0]


def raw_group_model(name: str, fields: list[str]) -> type[BaseModel]:
    """Build the schema the LLM must fill for one group of fields."""
    definitions: dict[str, Any] = {}
    for field_name in fields:
        info = EditalExtraction.model_fields[field_name]
        annotation = info.annotation
        if get_origin(annotation) is list:
            raw_type: Any = list[RawField[_value_type(get_args(annotation)[0])]]  # type: ignore[misc]
        else:
            raw_type = RawField[_value_type(annotation)]  # type: ignore[misc]
        definitions[field_name] = (raw_type, Field(description=info.description))
    return create_model(name, **definitions)
