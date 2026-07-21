from unittest.mock import MagicMock

import pytest

from pactum.lineage.graph import LineageGraph
from pactum.models import Contract
from pactum.sources import registry as source_registry
from pactum.sources.business_context import register_business_context
from pactum.tools.understand_source import (
    fetch_business_context,
    fetch_upstream_contract,
    inspect_schema,
)


class FakeAdapter:
    def list_datasets(self) -> list[str]:
        return ["orders"]

    def get_schema(self, dataset: str) -> dict[str, str]:
        return {"order_id": "TEXT", "amount": "DOUBLE"}

    def sample(self, dataset: str, n: int = 10) -> list[tuple[object, ...]]:
        return [("o1", 9.99)]


@pytest.fixture(autouse=True)
def _clear_registries() -> None:
    source_registry._adapters.clear()
    from pactum.sources import business_context

    business_context._context.clear()


def test_inspect_schema_uses_registered_adapter() -> None:
    source_registry.register_source(FakeAdapter())
    result = inspect_schema.invoke({"dataset_id": "orders"})
    assert result == {"order_id": "TEXT", "amount": "DOUBLE"}


def test_inspect_schema_unknown_dataset_raises() -> None:
    with pytest.raises(KeyError):
        inspect_schema.invoke({"dataset_id": "missing"})


def test_fetch_upstream_contract_returns_empty_when_no_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pactum.tools.understand_source.load_graph", lambda: LineageGraph())
    result = fetch_upstream_contract.invoke({"dataset_id": "orders"})
    assert result == []


def test_fetch_upstream_contract_pulls_active_upstream_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = LineageGraph()
    graph.add_edge("raw_orders", "orders")
    monkeypatch.setattr("pactum.tools.understand_source.load_graph", lambda: graph)

    fake_contract = MagicMock(spec=Contract)
    monkeypatch.setattr(
        "pactum.tools.understand_source.get_active",
        lambda dataset_id: fake_contract if dataset_id == "raw_orders" else None,
    )

    result = fetch_upstream_contract.invoke({"dataset_id": "orders"})
    assert result == [fake_contract]


def test_fetch_business_context_returns_none_when_unregistered() -> None:
    assert fetch_business_context.invoke({"dataset_id": "unknown"}) is None


def test_fetch_business_context_returns_registered_text() -> None:
    register_business_context("orders", "Customer purchase events.")
    assert fetch_business_context.invoke({"dataset_id": "orders"}) == "Customer purchase events."
