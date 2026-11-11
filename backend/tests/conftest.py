import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, delete, func, select
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db import session as db_session
from app.db.base import Base
from app.db.models import Document, LawProvision
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[1]
SAMPLES_DIR = BACKEND_DIR.parent / "data" / "samples"

# With RUN_DB_TESTS=1 (CI) the suite runs against the real PostgreSQL in DATABASE_URL.
# Otherwise it uses an in-memory SQLite database, so no external service is needed.
USE_POSTGRES = os.getenv("RUN_DB_TESTS") == "1"


def alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


@pytest.fixture(scope="session")
def _postgres_engine() -> Iterator[Engine | None]:
    if not USE_POSTGRES:
        yield None
        return
    engine = create_engine(get_settings().database_url)
    command.upgrade(alembic_config(), "head")
    # Tests delete every document and the law index when they finish. Refuse to
    # run against a database that already holds data (e.g. the development one).
    with engine.connect() as connection:
        existing = {
            model.__tablename__: connection.execute(
                select(func.count()).select_from(model)
            ).scalar()
            for model in (Document, LawProvision)
        }
    if any(existing.values()):
        engine.dispose()
        pytest.exit(
            f"The database in DATABASE_URL already holds data ({existing}) that the tests "
            "would delete. Point DATABASE_URL to an empty database used only for tests.",
            returncode=2,
        )
    yield engine
    engine.dispose()


@pytest.fixture
def db_engine(
    _postgres_engine: Engine | None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Engine]:
    """A clean database, with uploads redirected to a temporary folder."""
    if _postgres_engine is not None:
        engine = _postgres_engine
    else:
        engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        # Tables that need PostgreSQL features (pgvector, full-text search) are left out.
        portable = [t for t in Base.metadata.sorted_tables if not t.info.get("postgres_only")]
        Base.metadata.create_all(engine, tables=portable)

    monkeypatch.setattr(db_session, "get_engine", lambda: engine)
    monkeypatch.setattr(get_settings(), "storage_dir", tmp_path / "uploads")
    yield engine

    if _postgres_engine is not None:
        with engine.begin() as connection:
            connection.execute(delete(Document))  # pages and chunks go with it (cascade)
    else:
        engine.dispose()


@pytest.fixture
def client(db_engine: Engine) -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def florianopolis_pdf() -> bytes:
    """88-page edital with a native text layer."""
    return (SAMPLES_DIR / "florianopolis_cc_90330_2026.pdf").read_bytes()


@pytest.fixture(scope="session")
def lauro_muller_pdf() -> bytes:
    """28-page edital with a native text layer."""
    return (SAMPLES_DIR / "lauro_muller_cc_233_2026.pdf").read_bytes()


@pytest.fixture(scope="session")
def mixed_scan_pdf() -> bytes:
    """Pages 3-5 of the Lauro Müller edital; the middle page is an image without text."""
    return (SAMPLES_DIR / "lauro_muller_cc_233_2026_ocr_misto.pdf").read_bytes()
