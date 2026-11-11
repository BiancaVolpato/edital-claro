"""PNCP client, search and import, against responses recorded from the real API.

The fixtures in ``tests/fixtures/pncp`` were recorded on 11/11/2026 from the
official endpoints (see the README there). No test touches the network.
"""

import datetime as dt
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.pncp import get_pncp_client
from app.core.config import get_settings
from app.pncp.client import PncpClient, PncpError, ResponseCache
from app.pncp.schemas import Procurement
from app.pncp.service import (
    PncpInputError,
    SearchFilters,
    parse_control_number,
    search,
)
from tests.fakes import FakeEmbedder, FakeLLM
from tests.test_analyses_api import fakes  # noqa: F401 (pytest fixture)

FIXTURES = Path(__file__).parent / "fixtures" / "pncp"
CONSULTA = "https://pncp.test/api/consulta"
API = "https://pncp.test/api/pncp"
CONTROL = "82939422000191-1-000153/2026"  # Erval Velho, asphalt paving
PROCUREMENT_PATH = "/api/consulta/v1/orgaos/82939422000191/compras/2026/153"
FILES_PATH = "/api/pncp/v1/orgaos/82939422000191/compras/2026/153/arquivos"

Handler = Callable[[httpx.Request], httpx.Response]


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakePncp:
    """Serves the recorded responses and records every request it receives."""

    def __init__(self, download: bytes | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.download = download if download is not None else b"%PDF-1.4 fake"
        self.overrides: dict[str, Handler] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path in self.overrides:
            return self.overrides[path](request)
        if path == "/api/consulta/v1/contratacoes/publicacao":
            params = request.url.params
            name = (
                f"publicacao_{params['dataInicial']}_{params.get('uf', '').lower()}"
                f"_mod{params['codigoModalidadeContratacao']}_p{params['pagina']}.json"
            )
            if not (FIXTURES / name).exists():
                return httpx.Response(204)
            return httpx.Response(200, json=fixture(name))
        if path == PROCUREMENT_PATH:
            return httpx.Response(200, json=fixture("compra_82939422000191_2026_153.json"))
        if path == FILES_PATH:
            return httpx.Response(200, json=fixture("arquivos_82939422000191_2026_153.json"))
        if path.startswith(f"{FILES_PATH}/"):
            return httpx.Response(200, content=self.download)
        return httpx.Response(404, json={"message": "não encontrado"})

    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]


def make_client(
    fake: Handler,
    *,
    cache: ResponseCache | None = None,
    sleeps: list[float] | None = None,
    min_interval: float = 0.0,
    clock: Callable[[], float] | None = None,
) -> PncpClient:
    recorded = sleeps if sleeps is not None else []
    return PncpClient(
        consulta_url=CONSULTA,
        api_url=API,
        max_retries=3,
        min_interval_seconds=min_interval,
        cache=cache,
        transport=httpx.MockTransport(fake),
        sleep=recorded.append,
        clock=clock or (lambda: 0.0),
    )


def filters(**overrides: Any) -> SearchFilters:
    base: dict[str, Any] = {
        "date_from": dt.date(2026, 11, 4),
        "date_to": dt.date(2026, 11, 4),
        "modalities": (4, 5),
        "uf": "SC",
        "keywords": "pavimentação",
    }
    return SearchFilters(**{**base, **overrides})


# --- Client: retry, timeout, rate limit, cache -----------------------------------------


def test_server_errors_are_retried_with_backoff() -> None:
    answers = iter([httpx.Response(503), httpx.Response(502), httpx.Response(200, json=[])])
    sleeps: list[float] = []
    client = make_client(lambda request: next(answers), sleeps=sleeps)

    assert client.get_json(f"{API}/x") == []
    assert sleeps == [1.0, 2.0]


def test_retry_after_is_honoured_on_429() -> None:
    answers = iter(
        [httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json={"a": 1})]
    )
    sleeps: list[float] = []
    client = make_client(lambda request: next(answers), sleeps=sleeps)

    assert client.get_json(f"{API}/x") == {"a": 1}
    assert sleeps == [7.0]


