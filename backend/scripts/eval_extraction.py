"""Evaluate the extraction against the hand-annotated golden set (eval/golden/).

Runs every variant of eval/variants.toml over every annotated edital, scores the
results and writes eval/RESULTADOS.md. It calls the real LLM, so it needs
ANTHROPIC_API_KEY and costs money; --reuse scores the results already saved in
eval/runs/ again without calling the model.

Usage (from the backend folder):
    uv run python scripts/eval_extraction.py --check              # validate the golden set only
    uv run python scripts/eval_extraction.py                      # all variants, all editais
    uv run python scripts/eval_extraction.py --variants opus-secoes --limit 3
    uv run python scripts/eval_extraction.py --reuse              # rebuild the report for free
"""

import argparse
import datetime as dt
import sys
from functools import cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.embeddings.base import EmbeddingProvider, Vectors, get_embedding_provider
from app.evaluation.golden import GoldenError, load_golden
from app.evaluation.report import pct, render_report
from app.evaluation.runner import PreparedDocument, load_variants, run_variant
from app.extraction.prompts import load_prompt_set
from app.ingestion.service import default_ocr_engine
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProvider

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "eval"


class LazyEmbedder:
    """Loads the embedding model (about 1 GB) only if some edital needs extracting."""

    def __init__(self) -> None:
        self.model_name = get_settings().embedding_model
        self._model: EmbeddingProvider | None = None

    def _get(self) -> EmbeddingProvider:
        if self._model is None:
            self._model = get_embedding_provider()
        return self._model

    def embed_passages(self, texts: list[str]) -> Vectors:
        return self._get().embed_passages(texts)

    def embed_queries(self, texts: list[str]) -> Vectors:
        return self._get().embed_queries(texts)


@cache
def llm_for(model: str) -> LLMProvider:
    key = get_settings().anthropic_api_key
    if key is None or not key.get_secret_value():
        sys.exit(
            "ANTHROPIC_API_KEY não está configurada no .env. Para refazer o relatório com os "
            "resultados já salvos, use --reuse."
        )
    return AnthropicProvider(model=model, api_key=key.get_secret_value())


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="só valida o gabarito")
    parser.add_argument("--variants", help="variantes separadas por vírgula (padrão: todas)")
    parser.add_argument("--limit", type=int, help="avalia só os N primeiros editais")
    parser.add_argument(
        "--reuse", action="store_true", help="reaproveita resultados salvos em eval/runs"
    )
    parser.add_argument("--output", type=Path, default=EVAL_DIR / "RESULTADOS.md")
    args = parser.parse_args()

    try:
        cases = load_golden(EVAL_DIR / "golden", REPO_ROOT)
    except GoldenError as exc:
        sys.exit(f"Gabarito com problemas:\n{exc}")
    if not cases:
        sys.exit("Nenhum edital anotado em eval/golden/ (veja eval/ANOTACAO.md).")
    reviewed = sum(case.golden.annotation.reviewed for case in cases)
    print(f"Gabarito: {len(cases)} edital(is), {reviewed} revisado(s).")
    if args.check:
        for case in cases:
            flag = "revisado" if case.golden.annotation.reviewed else "NÃO revisado"
            print(f"  {case.name}: ok ({flag})")
        return
    if args.limit:
        cases = cases[: args.limit]

    variants = load_variants(EVAL_DIR / "variants.toml")
    if args.variants:
        wanted = [name.strip() for name in args.variants.split(",")]
        unknown = set(wanted) - {v.name for v in variants}
        if unknown:
            sys.exit(f"Variantes desconhecidas: {', '.join(sorted(unknown))}")
        variants = [v for v in variants if v.name in wanted]

    prompt = load_prompt_set(get_settings().extraction_prompt_version)
    embedder = LazyEmbedder()
    prepared: dict[str, PreparedDocument] = {}
    summaries = []
    for variant in variants:
        print(f"\n== {variant.name} ({variant.model}, {variant.strategy})")
        summary = run_variant(
            variant=variant,
            cases=cases,
            prompt=prompt,
            llm_for=llm_for,
            embedder=embedder,
            runs_dir=EVAL_DIR / "runs",
            reuse=args.reuse,
            prepared=prepared,
            ocr=default_ocr_engine(),
        )
        requirements = summary.requirements
        print(
            f"   acurácia {pct(summary.accuracy)}, exigências P {pct(requirements.precision)} "
            f"R {pct(requirements.recall)}, citações válidas {pct(summary.citation_valid_rate)}"
        )
        summaries.append(summary)

    args.output.write_text(
        render_report(
            summaries=summaries,
            variants=variants,
            cases=cases,
            prompt_version=prompt.version,
            prompt_hash=prompt.content_hash,
            generated_at=dt.datetime.now(),
        ),
        encoding="utf-8",
    )
    print(f"\nRelatório: {args.output}")


if __name__ == "__main__":
    main()
