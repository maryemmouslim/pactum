import uuid
from datetime import UTC, date, datetime

import psycopg
import pytest

from pactum.monitoring.snapshot_store import load_reference_snapshot, save_reference_snapshot
from pactum.settings import settings


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


@pytest.fixture
def dataset_id() -> str:
    return f"test_dataset_{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _cleanup(dataset_id: str):  # type: ignore[no-untyped-def]
    yield
    with _connect() as conn:
        conn.execute(
            "DELETE FROM column_snapshots WHERE dataset_id = %(dataset_id)s",
            {"dataset_id": dataset_id},
        )


def test_load_reference_snapshot_returns_none_when_none_saved(dataset_id: str) -> None:
    assert load_reference_snapshot(dataset_id, "amount") is None


def test_save_and_load_reference_snapshot_round_trip(dataset_id: str) -> None:
    save_reference_snapshot(dataset_id, "amount", [10.0, 20.0, 30.0])

    result = load_reference_snapshot(dataset_id, "amount")

    assert result == [10.0, 20.0, 30.0]


def test_save_reference_snapshot_does_not_overwrite_an_existing_one(dataset_id: str) -> None:
    save_reference_snapshot(dataset_id, "amount", [1.0, 2.0])
    save_reference_snapshot(dataset_id, "amount", [999.0])  # should be ignored

    result = load_reference_snapshot(dataset_id, "amount")

    assert result == [1.0, 2.0]


def test_snapshots_are_independent_per_column(dataset_id: str) -> None:
    save_reference_snapshot(dataset_id, "amount", [1.0])
    save_reference_snapshot(dataset_id, "status", ["pending"])

    assert load_reference_snapshot(dataset_id, "amount") == [1.0]
    assert load_reference_snapshot(dataset_id, "status") == ["pending"]


def test_save_and_load_reference_snapshot_round_trips_datetime_values(dataset_id: str) -> None:
    # Reproduces the real bug: a "timestamp" column's raw values are real
    # datetime objects, which psycopg's Json wrapper can't serialize at all
    # without the _to_json_safe/_from_json_safe tagging.
    values = [
        datetime(2026, 7, 24, 11, 45, 0, tzinfo=UTC),
        datetime(2026, 7, 24, 11, 40, 0, tzinfo=UTC),
    ]
    save_reference_snapshot(dataset_id, "created_at", values)

    result = load_reference_snapshot(dataset_id, "created_at")

    assert result == values


def test_save_and_load_reference_snapshot_round_trips_date_values(dataset_id: str) -> None:
    # Reproduces the real bug: a source column stored as SQL DATE (no time
    # component, e.g. "Order Date" from a CSV like 08/11/2017) comes back
    # from the adapter as a plain date, not a datetime.
    values = [date(2017, 11, 8), date(2017, 11, 9)]
    save_reference_snapshot(dataset_id, "order_date", values)

    result = load_reference_snapshot(dataset_id, "order_date")

    assert result == values
