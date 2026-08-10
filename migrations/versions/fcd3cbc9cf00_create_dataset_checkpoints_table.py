"""create dataset checkpoints table

Revision ID: fcd3cbc9cf00
Revises: b98fd2ee454f
Create Date: 2026-07-28 17:02:15.762619

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fcd3cbc9cf00"
down_revision: str | Sequence[str] | None = "b98fd2ee454f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "dataset_checkpoints",
        sa.Column("dataset_id", sa.Text(), primary_key=True),
        sa.Column("checked_through", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("dataset_checkpoints")
