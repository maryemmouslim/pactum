import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import psycopg

from pactum.models import CalendarEvent
from pactum.settings import settings


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


def add_event(
    event_type: Literal["deployment", "holiday", "regulatory", "other"],
    description: str,
    event_at: datetime,
    dataset_id: str | None = None,
) -> CalendarEvent:
    """Record a known event (deployment, holiday, regulatory change, ...).

    dataset_id=None means the event applies to every dataset (e.g. a company
    holiday); set it to scope the event to one dataset (e.g. a deploy of
    that dataset's ingestion job). There's no external calendar source to
    pull from -- this is a manually maintained list.
    """
    event = CalendarEvent(
        id=uuid.uuid4(),
        dataset_id=dataset_id,
        event_type=event_type,
        description=description,
        event_at=event_at,
        created_at=datetime.now(UTC),
    )
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO calendar_events
                (id, dataset_id, event_type, description, event_at, created_at)
            VALUES
                (%(id)s, %(dataset_id)s, %(event_type)s, %(description)s, %(event_at)s,
                 %(created_at)s)
            """,
            event.model_dump(),
        )
    return event


def list_events_near(
    dataset_id: str, around: datetime, window: timedelta = timedelta(days=3)
) -> list[CalendarEvent]:
    """Return events for this dataset (or global events) within `window` of `around`."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, dataset_id, event_type, description, event_at, created_at
            FROM calendar_events
            WHERE (dataset_id = %(dataset_id)s OR dataset_id IS NULL)
              AND event_at BETWEEN %(start)s AND %(end)s
            ORDER BY event_at ASC
            """,
            {
                "dataset_id": dataset_id,
                "start": around - window,
                "end": around + window,
            },
        ).fetchall()
    return [_row_to_event(row) for row in rows]


def _row_to_event(row: tuple[object, ...]) -> CalendarEvent:
    columns = ["id", "dataset_id", "event_type", "description", "event_at", "created_at"]
    return CalendarEvent.model_validate(dict(zip(columns, row, strict=True)))
