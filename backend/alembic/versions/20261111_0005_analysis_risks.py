"""Add the risk report and its prompt version to analyses.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("risk_prompt_version", sa.String(100), nullable=True))
    op.add_column("analyses", sa.Column("risk_prompt_hash", sa.String(64), nullable=True))
    op.add_column("analyses", sa.Column("risks", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("analyses", "risks")
    op.drop_column("analyses", "risk_prompt_hash")
    op.drop_column("analyses", "risk_prompt_version")
