"""add reason to refinements

Revision ID: b49ef078fa87
Revises: 16cb1fee0299
Create Date: 2026-08-10 16:07:31.108447

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b49ef078fa87"
down_revision: str | Sequence[str] | None = "16cb1fee0299"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("refinements", sa.Column("reason", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("refinements", "reason")
