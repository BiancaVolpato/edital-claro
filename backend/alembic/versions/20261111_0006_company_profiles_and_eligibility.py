"""Add company profiles and eligibility checks.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "company_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "eligibility_checks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.Uuid(),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("company_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("profile_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("report", postgresql.JSONB(), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("llm_model", sa.String(100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_eligibility_checks_analysis_id", "eligibility_checks", ["analysis_id"])
    op.create_index("ix_eligibility_checks_profile_id", "eligibility_checks", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_eligibility_checks_profile_id", table_name="eligibility_checks")
    op.drop_index("ix_eligibility_checks_analysis_id", table_name="eligibility_checks")
    op.drop_table("eligibility_checks")
    op.drop_table("company_profiles")
