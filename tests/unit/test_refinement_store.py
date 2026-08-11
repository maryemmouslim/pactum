import uuid
from datetime import UTC, datetime

import pytest

from pactum.models import RefinementProposal
from pactum.monitoring.refinement_store import (
    get_refinements_for_incident,
    list_pending_refinements,
    save_refinement_proposal,
    update_refinement_status,
)


class FakeConnection:
    def __init__(self, rows: list[tuple[object, ...]] | None = None) -> None:
        self.executed: list[tuple[str, dict[str, object]]] = []
        self._rows = rows or []

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def execute(self, sql: str, params: dict[str, object] | None = None) -> "FakeConnection":
        self.executed.append((sql, params or {}))
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


def _make_proposal(**overrides: object) -> RefinementProposal:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "incident_id": uuid.uuid4(),
        "contract_id": uuid.uuid4(),
        "kind": "relaxation",
        "proposed_yaml": "dataset_id: orders",
        "status": "pending",
        "reason": None,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return RefinementProposal(**defaults)  # type: ignore[arg-type]


def _row_for(proposal: RefinementProposal) -> tuple[object, ...]:
    return (
        proposal.id,
        proposal.incident_id,
        proposal.contract_id,
        proposal.kind,
        proposal.proposed_yaml,
        proposal.status,
        proposal.reason,
        proposal.created_at,
    )


def test_save_refinement_proposal_inserts_and_returns_it(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = FakeConnection()
    monkeypatch.setattr("pactum.monitoring.refinement_store._connect", lambda: fake_conn)

    proposal = _make_proposal()
    result = save_refinement_proposal(proposal)

    assert result is proposal
    sql, params = fake_conn.executed[0]
    assert "INSERT INTO refinements" in sql
    assert params["id"] == proposal.id
    assert params["reason"] is None


def test_get_refinements_for_incident_returns_matching_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = _make_proposal(status="accepted", reason=None)
    fake_conn = FakeConnection(rows=[_row_for(proposal)])
    monkeypatch.setattr("pactum.monitoring.refinement_store._connect", lambda: fake_conn)

    results = get_refinements_for_incident(proposal.incident_id)

    assert results == [proposal]


def test_list_pending_refinements_returns_all_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    proposal = _make_proposal()
    fake_conn = FakeConnection(rows=[_row_for(proposal)])
    monkeypatch.setattr("pactum.monitoring.refinement_store._connect", lambda: fake_conn)

    results = list_pending_refinements()

    assert results == [proposal]
    sql, _ = fake_conn.executed[0]
    assert "WHERE status = 'pending'" in sql


def test_update_refinement_status_accepts_and_returns_updated_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = _make_proposal(status="accepted", reason=None)
    fake_conn = FakeConnection(rows=[_row_for(proposal)])
    monkeypatch.setattr("pactum.monitoring.refinement_store._connect", lambda: fake_conn)

    result = update_refinement_status(proposal.id, "accepted")

    assert result.status == "accepted"
    sql, params = fake_conn.executed[0]
    assert "UPDATE refinements" in sql
    assert params["status"] == "accepted"
    assert params["reason"] is None


def test_update_refinement_status_rejects_with_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    proposal = _make_proposal(status="rejected", reason="rule was already loosened last week")
    fake_conn = FakeConnection(rows=[_row_for(proposal)])
    monkeypatch.setattr("pactum.monitoring.refinement_store._connect", lambda: fake_conn)

    result = update_refinement_status(
        proposal.id, "rejected", reason="rule was already loosened last week"
    )

    assert result.status == "rejected"
    assert result.reason == "rule was already loosened last week"


def test_update_refinement_status_raises_if_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = FakeConnection(rows=[])
    monkeypatch.setattr("pactum.monitoring.refinement_store._connect", lambda: fake_conn)

    with pytest.raises(ValueError, match="No refinement proposal found"):
        update_refinement_status(uuid.uuid4(), "accepted")
