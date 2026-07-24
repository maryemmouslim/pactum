from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from dagster import (
    AssetCheckResult,
    Definitions,
    ScheduleDefinition,
    asset,
    asset_check,
    define_asset_job,
)

from pactum.agents.contract_generator import build_contract_generator_graph
from pactum.agents.state import ContractGeneratorState
from pactum.monitoring.adherence.completeness_sla import check_completeness_sla
from pactum.monitoring.adherence.freshness_sla import check_freshness_sla
from pactum.monitoring.adherence.range_enum import check_enum, check_range
from pactum.monitoring.adherence.referential_integrity import check_referential_integrity
from pactum.monitoring.adherence.regex import check_regex
from pactum.monitoring.adherence.schema import check_schema
from pactum.monitoring.adherence.uniqueness import check_uniqueness
from pactum.monitoring.adherence.violation import Violation
from pactum.monitoring.incident_store import emit_incident
from pactum.sources.duckdb_adapter import DuckDBAdapter
from pactum.sources.registry import get_adapter, register_source

DATASET_ID = "orders"
CUSTOMERS_DATASET_ID = "customers"

# The min/max, allowed values, regex, and SLA thresholds below are placeholders
# standing in for real rules. There is no ODCS YAML parser yet to pull actual
# rules out of `contract["yaml"]`, so we can't read them from the contract
# itself -- this is a known gap, not a finished rule-extraction pipeline.
EMAIL_PATTERN = r"[^@\s]+@[^@\s]+\.[^@\s]+"

# Register the example "orders" and "customers" datasets so this module works
# standalone (e.g. under `dagster dev`). Tests override this via their own
# fake adapters, registered after the autouse _clear_registry fixture runs.
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
        "dataset_id": written.dataset_id,
        "version": written.version,
        "yaml": written.yaml,
        "columns": result["columns"],
    }


def _get_column_values(dataset_id: str, column: str, n: int = 1000) -> list[object]:
    adapter = get_adapter(dataset_id)
    columns = list(adapter.get_schema(dataset_id).keys())
    rows = adapter.sample(dataset_id, n)
    index = columns.index(column)
    return [row[index] for row in rows]


def _finish(
    contract: dict[str, object],
    check_type: str,
    violation: Violation,
    column: str | None = None,
) -> AssetCheckResult:
    if not violation.passed:
        emit_incident(
            dataset_id=DATASET_ID,
            kind="violation",
            severity="high",
            check_type=check_type,
            payload=violation.details,
            contract_version=str(contract["version"]),
            column=column,
        )
    return AssetCheckResult(
        passed=violation.passed,
        metadata={key: str(value) for key, value in violation.details.items()},
    )


def _evaluate_schema_adherence(contract: dict[str, object]) -> AssetCheckResult:
    expected_schema = cast(dict[str, str], contract["columns"])
    actual_schema = get_adapter(DATASET_ID).get_schema(DATASET_ID)
    violation = check_schema(actual_schema, expected_schema)
    return _finish(contract, "schema", violation)


def _evaluate_uniqueness(contract: dict[str, object]) -> AssetCheckResult:
    values = _get_column_values(DATASET_ID, "order_id")
    violation = check_uniqueness(values)
    return _finish(contract, "uniqueness", violation, column="order_id")


def _evaluate_completeness(contract: dict[str, object]) -> AssetCheckResult:
    values = _get_column_values(DATASET_ID, "amount")
    violation = check_completeness_sla(values, min_completeness=0.95)
    return _finish(contract, "completeness_sla", violation, column="amount")


def _evaluate_range(contract: dict[str, object]) -> AssetCheckResult:
    values = _get_column_values(DATASET_ID, "amount")
    violation = check_range(values, minimum=0.0)
    return _finish(contract, "range", violation, column="amount")


def _evaluate_enum(contract: dict[str, object]) -> AssetCheckResult:
    values = _get_column_values(DATASET_ID, "status")
    violation = check_enum(values, allowed_values={"pending", "shipped", "cancelled"})
    return _finish(contract, "enum", violation, column="status")


def _evaluate_regex(contract: dict[str, object]) -> AssetCheckResult:
    values = _get_column_values(DATASET_ID, "email")
    violation = check_regex(values, EMAIL_PATTERN)
    return _finish(contract, "regex", violation, column="email")


def _evaluate_freshness_sla(contract: dict[str, object]) -> AssetCheckResult:
    values = _get_column_values(DATASET_ID, "created_at")
    violation = check_freshness_sla(values, max_age=timedelta(hours=1), now=datetime.now(UTC))
    return _finish(contract, "freshness_sla", violation, column="created_at")


def _evaluate_referential_integrity(contract: dict[str, object]) -> AssetCheckResult:
    values = _get_column_values(DATASET_ID, "customer_id")
    valid_customer_ids = set(_get_column_values(CUSTOMERS_DATASET_ID, "id"))
    violation = check_referential_integrity(values, valid_customer_ids)
    return _finish(contract, "referential_integrity", violation, column="customer_id")


@asset_check(asset=contract)
def schema_adherence_check(contract: dict[str, object]) -> AssetCheckResult:
    """Verify live data still matches the contract's recorded schema; emit an incident if not."""
    return _evaluate_schema_adherence(contract)


@asset_check(asset=contract)
def uniqueness_check(contract: dict[str, object]) -> AssetCheckResult:
    """Check order_id has no duplicates; emit an incident if it does."""
    return _evaluate_uniqueness(contract)


@asset_check(asset=contract)
def completeness_check(contract: dict[str, object]) -> AssetCheckResult:
    """Check amount is at least 95% non-null; emit an incident if not."""
    return _evaluate_completeness(contract)


@asset_check(asset=contract)
def range_check(contract: dict[str, object]) -> AssetCheckResult:
    """Check amount is never negative; emit an incident if it is."""
    return _evaluate_range(contract)


@asset_check(asset=contract)
def enum_check(contract: dict[str, object]) -> AssetCheckResult:
    """Check status is one of the allowed values; emit an incident if not."""
    return _evaluate_enum(contract)


@asset_check(asset=contract)
def regex_check(contract: dict[str, object]) -> AssetCheckResult:
    """Check email matches a standard email pattern; emit an incident if not."""
    return _evaluate_regex(contract)


@asset_check(asset=contract)
def freshness_sla_check(contract: dict[str, object]) -> AssetCheckResult:
    """Check created_at is no more than 1 hour old; emit an incident if it is."""
    return _evaluate_freshness_sla(contract)


@asset_check(asset=contract)
def referential_integrity_check(contract: dict[str, object]) -> AssetCheckResult:
    """Check customer_id references an existing customer; emit an incident if not."""
    return _evaluate_referential_integrity(contract)


monitoring_job = define_asset_job("monitoring_job", selection=[contract])

hourly_monitoring_schedule = ScheduleDefinition(
    job=monitoring_job,
    cron_schedule="0 * * * *",
)

defs = Definitions(
    assets=[source_data, contract],
    asset_checks=[
        schema_adherence_check,
        uniqueness_check,
        completeness_check,
        range_check,
        enum_check,
        regex_check,
        freshness_sla_check,
        referential_integrity_check,
    ],
    schedules=[hourly_monitoring_schedule],
)
