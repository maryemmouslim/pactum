import pytest

from pactum.sources import registry as source_registry


class FakeAdapter:
    def __init__(self, datasets: list[str]) -> None:
        self._datasets = datasets

    def list_datasets(self) -> list[str]:
        return self._datasets

    def get_schema(self, dataset: str) -> dict[str, str]:
        return {}

    def sample(self, dataset: str, n: int = 10) -> list[tuple[object, ...]]:
        return []


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    source_registry._adapters.clear()


def test_register_source_makes_all_its_datasets_lookupable() -> None:
    adapter = FakeAdapter(["orders", "customers"])
    source_registry.register_source(adapter)

    assert source_registry.get_adapter("orders") is adapter
    assert source_registry.get_adapter("customers") is adapter


def test_get_adapter_raises_clear_error_for_unregistered_dataset() -> None:
    with pytest.raises(KeyError, match="No source registered for dataset 'unknown'"):
        source_registry.get_adapter("unknown")


def test_registering_a_second_adapter_does_not_clobber_the_first() -> None:
    orders_adapter = FakeAdapter(["orders"])
    customers_adapter = FakeAdapter(["customers"])

    source_registry.register_source(orders_adapter)
    source_registry.register_source(customers_adapter)

    assert source_registry.get_adapter("orders") is orders_adapter
    assert source_registry.get_adapter("customers") is customers_adapter


def test_register_source_default_never_touches_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # persist defaults to False specifically so unit tests (and any code that
    # just wants an in-memory registration) never need a real database.
    monkeypatch.setattr(
        "pactum.sources.registry._persist_registration",
        lambda adapter: (_ for _ in ()).throw(AssertionError("should not persist by default")),
    )

    source_registry.register_source(FakeAdapter(["orders"]))

    assert source_registry.get_adapter("orders") is not None


def test_adapter_from_config_raises_for_unknown_adapter_type() -> None:
    with pytest.raises(ValueError, match="Unknown adapter_type"):
        source_registry._adapter_from_config({"adapter_type": "carrier_pigeon"})


def test_list_registered_datasets_reflects_every_registered_adapter() -> None:
    source_registry.register_source(FakeAdapter(["orders", "customers"]))
    source_registry.register_source(FakeAdapter(["widgets"]))

    assert source_registry.list_registered_datasets() == ["customers", "orders", "widgets"]


def test_list_registered_datasets_is_empty_when_nothing_registered() -> None:
    assert source_registry.list_registered_datasets() == []
