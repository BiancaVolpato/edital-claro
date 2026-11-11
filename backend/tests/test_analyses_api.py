import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document, DocumentSource, DocumentStatus
from app.extraction.prompts import load_prompt_set
from app.extraction.schemas import EditalExtraction
from app.llm.base import LLMNotConfiguredError
from app.risks.prompts import load_risk_prompt_set
from tests.fakes import FailingLLM, FakeEmbedder, FakeLawRepository, FakeLLM, found

PDF = "application/pdf"
GROUPS = len(load_prompt_set("extraction/v1").groups)
TOPICS = len(load_risk_prompt_set("risks/v1").topics)
CALLS = GROUPS + TOPICS
TECHNICAL_TASK = "Tema: exigências de qualificação técnica."
LAURO_MULLER_ATTESTATION = "não serão permitidos atestados da própria empresa ou mesmo grupo"

# Answers with real quotes from the Lauro Müller edital, plus one hallucination.
LAURO_MULLER_ANSWERS: dict[str, Any] = {
    "identification": {
        "number": found(
            "Concorrência Eletrônica nº 233/PMLM/2026",
            2,
            "CONCORRÊNCIA ELETRÔNICA Nº. 233/PMLM/2026",
        ),
        "modality": found("concorrencia", 3, "realizará licitação, na modalidade CONCORRÊNCIA"),
        "estimated_value": found(60296.85, 2, "Valor previamente estimado em R$ 60.296,85."),
        "judgment_criterion": found("menor_preco", 2, "CRITÉRIO DE JULGAMENTO: Menor Preço Global"),
        "execution_regime": found(
            "empreitada_por_preco_unitario", 2, "REGIME ADOTADO Empreitada por valor unitário"
        ),
    },
    "dates": {
        "opening": found(
            {"date": "2026-10-19", "time": "09:00"}, 2, "DATA DA ABERTURA: 19/10/2026 ÀS 09H00MIN"
        ),
    },
    "guarantees_participation": {
        "bid_guarantee": found(
            {"required": False, "percent": None},
            11,
            "18.1.1. Não será exigida garantia da proposta.",
        ),
        "me_epp_exclusive": found(True, 2, "EXCLUSIVO ME E EPP"),
        # Not in the document: must be caught by citation validation.
        "contract_guarantee": found(
            {"required": True, "percent": 5.0},
            11,
            "A contratada prestará garantia de 5% do valor do contrato",
        ),
    },
    # One risk with a real quote (page 7) and one whose quote is invented.
    "RiskFindings": lambda user: (
        {
            "risks": [
                {
                    "type": "vedacao_a_atestado_do_mesmo_grupo",
                    "severity": "baixa",
                    "title": "Vedação a atestados emitidos pelo mesmo grupo",
                    "description": "O edital veda atestados do mesmo grupo econômico.",
                    "bidder_note": "Use atestados emitidos por terceiros.",
                    "agency_note": None,
                    "citation": {"page": 7, "quote": LAURO_MULLER_ATTESTATION},
                    "legal_basis": ["Art. 67, § 1º"],
                },
                {
                    "type": "inventado",
                    "severity": "alta",
                    "title": "Exigência inventada",
                    "description": "Não existe.",
                    "bidder_note": "x",
                    "agency_note": "y",
                    "citation": {
                        "page": 7,
                        "quote": "exigência de 3 atestados de obras no exterior",
                    },
                    "legal_basis": ["Art. 67, § 1º"],
                },
            ]
        }
        if TECHNICAL_TASK in user
        else {}
    ),
}


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> tuple[FakeLLM, FakeEmbedder]:
    llm, embedder = FakeLLM(LAURO_MULLER_ANSWERS), FakeEmbedder()
    monkeypatch.setattr("app.api.analyses.get_llm_provider", lambda: llm)
    monkeypatch.setattr("app.extraction.service.get_embedding_provider", lambda: embedder)
    monkeypatch.setattr(
        "app.extraction.service.get_law_repository",
        lambda session, embedder: FakeLawRepository(
            search_results=["Art. 67, § 1º", "Art. 67, § 2º"]
        ),
    )
    return llm, embedder


@pytest.fixture
def document_id(client: TestClient, lauro_muller_pdf: bytes) -> str:
    response = client.post("/documents", files={"file": ("edital.pdf", lauro_muller_pdf, PDF)})
    assert response.status_code == 202
    return str(response.json()["id"])


