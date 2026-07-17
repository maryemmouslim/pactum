"""create lineage_edges table

Revision ID: 565c8114e4f5
Revises: f822946a2735
Create Date: 2026-07-17 16:19:58.064171

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '565c8114e4f5'
down_revision: Union[str, Sequence[str], None] = 'f822946a2735'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "lineage_edges",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("upstream_dataset_id", sa.Text(), nullable=False),
        sa.Column("downstream_dataset_id", sa.Text(), nullable=False),
        sa.UniqueConstraint("upstream_dataset_id", "downstream_dataset_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("lineage_edges")
