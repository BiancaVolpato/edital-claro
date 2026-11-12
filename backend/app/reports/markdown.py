"""Markdown reports of an analysis and of an eligibility check.

Markdown is the export format because it is readable as plain text, pastes into
any editor and converts to PDF or DOCX with common tools. Every value keeps the
page and the quote it came from, as on screen.
"""

import datetime as dt
from typing import Any

from app.eligibility.checks import brl
from app.eligibility.schemas import EligibilityReport, RequirementResult
from app.extraction.schemas import EditalExtraction, ExtractedField, ValidatedCitation
from app.risks.schemas import Audience, RiskReport, for_audience

DISCLAIMER = (
    "> Relatório gerado pelo Edital Claro com apoio de IA. É um apoio à leitura do edital e "
    "não substitui parecer jurídico. Confira cada informação no trecho citado."
)

FIELD_LABELS: dict[str, str] = {
    "number": "Número",
    "modality": "Modalidade",
    "agency": "Órgão",
    "object": "Objeto",
    "estimated_value": "Valor estimado",
    "judgment_criterion": "Critério de julgamento",
    "execution_regime": "Regime de execução",
    "publication_date": "Data de publicação",
    "opening": "Abertura da sessão",
    "impugnation_deadline": "Prazo de impugnação",
    "clarification_deadline": "Prazo de esclarecimentos",
    "execution_period": "Prazo de execução",
    "bid_guarantee": "Garantia de proposta",
    "contract_guarantee": "Garantia contratual",
    "site_visit": "Visita técnica",
    "consortium_allowed": "Consórcio permitido",
    "me_epp_exclusive": "Exclusiva para ME/EPP",
}
LIST_LABELS: dict[str, str] = {
    "qualification_legal": "Habilitação jurídica",
    "qualification_fiscal": "Regularidade fiscal, social e trabalhista",
    "qualification_technical": "Qualificação técnica",
    "qualification_economic": "Qualificação econômico-financeira",
    "annexes": "Anexos",
}
SEVERITY_LABELS = {"alta": "Alta", "media": "Média", "baixa": "Baixa"}
STATUS_LABELS = {
    "atende": "Atende",
    "nao_atende": "Não atende",
    "nao_verificavel": "Verificar",
}
VERDICT_LABELS = {
    "apto": "Apto",
    "apto_com_ressalvas": "Apto, com itens a conferir",
    "inapto": "Inapto",
}


def _date(value: Any) -> str:
    if isinstance(value, str):
        value = dt.date.fromisoformat(value)
    return value.strftime("%d/%m/%Y") if isinstance(value, dt.date) else str(value)


def format_value(name: str, value: Any) -> str:
    """A field value as a person reads it."""
    if value is None:
        return "Não encontrado"
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    if name == "estimated_value":
        return brl(float(value))
    if isinstance(value, dt.date):
        return _date(value)
    if isinstance(value, dict):
        if "time" in value and "date" in value:  # opening session
            time = f" às {value['time']}" if value.get("time") else ""
            return f"{_date(value['date'])}{time}"
        if "rule" in value:  # deadline
            parts = [_date(value["date"])] if value.get("date") else []
            if value.get("rule"):
                parts.append(value["rule"])
            return " — ".join(parts) or "Não encontrado"
        if "amount" in value:  # duration
            return f"{value['amount']} {value['unit']}"
        if "required" in value:  # guarantee
            if not value["required"]:
                return "Não exigida"
            percent = value.get("percent")
            return f"Exigida ({percent:g}%)".replace(".", ",") if percent else "Exigida"
    if isinstance(value, str) and "_" in value and " " not in value:  # enum code
        return value.replace("_", " ").capitalize()
    return str(value)


def _cite(citations: list[ValidatedCitation]) -> str:
    confirmed = [c for c in citations if c.status in ("valid", "wrong_page")]
    if not confirmed:
        return "sem trecho confirmado"
    return "; ".join(f'p. {c.page}: "{c.quote.strip()}"' for c in confirmed)