def test_timeouts_give_up_after_the_retries() -> None:
    calls: list[int] = []

    def timeout(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(PncpError, match="não respondeu"):
        make_client(timeout).get_json(f"{API}/x")
    assert len(calls) == 4  # first attempt + 3 retries


def test_client_errors_are_not_retried_and_keep_the_pncp_message() -> None:
    calls: list[int] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(422, json={"message": "Período inicial e final maior que 365 dias."})

    with pytest.raises(PncpError, match="365 dias") as error:
        make_client(refuse).get_json(f"{API}/x")
    assert error.value.status_code == 422
    assert len(calls) == 1


def test_no_content_is_none() -> None:
    assert make_client(lambda request: httpx.Response(204)).get_json(f"{API}/x") is None


def test_requests_are_spaced_by_the_minimum_interval() -> None:
    times = iter([10.0, 10.0, 10.2, 10.2, 12.0, 12.0])
    sleeps: list[float] = []
    client = make_client(
        lambda request: httpx.Response(200, json=[]),
        sleeps=sleeps,
        min_interval=1.0,
        clock=lambda: next(times),
    )

    for _ in range(3):
        client.get_json(f"{API}/x")

    assert sleeps == [pytest.approx(0.8)]  # the second came 0.2 s after the first


def test_cached_responses_are_not_requested_again(tmp_path: Path) -> None:
    fake = FakePncp()
    client = make_client(fake, cache=ResponseCache(tmp_path, ttl_seconds=3600))

    first = client.list_files("82939422000191", 2026, 153)
    second = client.list_files("82939422000191", 2026, 153)

    assert first == second and len(first) == 7
    assert len(fake.requests) == 1


def test_cache_expires_and_remembers_no_content(tmp_path: Path) -> None:
    now = [1_000.0]
    cache = ResponseCache(tmp_path, ttl_seconds=60, clock=lambda: now[0])
    cache.set("k", {"data": None})

    assert cache.get("k") == {"data": None}  # a cached 204, not a miss
    now[0] = (tmp_path / next(p.name for p in tmp_path.iterdir())).stat().st_mtime + 61
    assert cache.get("k") is None


def test_downloads_above_the_limit_are_refused() -> None:
    client = make_client(lambda request: httpx.Response(200, content=b"x" * 2048))

    with pytest.raises(PncpError, match="limite"):
        client.download(f"{API}/file", max_bytes=1024)


# --- Search -----------------------------------------------------------------------------


def _all_recorded() -> list[dict[str, Any]]:
    return [
        item
        for path in sorted(FIXTURES.glob("publicacao_*.json"))
        for item in json.loads(path.read_text(encoding="utf-8"))["data"]
    ]


def test_search_reads_every_page_and_filters_the_object_by_keyword() -> None:
    fake = FakePncp()

    outcome = search(make_client(fake), filters(), limit=50)

    expected = {
        item["numeroControlePNCP"]
        for item in _all_recorded()
        if "paviment" in item["objetoCompra"].lower()
    }
    assert {p.control_number for p in outcome.results} == expected
    assert CONTROL in expected and len(expected) >= 8
    # 3 pages of concorrência eletrônica (4) and 1 of presencial (5).
    assert outcome.scanned == len(_all_recorded())
    assert not outcome.truncated
    params = [dict(r.url.params) for r in fake.requests]
    assert params[0] == {
        "dataInicial": "20261104",
        "dataFinal": "20261104",
        "codigoModalidadeContratacao": "4",
        "pagina": "1",
        "tamanhoPagina": "50",
        "uf": "SC",
    }


def test_keywords_ignore_accents_and_case_and_all_must_appear() -> None:
    accentless = search(make_client(FakePncp()), filters(keywords="PAVIMENTACAO"), limit=50)
    narrower = search(make_client(FakePncp()), filters(keywords="pavimentação asfáltica"), limit=50)

    assert (
        accentless.total_matches
        == search(make_client(FakePncp()), filters(), limit=50).total_matches
    )
    assert 0 < narrower.total_matches < accentless.total_matches
    assert all("asf" in p.object.lower() for p in narrower.results)


def test_municipality_name_is_matched_locally() -> None:
    outcome = search(make_client(FakePncp()), filters(municipality="erval velho"), limit=50)

    assert [p.control_number for p in outcome.results] == [CONTROL]
    assert outcome.results[0].estimated_value == 371811.12


def test_page_limit_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "pncp_search_max_pages", 1)

    outcome = search(make_client(FakePncp()), filters(modalities=(4,)), limit=50)

    assert outcome.truncated
    assert "primeiras 1 páginas" in outcome.warnings[0]


