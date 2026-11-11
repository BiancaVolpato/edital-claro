"""Profile CRUD and POST /analyses/{id}/eligibility, including the acceptance case."""

import datetime as dt
import uuid
from functools import cache
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.api.eligibility import optional_llm, today
from app.db.models import (
    Analysis,
    AnalysisStatus,
    Document,
    DocumentSource,
    DocumentStatus,
    EligibilityCheck,
)
from app.extraction.citations import normalize_for_match, validate_citation
from app.extraction.schemas import Citation, EditalExtraction, ExtractedField, is_list_field
from app.ingestion.extract import extract_pdf
from app.ingestion.normalize import normalize_pages
from tests.conftest import SAMPLES_DIR
from tests.fakes import FakeLLM

PROFILE: dict[str, Any] = {
    "name": "Construtora Exemplo Ltda",
    "cnpj": "11.222.333/0001-81",
    "size": "EPP",
    "cnaes": ["4211-1/01", "4213-8/00"],
    "share_capital": 300000,
    "net_worth": 450000,
    "attestations": [
        {
            "description": "Pavimentação de vias urbanas no bairro Centro",
            "issuer": "Prefeitura de Exemplo",
            "quantities": [
                {"service": "Pavimentação asfáltica em CBUQ", "quantity": 2100, "unit": "m2"},
                {"service": "Drenagem pluvial com tubos de concreto", "quantity": 300, "unit": "m"},
            ],
        },
        {
            "description": "Recapeamento asfáltico da Rua das Flores",
            "issuer": "Município de Outro Exemplo",
            "quantities": [{"service": "Recapeamento em CBUQ", "quantity": 1500, "unit": "m2"}],
        },
    ],
    "certificates": [
        {"kind": "federal", "valid_until": "2026-12-20"},
        {"kind": "estadual", "valid_until": "2026-10-10"},  # expires before the opening
        {"kind": "municipal", "valid_until": "2026-11-30"},
        {"kind": "fgts", "valid_until": "2026-10-30"},
        {"kind": "trabalhista", "valid_until": "2027-03-01"},
        {"kind": "falencia", "valid_until": "2026-12-01"},
    ],
    "registration": {"council": "CREA", "number": "123456-7", "state": "sc"},
}


# --- Profiles CRUD --------------------------------------------------------------------


def test_profile_crud(client: TestClient) -> None:
    created = client.post("/profiles", json=PROFILE)
    assert created.status_code == 201
    body = created.json()
    assert body["cnpj"] == "11222333000181"
    assert body["cnaes"] == ["4211101", "4213800"]
    assert body["registration"]["state"] == "SC"
    profile_id = body["id"]

    assert client.get(f"/profiles/{profile_id}").json()["name"] == PROFILE["name"]
    assert [p["id"] for p in client.get("/profiles").json()] == [profile_id]

    updated = client.put(f"/profiles/{profile_id}", json={**PROFILE, "size": "demais"})
    assert updated.status_code == 200
    assert updated.json()["size"] == "demais"

    assert client.delete(f"/profiles/{profile_id}").status_code == 204
    assert client.get(f"/profiles/{profile_id}").status_code == 404
    assert client.delete(f"/profiles/{profile_id}").status_code == 404


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"cnpj": "123"}, "cnpj"),
        ({"cnaes": ["42111"]}, "cnaes"),
        ({"size": "grande"}, "size"),
        ({"share_capital": -1}, "share_capital"),
        ({"certificates": [{"kind": "federal", "valid_until": "amanhã"}]}, "certificates"),
        (
            {
                "attestations": [
                    {
                        "description": "Obra",
                        "quantities": [{"service": "x", "quantity": 0, "unit": "m2"}],
                    }
                ]
            },
            "attestations",
        ),
        ({"registration": {"council": "CRA", "number": "1"}}, "registration"),
    ],
)
def test_invalid_profiles_are_rejected(
    client: TestClient, override: dict[str, Any], field: str
) -> None:
    response = client.post("/profiles", json={**PROFILE, **override})

    assert response.status_code == 422
    assert field in str(response.json()["detail"])


def test_minimal_profile_is_accepted(client: TestClient) -> None:
    response = client.post("/profiles", json={"name": "Empresa Mínima", "size": "ME"})

    assert response.status_code == 201
    assert response.json()["attestations"] == []


