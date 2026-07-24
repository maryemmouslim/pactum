import uuid
from datetime import UTC, datetime

import pytest

from pactum.models import Incident
from pactum.monitoring.incident_store import build_signature, emit_incident


def test_build_signature_is_deterministic() -> None:
    sig1 = build_signature("orders", "psi", "amount")
    sig2 = build_signature("orders", "psi", "amount")

    assert sig1 == sig2


def test_build_signature_differs_by_column() -> None:
    sig_amount = build_signature("orders", "psi", "amount")
    sig_status = build_signature("orders", "psi", "status")

    assert sig_amount != sig_status


def test_build_signature_differs_by_check_type() -> None:
    sig_psi = build_signature("orders", "psi", "amount")
    sig_ks = build_signature("orders", "ks", "amount")

    assert sig_psi != sig_ks


class FakeConnection:
    """Simulates INSERT ... ON CONFLICT DO NOTHING RETURNING ....

    If simulate_conflict is False, fetchone() returns a row built from
    whatever params were just "inserted" -- mimicking a real RETURNING
    clause. If True, fetchone() returns None, simulating a skipped insert
    because a row with this signature already existed.
    """

    def __init__(self, simulate_conflict: bool = False) -> None:
        self.executed: list[dict[str, object]] = []
        self._simulate_conflict = simulate_conflict

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def execute(self, sql: str, params: dict[str, object]) -> "FakeConnection":
        self.executed.append(params)
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        if self._simulate_conflict:
            return None
        params = self.executed[-1]
        payload = params["payload"]
        raw_payload = payload.obj if hasattr(payload, "obj") else payload
        return (
            params["id"],
            params["dataset_id"],
            params["detected_at"],
            params["kind"],
            params["severity"],
            params["signature"],
            raw_payload,
            params["contract_version"],
        )


def test_emit_incident_creates_new_incident_when_none_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = FakeConnection(simulate_conflict=False)
    monkeypatch.setattr("pactum.monitoring.incident_store._connect", lambda: fake_conn)

    incident = emit_incident(
        dataset_id="orders",
        kind="drift",
        severity="high",
        check_type="psi",
        payload={"score": 0.5},
        contract_version="1",
        column="amount",
    )

    assert incident.dataset_id == "orders"
    assert incident.kind == "drift"
    assert incident.severity == "high"
    assert len(fake_conn.executed) == 1
    assert fake_conn.executed[0]["dataset_id"] == "orders"


def test_emit_incident_reuses_existing_incident_on_insert_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulates: two concurrent calls compute the same signature, the other
    # one already won the race and inserted, so our INSERT ... ON CONFLICT
    # is skipped (fetchone() returns None) and we fall back to fetching it.
    fake_conn = FakeConnection(simulate_conflict=True)
    monkeypatch.setattr("pactum.monitoring.incident_store._connect", lambda: fake_conn)

    existing = Incident(
        id=uuid.uuid4(),
        dataset_id="orders",
        detected_at=datetime.now(UTC),
        kind="drift",
        severity="high",
        signature=build_signature("orders", "psi", "amount"),
        payload={},
        contract_version="1",
    )
    monkeypatch.setattr(
        "pactum.monitoring.incident_store.find_open_incident", lambda signature: existing
    )

    incident = emit_incident(
        dataset_id="orders",
        kind="drift",
        severity="high",
        check_type="psi",
        payload={"score": 0.5},
        contract_version="1",
        column="amount",
    )

    assert incident is existing


def test_emit_incident_raises_if_conflict_but_no_row_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Should be practically unreachable (Postgres serializes the conflicting
    # transaction so the row is always visible afterward) -- but if it ever
    # happened, fail loudly instead of returning something wrong silently.
    fake_conn = FakeConnection(simulate_conflict=True)
    monkeypatch.setattr("pactum.monitoring.incident_store._connect", lambda: fake_conn)
    monkeypatch.setattr(
        "pactum.monitoring.incident_store.find_open_incident", lambda signature: None
    )

    with pytest.raises(RuntimeError):
        emit_incident(
            dataset_id="orders",
            kind="drift",
            severity="high",
            check_type="psi",
            payload={"score": 0.5},
            contract_version="1",
            column="amount",
        )
