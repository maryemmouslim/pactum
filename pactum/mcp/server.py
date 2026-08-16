from uuid import UUID

from mcp.server.mcpserver import MCPServer

from pactum.contract_schema import parse_contract_yaml
from pactum.monitoring.explanation_store import get_explanations_for_incident
from pactum.monitoring.incident_store import list_incidents_for_dataset
from pactum.monitoring.runner import evaluate_contract
from pactum.registry.contract_registry import get_active
from pactum.sources.registry import list_registered_datasets, load_persisted_registrations

server = MCPServer(
    name="pactum",
    instructions=(
        "Read-only access to Pactum's data contracts, incidents, and causal "
        "investigations. Nothing here modifies a contract or accepts a "
        "refinement proposal -- those stay human actions in the Pactum UI, "
        "not something this server exposes."
    ),
)


@server.tool()
def list_datasets() -> list[str]:
    """List every dataset Pactum currently has registered."""
    return list_registered_datasets()


@server.tool()
def get_contract(dataset_id: str) -> dict[str, object]:
    """Return the active contract for a dataset: its column rules, SLAs, and version.

    Returns status="no_active_contract" if the dataset has no active contract
    (only drafts, or the dataset doesn't exist).
    """
    contract = get_active(dataset_id)
    if contract is None:
        return {"status": "no_active_contract", "dataset_id": dataset_id}
    parsed = parse_contract_yaml(contract.yaml)
    return {
        "status": "ok",
        "dataset_id": dataset_id,
        "version": contract.version,
        "freshness_sla_seconds": parsed.freshness_sla_seconds,
        "completeness_sla": parsed.completeness_sla,
        "columns": [rule.model_dump(mode="json") for rule in parsed.columns],
    }


@server.tool()
def get_incidents(dataset_id: str, limit: int = 20) -> list[dict[str, object]]:
    """List recent incidents (drift or contract violations) for a dataset, most recent first."""
    incidents = list_incidents_for_dataset(dataset_id, limit=limit)
    return [incident.model_dump(mode="json") for incident in incidents]


@server.tool()
def explain_incident(incident_id: str) -> dict[str, object]:
    """Return the Causal Explanation Agent's ranked hypotheses for an incident.

    Returns status="not_investigated" if no explanation exists yet -- either
    the incident is too new for the auto-investigation sensor to have picked
    it up, or Dagster wasn't running when it was detected.
    """
    explanations = get_explanations_for_incident(UUID(incident_id))
    if not explanations:
        return {"status": "not_investigated", "incident_id": incident_id}
    latest = explanations[-1]
    return {
        "status": "ok",
        "incident_id": incident_id,
        "hypotheses": [h.model_dump(mode="json") for h in latest.hypotheses],
    }


@server.tool()
def run_checks(dataset_id: str) -> dict[str, object]:
    """Run a dataset's contract adherence + drift checks right now and report the outcome.

    Equivalent to clicking "Run checks" in the Pactum UI -- this can create
    new incidents as a side effect if a check fails, but never modifies the
    contract itself.
    """
    contract = get_active(dataset_id)
    if contract is None:
        return {"status": "no_active_contract", "dataset_id": dataset_id}
    parsed = parse_contract_yaml(contract.yaml)
    outcomes = evaluate_contract(dataset_id, parsed, contract.id)
    return {
        "status": "ok",
        "dataset_id": dataset_id,
        "failed": [o.model_dump(mode="json") for o in outcomes if o.status == "failed"],
        "passed": sum(1 for o in outcomes if o.status == "passed"),
        "skipped": sum(1 for o in outcomes if o.status == "skipped"),
    }


def main() -> None:
    load_persisted_registrations()
    server.run()