# --- Eligibility endpoint ----------------------------------------------------------------


def _store_analysis(engine: Engine, result: dict[str, Any] | None, status: str) -> uuid.UUID:
    with Session(engine) as session:
        document = Document(
            source=DocumentSource.UPLOAD.value,
            filename="edital.pdf",
            file_hash=uuid.uuid4().hex * 2,
            file_size=1,
            status=DocumentStatus.READY.value,
        )
        session.add(document)
        session.flush()
        analysis = Analysis(
            document_id=document.id,
            status=status,
            strategy="sections",
            prompt_version="extraction/v1",
            prompt_hash="x",
            llm_provider="fake",
            llm_model="claude-opus-5-5",
            embedding_model="fake",
            result=result,
            runs=[],
            citation_counts={},
            warnings=[],
        )
        session.add(analysis)
        session.commit()
        return analysis.id


def _use(client: TestClient, llm: Any, on: dt.date) -> None:
    app: Any = client.app
    app.dependency_overrides[optional_llm] = lambda: llm
    app.dependency_overrides[today] = lambda: on


def test_unknown_analysis_or_profile_is_404(client: TestClient, db_engine: Engine) -> None:
    profile_id = client.post("/profiles", json=PROFILE).json()["id"]
    analysis_id = _store_analysis(db_engine, witmarsum_extraction(), AnalysisStatus.COMPLETED.value)

    missing_analysis = client.post(
        f"/analyses/{uuid.uuid4()}/eligibility", json={"profile_id": profile_id}
    )
    missing_profile = client.post(
        f"/analyses/{analysis_id}/eligibility", json={"profile_id": str(uuid.uuid4())}
    )

    assert missing_analysis.status_code == 404
    assert missing_profile.status_code == 404
    assert missing_profile.json()["detail"] == "Perfil não encontrado."


def test_analysis_without_fields_is_409(client: TestClient, db_engine: Engine) -> None:
    profile_id = client.post("/profiles", json=PROFILE).json()["id"]
    analysis_id = _store_analysis(db_engine, None, AnalysisStatus.RUNNING.value)

    response = client.post(f"/analyses/{analysis_id}/eligibility", json={"profile_id": profile_id})

    assert response.status_code == 409


# --- Acceptance: a test profile against the real Witmarsum edital -------------------------

# (field, page, quote, value). Quotes are copied from the PDF; values are what a correct
# extraction returns. Requirements keep the edital's wording.
WITMARSUM: list[tuple[str, int, str, Any]] = [
    (
        "opening",
        1,
        "ABERTURA DAS PROPOSTAS:08:31 HORAS DO 15 DE OUTUBRO DE 2026",
        {"date": "2026-10-15", "time": "08:31"},
    ),
    ("estimated_value", 1, "VALOR ESTIMADO GLOBAL DE CONTRATAÇÃO: R$ 3.809.907,22", 3809907.22),
    ("me_epp_exclusive", 1, "VALOR ESTIMADO GLOBAL DE CONTRATAÇÃO: R$ 3.809.907,22", False),
    (
        "qualification_legal",
        8,
        "7.10.2. Ato constitutivo, estatuto ou contrato social e última alteração "
        "(se houver) em vigor",
        None,
    ),
    (
        "qualification_fiscal",
        8,
        "a) prova de inscrição no Cadastro Nacional de Pessoal Jurídica, através do cartão do CNPJ",
        None,
    ),
    (
        "qualification_fiscal",
        8,
        "b) prova de regularidade para com a Fazenda Federal relativa a Tributos Federais e à "
        "dívida Ativa da União",
        None,
    ),
    (
        "qualification_fiscal",
        8,
        "c) prova de regularidade fiscal para com a Fazenda Pública Estadual",
        None,
    ),
    (
        "qualification_fiscal",
        8,
        "d) prova de inscrição no cadastro de contribuintes estadual, "
        "Cartão de Inscrição Estadual, (se houver)",
        None,
    ),
    (
        "qualification_fiscal",
        8,
        "e) prova de regularidade fiscal para com a Fazenda Pública Municipal do "
        "domicílio ou sede do licitante",
        None,
    ),
    (
        "qualification_fiscal",
        8,
        "f) prova de regularidade fiscal perante ao Fundo de Garantia por Tempo de "
        "Serviço (CRF - FGTS)",
        None,
    ),
    (
        "qualification_fiscal",
        9,
        "mediante apresentação de Certidão Negativa de Débitos Trabalhistas (CNDT)",
        None,
    ),
    (
        "qualification_technical",
        10,
        "a) Apresentar Atestado de Visita Técnica, nos termos do item 6.14 (opcional).",
        None,
    ),
    (
        "qualification_technical",
        10,
        "b) Certidão de Registro e Quitação de Pessoa Jurídica e Pessoa Fisica na entidade "
        "profissional competente",
        None,
    ),
    (
        "qualification_technical",
        11,
        "f.6) A licitante deverá apresentar atestado de capacidade técnica de PAVIMENTAÇÃO EM "
        "ASFALTICO COM METRAGEM MINIMA DE 3.404 M2",
        None,
    ),
    (
        "qualification_economic",
        9,
        "a) Balanço Patrimonial e demonstração de resultado dos dois ultimos exercícios social",
        None,
    ),
    (
        "qualification_economic",
        9,
        "c.1) Índice de Liquidez Geral (ILG) maior ou igual a 1.00 (um.zero.zero)",
        None,
    ),
    (
        "qualification_economic",
        9,
        "deverá comprovar patrimônio líquido de 10% (dez por cento) do valor estimado "
        "da contratação",
        None,
    ),
    ("qualification_economic", 9, "d) CERTIDÃO NEGATIVA DE PEDIDO DE FALÊNCIA OU CONCORDATA", None),
]
# Codes follow the section order (legal, fiscal, technical, economic): the attestation is R11.
ATTESTATION_CODE = "R11"


