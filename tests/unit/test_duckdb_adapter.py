from datetime import datetime
from pathlib import Path

import pytest

from pactum.sources.duckdb_adapter import DuckDBAdapter

DATA_DIR = Path(__file__).resolve().parents[2] / "examples" / "data"


def test_list_datasets_finds_csv_files() -> None:
    adapter = DuckDBAdapter(str(DATA_DIR))

    datasets = adapter.list_datasets()

    assert "orders" in datasets
    assert "customers" in datasets


def test_get_schema_returns_column_types() -> None:
    adapter = DuckDBAdapter(str(DATA_DIR))

    schema = adapter.get_schema("orders")

    assert schema["order_id"] == "VARCHAR"
    assert schema["amount"] == "DOUBLE"
    assert "TIMESTAMP" in schema["created_at"]


def test_sample_returns_real_rows() -> None:
    adapter = DuckDBAdapter(str(DATA_DIR))

    rows = adapter.sample("orders", n=2)

    assert len(rows) == 2
    assert all(len(row) == 6 for row in rows)


def test_sample_respects_row_limit() -> None:
    adapter = DuckDBAdapter(str(DATA_DIR))

    rows = adapter.sample("orders", n=1)

    assert len(rows) == 1


def test_get_schema_raises_for_unknown_dataset() -> None:
    adapter = DuckDBAdapter(str(DATA_DIR))

    with pytest.raises(FileNotFoundError):
        adapter.get_schema("nonexistent_dataset")


def test_to_registration_config_captures_enough_to_reconstruct() -> None:
    adapter = DuckDBAdapter(str(DATA_DIR))

    config = adapter.to_registration_config()

    assert config == {"adapter_type": "duckdb", "directory": str(DATA_DIR)}


def test_query_window_returns_only_rows_in_range_ordered_by_timestamp(tmp_path: Path) -> None:
    csv_path = tmp_path / "events.csv"
    csv_path.write_text(
        "id,ts\n"
        "1,2026-01-01 10:00:00\n"
        "2,2026-01-01 11:00:00\n"
        "3,2026-01-01 12:00:00\n"
        "4,2026-01-01 13:00:00\n"
    )
    adapter = DuckDBAdapter(str(tmp_path))

    rows = adapter.query_window(
        "events",
        "ts",
        start=datetime(2026, 1, 1, 10, 30),
        end=datetime(2026, 1, 1, 12, 30),
    )

    assert [row[0] for row in rows] == [2, 3]


def test_query_window_returns_empty_when_nothing_in_range(tmp_path: Path) -> None:
    csv_path = tmp_path / "events.csv"
    csv_path.write_text("id,ts\n1,2026-01-01 10:00:00\n")
    adapter = DuckDBAdapter(str(tmp_path))

    rows = adapter.query_window(
        "events",
        "ts",
        start=datetime(2026, 1, 2, 0, 0),
        end=datetime(2026, 1, 3, 0, 0),
    )

    assert rows == []


def test_list_datasets_finds_json_files(tmp_path: Path) -> None:
    (tmp_path / "widgets.json").write_text('[{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]')
    adapter = DuckDBAdapter(str(tmp_path))

    assert adapter.list_datasets() == ["widgets"]


def test_get_schema_and_sample_read_json_files(tmp_path: Path) -> None:
    (tmp_path / "widgets.json").write_text('[{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]')
    adapter = DuckDBAdapter(str(tmp_path))

    schema = adapter.get_schema("widgets")
    rows = adapter.sample("widgets", n=10)

    assert schema["id"] == "BIGINT"
    assert schema["name"] == "VARCHAR"
    assert rows == [(1, "a"), (2, "b")]
