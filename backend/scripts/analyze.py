"""Analyze one edital from the command line, without the API or a database.

Runs the same pipeline as POST /documents/{id}/analyze (extraction, chunking,
section retrieval, LLM calls, citation validation) fully in memory and prints
a summary. It calls the real LLM, so it needs ANTHROPIC_API_KEY and costs money.

Usage (from the backend folder):
    uv run python scripts/analyze.py ../data/samples/lauro_muller_cc_233_2026.pdf
    uv run python scripts/analyze.py edital.pdf --output resultado.json
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.embeddings.base import get_embedding_provider
from app.extraction.pipeline import run_extraction
from app.extraction.prompts import load_prompt_set
from app.extraction.retrieval import ChunkData, embed_chunks
from app.extraction.schemas import EditalExtraction
from app.ingestion.chunking import chunk_pages
from app.ingestion.extract import extract_pdf
from app.ingestion.normalize import normalize_pages
from app.ingestion.service import default_ocr_engine
from app.llm.base import LLMNotConfiguredError
from app.llm.factory import get_llm_provider


def _describe(field: dict[str, Any]) -> str:
    pages = sorted({citation["page"] for citation in field["citations"]})
    unconfirmed = [c["status"] for c in field["citations"] if c["status"] != "valid"]
    flags = " REVISAR" if field["needs_review"] else ""
    notes = f" citações não confirmadas: {unconfirmed}" if unconfirmed else ""
    return f"{field['value']!r}  (confiança {field['confidence']}, pág. {pages}){flags}{notes}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf", type=Path, help="edital em PDF")
    parser.add_argument("--output", type=Path, help="grava o resultado completo em JSON")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    settings = get_settings()
    try:
        llm = get_llm_provider()
    except LLMNotConfiguredError:
        print("Chave da API não encontrada. Defina ANTHROPIC_API_KEY no arquivo .env da raiz.")
        return 1

    started = time.perf_counter()
    extraction = extract_pdf(args.pdf.read_bytes(), default_ocr_engine())
    texts = normalize_pages([page.text for page in extraction.pages])
    chunks = [
        ChunkData(c.index, c.kind.value, c.heading, c.text, c.page_spans)
        for c in chunk_pages(texts, max_chars=settings.chunk_max_chars)
    ]
    print(f"{args.pdf.name}: {len(texts)} páginas, {len(chunks)} trechos")
    for warning in extraction.warnings:
        print(f"AVISO: {warning}")

    print(f"Localizando seções com {settings.embedding_model} (pode levar alguns minutos)...")
    embedder = get_embedding_provider()
    vectors = embed_chunks(chunks, embedder)

    prompt = load_prompt_set(settings.extraction_prompt_version)
    print(f"Extraindo com {llm.model}, prompt {prompt.version} ({prompt.content_hash})...")
    outcome = run_extraction(
        pages=dict(enumerate(texts, start=1)),
        chunks=chunks,
        chunk_vectors=vectors,
        prompt=prompt,
        llm=llm,
        embedder=embedder,
        max_concurrency=settings.llm_max_concurrency,
        on_progress=lambda done, total: print(f"  grupo {done}/{total} concluído"),
    )

    result = outcome.extraction.model_dump(mode="json")
    print("\n=== Campos ===")
    for name in EditalExtraction.model_fields:
        value = result[name]
        if isinstance(value, list):
            print(f"{name}: {len(value)} itens")
            for item in value:
                print(f"  - {_describe(item)}")
        else:
            print(f"{name}: {_describe(value)}")

    costs = [run.cost_usd for run in outcome.runs if not run.error]
    total_cost = None if any(cost is None for cost in costs) else sum(c for c in costs if c)
    print("\n=== Resumo ===")
    print(f"Citações: {outcome.citation_counts}")
    print(
        f"Tokens: {sum(r.input_tokens for r in outcome.runs)} de entrada, "
        f"{sum(r.output_tokens for r in outcome.runs)} de saída"
    )
    print(f"Custo estimado: {'desconhecido' if total_cost is None else f'US$ {total_cost:.4f}'}")
    print(f"Tempo total: {time.perf_counter() - started:.1f} s")
    for run in outcome.runs:
        if run.error:
            print(f"FALHA no grupo {run.group}: {run.error}")

    if args.output:
        payload = {
            "result": result,
            "runs": [run.__dict__ for run in outcome.runs],
            "citation_counts": outcome.citation_counts,
            "prompt_version": prompt.version,
            "prompt_hash": prompt.content_hash,
            "llm_model": llm.model,
        }
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Resultado completo gravado em {args.output}")
    return 0 if not outcome.failed_groups else 2


if __name__ == "__main__":
    raise SystemExit(main())