def test_analysis_of_a_real_edital_returns_fields_citations_and_cost(
    client: TestClient, document_id: str, fakes: tuple[FakeLLM, FakeEmbedder]
) -> None:
    started = client.post(f"/documents/{document_id}/analyze")

    assert started.status_code == 202
    assert started.json()["status"] == "pending"
    assert started.json()["result"] is None

    # TestClient runs the background task before returning.
    analysis = client.get(f"/analyses/{started.json()['id']}").json()
    assert analysis["status"] == "completed"
    assert analysis["error"] is None
    assert (analysis["steps_done"], analysis["steps_total"]) == (CALLS + 1, CALLS + 1)

    # The result is a valid EditalExtraction.
    extraction = EditalExtraction.model_validate(analysis["result"])
    assert extraction.estimated_value.value == 60296.85
    assert extraction.opening.value is not None
    assert extraction.opening.value.date.isoformat() == "2026-10-19"
    assert extraction.me_epp_exclusive.value is True
    assert extraction.bid_guarantee.value is not None
    assert extraction.bid_guarantee.value.required is False
    assert extraction.estimated_value.citations[0].model_dump() == {
        "page": 2,
        "quote": "Valor previamente estimado em R$ 60.296,85.",
        "status": "valid",
        "cited_page": 2,
        "match_score": 100.0,
    }

    # Every returned citation was validated; the hallucinated one is marked, not hidden.
    assert analysis["citation_counts"] == {"total": 9, "not_found": 1, "valid": 8}
    hallucinated = extraction.contract_guarantee
    assert hallucinated.citations[0].status == "not_found"
    assert (hallucinated.confidence, hallucinated.needs_review) == (0.2, True)

    # Usage, cost and latency are part of the result.
    # Usage covers the extraction calls and the risk calls.
    assert analysis["input_tokens"] == CALLS * 1000
    assert analysis["output_tokens"] == CALLS * 200
    assert analysis["cost_usd"] == pytest.approx(CALLS * 0.008)
    assert analysis["latency_ms"] > 0
    assert len(analysis["runs"]) == CALLS
    assert analysis["runs"][-1]["group"].startswith("risk:")
    assert analysis["runs"][0]["chunk_indexes"]

    # Audit trail.
    prompt = load_prompt_set("extraction/v1")
    assert analysis["strategy"] == "sections"
    assert (analysis["prompt_version"], analysis["prompt_hash"]) == (
        prompt.version,
        prompt.content_hash,
    )
    assert (analysis["llm_provider"], analysis["llm_model"]) == ("fake", "claude-opus-5-5")
    assert analysis["embedding_model"] == "intfloat/multilingual-e5-base"
    risk_prompt = load_risk_prompt_set("risks/v1")
    assert (analysis["risk_prompt_version"], analysis["risk_prompt_hash"]) == (
        risk_prompt.version,
        risk_prompt.content_hash,
    )

    # Risks: the grounded one is reported, the invented one is discarded.
    risks = analysis["risks"]
    assert [r["type"] for r in risks["risks"]] == ["vedacao_a_atestado_do_mesmo_grupo"]
    assert risks["risks"][0]["citations"][0]["status"] == "valid"
    assert risks["risks"][0]["legal_basis"][0]["citation"] == "Lei 14.133/2021, Art. 67, § 1º"
    assert [d["title"] for d in risks["discarded"]] == ["Exigência inventada"]
    assert analysis["warnings"] == []


def test_chunk_embeddings_are_computed_once_and_reused(
    client: TestClient, db_engine: Engine, document_id: str, fakes: tuple[FakeLLM, FakeEmbedder]
) -> None:
    _, embedder = fakes

    client.post(f"/documents/{document_id}/analyze")
    client.post(f"/documents/{document_id}/analyze")

    assert embedder.passage_batches == [60]  # 60 chunks, embedded only in the first analysis
    with Session(db_engine) as session:
        models = set(session.scalars(select(Chunk.embedding_model)))
    assert models == {"fake-bag-of-words"}


