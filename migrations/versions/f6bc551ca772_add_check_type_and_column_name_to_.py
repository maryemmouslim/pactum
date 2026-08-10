"""add check_type and column_name to incidents

Revision ID: f6bc551ca772
Revises: fcd3cbc9cf00
Create Date: 2026-08-10 11:57:42.046055

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6bc551ca772"
down_revision: str | Sequence[str] | None = "fcd3cbc9cf00"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default backfills any pre-existing rows so the column can be
    # NOT NULL immediately; every future insert supplies it explicitly via
    # emit_incident(), so the default is just a one-time migration safety net.
    op.add_column(
        "incidents",
        sa.Column("check_type", sa.Text(), nullable=False, server_default="unknown"),
    )
    op.alter_column("incidents", "check_type", server_default=None)
    op.add_column("incidents", sa.Column("column_name", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("incidents", "column_name")
    op.drop_column("incidents", "check_type")
