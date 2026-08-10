import uuid
from datetime import datetime

import psycopg
import pytest
from psycopg import sql

from pactum.settings import settings
from pactum.sources.postgres_adapter import PostgresAdapter


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


@pytest.fixture
def table_name() -> str:
    return f"test_table_{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _setup_and_teardown(table_name: str):  # type: ignore[no-untyped-def]
    with _connect() as conn:
        conn.execute(
            sql.SQL("CREATE TABLE {} (id INTEGER, name TEXT)").format(sql.Identifier(table_name))
        )
        conn.execute(
            sql.SQL("INSERT INTO {} (id, name) VALUES (1, 'a'), (2, 'b'), (3, 'c')").format(
                sql.Identifier(table_name)
            )
        )
    yield
    with _connect() as conn:
        conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(table_name)))


def test_list_datasets_includes_created_table(table_name: str) -> None:
    adapter = PostgresAdapter(settings.database_url)

    assert table_name in adapter.list_datasets()


def test_get_schema_returns_column_types(table_name: str) -> None:
    adapter = PostgresAdapter(settings.database_url)

    schema = adapter.get_schema(table_name)

    assert schema["id"] == "integer"
    assert schema["name"] == "text"


def test_sample_returns_real_rows(table_name: str) -> None:
    adapter = PostgresAdapter(settings.database_url)

    rows = adapter.sample(table_name, n=2)

    assert len(rows) == 2


def test_sample_respects_row_limit(table_name: str) -> None:
    adapter = PostgresAdapter(settings.database_url)

    rows = adapter.sample(table_name, n=1)

    assert len(rows) == 1


def test_to_registration_config_captures_enough_to_reconstruct(table_name: str) -> None:
    adapter = PostgresAdapter(settings.database_url)

    config = adapter.to_registration_config()

    assert config == {"adapter_type": "postgres", "connection_url": settings.database_url}


@pytest.fixture
def events_table_name() -> str:
    return f"test_events_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def _events_setup_and_teardown(events_table_name: str):  # type: ignore[no-untyped-def]
    with _connect() as conn:
        conn.execute(
            sql.SQL("CREATE TABLE {} (id INTEGER, ts TIMESTAMP)").format(
                sql.Identifier(events_table_name)
            )
        )
        conn.execute(
            sql.SQL("INSERT INTO {} (id, ts) VALUES (1, %(t1)s), (2, %(t2)s), (3, %(t3)s)").format(
                sql.Identifier(events_table_name)
            ),
            {
                "t1": datetime(2026, 1, 1, 10, 0),
                "t2": datetime(2026, 1, 1, 11, 0),
                "t3": datetime(2026, 1, 1, 12, 0),
            },
        )
    yield
    with _connect() as conn:
        conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(events_table_name)))


def test_query_window_returns_only_rows_in_range_ordered_by_timestamp(
    events_table_name: str, _events_setup_and_teardown: None
) -> None:
    adapter = PostgresAdapter(settings.database_url)

    rows = adapter.query_window(
        events_table_name,
        "ts",
        start=datetime(2026, 1, 1, 10, 30),
        end=datetime(2026, 1, 1, 11, 30),
    )

    assert [row[0] for row in rows] == [2]
