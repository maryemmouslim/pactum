import uuid
from datetime import UTC, datetime

import pytest

from pactum.models import Incident
from pactum.monitoring.incident_store import (
    _json_safe,
    build_signature,
    emit_incident,
    list_incidents_for_dataset,
)


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


def test_json_safe_converts_infinities_to_strings() -> None:
    assert _json_safe(float("inf")) == "inf"
    assert _json_safe(float("-inf")) == "-inf"
    assert _json_safe(float("nan")) == "nan"


def test_json_safe_leaves_normal_floats_untouched() -> None:
    assert _json_safe(3.14) == 3.14
    assert _json_safe(0.0) == 0.0


def test_json_safe_recurses_into_nested_dicts_and_lists() -> None:
    # This is exactly the shape PSI produces: bin_edges containing +-inf,
    # nested inside a details dict that becomes part of an incident payload.
    payload = {"score": 6.6, "bin_edges": [float("-inf"), 1.0, 2.0, float("inf")]}

    result = _json_safe(payload)

    assert result == {"score": 6.6, "bin_edges": ["-inf", 1.0, 2.0, "inf"]}


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
            params["contract_version_id"],
            params["check_type"],
            params["column_name"],
        )


def test_emit_incident_sanitizes_infinite_values_in_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Reproduces the real bug: a PSI-shaped payload with +-inf in bin_edges
    # used to crash psycopg's JSON encoding when actually written to Postgres.
    fake_conn = FakeConnection(simulate_conflict=False)
    monkeypatch.setattr("pactum.monitoring.incident_store._connect", lambda: fake_conn)

    incident = emit_incident(
        dataset_id="orders",
        kind="drift",
        severity="high",
        check_type="psi",
        payload={"score": 6.6, "bin_edges": [float("-inf"), 1.0, float("inf")]},
        contract_version_id=uuid.uuid4(),
        column="amount",
    )

    assert incident.payload["bin_edges"] == ["-inf", 1.0, "inf"]


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
        contract_version_id=uuid.uuid4(),
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
        contract_version_id=uuid.uuid4(),
        check_type="psi",
        column_name="amount",
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
        contract_version_id=uuid.uuid4(),
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
            contract_version_id=uuid.uuid4(),
            column="amount",
        )


class FakeListConnection:
    def __init__(self, rows: list[tuple[object, ...]] | None = None) -> None:
        self.executed: list[tuple[str, dict[str, object]]] = []
        self._rows = rows or []

    def __enter__(self) -> "FakeListConnection":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def execute(self, sql: str, params: dict[str, object]) -> "FakeListConnection":
        self.executed.append((sql, params))
        return self

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


def _incident_row(incident: Incident) -> tuple[object, ...]:
    return (
        incident.id,
        incident.dataset_id,
        incident.detected_at,
        incident.kind,
        incident.severity,
        incident.signature,
        incident.payload,
        incident.contract_version_id,
        incident.check_type,
        incident.column_name,
    )


def test_list_incidents_for_dataset_returns_matching_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident = Incident(
        id=uuid.uuid4(),
        dataset_id="orders",
        detected_at=datetime.now(UTC),
        kind="violation",
        severity="high",
        signature="sig",
        payload={},
        contract_version_id=uuid.uuid4(),
        check_type="uniqueness",
        column_name="order_id",
    )
    fake_conn = FakeListConnection(rows=[_incident_row(incident)])
    monkeypatch.setattr("pactum.monitoring.incident_store._connect", lambda: fake_conn)

    results = list_incidents_for_dataset("orders")

    assert results == [incident]
    sql, params = fake_conn.executed[0]
    assert "WHERE dataset_id = %(dataset_id)s" in sql
    assert params["dataset_id"] == "orders"
    assert params["limit"] == 20


def test_list_incidents_for_dataset_respects_custom_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_conn = FakeListConnection(rows=[])
    monkeypatch.setattr("pactum.monitoring.incident_store._connect", lambda: fake_conn)

    list_incidents_for_dataset("orders", limit=5)

    _, params = fake_conn.executed[0]
    assert params["limit"] == 5
