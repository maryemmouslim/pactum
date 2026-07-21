import pytest

from pactum.agents.contract_generator import understand_source
from pactum.agents.state import ContractGeneratorState
from pactum.lineage.graph import LineageGraph
from pactum.sources import registry as source_registry
from pactum.sources.business_context import register_business_context


class FakeAdapter:
    def list_datasets(self) -> list[str]:
        return ["orders"]

    def get_schema(self, dataset: str) -> dict[str, str]:
        return {"order_id": "TEXT"}

    def sample(self, dataset: str, n: int = 10) -> list[tuple[object, ...]]:
        return []


@pytest.fixture(autouse=True)
def _clear_registries() -> None:
    source_registry._adapters.clear()
    from pactum.sources import business_context

    business_context._context.clear()


def test_understand_source_populates_state(monkeypatch: pytest.MonkeyPatch) -> None:
    source_registry.register_source(FakeAdapter())
    register_business_context("orders", "Customer purchase events.")
    monkeypatch.setattr("pactum.tools.understand_source.load_graph", lambda: LineageGraph())

    result = understand_source(ContractGeneratorState(dataset_id="orders"))

    assert result.columns == {"order_id": "TEXT"}
    assert result.upstream_contracts == []
    assert result.business_context == "Customer purchase events."
