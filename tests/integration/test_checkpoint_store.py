import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from pactum.monitoring.checkpoint_store import load_checkpoint, save_checkpoint
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
            "DELETE FROM dataset_checkpoints WHERE dataset_id = %(dataset_id)s",
            {"dataset_id": dataset_id},
        )


def test_load_checkpoint_returns_none_when_never_saved(dataset_id: str) -> None:
    assert load_checkpoint(dataset_id) is None


def test_save_and_load_checkpoint_round_trip(dataset_id: str) -> None:
    checked_through = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    save_checkpoint(dataset_id, checked_through)

    assert load_checkpoint(dataset_id) == checked_through


def test_save_checkpoint_overwrites_the_previous_value(dataset_id: str) -> None:
    save_checkpoint(dataset_id, datetime(2026, 1, 1, tzinfo=UTC))
    save_checkpoint(dataset_id, datetime(2026, 1, 2, tzinfo=UTC))

    assert load_checkpoint(dataset_id) == datetime(2026, 1, 2, tzinfo=UTC)
