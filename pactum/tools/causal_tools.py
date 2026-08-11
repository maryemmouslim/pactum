from datetime import datetime
from uuid import UUID

from pactum.contract_schema import parse_contract_yaml
from pactum.lineage.graph import load_graph
from pactum.monitoring.calendar_store import list_events_near
from pactum.monitoring.drift.chi_squared import ChiSquaredDetector
from pactum.monitoring.drift.ks import KSDetector
from pactum.monitoring.drift.psi import PSIDetector
from pactum.monitoring.incident_index import find_similar
from pactum.monitoring.incident_store import get_incident
from pactum.monitoring.pipeline_logs import fetch_recent_runs
from pactum.monitoring.snapshot_store import load_reference_snapshot
from pactum.registry.contract_registry import get_by_id
from pactum.sources.registry import get_adapter
from pactum.tools import tool


@tool
def get_lineage(dataset_id: str) -> dict[str, list[str]]:
    """Return the datasets directly upstream and downstream of a dataset.

    Args:
        dataset_id: Fully-qualified dataset identifier.

    Returns:
        Dict with "upstream" and "downstream" lists of dataset ids.
    """
    graph = load_graph()
    return {
        "upstream": graph.upstream_of(dataset_id),
        "downstream": graph.downstream_of(dataset_id),
    }


@tool
def diff_schema(dataset_id: str, contract_version_id: str) -> dict[str, object]:
    """Compare a dataset's live schema against what its contract expects.

    Args:
        dataset_id: Fully-qualified dataset identifier.
        contract_version_id: UUID (as a string) of the contract version the
            incident was detected against -- the specific version, not just
            whatever happens to be active now.

    Returns:
        status="contract_not_found" if the contract version doesn't exist,
        else added/removed/type-changed column names between the live
        schema and the contract's expected schema.
    """
    contract = get_by_id(UUID(contract_version_id))
    if contract is None:
        return {"status": "contract_not_found"}

    parsed = parse_contract_yaml(contract.yaml)
    expected = {rule.name: rule.data_type for rule in parsed.columns}
    actual = get_adapter(dataset_id).get_schema(dataset_id)

    return {
        "status": "ok",
        "added_columns": sorted(set(actual) - set(expected)),
        "removed_columns": sorted(set(expected) - set(actual)),
        "type_changed_columns": sorted(
            name for name in set(actual) & set(expected) if actual[name] != expected[name]
        ),
    }


def _current_column_values(dataset_id: str, column: str, n: int = 1000) -> list[object]:
    adapter = get_adapter(dataset_id)
    columns = list(adapter.get_schema(dataset_id).keys())
    rows = adapter.sample(dataset_id, n)
    index = columns.index(column)
    return [row[index] for row in rows]


@tool
def compare_distributions(dataset_id: str, column: str) -> dict[str, object]:
    """Compare a column's current distribution against its saved reference snapshot.

    Tries the numeric detectors (PSI, KS) first; falls back to chi-squared if
    the values aren't numeric.

    Args:
        dataset_id: Fully-qualified dataset identifier.
        column: Name of the column to compare.

    Returns:
        status="no_reference_snapshot" if no baseline has been captured yet,
        else the drift detector results (score, drifted, details) that ran.
    """
    reference = load_reference_snapshot(dataset_id, column)
    if reference is None:
        return {"status": "no_reference_snapshot"}

    current = _current_column_values(dataset_id, column)

    try:
        results = {
            name: detector.detect(reference, current).model_dump()
            for name, detector in (("psi", PSIDetector()), ("ks", KSDetector()))
        }
    except (TypeError, ValueError):
        results = {"chi_squared": ChiSquaredDetector().detect(reference, current).model_dump()}

    return {"status": "ok", "results": results}


@tool
def query_contract_context(
    dataset_id: str, contract_version_id: str, column: str | None = None
) -> dict[str, object]:
    """Return the contract's status and rules relevant to an incident.

    Args:
        dataset_id: Fully-qualified dataset identifier.
        contract_version_id: UUID (as a string) of the contract version the
            incident was detected against.
        column: If set, also return the specific rule for this column.

    Returns:
        status="contract_not_found" if the contract version doesn't exist,
        else the contract's status, SLAs, and (if column was given) that
        column's rule.
    """
    contract = get_by_id(UUID(contract_version_id))
    if contract is None:
        return {"status": "contract_not_found"}

    parsed = parse_contract_yaml(contract.yaml)
    column_rule = parsed.get_column(column) if column else None
    return {
        "status": "ok",
        "contract_status": contract.status,
        "freshness_sla_seconds": parsed.freshness_sla_seconds,
        "completeness_sla": parsed.completeness_sla,
        "column_rule": column_rule.model_dump() if column_rule else None,
    }


@tool
def find_similar_incidents(incident_id: str) -> list[dict[str, object]]:
    """Return past incidents most semantically similar to this one, ranked by similarity.

    Vector search over every incident's (check_type, column, payload, and
    prior hypotheses) embedding -- not just an exact (dataset_id, check_type)
    match, so it can surface real precedent across different check types
    that turned out to share a root cause.

    Args:
        incident_id: UUID (as a string) of the incident being investigated.

    Returns:
        Empty list if the incident doesn't exist. Otherwise up to 5 similar
        past incidents, each with an added "similarity_score" (lower = closer).
    """
    incident = get_incident(UUID(incident_id))
    if incident is None:
        return []

    results = []
    for match in find_similar(incident):
        related = get_incident(UUID(str(match["id"])))
        if related is not None:
            results.append(
                {**related.model_dump(mode="json"), "similarity_score": match.get("_distance")}
            )
    return results


@tool
def fetch_pipeline_logs(dataset_id: str, around: str) -> dict[str, object]:
    """Return recent Dagster monitoring_job run records for a dataset.

    Only runs that actually went through Dagster are visible here -- an
    ad-hoc "Run checks" click in the UI calls evaluate_contract directly and
    never creates a Dagster run. status="not_configured" if no persistent
    Dagster instance exists yet (e.g. run_monitoring_job.py has never run).

    Args:
        dataset_id: Fully-qualified dataset identifier.
        around: ISO timestamp to search near (typically the incident's detected_at).

    Returns:
        status="ok" with recent run records, or status="not_configured".
    """
    return fetch_recent_runs(dataset_id, datetime.fromisoformat(around))


@tool
def fetch_calendar_events(dataset_id: str, around: str) -> dict[str, object]:
    """Return deployments, holidays, or regulatory events near an incident's detection time.

    There's no external calendar integration -- events are manually recorded
    (see pactum/scripts/add_calendar_event.py) via pactum.monitoring.calendar_store.

    Args:
        dataset_id: Fully-qualified dataset identifier.
        around: ISO timestamp to search near (typically the incident's detected_at).

    Returns:
        status="ok" with events within a few days of `around`, scoped to this
        dataset or global.
    """
    events = list_events_near(dataset_id, datetime.fromisoformat(around))
    return {"status": "ok", "events": [event.model_dump(mode="json") for event in events]}
