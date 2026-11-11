"""Create law_provisions with a vector column and a full-text index.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "law_provisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("law", sa.String(50), nullable=False),
        sa.Column("identifier", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("article", sa.Integer(), nullable=False),
        sa.Column("parent", sa.String(100), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("heading", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column(
            "search",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('portuguese', context)", persisted=True),
            nullable=False,
        ),
        sa.UniqueConstraint("law", "identifier", name="uq_law_provisions_law_identifier"),
    )
    op.create_index("ix_law_provisions_article", "law_provisions", ["article"])
    # The embedding column has no approximate index: at this size an exact scan is
    # fast and exact (see the model for details).
    op.create_index(
        "ix_law_provisions_search", "law_provisions", ["search"], postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_table("law_provisions")
