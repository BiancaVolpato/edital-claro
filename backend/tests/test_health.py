import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app import __version__
from app.db import session as db_session
from app.db.session import check_database


def test_health_reports_database_ok(client: TestClient) -> None:
    client.app.dependency_overrides[check_database] = lambda: True  # type: ignore[attr-defined]

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": __version__,
        "database": "ok",
        "demo": False,
    }


def test_health_stays_up_when_database_is_down(client: TestClient) -> None:
    client.app.dependency_overrides[check_database] = lambda: False  # type: ignore[attr-defined]

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "unavailable"


def test_check_database_returns_false_when_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Port 1 is never a PostgreSQL server, so the connection is refused immediately.
    unreachable = create_engine(
        "postgresql+psycopg://user:pass@127.0.0.1:1/nope",
        connect_args={"connect_timeout": 1},
    )
    monkeypatch.setattr(db_session, "get_engine", lambda: unreachable)

    assert check_database() is False