def test_analysis_fails_cleanly_when_every_call_fails(
    client: TestClient, document_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.analyses.get_llm_provider", lambda: FailingLLM())
    monkeypatch.setattr("app.extraction.service.get_embedding_provider", lambda: FakeEmbedder())

    started = client.post(f"/documents/{document_id}/analyze")
    analysis = client.get(f"/analyses/{started.json()['id']}").json()

    assert analysis["status"] == "failed"
    assert analysis["error"] == "service unavailable"
    assert analysis["result"] is None
    assert len(analysis["warnings"]) == GROUPS


def test_unexpected_error_marks_the_analysis_failed(
    client: TestClient, document_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_embedder() -> FakeEmbedder:
        raise RuntimeError("model file is corrupted")

    monkeypatch.setattr("app.api.analyses.get_llm_provider", lambda: FakeLLM())
    monkeypatch.setattr("app.extraction.service.get_embedding_provider", broken_embedder)

    started = client.post(f"/documents/{document_id}/analyze")
    analysis = client.get(f"/analyses/{started.json()['id']}").json()

    assert analysis["status"] == "failed"
    # Internal details stay in the logs, not in the API response.
    assert analysis["error"] == "unexpected error during analysis"


def test_analysis_requires_a_processed_document(
    client: TestClient, db_engine: Engine, fakes: tuple[FakeLLM, FakeEmbedder]
) -> None:
    with Session(db_engine) as session:
        document = Document(
            source=DocumentSource.UPLOAD.value,
            filename="edital.pdf",
            file_hash="0" * 64,
            file_size=1,
            status=DocumentStatus.PROCESSING.value,
            meta={},
        )
        session.add(document)
        session.commit()
        pending_id = document.id

    assert client.post(f"/documents/{pending_id}/analyze").status_code == 409
    assert client.post(f"/documents/{uuid.uuid4()}/analyze").status_code == 404
    assert client.get(f"/analyses/{uuid.uuid4()}").status_code == 404


def test_missing_api_key_is_reported_as_service_unavailable(
    client: TestClient, document_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def not_configured() -> FakeLLM:
        raise LLMNotConfiguredError("no Anthropic credentials found")

    monkeypatch.setattr("app.api.analyses.get_llm_provider", not_configured)

    response = client.post(f"/documents/{document_id}/analyze")

    assert response.status_code == 503
    assert "chave da API" in response.json()["detail"]


def test_risks_are_served_per_audience(
    client: TestClient, document_id: str, fakes: tuple[FakeLLM, FakeEmbedder]
) -> None:
    analysis_id = client.post(f"/documents/{document_id}/analyze").json()["id"]

    bidder = client.get(f"/analyses/{analysis_id}/risks").json()
    agency = client.get(f"/analyses/{analysis_id}/risks", params={"audience": "orgao"}).json()

    assert bidder["audience"] == "licitante"
    assert [r["message"] for r in bidder["risks"]] == ["Use atestados emitidos por terceiros."]
    # The finding has no note for the agency, so the agency view leaves it out.
    assert agency["risks"] == []
    assert client.get(f"/analyses/{analysis_id}/risks", params={"audience": "x"}).status_code == 422
    assert client.get(f"/analyses/{uuid.uuid4()}/risks").status_code == 404


def test_a_failed_risk_analysis_keeps_the_extracted_fields(
    client: TestClient,
    document_id: str,
    fakes: tuple[FakeLLM, FakeEmbedder],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_law(session: Session, embedder: FakeEmbedder) -> FakeLawRepository:
        raise RuntimeError("law index unavailable")

    monkeypatch.setattr("app.extraction.service.get_law_repository", broken_law)

    analysis_id = client.post(f"/documents/{document_id}/analyze").json()["id"]
    analysis = client.get(f"/analyses/{analysis_id}").json()

    assert analysis["status"] == "completed"
    assert analysis["result"]["estimated_value"]["value"] == 60296.85
    assert analysis["risks"] is None
    assert any("análise de riscos falhou" in w for w in analysis["warnings"])
    assert client.get(f"/analyses/{analysis_id}/risks").status_code == 409


def test_without_the_law_in_the_database_the_law_file_is_used(
    db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.extraction.service import get_law_repository
    from app.risks.law_repository import DatabaseLawRepository, InMemoryLawRepository

    monkeypatch.setattr(DatabaseLawRepository, "is_indexed", lambda self: False)

    with Session(db_engine) as session:
        repository = get_law_repository(session, FakeEmbedder(768))

    assert isinstance(repository, InMemoryLawRepository)
    found_provision = repository.get("Art. 58, § 1º")
    assert found_provision is not None
    assert "1% (um por cento)" in found_provision.text
