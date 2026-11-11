import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.db.session import get_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


def test_migration_history_has_a_single_head() -> None:
    script = ScriptDirectory.from_config(_alembic_config())

    assert script.get_heads() == [script.get_current_head()]
    assert script.get_base() == "0001"


def test_initial_migration_enables_pgvector_offline(capsys: pytest.CaptureFixture[str]) -> None:
    """Render the migration as SQL, which needs no database connection."""
    command.upgrade(_alembic_config(), "head", sql=True)

    assert "CREATE EXTENSION IF NOT EXISTS vector" in capsys.readouterr().out


@pytest.mark.db
@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="needs PostgreSQL (RUN_DB_TESTS=1)")
def test_migrations_apply_to_a_real_database() -> None:
    command.upgrade(_alembic_config(), "head")

    with get_engine().connect() as connection:
        installed = connection.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar()

    assert installed == 1
