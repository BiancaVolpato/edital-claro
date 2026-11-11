"""Analyze editais from the command line, without the API or a database.

Runs the same pipeline as POST /documents/{id}/analyze (extraction, chunking,
section retrieval, LLM calls, citation validation, risk analysis) fully in
memory and prints a summary. The law is read from data/law with its cached
embeddings. It calls the real LLM, so it needs ANTHROPIC_API_KEY and costs money.

With several PDFs, it ends with a check of the risk acceptance criterion:
every reported risk must have a validated edital quote and a provision that
exists in the indexed law.

Usage (from the backend folder):
    uv run python scripts/analyze.py ../data/samples/lauro_muller_cc_233_2026.pdf
    uv run python scripts/analyze.py ../data/samples/*.pdf --output-dir ../eval/runs
"""

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.embeddings.base import EmbeddingProvider, get_embedding_provider
from app.extraction.pipeline import GroupRun, run_extraction
from app.extraction.prompts import load_prompt_set
from app.extraction.retrieval import ChunkData, embed_chunks
from app.extraction.schemas import EditalExtraction
from app.ingestion.chunking import chunk_pages
from app.ingestion.extract import extract_pdf
from app.ingestion.normalize import normalize_pages
from app.ingestion.service import default_ocr_engine
from app.llm.base import LLMNotConfiguredError, LLMProvider
from app.llm.factory import get_llm_provider
from app.risks.assessment import assess_risks
from app.risks.law_repository import InMemoryLawRepository
from app.risks.prompts import load_risk_prompt_set
from app.risks.schemas import RiskReport

SEVERITY_LABELS = {"alta": "ALTA", "media": "MÉDIA", "baixa": "BAIXA"}


@dataclass
class EditalSummary:
    name: str
    risks: int
    grounded: int
    discarded: int
    cost_usd: float | None
    failed_calls: list[str]


def _describe(field: dict[str, Any]) -> str:
    pages = sorted({citation["page"] for citation in field["citations"]})
    unconfirmed = [c["status"] for c in field["citations"] if c["status"] != "valid"]
    flags = " REVISAR" if field["needs_review"] else ""
    notes = f" citações não confirmadas: {unconfirmed}" if unconfirmed else ""
    return f"{field['value']!r}  (confiança {field['confidence']}, pág. {pages}){flags}{notes}"


def _print_risks(report: RiskReport) -> None:
    print(f"\n=== Riscos ({len(report.risks)}) ===")
    for risk in report.risks:
        pages = sorted({citation.page for citation in risk.citations})
        basis = "; ".join(provision.identifier for provision in risk.legal_basis)
        origin = "regra" if risk.origin == "rule" else "IA"
        print(f"[{SEVERITY_LABELS[risk.severity]}] {risk.title}  ({origin}; pág. {pages}; {basis})")
        print(f"    {risk.description}")
        if risk.bidder_note:
            print(f"    Licitante: {risk.bidder_note}")
        if risk.agency_note:
            print(f"    Órgão: {risk.agency_note}")
    for discarded in report.discarded:
        print(f"[DESCARTADO] {discarded.title}: {discarded.reason}")
    for warning in report.warnings:
        print(f"AVISO: {warning}")


def _is_grounded(report: RiskReport) -> list[bool]:
    """For each risk: a validated quote and at least one provision with its official text."""
    return [
        bool(risk.citations)
        and all(c.status in ("valid", "wrong_page") for c in risk.citations)
        and bool(risk.legal_basis)
        and all(provision.text for provision in risk.legal_basis)
        for risk in report.risks
    ]


