import pytest

from pactum.sources import business_context


@pytest.fixture(autouse=True)
def _clear_context() -> None:
    business_context._context.clear()


def test_get_business_context_returns_none_when_unregistered() -> None:
    assert business_context.get_business_context("orders") is None


def test_register_business_context_makes_it_retrievable() -> None:
    business_context.register_business_context("orders", "Customer purchase events.")

    assert business_context.get_business_context("orders") == "Customer purchase events."


def test_register_business_context_overwrites_previous_value() -> None:
    business_context.register_business_context("orders", "First description.")
    business_context.register_business_context("orders", "Updated description.")

    assert business_context.get_business_context("orders") == "Updated description."
