"""create explanations table

Revision ID: 11dc5b0c9362
Revises: f6bc551ca772
Create Date: 2026-08-10 11:57:43.945148

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "11dc5b0c9362"
down_revision: str | Sequence[str] | None = "f6bc551ca772"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "explanations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("hypotheses", sa.JSON(), nullable=False),
        sa.Column("reasoning_trace", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_foreign_key(
        "fk_explanations_incident_id",
        "explanations",
        "incidents",
        ["incident_id"],
        ["id"],
    )
    op.create_index("ix_explanations_incident_id", "explanations", ["incident_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_explanations_incident_id", table_name="explanations")
    op.drop_constraint("fk_explanations_incident_id", "explanations", type_="foreignkey")
    op.drop_table("explanations")
