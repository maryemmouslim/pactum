from pathlib import Path

from dagster import (
    AssetCheckResult,
    DefaultScheduleStatus,
    Definitions,
    ScheduleDefinition,
    asset,
    asset_check,
    define_asset_job,
)

from pactum.agents.contract_generator import build_contract_generator_graph
from pactum.agents.state import ContractGeneratorState
from pactum.contract_schema import parse_contract_yaml
from pactum.monitoring.runner import evaluate_contract
from pactum.monitoring.snapshot_store import save_reference_snapshot
from pactum.orchestration.causal_sensor import new_incident_sensor
from pactum.registry.contract_registry import get_active
from pactum.sources.duckdb_adapter import DuckDBAdapter
from pactum.sources.registry import get_adapter, list_registered_datasets, register_source

DATASET_ID = "orders"

# Register the example "orders" and "customers" datasets so this module works
# standalone (e.g. under `dagster dev`). Deliberately persist=False (the
# default): every other Postgres-touching module in this project only
# connects *inside* its functions, never at import time, so unit tests can
# import freely without a real database -- this keeps that invariant.
# Durable persistence (register_source(..., persist=True) and
# load_persisted_registrations()) is a real, tested capability, just not
# wired into this module-level import.
_EXAMPLE_DATA_DIR = Path(__file__).resolve().parents[2] / "examples" / "data"
register_source(DuckDBAdapter(str(_EXAMPLE_DATA_DIR)))


@asset
def source_data() -> dict[str, str]:
    """The registered source's current schema -- Dagster's tracked view of the raw source."""
    adapter = get_adapter(DATASET_ID)
    return adapter.get_schema(DATASET_ID)


@asset(deps=[source_data])
def contract() -> dict[str, object]:
    """Run the Contract Generator Agent end-to-end and return the written contract."""
    app = build_contract_generator_graph()
    result = app.invoke(ContractGeneratorState(dataset_id=DATASET_ID))
    written = result["written_contract"]
    return {
        "id": written.id,
        "dataset_id": written.dataset_id,
        "version": written.version,
        "yaml": written.yaml,
    }


@asset_check(asset=contract)
def contract_checks(contract: dict[str, object]) -> AssetCheckResult:
    """Check live data against the currently APPROVED contract for this dataset.

    Deliberately ignores the fresh draft the `contract` asset just generated
    -- `contract` proposes what the rules *could* be every time it runs, but
    a human has to explicitly approve one (via the interface, which calls
    activate_version) before monitoring treats it as authoritative. Until
    that happens, there's nothing approved to check against yet, so this
    skips rather than silently enforcing an unreviewed draft.

    Uses the same generic evaluate_contract() the interface uses -- driven
    entirely by whatever rules the contract defines for whatever columns
    exist, not hardcoded to specific column names. That makes this check
    work for any dataset, and keeps a single implementation of "how do we
    check a contract" instead of maintaining a second, hardcoded one here
    that could silently drift out of sync with the first.
    """
    active = get_active(DATASET_ID)
    if active is None:
        return AssetCheckResult(
            passed=True,
            metadata={"skipped": "no approved contract yet -- approve a draft via the interface"},
        )

    parsed = parse_contract_yaml(active.yaml)
    outcomes = evaluate_contract(DATASET_ID, parsed, active.id, incremental=True)

    failed = [outcome for outcome in outcomes if outcome.status == "failed"]
    passed = [outcome for outcome in outcomes if outcome.status == "passed"]
    skipped = [outcome for outcome in outcomes if outcome.status == "skipped"]

    return AssetCheckResult(
        passed=not failed,
        metadata={
            "failed": len(failed),
            "passed": len(passed),
            "skipped": len(skipped),
            "failures": str(
                [
                    {"check_type": o.check_type, "column": o.column, "message": o.message}
                    for o in failed
                ]
            ),
        },
    )


monitoring_job = define_asset_job("monitoring_job", selection=[contract])

hourly_monitoring_schedule = ScheduleDefinition(
    job=monitoring_job,
    cron_schedule="0 * * * *",
    default_status=DefaultScheduleStatus.RUNNING,
)

defs = Definitions(
    assets=[source_data, contract],
    asset_checks=[contract_checks],
    schedules=[hourly_monitoring_schedule],
)


# Daily snapshot asset: capture and persist a column snapshot for each registered
# dataset so drift detectors can build a multi-day reference window.


@asset
def capture_snapshots() -> dict[str, int]:
    counts: dict[str, int] = {}
    for dataset_id in list_registered_datasets():
        adapter = get_adapter(dataset_id)
        schema = adapter.get_schema(dataset_id)
        rows = adapter.sample(dataset_id, n=1000)
        for col_idx, col_name in enumerate(schema):
            values = [row[col_idx] for row in rows]
            save_reference_snapshot(dataset_id, col_name, values)
        counts[dataset_id] = len(rows)
    return counts


snapshot_job = define_asset_job("snapshot_job", selection=[capture_snapshots])

daily_snapshot_schedule = ScheduleDefinition(
    job=snapshot_job, cron_schedule="0 0 * * *", default_status=DefaultScheduleStatus.RUNNING
)

# Recreate Definitions to include the new asset and schedule
defs = Definitions(
    assets=[source_data, contract, capture_snapshots],
    asset_checks=[contract_checks],
    schedules=[hourly_monitoring_schedule, daily_snapshot_schedule],
    sensors=[new_incident_sensor],
)
