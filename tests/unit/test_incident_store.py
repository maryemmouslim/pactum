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
    def __init__(self) -> None:
        self.executed: list[dict[str, object]] = []

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def execute(self, sql: str, params: dict[str, object]) -> None:
        self.executed.append(params)


def test_emit_incident_creates_new_incident_when_none_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pactum.monitoring.incident_store.find_open_incident", lambda signature: None
    )
    fake_conn = FakeConnection()
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


def test_emit_incident_reuses_existing_open_incident(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = Incident(
        id="12345678-1234-5678-1234-567812345678",  # type: ignore[arg-type]
        dataset_id="orders",
        detected_at="2026-01-01T00:00:00Z",  # type: ignore[arg-type]
        kind="drift",
        severity="high",
        signature="abc123",
        payload={},
        contract_version="1",
    )
    monkeypatch.setattr(
        "pactum.monitoring.incident_store.find_open_incident", lambda signature: existing
    )

    def _fail_connect() -> None:
        raise AssertionError("should not connect to the database when reusing an incident")

    monkeypatch.setattr("pactum.monitoring.incident_store._connect", _fail_connect)

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