@cache
def _witmarsum_pages() -> dict[int, str]:
    pdf = (SAMPLES_DIR / "witmarsum_cce_4_2026.pdf").read_bytes()
    pages = normalize_pages([page.text for page in extract_pdf(pdf).pages])
    return {number: normalize_for_match(text) for number, text in enumerate(pages, start=1)}


def witmarsum_extraction() -> dict[str, Any]:
    """The extraction of the Witmarsum edital, with every quote checked against the PDF."""
    pages = _witmarsum_pages()
    data: dict[str, Any] = {
        name: []
        if is_list_field(name)
        else {"value": None, "citations": [], "confidence": 0.9, "needs_review": False}
        for name in EditalExtraction.model_fields
    }
    for name, page, quote, value in WITMARSUM:
        citation = validate_citation(Citation(page=page, quote=quote), pages)
        assert citation.status == "valid", (name, quote, citation)
        field = ExtractedField[Any](
            value=quote if value is None else value,
            citations=[citation],
            confidence=0.9,
            needs_review=False,
        ).model_dump(mode="json")
        if is_list_field(name):
            data[name].append(field)
        else:
            data[name] = field
    return EditalExtraction.model_validate(data).model_dump(mode="json")


def _attestation_answer(user: str) -> dict[str, Any]:
    assert f"{ATTESTATION_CODE}.Q1: parcela '3.404 m2' [unidade: m²]" in user
    return {
        "requirements": [
            {
                "requirement": ATTESTATION_CODE,
                "compatible_attestations": ["A1", "A2"],
                "parcels": [
                    {
                        "parcel": f"{ATTESTATION_CODE}.Q1",
                        "compatible_items": ["A1.1", "A2.1"],
                        "reason": "Pavimentação e recapeamento em CBUQ são pavimentação asfáltica.",
                    }
                ],
                "reason": "Os dois atestados são de pavimentação asfáltica.",
            }
        ]
    }


