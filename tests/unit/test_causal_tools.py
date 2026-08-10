import uuid
from datetime import UTC, datetime

import pytest

from pactum.contract_schema import ColumnRule, ParsedContract, render_contract_yaml
from pactum.lineage.graph import LineageGraph
from pactum.models import Contract, Incident
from pactum.monitoring.drift.protocol import DriftResult
from pactum.tools.causal_tools import (
    compare_distributions,
    diff_schema,
    fetch_calendar_events,
    fetch_pipeline_logs,
    find_similar_incidents,
    get_lineage,
    query_contract_context,
)


class FakeAdapter:
    def __init__(self, schema: dict[str, str], rows: list[tuple[object, ...]]) -> None:
        self._schema = schema
        self._rows = rows

    def get_schema(self, dataset: str) -> dict[str, str]:
        return self._schema

    def sample(self, dataset: str, n: int = 10) -> list[tuple[object, ...]]:
        return self._rows


def _make_contract(parsed: ParsedContract) -> Contract:
    return Contract(
        id=uuid.uuid4(),
        dataset_id=parsed.dataset_id,
        version=1,
        yaml=render_contract_yaml(parsed),
        status="active",
        parent_version_id=None,
        created_at=datetime.now(UTC),
        created_by="test",
    )


def _make_incident(**overrides: object) -> Incident:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "dataset_id": "orders",
        "detected_at": datetime.now(UTC),
        "kind": "violation",
        "severity": "high",
        "signature": "abc123",
        "payload": {},
        "contract_version_id": uuid.uuid4(),
        "check_type": "schema",
        "column_name": None,
    }
    defaults.update(overrides)
    return Incident(**defaults)  # type: ignore[arg-type]


def test_get_lineage_returns_upstream_and_downstream(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = LineageGraph()
    graph.add_edge("raw_orders", "orders")
    graph.add_edge("orders", "order_summary")
    monkeypatch.setattr("pactum.tools.causal_tools.load_graph", lambda: graph)

    result = get_lineage.invoke({"dataset_id": "orders"})

    assert result == {"upstream": ["raw_orders"], "downstream": ["order_summary"]}


def test_diff_schema_reports_not_found_for_missing_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pactum.tools.causal_tools.get_by_id", lambda contract_id: None)

    result = diff_schema.invoke({"dataset_id": "orders", "contract_version_id": str(uuid.uuid4())})

    assert result == {"status": "contract_not_found"}


def test_diff_schema_detects_added_removed_and_type_changed_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(name="order_id", data_type="TEXT", semantic_type="identifier"),
            ColumnRule(name="amount", data_type="INTEGER", semantic_type="currency"),
        ],
    )
    contract = _make_contract(parsed)
    monkeypatch.setattr("pactum.tools.causal_tools.get_by_id", lambda contract_id: contract)
    monkeypatch.setattr(
        "pactum.tools.causal_tools.get_adapter",
        lambda dataset_id: FakeAdapter(
            schema={"order_id": "TEXT", "amount": "FLOAT", "status": "TEXT"}, rows=[]
        ),
    )

    result = diff_schema.invoke({"dataset_id": "orders", "contract_version_id": str(contract.id)})

    assert result == {
        "status": "ok",
        "added_columns": ["status"],
        "removed_columns": [],
        "type_changed_columns": ["amount"],
    }


def test_compare_distributions_reports_no_reference_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pactum.tools.causal_tools.load_reference_snapshot", lambda dataset_id, column: None
    )

    result = compare_distributions.invoke({"dataset_id": "orders", "column": "amount"})

    assert result == {"status": "no_reference_snapshot"}


def test_compare_distributions_runs_numeric_detectors_for_numeric_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pactum.tools.causal_tools.load_reference_snapshot",
        lambda dataset_id, column: [1.0, 2.0, 3.0, 4.0, 5.0],
    )
    monkeypatch.setattr(
        "pactum.tools.causal_tools.get_adapter",
        lambda dataset_id: FakeAdapter(schema={"amount": "FLOAT"}, rows=[(1.0,), (2.0,), (3.0,)]),
    )

    result = compare_distributions.invoke({"dataset_id": "orders", "column": "amount"})

    assert result["status"] == "ok"
    assert set(result["results"].keys()) == {"psi", "ks"}


