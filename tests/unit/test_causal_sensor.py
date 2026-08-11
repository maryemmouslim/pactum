import uuid
from datetime import UTC, datetime

import pytest
from dagster import DagsterInstance, build_sensor_context

from pactum.models import Incident
from pactum.orchestration.causal_sensor import (
    causal_investigation_job,
    new_incident_sensor,
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


def test_sensor_first_tick_only_records_cursor_and_yields_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_list_incidents_since(since: object, *, limit: int = 50) -> list[Incident]:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(
        "pactum.orchestration.causal_sensor.list_incidents_since", fake_list_incidents_since
    )

    with DagsterInstance.ephemeral() as instance:
        context = build_sensor_context(instance=instance, cursor=None)
        result = list(new_incident_sensor(context))

    assert result == []
    assert context.cursor is not None
    assert not called  # first tick shouldn't even query -- just bootstraps the cursor


def test_sensor_yields_a_run_request_per_new_incident_and_advances_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident_a = _make_incident(detected_at=datetime(2026, 8, 10, 12, 0, tzinfo=UTC))
    incident_b = _make_incident(detected_at=datetime(2026, 8, 10, 13, 0, tzinfo=UTC))

    monkeypatch.setattr(
        "pactum.orchestration.causal_sensor.list_incidents_since",
        lambda since, *, limit=50: [incident_a, incident_b],
    )

    with DagsterInstance.ephemeral() as instance:
        context = build_sensor_context(
            instance=instance, cursor=datetime(2026, 8, 10, 11, 0, tzinfo=UTC).isoformat()
        )
        run_requests = list(new_incident_sensor(context))

    assert {rr.run_key for rr in run_requests} == {str(incident_a.id), str(incident_b.id)}
    for rr in run_requests:
        assert rr.run_config is not None
        incident_id = rr.run_config["ops"]["investigate_incident_op"]["config"]["incident_id"]
        assert incident_id in {str(incident_a.id), str(incident_b.id)}
    assert context.cursor == incident_b.detected_at.isoformat()


def test_sensor_does_nothing_when_no_new_incidents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pactum.orchestration.causal_sensor.list_incidents_since", lambda since, *, limit=50: []
    )

    with DagsterInstance.ephemeral() as instance:
        cursor_before = datetime(2026, 8, 10, 11, 0, tzinfo=UTC).isoformat()
        context = build_sensor_context(instance=instance, cursor=cursor_before)
        result = list(new_incident_sensor(context))

    assert result == []
    assert context.cursor == cursor_before


def test_investigate_incident_op_invokes_the_causal_graph_for_the_configured_incident(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident = _make_incident()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "pactum.orchestration.causal_sensor.load_persisted_registrations", lambda: 0
    )
    monkeypatch.setattr(
        "pactum.orchestration.causal_sensor.get_incident",
        lambda incident_id: incident if incident_id == incident.id else None,
    )

    class FakeApp:
        def invoke(self, state: object) -> dict[str, object]:
            captured["state"] = state
            return {}

    monkeypatch.setattr(
        "pactum.orchestration.causal_sensor.build_causal_explainer_graph", lambda: FakeApp()
    )

    result = causal_investigation_job.execute_in_process(
        run_config={
            "ops": {"investigate_incident_op": {"config": {"incident_id": str(incident.id)}}}
        }
    )

    assert result.success
    assert captured["state"].incident == incident  # type: ignore[attr-defined]


def test_investigate_incident_op_is_a_no_op_for_an_unknown_incident(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pactum.orchestration.causal_sensor.load_persisted_registrations", lambda: 0
    )
    monkeypatch.setattr("pactum.orchestration.causal_sensor.get_incident", lambda incident_id: None)

    def fail_if_called() -> None:
        raise AssertionError("build_causal_explainer_graph should not be called")

    monkeypatch.setattr(
        "pactum.orchestration.causal_sensor.build_causal_explainer_graph", fail_if_called
    )

    result = causal_investigation_job.execute_in_process(
        run_config={
            "ops": {"investigate_incident_op": {"config": {"incident_id": str(uuid.uuid4())}}}
        }
    )

    assert result.success