def test_acceptance_profile_against_the_witmarsum_edital(
    client: TestClient, db_engine: Engine
) -> None:
    llm = FakeLLM({"AttestationMatches": _attestation_answer})
    _use(client, llm, dt.date(2026, 10, 1))  # two weeks before the opening session
    profile_id = client.post("/profiles", json=PROFILE).json()["id"]
    analysis_id = _store_analysis(db_engine, witmarsum_extraction(), AnalysisStatus.COMPLETED.value)

    response = client.post(f"/analyses/{analysis_id}/eligibility", json={"profile_id": profile_id})

    assert response.status_code == 201
    body = response.json()
    report = body["report"]
    statuses = {(r["kind"], r["requirement"][:25]): r["status"] for r in report["results"]}
    assert statuses == {
        ("outro", "7.10.2. Ato constitutivo,"): "nao_verificavel",
        ("cnpj", "a) prova de inscrição no "): "atende",
        ("certidao", "b) prova de regularidade "): "atende",
        ("certidao", "c) prova de regularidade "): "nao_atende",  # estadual expires on 10/10
        ("outro", "d) prova de inscrição no "): "nao_verificavel",
        ("certidao", "e) prova de regularidade "): "atende",
        ("certidao", "f) prova de regularidade "): "atende",
        ("certidao", "mediante apresentação de "): "atende",
        ("visita_tecnica", "a) Apresentar Atestado de"): "nao_verificavel",
        ("registro_profissional", "b) Certidão de Registro e"): "atende",
        ("atestado", "f.6) A licitante deverá a"): "atende",  # 2.100 + 1.500 >= 3.404 m²
        ("balanco", "a) Balanço Patrimonial e "): "nao_verificavel",
        ("indices_contabeis", "c.1) Índice de Liquidez G"): "nao_verificavel",
        ("capital_ou_patrimonio", "deverá comprovar patrimôn"): "atende",  # 450.000 >= 380.990,72
        ("certidao", "d) CERTIDÃO NEGATIVA DE P"): "atende",
    }
    # Every result points to the page of the edital it came from.
    assert all(r["citations"][0]["status"] == "valid" for r in report["results"])

    summary = report["summary"]
    assert summary["verdict"] == "inapto"
    assert summary["counts"] == {"atende": 9, "nao_atende": 1, "nao_verificavel": 5}
    assert len(summary["missing"]) == 1 and "10/10/2026" in summary["missing"][0]
    assert [(d["label"], d["date"]) for d in summary["deadlines"]] == [
        ("Renovar: Certidão de regularidade com a Fazenda Estadual", "2026-10-10"),
        ("Sessão pública de abertura", "2026-10-15"),
    ]
    assert report["reference_date"] == "2026-10-15"
    # Audit trail: prompt, model and usage of the single LLM call.
    assert body["prompt_version"] == "eligibility/v1" and len(body["prompt_hash"]) == 12
    assert (body["llm_model"], body["input_tokens"], body["output_tokens"]) == (
        "claude-opus-5-5",
        1000,
        200,
    )
    assert len(llm.calls) == 1

    # Renewing the certificate leaves only items to check by hand.
    renewed = {
        **PROFILE,
        "certificates": [{**c, "valid_until": "2026-12-31"} for c in PROFILE["certificates"]],
    }
    client.put(f"/profiles/{profile_id}", json=renewed)
    again = client.post(f"/analyses/{analysis_id}/eligibility", json={"profile_id": profile_id})
    assert again.json()["report"]["summary"]["verdict"] == "apto_com_ressalvas"


def test_checks_are_stored_and_survive_the_profile(client: TestClient, db_engine: Engine) -> None:
    _use(client, None, dt.date(2026, 10, 1))
    profile_id = client.post("/profiles", json=PROFILE).json()["id"]
    analysis_id = _store_analysis(db_engine, witmarsum_extraction(), AnalysisStatus.COMPLETED.value)

    body = client.post(
        f"/analyses/{analysis_id}/eligibility", json={"profile_id": profile_id}
    ).json()
    client.delete(f"/profiles/{profile_id}")

    with Session(db_engine) as session:
        [check] = session.scalars(select(EligibilityCheck)).all()
        assert str(check.id) == body["id"]
        assert check.profile_snapshot["name"] == PROFILE["name"]
        assert check.report["summary"]["verdict"] == body["report"]["summary"]["verdict"]
        assert check.llm_model is None and check.cost_usd == 0.0
    # Without the LLM, only the attestation is left unverified.
    attestation = next(r for r in body["report"]["results"] if r["kind"] == "atestado")
    assert attestation["status"] == "nao_verificavel"


def test_the_sample_profile_in_the_docs_is_valid(client: TestClient) -> None:
    sample = SAMPLES_DIR.parent / "profiles" / "construtora_exemplo.json"

    response = client.post(
        "/profiles", content=sample.read_bytes(), headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 201
