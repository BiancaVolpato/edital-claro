"""Evaluate the law search and write eval/law_search/RESULTADOS.md.

Runs the known questions through the three search modes (hybrid, vector only,
full-text only) and reports recall@5 and the rank of the expected article.

Usage (from the backend folder, with the database running and the law indexed):
    uv run python scripts/eval_law_search.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import LawProvision
from app.db.session import new_session
from app.law.evaluation import (
    EVAL_DIR,
    MODES,
    QuestionResult,
    evaluate,
    mean_reciprocal_rank,
    query_embedder,
    recall,
)

K = 5
TARGET = 0.8
MODE_LABELS = {"hybrid": "Híbrida", "vector": "Só vetorial", "lexical": "Só texto (full-text)"}


def _rank(result: QuestionResult) -> str:
    return str(result.rank) if result.rank else "fora"


def main() -> int:
    session = new_session()
    try:
        indexed = session.scalar(select(func.count()).select_from(LawProvision))
        if not indexed:
            print("A lei não está indexada. Rode antes: uv run python scripts/index_law.py")
            return 1
        embedder = query_embedder()
        results = {mode: evaluate(session, embedder, mode, K) for mode in MODES}
        embedder.save()
    finally:
        session.close()

    hybrid = results["hybrid"]
    lines = [
        "# Busca na Lei 14.133/2021: resultados",
        "",
        f"Gerado por `backend/scripts/eval_law_search.py` em {date.today():%d/%m/%Y}.",
        "",
        f"- Dispositivos indexados: {indexed}",
        f"- Modelo de embeddings: `{get_settings().embedding_model}`",
        f"- Perguntas: {len(hybrid)} (em `questions.json`)",
        f"- Métrica: recall@{K}, a fração das perguntas em que um dispositivo do artigo "
        f"esperado aparece entre os {K} primeiros resultados",
        f"- Meta: recall@{K} de pelo menos {TARGET:.1f}".replace(".", ","),
        "",
        "## Resumo por modo de busca",
        "",
        f"| Modo | Recall@{K} | Acertos | MRR |",
        "| --- | --- | --- | --- |",
    ]
    for mode in MODES:
        found = sum(1 for result in results[mode] if result.rank)
        lines.append(
            f"| {MODE_LABELS[mode]} | {recall(results[mode]):.2f} | {found}/{len(results[mode])} "
            f"| {mean_reciprocal_rank(results[mode]):.2f} |".replace(".", ",")
        )
    lines += [
        "",
        "MRR (mean reciprocal rank) é a média de 1/posição do artigo esperado: 1,00 significa "
        "que ele veio sempre em primeiro lugar.",
        "",
        "## Posição do artigo esperado, por pergunta",
        "",
        "| Pergunta | Artigo esperado | Híbrida | Só vetorial | Só texto |",
        "| --- | --- | --- | --- | --- |",
    ]
    for position, result in enumerate(hybrid):
        expected = ", ".join(f"Art. {n}" for n in result.question.expected_articles)
        ranks = " | ".join(_rank(results[mode][position]) for mode in MODES)
        lines.append(f"| {result.question.question} | {expected} | {ranks} |")
    lines += ["", "## Resultados da busca híbrida", ""]
    for result in hybrid:
        lines += [
            f"**{result.question.question}** (esperado: Art. "
            f"{', '.join(map(str, result.question.expected_articles))})",
            "",
        ]
        for position, hit in enumerate(result.hits, start=1):
            mark = " ✔" if hit.article in result.question.expected_articles else ""
            text = hit.text if len(hit.text) <= 160 else f"{hit.text[:160]}..."
            lines.append(f"{position}. `{hit.identifier}`{mark}: {text}")
        lines.append("")

    output = EVAL_DIR / "RESULTADOS.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    achieved = recall(hybrid)
    print(f"recall@{K} (híbrida) = {achieved:.2f}; relatório em {output}")
    return 0 if achieved >= TARGET else 2


if __name__ == "__main__":
    raise SystemExit(main())
