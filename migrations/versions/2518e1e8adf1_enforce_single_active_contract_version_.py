"""enforce single active contract version per dataset

Revision ID: 2518e1e8adf1
Revises: 2032c170f98e
Create Date: 2026-07-27 12:51:23.675999

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2518e1e8adf1"
down_revision: str | Sequence[str] | None = "2032c170f98e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ix_contracts_one_active_per_dataset",
        "contracts",
        ["dataset_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_contracts_one_active_per_dataset", table_name="contracts")
