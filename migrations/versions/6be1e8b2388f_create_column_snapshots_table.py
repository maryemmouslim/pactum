"""create column snapshots table

Revision ID: 6be1e8b2388f
Revises: 300533c2d6fb
Create Date: 2026-07-27 12:29:06.248044

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6be1e8b2388f"
down_revision: str | Sequence[str] | None = "300533c2d6fb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "column_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("dataset_id", sa.Text(), nullable=False),
        sa.Column("column_name", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.UniqueConstraint("dataset_id", "column_name"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("column_snapshots")
