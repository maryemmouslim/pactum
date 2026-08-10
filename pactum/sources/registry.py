from datetime import UTC, datetime

import psycopg
import psycopg.types.json

from pactum.settings import settings
from pactum.sources.duckdb_adapter import DuckDBAdapter
from pactum.sources.postgres_adapter import PostgresAdapter
from pactum.sources.protocol import SourceAdapter

_adapters: dict[str, SourceAdapter] = {}


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


def register_source(adapter: SourceAdapter, *, persist: bool = False) -> None:
    """Register every dataset exposed by a source adapter, in the in-memory cache.

    Pass persist=True to also durably save the registration to Postgres, so
    a future process can call load_persisted_registrations() to restore it
    after a restart instead of losing it. Defaults to False so unit tests
    registering fake adapters never need a real database.
    """
    for dataset_id in adapter.list_datasets():
        _adapters[dataset_id] = adapter
    if persist:
        _persist_registration(adapter)


def list_registered_datasets() -> list[str]:
    """Return every dataset_id currently registered, regardless of which adapter owns it."""
    return sorted(_adapters)


def get_adapter(dataset_id: str) -> SourceAdapter:
    """Return the adapter that owns a given dataset_id, from the in-memory cache.

    Call load_persisted_registrations() at process startup to restore
    registrations saved in a previous run before relying on this.
    """
    try:
        return _adapters[dataset_id]
    except KeyError:
        raise KeyError(f"No source registered for dataset '{dataset_id}'") from None


def load_persisted_registrations() -> int:
    """Rebuild the in-memory cache from registrations durably saved in Postgres.

    Call this once at process startup, before anything calls get_adapter, so
    registrations survive a restart. Returns how many datasets were restored.
    """
    with _connect() as conn:
        rows = conn.execute("SELECT dataset_id, config FROM source_registrations").fetchall()
    for dataset_id, config in rows:
        _adapters[dataset_id] = _adapter_from_config(config)
    return len(rows)


def _persist_registration(adapter: SourceAdapter) -> None:
    config = adapter.to_registration_config()
    with _connect() as conn:
        for dataset_id in adapter.list_datasets():
            conn.execute(
                """
                INSERT INTO source_registrations (dataset_id, adapter_type, config, registered_at)
                VALUES (%(dataset_id)s, %(adapter_type)s, %(config)s, %(registered_at)s)
                ON CONFLICT (dataset_id) DO UPDATE SET
                    adapter_type = EXCLUDED.adapter_type,
                    config = EXCLUDED.config,
                    registered_at = EXCLUDED.registered_at
                """,
                {
                    "dataset_id": dataset_id,
                    "adapter_type": config["adapter_type"],
                    "config": psycopg.types.json.Json(config),
                    "registered_at": datetime.now(UTC),
                },
            )


def _adapter_from_config(config: dict[str, object]) -> SourceAdapter:
    adapter_type = config["adapter_type"]
    if adapter_type == "duckdb":
        return DuckDBAdapter(str(config["directory"]))
    if adapter_type == "postgres":
        return PostgresAdapter(str(config["connection_url"]))
    raise ValueError(f"Unknown adapter_type: {adapter_type!r}")
