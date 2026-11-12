"""Endpoints added for the interface: the PDF file, the list of analyses and the exports."""

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.db.models import AnalysisStatus
from app.reports.markdown import format_value
from tests.fakes import FakeEmbedder, FakeLLM
from tests.test_analyses_api import fakes  # noqa: F401 (pytest fixture)
from tests.test_eligibility_api import PROFILE, _store_analysis, _use, witmarsum_extraction

PDF = "application/pdf"


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("estimated_value", 3809907.22, "R$ 3.809.907,22"),
        ("opening", {"date": "2026-10-15", "time": "08:31"}, "15/10/2026 às 08:31"),
        (
            "impugnation_deadline",
            {"date": None, "rule": "até 3 dias úteis antes"},
            "até 3 dias úteis antes",
        ),
        ("execution_period", {"amount": 6, "unit": "meses"}, "6 meses"),
        ("bid_guarantee", {"required": True, "percent": 1.5}, "Exigida (1,5%)"),
        ("contract_guarantee", {"required": False, "percent": None}, "Não exigida"),
        ("consortium_allowed", False, "Não"),
        ("judgment_criterion", "menor_preco", "Menor preco"),
        ("object", None, "Não encontrado"),
    ],
)
def test_values_are_formatted_for_people(name: str, value: Any, expected: str) -> None:
    assert format_value(name, value) == expected


def test_the_original_pdf_is_served_inline(client: TestClient, lauro_muller_pdf: bytes) -> None:
    uploaded = client.post("/documents", files={"file": ("edital.pdf", lauro_muller_pdf, PDF)})
    document_id = uploaded.json()["id"]

    response = client.get(f"/documents/{document_id}/file")

    assert response.status_code == 200
    assert response.headers["content-type"] == PDF
    assert response.headers["content-disposition"].startswith("inline")
    assert response.content == lauro_muller_pdf
    assert client.get("/documents/00000000-0000-0000-0000-000000000000/file").status_code == 404


def test_analyses_are_listed_and_exported_as_markdown(
    client: TestClient,
    lauro_muller_pdf: bytes,
    fakes: tuple[FakeLLM, FakeEmbedder],  # noqa: F811
) -> None:
    uploaded = client.post("/documents", files={"file": ("lauro.pdf", lauro_muller_pdf, PDF)})
    document_id = uploaded.json()["id"]
    analysis_id = client.post(f"/documents/{document_id}/analyze").json()["id"]

    listed = client.get("/analyses", params={"document_id": document_id}).json()
    assert [(a["id"], a["filename"], a["status"]) for a in listed] == [
        (analysis_id, "lauro.pdf", "completed")
    ]
    assert client.get("/analyses").json()[0]["id"] == analysis_id

    report = client.get(f"/analyses/{analysis_id}/report.md")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/markdown")
    text = report.text
    assert "# Análise do edital: lauro.pdf" in text
    assert (
        '| Valor estimado | R$ 60.296,85 | 90% | p. 2: "Valor previamente estimado em '
        'R$ 60.296,85." |' in text
    )
    assert "⚠ revisar" in text  # the hallucinated guarantee is flagged, not hidden
    assert "### [Baixa] Vedação a atestados emitidos pelo mesmo grupo" in text
    assert "não substitui parecer jurídico" in text

    agency = client.get(f"/analyses/{analysis_id}/report.md", params={"audience": "orgao"}).text
    assert "orientação para o órgão" in agency
    assert "Nenhum risco apontado para este público." in agency  # the risk has no agency note


def test_export_of_an_analysis_without_result_is_409(client: TestClient, db_engine: Engine) -> None:
    analysis_id = _store_analysis(db_engine, None, AnalysisStatus.RUNNING.value)

    assert client.get(f"/analyses/{analysis_id}/report.md").status_code == 409


def test_eligibility_check_is_read_back_and_exported(client: TestClient, db_engine: Engine) -> None:
    _use(client, None, dt.date(2026, 10, 1))
    profile_id = client.post("/profiles", json=PROFILE).json()["id"]
    analysis_id = _store_analysis(db_engine, witmarsum_extraction(), AnalysisStatus.COMPLETED.value)
    created = client.post(
        f"/analyses/{analysis_id}/eligibility", json={"profile_id": profile_id}
    ).json()

    read = client.get(f"/eligibility/{created['id']}")
    report = client.get(f"/eligibility/{created['id']}/report.md")

    assert read.status_code == 200 and read.json()["report"] == created["report"]
    text = report.text
    assert "# Aptidão de Construtora Exemplo Ltda" in text
    assert "## Veredito: Inapto" in text
    assert "- 10/10/2026: Renovar: Certidão de regularidade com a Fazenda Estadual" in text
    assert (
        "- **Não atende** — c) prova de regularidade fiscal para com a Fazenda Pública Estadual"
        in text
    )
    assert client.get("/eligibility/00000000-0000-0000-0000-000000000000").status_code == 404
