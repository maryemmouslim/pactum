import uuid

import psycopg
import pytest

from pactum.settings import settings
from pactum.sources import registry as source_registry
from pactum.sources.duckdb_adapter import DuckDBAdapter


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


@pytest.fixture
def dataset_id() -> str:
    return f"test_dataset_{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _cleanup(dataset_id: str):  # type: ignore[no-untyped-def]
    source_registry._adapters.clear()
    yield
    source_registry._adapters.clear()
    with _connect() as conn:
        conn.execute(
            "DELETE FROM source_registrations WHERE dataset_id = %(dataset_id)s",
            {"dataset_id": dataset_id},
        )


def test_persisted_registration_survives_a_simulated_restart(
    dataset_id: str, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Set up a real CSV so DuckDBAdapter has something real to read.
    csv_path = tmp_path / f"{dataset_id}.csv"
    csv_path.write_text("id,name\n1,a\n2,b\n")
    adapter = DuckDBAdapter(str(tmp_path))
    monkeypatch.setattr(adapter, "list_datasets", lambda: [dataset_id])

    source_registry.register_source(adapter, persist=True)
    assert source_registry.get_adapter(dataset_id) is adapter

    # Simulate a process restart: the in-memory cache is gone.
    source_registry._adapters.clear()
    with pytest.raises(KeyError):
        source_registry.get_adapter(dataset_id)

    # Recover from what was durably saved in Postgres.
    restored_count = source_registry.load_persisted_registrations()
    assert restored_count >= 1

    recovered_adapter = source_registry.get_adapter(dataset_id)
    assert recovered_adapter is not adapter  # a genuinely new, reconstructed instance
    assert recovered_adapter.get_schema(dataset_id) == {"id": "BIGINT", "name": "VARCHAR"}
    assert recovered_adapter.sample(dataset_id, n=10) == [(1, "a"), (2, "b")]


def test_persisted_registration_upserts_on_re_registration(dataset_id: str, tmp_path) -> None:
    csv_path = tmp_path / f"{dataset_id}.csv"
    csv_path.write_text("id\n1\n")

    first_adapter = DuckDBAdapter(str(tmp_path))
    source_registry.register_source(first_adapter, persist=True)

    with _connect() as conn:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM source_registrations WHERE dataset_id = %(dataset_id)s",
            {"dataset_id": dataset_id},
        ).fetchone()
    assert count == 1

    # Re-registering the same dataset_id should update, not duplicate.
    source_registry.register_source(first_adapter, persist=True)

    with _connect() as conn:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM source_registrations WHERE dataset_id = %(dataset_id)s",
            {"dataset_id": dataset_id},
        ).fetchone()
    assert count == 1
