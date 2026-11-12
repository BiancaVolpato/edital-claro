"""Record the spending limit and the application version of each result.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("analyses", "eligibility_checks"):
        op.add_column(table, sa.Column("cost_limit_usd", sa.Float(), nullable=True))
        op.add_column(table, sa.Column("app_version", sa.String(50), nullable=True))


def downgrade() -> None:
    for table in ("eligibility_checks", "analyses"):
        op.drop_column(table, "app_version")
        op.drop_column(table, "cost_limit_usd")
