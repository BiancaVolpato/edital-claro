"""Demo mode, demo snapshots (export, seed, reset) and deploy settings."""

import datetime as dt
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select

from app.core.config import Settings, get_settings
from app.core.rate_limit import RateLimiter
from app.db import session as db_session
from app.db.models import Analysis, CompanyProfile, Document, EligibilityCheck
from app.demo.snapshots import (
    DEMO_SAMPLES,
    SAMPLES_DIR,
    SnapshotError,
    analyze_sample,
    clear_data,
    example_profile,
    export_snapshot,
    read_snapshots,
    seed,
    write_snapshot,
)
from app.main import create_app
from tests.fakes import FakeEmbedder, FakeLLM
from tests.test_analyses_api import fakes  # noqa: F401 (pytest fixture)

PDF = "application/pdf"
LAURO = SAMPLES_DIR / "lauro_muller_cc_233_2026.pdf"


@pytest.fixture
def generated(
    db_engine: Engine,
    fakes: tuple[FakeLLM, FakeEmbedder],  # noqa: F811
    tmp_path: Path,
) -> tuple[Path, dict[str, Any]]:
    """A snapshot made by the real pipeline (with the fake LLM) and saved to disk."""
    llm, _ = fakes
    with db_session.new_session() as session:
        profile = example_profile(session)
        analysis = analyze_sample(session, LAURO, llm, profile, dt.date(2026, 10, 1))
        snapshot = export_snapshot(session, analysis)
    demo_dir = tmp_path / "demo"
    write_snapshot(snapshot, demo_dir / "lauro.json")
    return demo_dir, snapshot


def _count(engine: Engine, model: type[Any]) -> int:
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(model)).scalar_one())


def test_a_snapshot_keeps_the_analysis_as_it_was_produced(
    generated: tuple[Path, dict[str, Any]],
) -> None:
    _, snapshot = generated

    assert snapshot["pdf"] == "data/samples/lauro_muller_cc_233_2026.pdf"
    assert snapshot["analysis"]["status"] == "completed"
    assert snapshot["analysis"]["result"]["estimated_value"]["value"] == 60296.85
    assert snapshot["analysis"]["risks"] is not None
    assert snapshot["analysis"]["runs"]  # per-call usage, for the audit trail
    [check] = snapshot["eligibility"]
    assert check["profile_snapshot"]["name"] == "Construtora Exemplo Ltda"
    json.dumps(snapshot)  # JSON-ready


def test_reset_and_seed_bring_back_the_same_results(
    client: TestClient, db_engine: Engine, generated: tuple[Path, dict[str, Any]]
) -> None:
    demo_dir, snapshot = generated

    with db_session.new_session() as session:
        cleared = clear_data(session)
        assert cleared["documents"] == 1 and cleared["arquivos"] == 1
        assert _count(db_engine, Document) == 0 and _count(db_engine, CompanyProfile) == 0
        result = seed(session, demo_dir)

    assert result.loaded == ["lauro"] and result.skipped == []
    [summary] = client.get("/analyses").json()
    analysis = client.get(f"/analyses/{summary['id']}").json()
    assert analysis["result"] == snapshot["analysis"]["result"]
    assert analysis["cost_usd"] == snapshot["analysis"]["cost_usd"]
    assert analysis["completed_at"].startswith(snapshot["analysis"]["completed_at"][:19])
    # The PDF and its pages are back, so citations open on the right page.
    document = client.get(f"/documents/{analysis['document_id']}").json()
    assert document["status"] == "ready" and document["page_count"] == 28
    assert client.get(f"/documents/{analysis['document_id']}/file").status_code == 200
    # The eligibility check is linked to the restored example profile.
    with db_engine.connect() as connection:
        check = connection.execute(select(EligibilityCheck)).one()
    assert check.profile_id is not None
    stored = client.get(f"/eligibility/{check.id}").json()
    assert stored["report"] == snapshot["eligibility"][0]["report"]


def test_seeding_twice_changes_nothing(
    db_engine: Engine, generated: tuple[Path, dict[str, Any]]
) -> None:
    demo_dir, _ = generated

    with db_session.new_session() as session:
        result = seed(session, demo_dir)

    assert result.loaded == [] and result.skipped == ["lauro"]
    assert _count(db_engine, Analysis) == 1
    assert _count(db_engine, CompanyProfile) == 1