def test_compare_distributions_falls_back_to_chi_squared_for_non_numeric_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pactum.tools.causal_tools.load_reference_snapshot",
        lambda dataset_id, column: ["gold", "silver", "gold"],
    )
    monkeypatch.setattr(
        "pactum.tools.causal_tools.get_adapter",
        lambda dataset_id: FakeAdapter(schema={"tier": "TEXT"}, rows=[("bronze",), ("gold",)]),
    )

    result = compare_distributions.invoke({"dataset_id": "orders", "column": "tier"})

    assert result["status"] == "ok"
    assert set(result["results"].keys()) == {"chi_squared"}


def test_query_contract_context_reports_not_found_for_missing_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pactum.tools.causal_tools.get_by_id", lambda contract_id: None)

    result = query_contract_context.invoke(
        {"dataset_id": "orders", "contract_version_id": str(uuid.uuid4())}
    )

    assert result == {"status": "contract_not_found"}


def test_query_contract_context_returns_column_rule_when_column_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(
                name="amount",
                data_type="FLOAT",
                semantic_type="currency",
                min_value=0.0,
                max_value=1000.0,
            )
        ],
        freshness_sla_seconds=3600.0,
    )
    contract = _make_contract(parsed)
    monkeypatch.setattr("pactum.tools.causal_tools.get_by_id", lambda contract_id: contract)

    result = query_contract_context.invoke(
        {
            "dataset_id": "orders",
            "contract_version_id": str(contract.id),
            "column": "amount",
        }
    )

    assert result["status"] == "ok"
    assert result["contract_status"] == "active"
    assert result["freshness_sla_seconds"] == 3600.0
    assert result["column_rule"]["min_value"] == 0.0
    assert result["column_rule"]["max_value"] == 1000.0


def test_find_similar_incidents_returns_related_incidents_as_dicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    related = _make_incident(check_type="psi", column_name="amount")
    monkeypatch.setattr(
        "pactum.tools.causal_tools.find_related_incidents",
        lambda dataset_id, check_type, exclude_id: [related],
    )

    result = find_similar_incidents.invoke(
        {
            "dataset_id": "orders",
            "check_type": "psi",
            "incident_id": str(uuid.uuid4()),
        }
    )

    assert len(result) == 1
    assert result[0]["id"] == str(related.id)
    assert result[0]["check_type"] == "psi"


def test_fetch_pipeline_logs_is_honest_about_no_backend_configured() -> None:
    result = fetch_pipeline_logs.invoke({"dataset_id": "orders"})
    assert result == {"status": "not_configured", "logs": []}


def test_fetch_calendar_events_is_honest_about_no_backend_configured() -> None:
    result = fetch_calendar_events.invoke({"dataset_id": "orders"})
    assert result == {"status": "not_configured", "events": []}


def test_no_tool_touches_a_real_database_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression guard: the deleted first attempt at these tools opened a real
    # psycopg connection with nothing mocked, which hung indefinitely with no
    # local Postgres running. Every DB-touching dependency must be patchable
    # at the causal_tools module boundary, never reached directly.
    def _fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("a causal tool tried to open a real DB connection")

    monkeypatch.setattr("psycopg.connect", _fail)

    monkeypatch.setattr("pactum.tools.causal_tools.load_graph", lambda: LineageGraph())
    get_lineage.invoke({"dataset_id": "orders"})

    monkeypatch.setattr("pactum.tools.causal_tools.get_by_id", lambda contract_id: None)
    diff_schema.invoke({"dataset_id": "orders", "contract_version_id": str(uuid.uuid4())})
    query_contract_context.invoke(
        {"dataset_id": "orders", "contract_version_id": str(uuid.uuid4())}
    )

    monkeypatch.setattr(
        "pactum.tools.causal_tools.load_reference_snapshot", lambda dataset_id, column: None
    )
    compare_distributions.invoke({"dataset_id": "orders", "column": "amount"})

    monkeypatch.setattr(
        "pactum.tools.causal_tools.find_related_incidents",
        lambda dataset_id, check_type, exclude_id: [],
    )
    find_similar_incidents.invoke(
        {"dataset_id": "orders", "check_type": "psi", "incident_id": str(uuid.uuid4())}
    )

    fetch_pipeline_logs.invoke({"dataset_id": "orders"})
    fetch_calendar_events.invoke({"dataset_id": "orders"})


def test_drift_result_model_dump_matches_expected_shape() -> None:
    # Sanity check the assumption compare_distributions relies on: DriftResult
    # serializes to plain JSON-safe primitives (no UUID/datetime).
    result = DriftResult(drifted=True, score=0.3, method="psi", details={"a": 1})
    assert result.model_dump() == {
        "drifted": True,
        "score": 0.3,
        "method": "psi",
        "details": {"a": 1},
        "insufficient_data": False,
    }
