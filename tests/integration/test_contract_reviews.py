import uuid

import psycopg
import pytest

from pactum.registry.contract_registry import create_version
from pactum.registry.contract_reviews import list_reviews, record_review
from pactum.settings import settings


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


@pytest.fixture
def dataset_id() -> str:
    return f"test_dataset_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def contract_id(dataset_id: str) -> uuid.UUID:
    contract = create_version(dataset_id=dataset_id, yaml="apiVersion: v3", created_by="test")
    return contract.id


@pytest.fixture(autouse=True)
def _cleanup(dataset_id: str):  # type: ignore[no-untyped-def]
    yield
    with _connect() as conn:
        conn.execute(
            "DELETE FROM contract_reviews WHERE contract_id IN "
            "(SELECT id FROM contracts WHERE dataset_id = %(dataset_id)s)",
            {"dataset_id": dataset_id},
        )
        conn.execute(
            "DELETE FROM contracts WHERE dataset_id = %(dataset_id)s", {"dataset_id": dataset_id}
        )


def test_record_review_persists_a_rejection_with_reason(contract_id: uuid.UUID) -> None:
    review = record_review(
        contract_id,
        "rejected",
        reviewed_by="ui-user",
        reason="Order ID isn't actually unique in this dataset",
    )

    assert review.decision == "rejected"
    assert review.reason == "Order ID isn't actually unique in this dataset"

    reviews = list_reviews(contract_id)
    assert len(reviews) == 1
    assert reviews[0].id == review.id


def test_record_review_persists_an_approval_without_a_reason(contract_id: uuid.UUID) -> None:
    review = record_review(contract_id, "approved", reviewed_by="ui-user")

    assert review.decision == "approved"
    assert review.reason is None


def test_list_reviews_returns_multiple_reviews_oldest_first(contract_id: uuid.UUID) -> None:
    first = record_review(contract_id, "rejected", reviewed_by="ui-user", reason="first pass")
    second = record_review(contract_id, "approved", reviewed_by="ui-user")

    reviews = list_reviews(contract_id)

    assert [review.id for review in reviews] == [first.id, second.id]


def test_list_reviews_returns_empty_for_a_contract_with_no_reviews(
    contract_id: uuid.UUID,
) -> None:
    assert list_reviews(contract_id) == []
