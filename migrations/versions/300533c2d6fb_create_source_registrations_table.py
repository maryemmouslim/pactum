"""create source registrations table

Revision ID: 300533c2d6fb
Revises: b1d31f13ac50
Create Date: 2026-07-27 11:58:58.925587

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "300533c2d6fb"
down_revision: str | Sequence[str] | None = "b1d31f13ac50"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "source_registrations",
        sa.Column("dataset_id", sa.Text(), primary_key=True),
        sa.Column("adapter_type", sa.Text(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("source_registrations")
