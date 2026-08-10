"""create refinements table

Revision ID: 16cb1fee0299
Revises: 11dc5b0c9362
Create Date: 2026-08-10 11:57:45.780054

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "16cb1fee0299"
down_revision: str | Sequence[str] | None = "11dc5b0c9362"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "refinements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("proposed_yaml", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_foreign_key(
        "fk_refinements_incident_id", "refinements", "incidents", ["incident_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_refinements_contract_id", "refinements", "contracts", ["contract_id"], ["id"]
    )
    op.create_index("ix_refinements_incident_id", "refinements", ["incident_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_refinements_incident_id", table_name="refinements")
    op.drop_constraint("fk_refinements_contract_id", "refinements", type_="foreignkey")
    op.drop_constraint("fk_refinements_incident_id", "refinements", type_="foreignkey")
    op.drop_table("refinements")