def test_results_are_capped_by_the_limit() -> None:
    outcome = search(make_client(FakePncp()), filters(), limit=2)

    assert len(outcome.results) == 2 and outcome.total_matches > 2


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"date_to": dt.date(2026, 11, 1)}, "anterior"),
        ({"date_from": dt.date(2025, 1, 1)}, "365"),
        ({"modalities": (99,)}, "Modalidade"),
        ({"uf": "Santa Catarina"}, "UF"),
        ({"ibge_code": "42"}, "IBGE"),
    ],
)
def test_invalid_filters_are_refused_before_calling_the_pncp(
    overrides: dict[str, Any], message: str
) -> None:
    fake = FakePncp()

    with pytest.raises(PncpInputError, match=message):
        search(make_client(fake), filters(**overrides), limit=10)
    assert fake.requests == []


def test_procurement_fields_are_mapped_from_the_recorded_response() -> None:
    procurement = Procurement.from_api(fixture("compra_82939422000191_2026_153.json"))

    assert procurement.control_number == CONTROL
    assert (procurement.cnpj, procurement.year, procurement.sequential) == (
        "82939422000191",
        2026,
        153,
    )
    assert procurement.municipality == "Erval Velho" and procurement.uf == "SC"
    assert "PAVIMENTAÇÃO ASFÁLTICA" in procurement.object


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (CONTROL, ("82939422000191", 2026, 153)),
        ("  95954509000180-1-000104/2026 ", ("95954509000180", 2026, 104)),
    ],
)
def test_control_numbers_are_parsed(value: str, expected: tuple[str, int, int]) -> None:
    assert parse_control_number(value) == expected


@pytest.mark.parametrize("value", ["123", "82939422000191-1-000153", "abc-1-1/2026"])
def test_invalid_control_numbers_are_refused(value: str) -> None:
    with pytest.raises(PncpInputError):
        parse_control_number(value)


# --- API: search and import ---------------------------------------------------------------


@pytest.fixture
def pncp(client: TestClient, lauro_muller_pdf: bytes) -> Iterator[FakePncp]:
    # The recorded Erval Velho procurement, serving a real (Lauro Müller) PDF as its edital.
    fake = FakePncp(download=lauro_muller_pdf)
    app: Any = client.app
    app.dependency_overrides[get_pncp_client] = lambda: make_client(fake)
    yield fake
    app.dependency_overrides.pop(get_pncp_client, None)


