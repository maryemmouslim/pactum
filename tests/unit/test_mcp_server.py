import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from pactum.contract_schema import ColumnRule, ParsedContract, render_contract_yaml
from pactum.mcp.server import server
from pactum.models import Contract, Explanation, Hypothesis, Incident
from pactum.monitoring.runner import CheckOutcome


def _call(name: str, arguments: dict[str, object]) -> dict[str, object]:
    result = asyncio.run(server.call_tool(name, arguments))
    assert not result.is_error, result.content
    return result.structured_content  # type: ignore[return-value]


def _make_contract(dataset_id: str) -> Contract:
    parsed = ParsedContract(
        dataset_id=dataset_id,
        columns=[ColumnRule(name="id", data_type="VARCHAR", semantic_type="identifier")],
    )
    return Contract(
        id=uuid4(),
        dataset_id=dataset_id,
        version=1,
        yaml=render_contract_yaml(parsed),
        status="active",
        parent_version_id=None,
        created_at=datetime.now(UTC),
        created_by="test",
    )


def test_list_datasets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pactum.mcp.server.list_registered_datasets", lambda: ["orders", "customers"]
    )
    assert _call("list_datasets", {}) == {"result": ["orders", "customers"]}


def test_get_contract_returns_rules_for_active_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = _make_contract("orders")
    monkeypatch.setattr("pactum.mcp.server.get_active", lambda dataset_id: contract)

    result = _call("get_contract", {"dataset_id": "orders"})

    assert result["status"] == "ok"
    assert result["version"] == 1
    assert result["columns"][0]["name"] == "id"  # type: ignore[index]


def test_get_contract_reports_no_active_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pactum.mcp.server.get_active", lambda dataset_id: None)

    result = _call("get_contract", {"dataset_id": "ghost"})

    assert result == {"status": "no_active_contract", "dataset_id": "ghost"}


def test_get_incidents_lists_recent_incidents(monkeypatch: pytest.MonkeyPatch) -> None:
    incident = Incident(
        id=uuid4(),
        dataset_id="orders",
        detected_at=datetime.now(UTC),
        kind="violation",
        severity="high",
        signature="sig",
        payload={},
        contract_version_id=uuid4(),
        check_type="schema",
        column_name=None,
    )
    monkeypatch.setattr(
        "pactum.mcp.server.list_incidents_for_dataset", lambda dataset_id, limit: [incident]
    )

    result = _call("get_incidents", {"dataset_id": "orders"})

    assert result["result"][0]["check_type"] == "schema"  # type: ignore[index]


def test_explain_incident_reports_not_investigated_when_no_explanation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pactum.mcp.server.get_explanations_for_incident", lambda incident_id: [])

    result = _call("explain_incident", {"incident_id": str(uuid4())})

    assert result["status"] == "not_investigated"


def test_explain_incident_returns_ranked_hypotheses(monkeypatch: pytest.MonkeyPatch) -> None:
    explanation = Explanation(
        id=uuid4(),
        incident_id=uuid4(),
        hypotheses=[Hypothesis(description="upstream broke", confidence=0.9)],
        reasoning_trace=[],
        created_at=datetime.now(UTC),
    )
    monkeypatch.setattr(
        "pactum.mcp.server.get_explanations_for_incident", lambda incident_id: [explanation]
    )

    result = _call("explain_incident", {"incident_id": str(uuid4())})

    assert result["status"] == "ok"
    assert result["hypotheses"][0]["description"] == "upstream broke"  # type: ignore[index]


def test_run_checks_reports_no_active_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pactum.mcp.server.get_active", lambda dataset_id: None)

    result = _call("run_checks", {"dataset_id": "ghost"})

    assert result == {"status": "no_active_contract", "dataset_id": "ghost"}


def test_run_checks_summarizes_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = _make_contract("orders")
    monkeypatch.setattr("pactum.mcp.server.get_active", lambda dataset_id: contract)
    outcomes = [
        CheckOutcome(check_type="schema", status="passed", message="ok"),
        CheckOutcome(check_type="range", column="amount", status="failed", message="out of range"),
        CheckOutcome(check_type="freshness_sla", status="skipped", message="no timestamp column"),
    ]
    monkeypatch.setattr("pactum.mcp.server.evaluate_contract", lambda *a, **k: outcomes)

    result = _call("run_checks", {"dataset_id": "orders"})

    assert result["status"] == "ok"
    assert result["passed"] == 1
    assert result["skipped"] == 1
    assert len(result["failed"]) == 1  # type: ignore[arg-type]
    assert result["failed"][0]["check_type"] == "range"  # type: ignore[index]
