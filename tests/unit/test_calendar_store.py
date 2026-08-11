import uuid
from datetime import UTC, datetime, timedelta

import pytest

from pactum.models import CalendarEvent
from pactum.monitoring.calendar_store import add_event, list_events_near


class FakeConnection:
    def __init__(self, rows: list[tuple[object, ...]] | None = None) -> None:
        self.executed: list[tuple[str, dict[str, object]]] = []
        self._rows = rows or []

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def execute(self, sql: str, params: dict[str, object] | None = None) -> "FakeConnection":
        self.executed.append((sql, params or {}))
        return self

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


def _row_for(event: CalendarEvent) -> tuple[object, ...]:
    return (
        event.id,
        event.dataset_id,
        event.event_type,
        event.description,
        event.event_at,
        event.created_at,
    )


def test_add_event_scoped_to_a_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = FakeConnection()
    monkeypatch.setattr("pactum.monitoring.calendar_store._connect", lambda: fake_conn)

    event = add_event(
        event_type="deployment",
        description="Shipped new ingestion pipeline",
        event_at=datetime(2026, 8, 10, tzinfo=UTC),
        dataset_id="orders",
    )

    assert event.dataset_id == "orders"
    sql, params = fake_conn.executed[0]
    assert "INSERT INTO calendar_events" in sql
    assert params["dataset_id"] == "orders"


def test_add_event_global_when_no_dataset_given(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = FakeConnection()
    monkeypatch.setattr("pactum.monitoring.calendar_store._connect", lambda: fake_conn)

    event = add_event(
        event_type="holiday",
        description="Public holiday",
        event_at=datetime(2026, 8, 10, tzinfo=UTC),
    )

    assert event.dataset_id is None


def test_list_events_near_passes_the_right_window(monkeypatch: pytest.MonkeyPatch) -> None:
    event = CalendarEvent(
        id=uuid.uuid4(),
        dataset_id="orders",
        event_type="deployment",
        description="Deploy",
        event_at=datetime(2026, 8, 10, tzinfo=UTC),
        created_at=datetime(2026, 8, 9, tzinfo=UTC),
    )
    fake_conn = FakeConnection(rows=[_row_for(event)])
    monkeypatch.setattr("pactum.monitoring.calendar_store._connect", lambda: fake_conn)

    around = datetime(2026, 8, 10, 12, tzinfo=UTC)
    results = list_events_near("orders", around, window=timedelta(days=2))

    assert results == [event]
    sql, params = fake_conn.executed[0]
    assert params["dataset_id"] == "orders"
    assert params["start"] == around - timedelta(days=2)
    assert params["end"] == around + timedelta(days=2)
