"""Evaluation: golden set validation, scoring rules, runner and report (fake LLM)."""

import datetime as dt
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from app.evaluation.golden import GoldenError, load_golden
from app.evaluation.report import recommend, render_report
from app.evaluation.runner import Variant, load_variants, run_variant
from app.evaluation.scoring import (
    VariantSummary,
    match_items,
    score_field,
    values_match,
)
from app.extraction.pipeline import leading_chunks, run_extraction
from app.extraction.prompts import load_prompt_set
from app.extraction.retrieval import ChunkData
from app.extraction.schemas import CitationStatus, ExtractedField, ValidatedCitation
from tests.fakes import FakeEmbedder, FakeLLM
from tests.test_analyses_api import LAURO_MULLER_ANSWERS

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "eval" / "golden"
PROMPT = load_prompt_set("extraction/v1")


def got(
    value: Any, page: int = 2, status: CitationStatus = "valid", review: bool = False
) -> ExtractedField[Any]:
    citation = ValidatedCitation(
        page=page, quote="x" * 20, status=status, cited_page=page, match_score=100
    )
    return ExtractedField(value=value, citations=[citation], confidence=0.9, needs_review=review)


# --- Scoring rules --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected", "predicted", "ok"),
    [
        ("estimated_value", 60296.85, 60296.85, True),
        ("estimated_value", 60296.85, 60296.80, False),
        (
            "number",
            "Concorrência Eletrônica nº 233/PMLM/2026",
            "CONCORRÊNCIA ELETRÔNICA Nº. 233/PMLM/2026",
            True,
        ),
        (
            "number",
            "Concorrência Eletrônica nº 233/PMLM/2026",
            "Concorrência Eletrônica nº 223/PMLM/2026",
            False,
        ),
        ("agency", "Município de Lauro Muller", "MUNICÍPIO DE LAURO MULLER", True),
        ("agency", "Município de Lauro Muller", "Município de Witmarsum", False),
        ("modality", "concorrencia", "pregao", False),
        (
            "opening",
            {"date": dt.date(2026, 10, 19), "time": "09:00"},
            {"date": dt.date(2026, 10, 19), "time": "08:30"},
            False,
        ),
        (
            "opening",
            {"date": dt.date(2026, 10, 19), "time": None},
            {"date": dt.date(2026, 10, 19), "time": "08:30"},
            True,
        ),
        (
            "impugnation_deadline",
            {"date": None, "rule": "com antecedência mínima de 3 dias úteis da data de abertura"},
            {"date": None, "rule": "até 3 (três) dias úteis antes da data de abertura do certame"},
            True,
        ),
        (
            "impugnation_deadline",
            {"date": None, "rule": "até 3 dias úteis antes da data de abertura"},
            {"date": None, "rule": "até 5 dias úteis antes da data de abertura"},
            False,
        ),
        (
            "bid_guarantee",
            {"required": False, "percent": None},
            {"required": False, "percent": None},
            True,
        ),
        (
            "contract_guarantee",
            {"required": True, "percent": 5.0},
            {"required": True, "percent": 10.0},
            False,
        ),
        (
            "contract_guarantee",
            {"required": True, "percent": None},
            {"required": True, "percent": 5.0},
            True,
        ),
        ("execution_period", {"amount": 60, "unit": "dias"}, {"amount": 2, "unit": "meses"}, False),
        ("me_epp_exclusive", True, True, True),
    ],
)
def test_values_are_compared_by_type(name: str, expected: Any, predicted: Any, ok: bool) -> None:
    assert values_match(name, expected, predicted)[0] is ok


def test_field_outcomes_cover_absent_values() -> None:
    assert score_field("estimated_value", 1.0, [2], got(1.0)).outcome == "correct"
    assert score_field("estimated_value", 1.0, [2], got(2.0)).outcome == "wrong"
    assert score_field("estimated_value", 1.0, [2], got(None)).outcome == "missed"
    assert score_field("consortium_allowed", None, [], got(True)).outcome == "hallucinated"
    assert score_field("consortium_allowed", None, [], got(None)).outcome == "correct"


def test_citation_page_is_checked_against_the_golden_pages() -> None:
    assert score_field("estimated_value", 1.0, [2], got(1.0, page=2)).on_expected_page is True
    assert score_field("estimated_value", 1.0, [2], got(1.0, page=9)).on_expected_page is False
    unconfirmed = score_field("estimated_value", 1.0, [2], got(1.0, status="not_found"))
    assert (unconfirmed.on_expected_page, unconfirmed.citation_confirmed) == (False, False)


