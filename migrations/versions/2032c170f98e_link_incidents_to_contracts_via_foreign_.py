"""link incidents to contracts via foreign key

Revision ID: 2032c170f98e
Revises: 6be1e8b2388f
Create Date: 2026-07-27 12:40:56.972456

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2032c170f98e"
down_revision: str | Sequence[str] | None = "6be1e8b2388f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("incidents", "contract_version")
    op.add_column("incidents", sa.Column("contract_version_id", sa.Uuid(), nullable=False))
    op.create_foreign_key(
        "fk_incidents_contract_version_id",
        "incidents",
        "contracts",
        ["contract_version_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_incidents_contract_version_id", "incidents", type_="foreignkey")
    op.drop_column("incidents", "contract_version_id")
    op.add_column("incidents", sa.Column("contract_version", sa.Text(), nullable=True))
