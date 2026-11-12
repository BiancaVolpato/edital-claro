"""eval/RESULTADOS.md: tables per variant and field, worst cases and error analysis."""

import datetime as dt
from typing import Any

from app.evaluation.golden import GoldenCase
from app.evaluation.runner import Variant
from app.evaluation.scoring import FIELD_GROUPS, FieldScore, PrecisionRecall, VariantSummary
from app.reports.markdown import FIELD_LABELS, LIST_LABELS

# A cheaper variant is recommended when it is at most this far behind in accuracy.
ACCURACY_TOLERANCE = 0.02
OUTCOME_LABELS = {
    "wrong": "valor errado",
    "missed": "não encontrado (o edital tem a informação)",
    "hallucinated": "valor inventado (o edital não tem a informação)",
}


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%".replace(".", ",")


def money(value: float | None) -> str:
    return "—" if value is None else f"US$ {value:.3f}".replace(".", ",")


def _show(value: Any) -> str:
    if value is None:
        return "*(nulo)*"
    if isinstance(value, dict):
        value = {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in value.items()}
    if isinstance(value, dt.date):
        value = value.isoformat()
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= 90 else f"{text[:87]}..."


def _pr(score: PrecisionRecall) -> str:
    return f"{pct(score.precision)} / {pct(score.recall)} / {pct(score.f1)}"


def recommend(summaries: list[VariantSummary]) -> tuple[VariantSummary, str]:
    """The best variant by accuracy, unless a cheaper one is within the tolerance."""
    best = max(summaries, key=lambda s: s.accuracy)
    cheaper = [
        s
        for s in summaries
        if s is not best
        and best.accuracy - s.accuracy <= ACCURACY_TOLERANCE
        and s.mean_cost_usd is not None
        and best.mean_cost_usd is not None
        and s.mean_cost_usd < best.mean_cost_usd
    ]
    if cheaper:
        choice = min(cheaper, key=lambda s: s.mean_cost_usd or 0)
        reason = (
            f"`{choice.variant}` fica a até {pct(ACCURACY_TOLERANCE)} da mais precisa "
            f"(`{best.variant}`, {pct(best.accuracy)}) e custa menos por edital "
            f"({money(choice.mean_cost_usd)} contra {money(best.mean_cost_usd)})."
        )
        return choice, reason
    return best, f"`{best.variant}` tem a maior acurácia nos campos ({pct(best.accuracy)})."


def _error_rows(summary: VariantSummary, limit: int) -> list[tuple[str, FieldScore]]:
    errors = [(e.name, f) for e in summary.editais for f in e.fields if not f.correct]
    # Unflagged errors first: they are the ones a reader would trust by mistake.
    errors.sort(key=lambda item: (item[1].needs_review, item[1].outcome))
    return errors[:limit]