def test_list_items_are_paired_once_best_first() -> None:
    expected = [
        "Certidão de regularidade do FGTS",
        "Certidão Negativa de Débitos Trabalhistas (CNDT)",
    ]
    predicted = [
        "CNDT - Certidão Negativa de Débitos Trabalhistas",
        "Prova de regularidade perante o FGTS (CRF)",
        "Certidão de regularidade do FGTS",
        "Alvará de funcionamento",
    ]

    pairs = match_items(expected, predicted)

    assert {(g, p) for g, p, _ in pairs} == {
        ("Certidão de regularidade do FGTS", "Certidão de regularidade do FGTS"),
        (
            "Certidão Negativa de Débitos Trabalhistas (CNDT)",
            "CNDT - Certidão Negativa de Débitos Trabalhistas",
        ),
    }


# --- Golden set -----------------------------------------------------------------------


def test_the_example_annotation_is_valid() -> None:
    [case] = [c for c in load_golden(GOLDEN_DIR, REPO_ROOT) if c.name == "lauro_muller_cc_233_2026"]

    assert case.golden.fields["estimated_value"].value == 60296.85
    assert case.golden.annotation.reviewed is False


def _copy_golden(tmp_path: Path, change: dict[str, Any] | None = None, **field_values: Any) -> Path:
    folder = tmp_path / "golden"
    folder.mkdir()
    shutil.copy(GOLDEN_DIR / "_template.json", folder / "_template.json")
    data = json.loads((GOLDEN_DIR / "lauro_muller_cc_233_2026.json").read_text(encoding="utf-8"))
    for name, value in field_values.items():
        if value is ...:
            del data["fields"][name]
        else:
            data["fields"][name]["value"] = value
    for key, value in (change or {}).items():
        data["document"][key] = value
    (folder / "lauro.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return folder


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"publication_date": "01/10/2026"}, "publication_date: valor inválido"),
        ({"modality": "concorrencia_eletronica"}, "modality: valor inválido"),
        ({"site_visit": ...}, "campos faltando: site_visit"),
        ({"change": {"sha256": "0" * 64}}, "SHA-256"),
        ({"change": {"file": "data/samples/nao_existe.pdf"}}, "PDF não encontrado"),
    ],
)
def test_annotation_mistakes_are_reported(
    tmp_path: Path, kwargs: dict[str, Any], message: str
) -> None:
    folder = _copy_golden(tmp_path, **kwargs)

    with pytest.raises(GoldenError, match=message):
        load_golden(folder, REPO_ROOT)


def test_the_template_is_not_an_edital() -> None:
    assert all(case.name != "_template" for case in load_golden(GOLDEN_DIR, REPO_ROOT))


def test_variants_file_is_valid() -> None:
    variants = load_variants(REPO_ROOT / "eval" / "variants.toml")

    assert variants[0].name == "opus-secoes"
    assert {v.strategy for v in variants} == {"sections", "direct"}
    assert len({v.model for v in variants}) >= 2


# --- Direct strategy -----------------------------------------------------------------


def _chunk(index: int, size: int) -> ChunkData:
    return ChunkData(index, "clause", None, "a" * size, [(1, 0)])


def test_direct_strategy_takes_the_start_of_the_document() -> None:
    chunks = [_chunk(i, 400) for i in range(10)]

    assert [c.index for c in leading_chunks(chunks, 1000)] == [0, 1]
    assert [c.index for c in leading_chunks([_chunk(0, 5000)], 1000)] == [0]  # never empty


def test_direct_strategy_sends_the_same_excerpts_to_every_group() -> None:
    chunks = [
        ChunkData(i, "clause", f"Seção {i}", f"texto da seção {i}", [(i + 1, 0)]) for i in range(5)
    ]
    llm = FakeLLM()
    embedder = FakeEmbedder()

    outcome = run_extraction(
        pages={i + 1: c.text for i, c in enumerate(chunks)},
        chunks=chunks,
        chunk_vectors=embedder.embed_passages([c.text for c in chunks]),
        prompt=PROMPT,
        llm=llm,
        embedder=embedder,
        strategy="direct",
        direct_max_chars=40,
    )

    assert {tuple(run.chunk_indexes) for run in outcome.runs} == {(0, 1)}