def _escape(text: str) -> str:
    """Make text safe inside a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ")


def _field_row(name: str, label: str, field: ExtractedField[Any]) -> str:
    review = " ⚠ revisar" if field.needs_review else ""
    cells = [
        label,
        format_value(name, field.value),
        f"{round(field.confidence * 100)}%{review}",
        _cite(field.citations),
    ]
    return "| " + " | ".join(_escape(cell) for cell in cells) + " |"


def render_analysis(
    *,
    filename: str,
    extraction: EditalExtraction,
    risks: RiskReport | None,
    audience: Audience,
    generated_at: dt.datetime,
) -> str:
    lines = [
        f"# Análise do edital: {filename}",
        "",
        f"Gerado em {generated_at.strftime('%d/%m/%Y %H:%M')}.",
        "",
        DISCLAIMER,
        "",
        "## Campos extraídos",
        "",
        "| Campo | Valor | Confiança | Origem no edital |",
        "| --- | --- | --- | --- |",
    ]
    for name, label in FIELD_LABELS.items():
        lines.append(_field_row(name, label, getattr(extraction, name)))
    for name, label in LIST_LABELS.items():
        items: list[ExtractedField[str]] = getattr(extraction, name)
        lines += ["", f"## {label}", ""]
        if not items:
            lines.append("Nenhum item encontrado.")
        for item in items:
            review = " (⚠ revisar)" if item.needs_review else ""
            lines.append(f"- [ ] {item.value}{review} — {_cite(item.citations)}")

    who = "a empresa licitante" if audience == "licitante" else "o órgão"
    lines += ["", f"## Riscos (orientação para {who})", ""]
    if risks is None:
        lines.append("A análise de riscos não está disponível.")
    else:
        view = for_audience(risks, audience)
        if not view:
            lines.append("Nenhum risco apontado para este público.")
        for risk in view:
            basis = "; ".join(b.citation for b in risk.legal_basis)
            origin = "regra" if risk.origin == "rule" else "IA"
            lines += [
                f"### [{SEVERITY_LABELS[risk.severity]}] {risk.title}",
                "",
                risk.description,
                "",
                f"**Orientação:** {risk.message}",
                "",
                f"- Trecho do edital: {_cite(risk.citations)}",
                f"- Fundamentação: {basis} (origem: {origin})",
                "",
            ]
    return "\n".join(lines).rstrip() + "\n"


def _result_line(result: RequirementResult) -> str:
    review = " (⚠ exigência a revisar no edital)" if result.requirement_needs_review else ""
    return (
        f"- **{STATUS_LABELS[result.status]}** — {result.requirement}{review}\n"
        f"  - Motivo: {result.reason}\n"
        f"  - Origem no edital: {_cite(result.citations)}"
    )


def render_eligibility(
    *, filename: str, company: str, report: EligibilityReport, generated_at: dt.datetime
) -> str:
    summary = report.summary
    lines = [
        f"# Aptidão de {company}",
        "",
        f"Edital: {filename}. Gerado em {generated_at.strftime('%d/%m/%Y %H:%M')}. "
        f"Validades conferidas em {_date(report.reference_date)}.",
        "",
        DISCLAIMER,
        "",
        f"## Veredito: {VERDICT_LABELS[summary.verdict]}",
        "",
        summary.message,
        "",
        f"- Atende: {summary.counts.get('atende', 0)}",
        f"- Não atende: {summary.counts.get('nao_atende', 0)}",
        f"- Verificar: {summary.counts.get('nao_verificavel', 0)}",
        "",
        "## O que falta",
        "",
    ]
    lines += [f"- {item}" for item in summary.missing] or [
        "Nada pendente entre os itens conferidos."
    ]
    lines += ["", "## Prazos críticos", ""]
    if not summary.deadlines:
        lines.append("Nenhum prazo identificado.")
    for deadline in summary.deadlines:
        when = _date(deadline.date) if deadline.date else (deadline.rule or "sem data")
        lines.append(f"- {when}: {deadline.label}")
    lines += ["", "## Exigências", ""]
    lines += [_result_line(result) for result in report.results] or ["Nenhuma exigência."]
    if report.warnings:
        lines += ["", "## Avisos", ""] + [f"- {w}" for w in report.warnings]
    return "\n".join(lines).rstrip() + "\n"
