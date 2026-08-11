"""create calendar_events table

Revision ID: cd0b454eac7b
Revises: b49ef078fa87
Create Date: 2026-08-10 16:14:00.941341

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cd0b454eac7b"
down_revision: str | Sequence[str] | None = "b49ef078fa87"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("dataset_id", sa.Text(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_calendar_events_dataset_id", "calendar_events", ["dataset_id"])
    op.create_index("ix_calendar_events_event_at", "calendar_events", ["event_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_calendar_events_event_at", table_name="calendar_events")
    op.drop_index("ix_calendar_events_dataset_id", table_name="calendar_events")
    op.drop_table("calendar_events")