def test_search_endpoint(client: TestClient, pncp: FakePncp) -> None:
    response = client.get(
        "/pncp/search",
        params={
            "data_inicial": "2026-11-04",
            "data_final": "2026-11-04",
            "uf": "SC",
            "q": "pavimentação",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_matches"] == len(body["results"]) >= 8
    assert body["results"][0]["control_number"]


def test_search_endpoint_validates_the_period(client: TestClient, pncp: FakePncp) -> None:
    response = client.get(
        "/pncp/search", params={"data_inicial": "2025-01-01", "data_final": "2026-11-04"}
    )

    assert response.status_code == 422
    assert "365" in response.json()["detail"]


def test_search_endpoint_reports_an_unavailable_pncp(client: TestClient, pncp: FakePncp) -> None:
    pncp.overrides["/api/consulta/v1/contratacoes/publicacao"] = lambda r: httpx.Response(500)

    response = client.get(
        "/pncp/search", params={"data_inicial": "2026-11-04", "data_final": "2026-11-04"}
    )

    assert response.status_code == 502


def test_import_downloads_the_edital_and_ingests_it(client: TestClient, pncp: FakePncp) -> None:
    response = client.post("/pncp/import", json={"numero_controle": CONTROL})

    assert response.status_code == 202
    body = response.json()
    assert body["procurement"]["municipality"] == "Erval Velho"
    assert body["skipped"] == []
    [imported] = body["documents"]
    assert imported["file"]["type_name"] == "Edital" and imported["file"]["sequential"] == 1
    assert imported["duplicate"] is False
    # Only the file of type "Edital" is downloaded, from the documented path.
    assert pncp.paths()[-1] == f"{FILES_PATH}/1"
    assert pncp.requests[-1].url.host == "pncp.test"

    # TestClient runs the background ingestion before returning.
    document = client.get(f"/documents/{imported['document']['id']}").json()
    assert document["status"] == "ready"
    assert (document["source"], document["source_ref"]) == ("pncp", f"{CONTROL}#arquivo-1")
    assert document["metadata"]["pncp"]["control_number"] == CONTROL
    assert document["metadata"]["pdf"]  # ingestion metadata kept alongside


def test_importing_again_does_not_download_again(client: TestClient, pncp: FakePncp) -> None:
    client.post("/pncp/import", json={"numero_controle": CONTROL})
    downloads = sum(p.startswith(f"{FILES_PATH}/") for p in pncp.paths())

    again = client.post("/pncp/import", json={"numero_controle": CONTROL})

    assert again.status_code == 202
    assert again.json()["documents"][0]["duplicate"] is True
    assert sum(p.startswith(f"{FILES_PATH}/") for p in pncp.paths()) == downloads


def test_a_chosen_file_can_be_imported(client: TestClient, pncp: FakePncp) -> None:
    response = client.post(
        "/pncp/import", json={"numero_controle": CONTROL, "sequencial_documento": 2}
    )

    assert response.status_code == 202
    assert response.json()["documents"][0]["file"]["type_name"] == "Termo de Referência"


def test_procurement_without_an_edital_file_lists_what_exists(
    client: TestClient, pncp: FakePncp
) -> None:
    files = [
        f for f in fixture("arquivos_82939422000191_2026_153.json") if f["tipoDocumentoId"] != 2
    ]
    pncp.overrides[FILES_PATH] = lambda r: httpx.Response(200, json=files)

    response = client.post("/pncp/import", json={"numero_controle": CONTROL})

    assert response.status_code == 404
    assert "2 (Termo de Referência)" in response.json()["detail"]


def test_a_zip_file_is_skipped_with_a_clear_message(client: TestClient, pncp: FakePncp) -> None:
    pncp.download = b"PK\x03\x04 zip content"

    response = client.post("/pncp/import", json={"numero_controle": CONTROL})

    assert response.status_code == 422
    assert "ZIP" in response.json()["detail"]


def test_unknown_procurement_and_invalid_number(client: TestClient, pncp: FakePncp) -> None:
    pncp.overrides[PROCUREMENT_PATH] = lambda r: httpx.Response(204)

    assert client.post("/pncp/import", json={"numero_controle": CONTROL}).status_code == 404
    assert client.post("/pncp/import", json={"numero_controle": "x"}).status_code == 422


def test_acceptance_search_import_and_analyze_end_to_end(
    client: TestClient,
    pncp: FakePncp,
    fakes: tuple[FakeLLM, FakeEmbedder],  # noqa: F811
) -> None:
    """Search "pavimentação" in SC, import the edital and analyse it (fake LLM)."""
    found = client.get(
        "/pncp/search",
        params={
            "data_inicial": "2026-11-04",
            "data_final": "2026-11-04",
            "uf": "SC",
            "q": "pavimentação",
        },
    ).json()
    chosen = next(r for r in found["results"] if r["control_number"] == CONTROL)

    imported = client.post("/pncp/import", json={"numero_controle": chosen["control_number"]})
    document_id = imported.json()["documents"][0]["document"]["id"]
    started = client.post(f"/documents/{document_id}/analyze")
    analysis = client.get(f"/analyses/{started.json()['id']}").json()

    assert analysis["status"] == "completed"
    assert analysis["result"]["estimated_value"]["citations"][0]["status"] == "valid"
    assert analysis["risks"] is not None
