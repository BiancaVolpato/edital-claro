"""Runs the extraction over the golden set, one variant at a time.

Each edital's raw result (the extraction, its usage and timing) is saved to
eval/runs/<variant>/<edital>.json. With ``reuse``, a saved result produced by the
same prompt is scored again without calling the LLM, so the report can be
regenerated (or the scoring rules changed) at no cost.
"""

import json
import logging
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.embeddings.base import EmbeddingProvider
from app.evaluation.golden import GoldenCase
from app.evaluation.scoring import EditalScore, VariantSummary, score_edital
from app.extraction.pipeline import Strategy, run_extraction
from app.extraction.prompts import PromptSet
from app.extraction.retrieval import ChunkData, embed_chunks
from app.extraction.schemas import EditalExtraction
from app.ingestion.chunking import chunk_pages
from app.ingestion.extract import extract_pdf
from app.ingestion.normalize import normalize_pages
from app.ingestion.ocr import OcrEngine
from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Variant:
    name: str
    model: str
    strategy: Strategy
    description: str


def load_variants(path: Path) -> list[Variant]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))["variants"]
    return [
        Variant(
            name=name,
            model=spec["model"],
            strategy=spec.get("strategy", "sections"),
            description=spec.get("description", ""),
        )
        for name, spec in data.items()
    ]


@dataclass(frozen=True)
class PreparedDocument:
    pages: dict[int, str]
    chunks: list[ChunkData]
    vectors: Any


def prepare(
    case: GoldenCase, embedder: EmbeddingProvider, ocr: OcrEngine | None
) -> PreparedDocument:
    """Ingest a PDF in memory, as the application does (text, OCR, chunks, embeddings)."""
    extracted = extract_pdf(case.pdf.read_bytes(), ocr)
    texts = normalize_pages([page.text for page in extracted.pages])
    chunks = [
        ChunkData(c.index, c.kind.value, c.heading, c.text, c.page_spans)
        for c in chunk_pages(texts, max_chars=get_settings().chunk_max_chars)
    ]
    return PreparedDocument(dict(enumerate(texts, start=1)), chunks, embed_chunks(chunks, embedder))


def _run_file(runs_dir: Path, variant: Variant, case: GoldenCase) -> Path:
    return runs_dir / variant.name / f"{case.name}.json"


def run_variant(
    *,
    variant: Variant,
    cases: list[GoldenCase],
    prompt: PromptSet,
    llm_for: Callable[[str], LLMProvider],
    embedder: EmbeddingProvider,
    runs_dir: Path,
    reuse: bool,
    prepared: dict[str, PreparedDocument],
    ocr: OcrEngine | None = None,
    log: Callable[[str], None] = print,
) -> VariantSummary:
    scores: list[EditalScore] = []
    for case in cases:
        saved_path = _run_file(runs_dir, variant, case)
        saved = _load(saved_path) if reuse else None
        if (
            saved
            and saved.get("prompt_hash") == prompt.content_hash
            and saved.get("model") == variant.model
        ):
            log(f"  {case.name}: resultado salvo reaproveitado")
        else:
            if case.name not in prepared:
                prepared[case.name] = prepare(case, embedder, ocr)
            document = prepared[case.name]
            log(f"  {case.name}: extraindo ({len(document.pages)} páginas)...")
            started = time.perf_counter()
            outcome = run_extraction(
                pages=document.pages,
                chunks=document.chunks,
                chunk_vectors=document.vectors,
                prompt=prompt,
                llm=llm_for(variant.model),
                embedder=embedder,
                max_concurrency=get_settings().llm_max_concurrency,
                strategy=variant.strategy,
            )
            costs = [run.cost_usd for run in outcome.runs]
            saved = {
                "variant": variant.name,
                "model": variant.model,
                "strategy": variant.strategy,
                "prompt_version": prompt.version,
                "prompt_hash": prompt.content_hash,
                "latency_s": round(time.perf_counter() - started, 2),
                "cost_usd": None
                if any(c is None for c in costs)
                else round(sum(c or 0 for c in costs), 6),
                "input_tokens": sum(run.input_tokens for run in outcome.runs),
                "output_tokens": sum(run.output_tokens for run in outcome.runs),
                "failed_calls": outcome.failed_groups,
                "citation_counts": outcome.citation_counts,
                "extraction": outcome.extraction.model_dump(mode="json"),
            }
            saved_path.parent.mkdir(parents=True, exist_ok=True)
            saved_path.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
        scores.append(
            score_edital(
                case.name,
                case.golden,
                EditalExtraction.model_validate(saved["extraction"]),
                saved["citation_counts"],
                saved["cost_usd"],
                saved["latency_s"],
                saved["failed_calls"],
            )
        )
    return VariantSummary(variant=variant.name, editais=scores)


def _load(path: Path) -> dict[str, Any] | None:
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data