def test_a_changed_pdf_is_refused(
    db_engine: Engine, generated: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    _, snapshot = generated
    snapshot["file_sha256"] = "0" * 64
    write_snapshot(snapshot, tmp_path / "other" / "x.json")

    with db_session.new_session() as session, pytest.raises(SnapshotError, match="mudou"):
        seed(session, tmp_path / "other")


def test_only_analyses_of_committed_samples_can_be_exported(
    client: TestClient,
    db_engine: Engine,
    fakes: tuple[FakeLLM, FakeEmbedder],  # noqa: F811
    tmp_path: Path,
) -> None:
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "Edital de teste, fora de data/samples.")
    path = tmp_path / "fora.pdf"
    path.write_bytes(document.tobytes())
    llm, _ = fakes

    with db_session.new_session() as session:
        analysis = analyze_sample(session, path, llm, example_profile(session), dt.date.today())
        with pytest.raises(SnapshotError, match="não está em"):
            export_snapshot(session, analysis)


def test_unknown_snapshot_formats_are_refused(tmp_path: Path) -> None:
    (tmp_path / "x.json").write_text('{"format": 99}', encoding="utf-8")

    with pytest.raises(SnapshotError, match="formato 99"):
        read_snapshots(tmp_path)


def test_committed_snapshots_point_to_the_demo_samples() -> None:
    """Whatever is in data/demo must be loadable: known format, existing PDF, same hash."""
    for name, snapshot in read_snapshots():
        assert name in DEMO_SAMPLES
        assert snapshot["analysis"]["status"] == "completed"
        pdf = SAMPLES_DIR.parent.parent / snapshot["pdf"]
        assert pdf.exists(), name


# --- Demo mode ------------------------------------------------------------------------


@pytest.fixture
def demo_client(db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    with TestClient(create_app()) as test_client:
        yield test_client


def test_demo_refuses_what_costs_money_or_needs_the_model(demo_client: TestClient) -> None:
    pdf = LAURO.read_bytes()
    refused = [
        demo_client.post("/documents", files={"file": ("e.pdf", pdf, PDF)}),
        demo_client.post("/documents/00000000-0000-0000-0000-000000000000/analyze"),
        demo_client.post("/pncp/import", json={"control_number": "x"}),
        demo_client.get("/law/search", params={"q": "garantia"}),
    ]

    assert [r.status_code for r in refused] == [403, 403, 403, 403]
    assert "demonstração pública" in refused[0].json()["detail"]
    assert demo_client.get("/analyses").status_code == 200
    assert demo_client.get("/profiles").status_code == 200
    assert demo_client.get("/health").json()["demo"] is True


def test_demo_eligibility_never_calls_the_llm(
    demo_client: TestClient,
    db_engine: Engine,
    generated: tuple[Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_llm() -> None:
        raise AssertionError("the demo must not build an LLM provider")

    monkeypatch.setattr("app.api.eligibility.get_llm_provider", no_llm)
    [summary] = demo_client.get("/analyses").json()
    [profile] = demo_client.get("/profiles").json()

    response = demo_client.post(
        f"/analyses/{summary['id']}/eligibility", json={"profile_id": profile["id"]}
    )

    assert response.status_code == 201
    assert response.json()["llm_model"] is None and response.json()["cost_usd"] == 0.0


# --- Deploy settings ------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "postgres://u:p@host:5432/db?sslmode=require",
        "postgresql://u:p@host:5432/db?sslmode=require",
        "postgresql+psycopg://u:p@host:5432/db?sslmode=require",
    ],
)
def test_platform_database_urls_get_the_psycopg_driver(url: str) -> None:
    settings = Settings(database_url=url, _env_file=None)

    assert settings.database_url == "postgresql+psycopg://u:p@host:5432/db?sslmode=require"


@pytest.mark.parametrize(
    ("token", "named", "expected"),
    [
        ("segredo", "1.2.3.4", "1.2.3.4"),  # the frontend proved itself
        ("errado", "1.2.3.4", "9.9.9.9"),  # wrong token: header ignored
        (None, "1.2.3.4", "9.9.9.9"),  # no token
        ("segredo", "não é ip", "9.9.9.9"),  # malformed address
    ],
)
def test_a_frontend_with_the_shared_token_names_the_visitor(
    token: str | None, named: str, expected: str
) -> None:
    limiter = RateLimiter(1, 1, [], proxy_token="segredo")

    assert limiter.client_ip("9.9.9.9", None, token, named) == expected


def test_without_a_configured_token_the_header_is_never_trusted() -> None:
    limiter = RateLimiter(1, 1, [])

    assert limiter.client_ip("9.9.9.9", None, "", "1.2.3.4") == "9.9.9.9"
