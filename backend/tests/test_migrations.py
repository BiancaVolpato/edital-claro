import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

from app.db.base import Base
from tests.conftest import USE_POSTGRES, alembic_config

needs_postgres = pytest.mark.skipif(not USE_POSTGRES, reason="needs PostgreSQL (RUN_DB_TESTS=1)")


def test_migration_history_has_a_single_head() -> None:
    script = ScriptDirectory.from_config(alembic_config())

    assert script.get_heads() == [script.get_current_head()]
    assert script.get_base() == "0001"


def test_migrations_render_as_sql_offline(capsys: pytest.CaptureFixture[str]) -> None:
    """Render the migrations as SQL, which needs no database connection."""
    command.upgrade(alembic_config(), "head", sql=True)

    sql = capsys.readouterr().out
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    for table in ("documents", "pages", "chunks"):
        assert f"CREATE TABLE {table}" in sql


@pytest.mark.db
@needs_postgres
def test_migrations_apply_to_a_real_database(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        installed = connection.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar()

    assert installed == 1


@pytest.mark.db
@needs_postgres
def test_migrations_match_the_orm_models(db_engine: Engine) -> None:
    """Migrations are written by hand, so guard against drift from the models."""
    with db_engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert differences == []
