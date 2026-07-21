import pytest

from pactum.sources import registry as source_registry
from pactum.tools.profile_columns import profile_column, sample_data


class FakeAdapter:
    def list_datasets(self) -> list[str]:
        return ["orders"]

    def get_schema(self, dataset: str) -> dict[str, str]:
        return {"order_id": "TEXT", "amount": "DOUBLE"}

    def sample(self, dataset: str, n: int = 10) -> list[tuple[object, ...]]:
        return [("o1", 10.0), ("o2", 20.0), ("o3", None)]


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    source_registry._adapters.clear()


def test_sample_data_returns_rows_as_dicts() -> None:
    source_registry.register_source(FakeAdapter())
    result = sample_data.invoke({"dataset_id": "orders", "n": 10})
    assert result == [
        {"order_id": "o1", "amount": 10.0},
        {"order_id": "o2", "amount": 20.0},
        {"order_id": "o3", "amount": None},
    ]


def test_profile_column_computes_stats_per_column() -> None:
    source_registry.register_source(FakeAdapter())
    result = profile_column.invoke({"dataset_id": "orders", "n": 10})

    assert set(result.keys()) == {"order_id", "amount"}
    assert result["amount"]["null_percent"] == pytest.approx(1 / 3)
    assert result["amount"]["min"] == 10.0
    assert result["amount"]["max"] == 20.0
