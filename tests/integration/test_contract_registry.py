import threading
import uuid

import psycopg
import pytest

from pactum.registry.contract_registry import create_version
from pactum.settings import settings


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


@pytest.fixture
def dataset_id() -> str:
    return f"test_dataset_{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _cleanup(dataset_id: str):  # type: ignore[no-untyped-def]
    yield
    with _connect() as conn:
        conn.execute(
            "DELETE FROM contracts WHERE dataset_id = %(dataset_id)s", {"dataset_id": dataset_id}
        )


def test_create_version_allocates_sequential_versions_with_parent_links(
    dataset_id: str,
) -> None:
    first = create_version(dataset_id=dataset_id, yaml="v1", created_by="test")
    second = create_version(dataset_id=dataset_id, yaml="v2", created_by="test")
    third = create_version(dataset_id=dataset_id, yaml="v3", created_by="test")

    assert (first.version, second.version, third.version) == (1, 2, 3)
    assert second.parent_version_id == first.id
    assert third.parent_version_id == second.id


def test_create_version_is_safe_under_concurrent_calls(dataset_id: str) -> None:
    results = []
    errors = []
    lock = threading.Lock()

    def _worker() -> None:
        try:
            contract = create_version(dataset_id=dataset_id, yaml="concurrent", created_by="test")
            with lock:
                results.append(contract)
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f"concurrent create_version calls raised: {errors}"
    versions = sorted(result.version for result in results)
    assert versions == list(range(1, 11))
