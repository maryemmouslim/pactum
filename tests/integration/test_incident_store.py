import threading
import uuid

import psycopg
import pytest

from pactum.monitoring.incident_store import emit_incident
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
            "DELETE FROM incidents WHERE dataset_id = %(dataset_id)s", {"dataset_id": dataset_id}
        )


def test_emit_incident_is_safe_under_concurrent_calls(dataset_id: str) -> None:
    # 10 threads all detect the "same" problem on the same column at once --
    # before the fix, this could insert 10 duplicate rows with the same
    # signature. The database's unique constraint plus the atomic upsert
    # should now guarantee exactly one row survives.
    results = []
    errors = []
    lock = threading.Lock()

    def _worker() -> None:
        try:
            incident = emit_incident(
                dataset_id=dataset_id,
                kind="violation",
                severity="high",
                check_type="schema",
                payload={"detail": "missing column"},
                contract_version="1",
                column="amount",
            )
            with lock:
                results.append(incident)
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f"concurrent emit_incident calls raised: {errors}"

    signatures = {incident.signature for incident in results}
    assert len(signatures) == 1, "all 10 calls should share the same signature"

    with _connect() as conn:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM incidents WHERE dataset_id = %(dataset_id)s",
            {"dataset_id": dataset_id},
        ).fetchone()
    assert count == 1, f"expected exactly 1 row in the database, found {count}"
