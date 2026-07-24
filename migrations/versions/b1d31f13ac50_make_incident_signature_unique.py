"""make incident signature unique

Revision ID: b1d31f13ac50
Revises: 41b5ea924013
Create Date: 2026-07-24 16:11:47.112597

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1d31f13ac50"
down_revision: str | Sequence[str] | None = "41b5ea924013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index("ix_incidents_signature", table_name="incidents")
    op.create_unique_constraint("uq_incidents_signature", "incidents", ["signature"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_incidents_signature", "incidents", type_="unique")
    op.create_index("ix_incidents_signature", "incidents", ["signature"])