def analyze(
    pdf: Path, llm: LLMProvider, embedder: EmbeddingProvider, output_dir: Path | None
) -> EditalSummary:
    settings = get_settings()
    started = time.perf_counter()
    extracted = extract_pdf(pdf.read_bytes(), default_ocr_engine())
    texts = normalize_pages([page.text for page in extracted.pages])
    pages = dict(enumerate(texts, start=1))
    chunks = [
        ChunkData(c.index, c.kind.value, c.heading, c.text, c.page_spans)
        for c in chunk_pages(texts, max_chars=settings.chunk_max_chars)
    ]
    print(f"\n##### {pdf.name}: {len(texts)} páginas, {len(chunks)} trechos")
    for warning in extracted.warnings:
        print(f"AVISO: {warning}")

    vectors = embed_chunks(chunks, embedder)
    prompt = load_prompt_set(settings.extraction_prompt_version)
    print(f"Extraindo com {llm.model}, prompt {prompt.version} ({prompt.content_hash})...")
    outcome = run_extraction(
        pages=pages,
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

    risk_prompt = load_risk_prompt_set(settings.risk_prompt_version)
    print(f"\nAnalisando riscos, prompt {risk_prompt.version} ({risk_prompt.content_hash})...")
    risk_outcome = assess_risks(
        extraction=outcome.extraction,
        pages=pages,
        chunks=chunks,
        chunk_vectors=vectors,
        law=InMemoryLawRepository(embedder),
        prompt=risk_prompt,
        llm=llm,
        embedder=embedder,
        max_concurrency=settings.llm_max_concurrency,
        on_progress=lambda done, total: print(f"  tema {done}/{total} concluído"),
    )
    report = risk_outcome.report
    _print_risks(report)

    runs: list[GroupRun] = [*outcome.runs, *risk_outcome.runs]
    costs = [run.cost_usd for run in runs if not run.error]
    total_cost = None if any(cost is None for cost in costs) else sum(c for c in costs if c)
    print("\n=== Resumo ===")
    print(f"Citações dos campos: {outcome.citation_counts}")
    print(
        f"Tokens: {sum(r.input_tokens for r in runs)} de entrada, "
        f"{sum(r.output_tokens for r in runs)} de saída"
    )
    print(f"Custo estimado: {'desconhecido' if total_cost is None else f'US$ {total_cost:.4f}'}")
    print(f"Tempo total: {time.perf_counter() - started:.1f} s")
    failed = [run.group for run in runs if run.error]
    for run in runs:
        if run.error:
            print(f"FALHA em {run.group}: {run.error}")

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"{pdf.stem}.json"
        payload = {
            "result": result,
            "risks": report.model_dump(mode="json"),
            "runs": [asdict(run) for run in runs],
            "citation_counts": outcome.citation_counts,
            "prompt_version": prompt.version,
            "prompt_hash": prompt.content_hash,
            "risk_prompt_version": risk_prompt.version,
            "risk_prompt_hash": risk_prompt.content_hash,
            "llm_model": llm.model,
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Resultado completo gravado em {target}")

    grounded = _is_grounded(report)
    return EditalSummary(
        name=pdf.name,
        risks=len(report.risks),
        grounded=sum(grounded),
        discarded=len(report.discarded),
        cost_usd=total_cost,
        failed_calls=failed,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdfs", type=Path, nargs="+", help="editais em PDF")
    parser.add_argument("--output-dir", type=Path, help="grava o resultado de cada edital em JSON")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    try:
        llm = get_llm_provider()
    except LLMNotConfiguredError:
        print("Chave da API não encontrada. Defina ANTHROPIC_API_KEY no arquivo .env da raiz.")
        return 1
    print(f"Carregando o modelo de embeddings {get_settings().embedding_model}...")
    embedder = get_embedding_provider()

    summaries = [analyze(pdf, llm, embedder, args.output_dir) for pdf in args.pdfs]

    print("\n=== Critério de aceite: todo risco com citação e artigo válidos ===")
    print(f"{'Edital':45} {'Riscos':>6} {'Válidos':>7} {'Descartados':>11} {'Custo':>10}")
    for s in summaries:
        cost = "?" if s.cost_usd is None else f"US$ {s.cost_usd:.3f}"
        print(f"{s.name:45} {s.risks:>6} {s.grounded:>7} {s.discarded:>11} {cost:>10}")
    ok = all(s.grounded == s.risks for s in summaries)
    failures = [f"{s.name}: {', '.join(s.failed_calls)}" for s in summaries if s.failed_calls]
    print("Resultado:", "atendido" if ok else "NÃO atendido")
    for failure in failures:
        print(f"Chamadas que falharam em {failure}")
    return 0 if ok and not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
