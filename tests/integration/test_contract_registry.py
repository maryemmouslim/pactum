import threading
import uuid

import psycopg
import pytest

from pactum.registry.contract_registry import activate_version, create_version, get_active
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


def test_activate_version_promotes_draft_and_deprecates_previous_active(
    dataset_id: str,
) -> None:
    first = create_version(dataset_id=dataset_id, yaml="v1", created_by="test")
    second = create_version(dataset_id=dataset_id, yaml="v2", created_by="test")

    activated_first = activate_version(dataset_id, first.version)
    assert activated_first.status == "active"
    assert get_active(dataset_id) is not None
    assert get_active(dataset_id).version == first.version  # type: ignore[union-attr]

    activated_second = activate_version(dataset_id, second.version)
    assert activated_second.status == "active"

    active = get_active(dataset_id)
    assert active is not None
    assert active.version == second.version, "activating a new version should replace the old one"


def test_activate_version_rejects_unknown_version(dataset_id: str) -> None:
    with pytest.raises(ValueError, match="No version"):
        activate_version(dataset_id, 99)


def test_activate_version_rejects_reactivating_a_deprecated_version(dataset_id: str) -> None:
    first = create_version(dataset_id=dataset_id, yaml="v1", created_by="test")
    create_version(dataset_id=dataset_id, yaml="v2", created_by="test")
    activate_version(dataset_id, first.version)
    activate_version(dataset_id, 2)  # deprecates version 1

    with pytest.raises(ValueError, match="not 'draft'"):
        activate_version(dataset_id, first.version)


def test_activate_version_is_safe_under_concurrent_calls(dataset_id: str) -> None:
    # Two draft versions both try to become active at once -- the advisory
    # lock should serialize them, and the partial unique index guarantees
    # only one ends up 'active' no matter what.
    first = create_version(dataset_id=dataset_id, yaml="v1", created_by="test")
    second = create_version(dataset_id=dataset_id, yaml="v2", created_by="test")

    errors = []
    lock = threading.Lock()

    def _activate(version: int) -> None:
        try:
            activate_version(dataset_id, version)
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [
        threading.Thread(target=_activate, args=(first.version,)),
        threading.Thread(target=_activate, args=(second.version,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with _connect() as conn:
        (active_count,) = conn.execute(
            "SELECT COUNT(*) FROM contracts WHERE dataset_id = %(d)s AND status = 'active'",
            {"d": dataset_id},
        ).fetchone()
    assert active_count == 1
