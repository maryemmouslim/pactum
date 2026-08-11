from datetime import UTC, datetime
from uuid import UUID

from dagster import (
    Config,
    DefaultSensorStatus,
    RunRequest,
    SensorEvaluationContext,
    job,
    op,
    sensor,
)

from pactum.agents.causal_explainer import build_causal_explainer_graph
from pactum.agents.state import CausalExplainerState
from pactum.monitoring.incident_store import get_incident, list_incidents_since
from pactum.sources.registry import load_persisted_registrations


class InvestigateIncidentConfig(Config):
    incident_id: str


@op
def investigate_incident_op(config: InvestigateIncidentConfig) -> None:
    """Run the causal explanation agent for one incident, triggered by new_incident_sensor.

    load_persisted_registrations() is called here, inside the op, rather
    than at module import time -- pactum/orchestration/definitions.py must
    stay importable without a real database connection (unit tests import
    it), and this module is wired into that same Definitions(...) call.
    """
    load_persisted_registrations()
    incident = get_incident(UUID(config.incident_id))
    if incident is None:
        return
    app = build_causal_explainer_graph()
    app.invoke(CausalExplainerState(incident=incident))


@job
def causal_investigation_job() -> None:
    investigate_incident_op()


@sensor(
    job=causal_investigation_job,
    minimum_interval_seconds=60,
    default_status=DefaultSensorStatus.RUNNING,
)
def new_incident_sensor(context: SensorEvaluationContext):  # type: ignore[no-untyped-def]
    """Poll for incidents detected since the last tick and investigate each one.

    On its very first tick (no cursor yet), it just records "now" as the
    starting point rather than investigating the entire historical backlog
    -- only incidents detected from this point on get auto-investigated.
    """
    if context.cursor is None:
        context.update_cursor(datetime.now(UTC).isoformat())
        return

    since = datetime.fromisoformat(context.cursor)
    incidents = list_incidents_since(since)
    if not incidents:
        return

    for incident in incidents:
        yield RunRequest(
            run_key=str(incident.id),
            run_config={
                "ops": {"investigate_incident_op": {"config": {"incident_id": str(incident.id)}}}
            },
        )

    context.update_cursor(max(incident.detected_at for incident in incidents).isoformat())