def render_report(
    *,
    summaries: list[VariantSummary],
    variants: list[Variant],
    cases: list[GoldenCase],
    prompt_version: str,
    prompt_hash: str,
    generated_at: dt.datetime,
) -> str:
    by_name = {v.name: v for v in variants}
    reference = summaries[0]
    reviewed = sum(case.golden.annotation.reviewed for case in cases)
    lines = [
        "# Resultados da avaliação da extração",
        "",
        f"Gerado por `just eval` em {generated_at.strftime('%d/%m/%Y %H:%M')}, com o prompt "
        f"`{prompt_version}` ({prompt_hash}), sobre {len(cases)} edital(is) do gabarito "
        f"(`eval/golden/`), dos quais {reviewed} revisado(s).",
        "",
    ]
    if reviewed < len(cases) or len(cases) < 15:
        lines += [
            "> **Números preliminares.** O gabarito ainda tem editais não revisados ou menos "
            "de 15 editais; os números servem para comparar variantes, não como medida final.",
            "",
        ]

    lines += [
        "## Resumo por variante",
        "",
        "| Variante | Modelo | Estratégia | Acurácia dos campos "
        "| Exigências (precisão / recall / F1) "
        "| Anexos (recall) | Citações válidas | Citação na página do gabarito | Custo médio por "
        "edital | Tempo médio por edital |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in summaries:
        v = by_name[s.variant]
        lines.append(
            f"| `{s.variant}` | {v.model} | {v.strategy} | {pct(s.accuracy)} "
            f"| {_pr(s.requirements)} "
            f"| {pct(s.list_score(['annexes']).recall)} | {pct(s.citation_valid_rate)} "
            f"| {pct(s.citation_page_rate)} | {money(s.mean_cost_usd)} | {s.mean_latency_s:.0f} s |"
        )
    choice, reason = recommend(summaries)
    lines += [
        "",
        f"**Escolha pelos números:** `{choice.variant}`. {reason} A decisão fica registrada no "
        "ADR-035 de `docs/DECISOES.md`.",
        "",
        "## Acurácia por campo",
        "",
        "| Campo | " + " | ".join(f"`{s.variant}`" for s in summaries) + " |",
        "| --- | " + " | ".join("---" for _ in summaries) + " |",
    ]
    for group, names in FIELD_GROUPS.items():
        lines.append(
            f"| **{group.capitalize()}** | "
            + " | ".join(f"**{pct(s.group_accuracy(group))}**" for s in summaries)
            + " |"
        )
        for name in names:
            lines.append(
                f"| {FIELD_LABELS[name]} | "
                + " | ".join(pct(s.field_accuracy(name)) for s in summaries)
                + " |"
            )

    lines += [
        "",
        "## Exigências de habilitação e anexos",
        "",
        "Precisão / recall / F1 de cada lista, somando todos os editais.",
        "",
        "| Lista | " + " | ".join(f"`{s.variant}`" for s in summaries) + " |",
        "| --- | " + " | ".join("---" for _ in summaries) + " |",
    ]
    for name, label in LIST_LABELS.items():
        lines.append(
            f"| {label} | " + " | ".join(_pr(s.list_score([name])) for s in summaries) + " |"
        )

    lines += [
        "",
        f"## Por edital (`{reference.variant}`)",
        "",
        "| Edital | Acurácia | Exigências (P / R / F1) | Citações válidas | Custo | Tempo "
        "| Chamadas com falha |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for e in sorted(reference.editais, key=lambda e: e.accuracy):
        single = VariantSummary(reference.variant, [e])
        lines.append(
            f"| {e.name} | {pct(e.accuracy)} | {_pr(single.requirements)} "
            f"| {pct(single.citation_valid_rate)} | {money(e.cost_usd)} | {e.latency_s:.0f} s "
            f"| {', '.join(e.failed_calls) or '—'} |"
        )

    outcomes = reference.outcomes
    total = sum(outcomes.values())
    errors = total - outcomes["correct"]
    lines += [
        "",
        f"## Análise de erros (`{reference.variant}`)",
        "",
        f"{errors} erro(s) em {total} campos avaliados.",
        "",
        "| Categoria | Quantidade | Parte dos erros |",
        "| --- | --- | --- |",
    ]
    for outcome, label in OUTCOME_LABELS.items():
        count = outcomes[outcome]
        lines.append(
            f"| {label.capitalize()} | {count} | {pct(count / errors if errors else None)} |"
        )
    lines += [
        "",
        f"- Erros que o sistema marcou para revisão (valor errado ou inventado com confiança "
        f'baixa): {pct(reference.review_recall)}. Quanto maior, mais o selo "Revisar" protege '
        "o usuário.",
        "- Acertos sem citação confirmada no texto: "
        f"{reference.unconfirmed_correct}. O valor estava "
        "certo, mas o trecho citado não foi achado; o campo aparece para revisão sem necessidade.",
    ]
    reqs = [
        item
        for e in reference.editais
        for item in e.lists
        if item.name.startswith("qualification_")
    ]
    lines += [
        f"- Exigências do gabarito não extraídas: {sum(len(i.missed) for i in reqs)}; itens "
        f"extraídos sem par no gabarito: {sum(len(i.extra) for i in reqs)}.",
        "",
        "Erros por grupo de campos:",
        "",
        "| Grupo | Errados | Não encontrados | Inventados |",
        "| --- | --- | --- | --- |",
    ]
    for group, names in FIELD_GROUPS.items():
        group_scores = [f for f in reference.field_scores if f.name in names]
        counts = {o: sum(f.outcome == o for f in group_scores) for o in OUTCOME_LABELS}
        lines.append(
            f"| {group.capitalize()} | {counts['wrong']} | {counts['missed']} "
            f"| {counts['hallucinated']} |"
        )

    lines += [
        "",
        f"## Piores casos (`{reference.variant}`)",
        "",
        'Erros sem o selo "Revisar" aparecem primeiro: são os que um leitor aceitaria sem '
        "conferir.",
        "",
        "| Edital | Campo | Esperado | Extraído | Categoria | Marcado para revisão |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    rows = _error_rows(reference, limit=20)
    if not rows:
        lines.append("| — | — | — | — | — | — |")
    for edital, f in rows:
        lines.append(
            f"| {edital} | {FIELD_LABELS[f.name]} | {_show(f.expected)} | {_show(f.predicted)} "
            f"| {OUTCOME_LABELS[f.outcome]} | {'sim' if f.needs_review else 'não'} |"
        )
    examples = [
        (e.name, item) for e in reference.editais for item in e.lists if item.missed or item.extra
    ]
    if examples:
        lines += ["", "Exigências e anexos sem par (até 10 exemplos):", ""]
        shown = 0
        for edital, item in examples:
            for missed in item.missed:
                if shown < 10:
                    lines.append(f'- {edital}, {LIST_LABELS[item.name]}: faltou "{_show(missed)}"')
                    shown += 1
            for extra in item.extra:
                if shown < 10:
                    lines.append(f'- {edital}, {LIST_LABELS[item.name]}: a mais "{_show(extra)}"')
                    shown += 1

    lines += [
        "",
        "## Como os números são calculados",
        "",
        "- **Acurácia dos campos:** proporção de campos certos entre os 17 campos de valor único, "
        'contando como certo responder "não informado" quando o gabarito é nulo. Datas, valores, '
        "opções e estruturas precisam ser iguais; textos são comparados por semelhança "
        "(órgão e número a partir de 80%, objeto a partir de 70%, com os mesmos números no número "
        "do edital).",
        "- **Exigências e anexos:** cada item extraído é pareado com no máximo um item do "
        "gabarito por semelhança de texto (a partir de 70%). Precisão = pares / itens extraídos; "
        "recall = pares / itens do gabarito.",
        "- **Citações válidas:** citações encontradas no texto do edital (na página indicada ou "
        "em outra) sobre o total de citações.",
        "- **Citação na página do gabarito:** campos com valor cuja citação confirmada está numa "
        "das páginas anotadas.",
        "- **Custo e tempo:** soma das chamadas de extração de cada edital (custo estimado pela "
        "tabela de preços em `backend/app/llm/pricing.py`) e tempo total da extração, com até "
        "3 chamadas em paralelo.",
        "",
        "As regras de anotação estão em [ANOTACAO.md](ANOTACAO.md) e as variantes em "
        "[variants.toml](variants.toml). Os resultados brutos de cada edital ficam em "
        "`eval/runs/`, e `just eval --reuse` refaz este relatório a partir deles sem chamar o "
        "modelo.",
    ]
    return "\n".join(lines) + "\n"