# --- Runner and report -----------------------------------------------------------------


def _run(
    tmp_path: Path, llm: FakeLLM, reuse: bool = False, variant: str = "fake-secoes"
) -> VariantSummary:
    cases = [c for c in load_golden(GOLDEN_DIR, REPO_ROOT) if c.name == "lauro_muller_cc_233_2026"]
    return run_variant(
        variant=Variant(variant, "claude-opus-5-5", "sections", "teste"),
        cases=cases,
        prompt=PROMPT,
        llm_for=lambda model: llm,
        embedder=FakeEmbedder(),
        runs_dir=tmp_path / "runs",
        reuse=reuse,
        prepared={},
        log=lambda message: None,
    )


def test_runner_scores_a_real_edital_and_saves_the_raw_result(tmp_path: Path) -> None:
    llm = FakeLLM(LAURO_MULLER_ANSWERS)

    summary = _run(tmp_path, llm)

    [edital] = summary.editais
    outcomes = {f.name: f.outcome for f in edital.fields}
    # The fake answers the identification and dates groups with real quotes.
    assert outcomes["estimated_value"] == outcomes["judgment_criterion"] == "correct"
    assert outcomes["opening"] == "correct"
    assert outcomes["me_epp_exclusive"] == "correct"
    assert outcomes["contract_guarantee"] == "hallucinated"  # golden: not stated
    assert outcomes["object"] == "missed"  # the fake does not answer it
    assert edital.cost_usd is not None and edital.cost_usd > 0
    saved = json.loads(
        (tmp_path / "runs" / "fake-secoes" / "lauro_muller_cc_233_2026.json").read_text("utf-8")
    )
    assert saved["prompt_hash"] == PROMPT.content_hash
    assert saved["extraction"]["estimated_value"]["value"] == 60296.85


def test_reuse_scores_saved_results_without_calling_the_llm(tmp_path: Path) -> None:
    first = _run(tmp_path, FakeLLM(LAURO_MULLER_ANSWERS))
    silent = FakeLLM()

    again = _run(tmp_path, silent, reuse=True)

    assert silent.calls == []
    assert again.accuracy == first.accuracy


def test_report_has_every_section_and_a_recommendation(tmp_path: Path) -> None:
    opus = _run(tmp_path, FakeLLM(LAURO_MULLER_ANSWERS), variant="opus-secoes")
    cheap_answers = {**LAURO_MULLER_ANSWERS, "identification": {}}
    cheap = _run(tmp_path, FakeLLM(cheap_answers, model="claude-haiku-5-5"), variant="haiku-secoes")
    variants = [
        Variant("opus-secoes", "claude-opus-5-5", "sections", ""),
        Variant("haiku-secoes", "claude-haiku-5-5", "sections", ""),
    ]
    cases = load_golden(GOLDEN_DIR, REPO_ROOT)

    report = render_report(
        summaries=[opus, cheap],
        variants=variants,
        cases=cases,
        prompt_version=PROMPT.version,
        prompt_hash=PROMPT.content_hash,
        generated_at=dt.datetime(2026, 11, 12, 10, 0),
    )

    for heading in (
        "## Resumo por variante",
        "## Acurácia por campo",
        "## Exigências de habilitação e anexos",
        "## Por edital (`opus-secoes`)",
        "## Análise de erros (`opus-secoes`)",
        "## Piores casos (`opus-secoes`)",
        "## Como os números são calculados",
    ):
        assert heading in report
    assert "Números preliminares" in report
    assert "| Garantia contratual | 60296.85" not in report
    assert "valor inventado" in report
    assert "**Escolha pelos números:** `opus-secoes`" in report  # haiku is far less accurate


def test_a_cheaper_variant_wins_when_almost_as_accurate(monkeypatch: pytest.MonkeyPatch) -> None:
    accurate = VariantSummary("caro", [])
    cheap = VariantSummary("barato", [])
    monkeypatch.setattr(
        VariantSummary, "accuracy", property(lambda s: {"caro": 0.90, "barato": 0.89}[s.variant])
    )
    monkeypatch.setattr(
        VariantSummary,
        "mean_cost_usd",
        property(lambda s: {"caro": 0.50, "barato": 0.10}[s.variant]),
    )

    choice, reason = recommend([accurate, cheap])

    assert choice.variant == "barato"
    assert "custa menos" in reason
