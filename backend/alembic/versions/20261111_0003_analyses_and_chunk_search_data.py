"""Add analyses, plus page spans and cached embeddings on chunks.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Chunks created before this migration get an empty list; re-ingest those
    # documents to have page markers in the extraction context.
    op.add_column(
        "chunks",
        sa.Column("page_spans", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.alter_column("chunks", "page_spans", server_default=None)
    op.add_column("chunks", sa.Column("embedding", sa.LargeBinary(), nullable=True))
    op.add_column("chunks", sa.Column("embedding_model", sa.String(200), nullable=True))

    op.create_table(
        "analyses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("steps_done", sa.Integer(), nullable=False),
        sa.Column("steps_total", sa.Integer(), nullable=False),
        sa.Column("strategy", sa.String(50), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("llm_provider", sa.String(50), nullable=False),
        sa.Column("llm_model", sa.String(100), nullable=False),
        sa.Column("embedding_model", sa.String(200), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("runs", postgresql.JSONB(), nullable=False),
        sa.Column("citation_counts", postgresql.JSONB(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_analyses_document_id", "analyses", ["document_id"])


def downgrade() -> None:
    op.drop_table("analyses")
    op.drop_column("chunks", "embedding_model")
    op.drop_column("chunks", "embedding")
    op.drop_column("chunks", "page_spans")
