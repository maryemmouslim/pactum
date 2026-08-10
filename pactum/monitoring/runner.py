from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from pactum.contract_schema import ColumnRule, ParsedContract
from pactum.monitoring.adherence.completeness_sla import check_completeness_sla
from pactum.monitoring.adherence.freshness_sla import check_freshness_sla
from pactum.monitoring.adherence.range_enum import check_enum, check_range
from pactum.monitoring.adherence.referential_integrity import check_referential_integrity
from pactum.monitoring.adherence.regex import check_regex
from pactum.monitoring.adherence.schema import check_schema
from pactum.monitoring.adherence.uniqueness import check_uniqueness
from pactum.monitoring.adherence.violation import Violation
from pactum.monitoring.checkpoint_store import load_checkpoint, save_checkpoint
from pactum.monitoring.drift.chi_squared import ChiSquaredDetector
from pactum.monitoring.drift.freshness import FreshnessDetector
from pactum.monitoring.drift.ks import KSDetector
from pactum.monitoring.drift.protocol import DriftDetector
from pactum.monitoring.drift.psi import PSIDetector
from pactum.monitoring.incident_store import emit_incident
from pactum.monitoring.snapshot_store import load_reference_snapshot, save_reference_snapshot
from pactum.sources.registry import get_adapter

# Which drift detectors apply to a column, based on what the agent classified
# it as -- not every semantic type has a statistical test that makes sense
# (e.g. free_text or identifier columns aren't meaningfully PSI/chi-squared-able).
# Numeric columns get both PSI and KS, same as the hardcoded Dagster pipeline.
_DRIFT_DETECTORS_BY_SEMANTIC_TYPE: dict[str, list[tuple[DriftDetector, str]]] = {
    "currency": [(PSIDetector(), "psi"), (KSDetector(), "ks")],
    "timestamp": [(FreshnessDetector(), "freshness_delta")],
    "categorical": [(ChiSquaredDetector(), "chi_squared")],
}


class CheckOutcome(BaseModel):
    check_type: str
    column: str | None = None
    status: Literal["passed", "failed", "skipped"]
    message: str
    details: dict[str, object] = Field(default_factory=dict)


def _get_column_values(
    dataset_id: str,
    column: str,
    n: int = 1000,
    rows: list[tuple[object, ...]] | None = None,
) -> list[object]:
    adapter = get_adapter(dataset_id)
    columns = list(adapter.get_schema(dataset_id).keys())
    if rows is None:
        rows = adapter.sample(dataset_id, n)
    index = columns.index(column)
    return [row[index] for row in rows]


def _from_violation(violation: Violation, column: str | None) -> CheckOutcome:
    return CheckOutcome(
        check_type=violation.check_type,
        column=column,
        status="passed" if violation.passed else "failed",
        message=violation.message,
        details=violation.details,
    )


def _skip(check_type: str, column: str | None, reason: str) -> CheckOutcome:
    return CheckOutcome(check_type=check_type, column=column, status="skipped", message=reason)


def _emit_if_failed(
    outcome: CheckOutcome, dataset_id: str, contract_version_id: UUID
) -> CheckOutcome:
    if outcome.status == "failed":
        emit_incident(
            dataset_id=dataset_id,
            kind="violation",
            severity="high",
            check_type=outcome.check_type,
            payload=outcome.details,
            contract_version_id=contract_version_id,
            column=outcome.column,
        )
    return outcome


def _evaluate_column_adherence(
    dataset_id: str,
    contract_version_id: UUID,
    column_name: str,
    rule: ColumnRule,
    rows: list[tuple[object, ...]] | None = None,
) -> list[CheckOutcome]:
    values = _get_column_values(dataset_id, column_name, rows=rows)
    outcomes: list[CheckOutcome] = []

    if rule.unique:
        outcomes.append(_from_violation(check_uniqueness(values), column_name))

    if not rule.nullable:
        outcomes.append(
            _from_violation(check_completeness_sla(values, min_completeness=1.0), column_name)
        )

    if rule.min_value is not None or rule.max_value is not None:
        outcomes.append(
            _from_violation(
                check_range(values, minimum=rule.min_value, maximum=rule.max_value), column_name
            )
        )

    if rule.allowed_values:
        outcomes.append(
            _from_violation(
                check_enum(values, allowed_values=set(rule.allowed_values)), column_name
            )
        )

    if rule.regex_pattern:
        outcomes.append(_from_violation(check_regex(values, rule.regex_pattern), column_name))

    if rule.references_dataset and rule.references_column:
        try:
            valid_references = set(
                _get_column_values(rule.references_dataset, rule.references_column)
            )
        except KeyError:
            outcomes.append(
                _skip(
                    "referential_integrity",
                    column_name,
                    f"referenced dataset '{rule.references_dataset}' is not registered",
                )
            )
        except ValueError:
            outcomes.append(
                _skip(
                    "referential_integrity",
                    column_name,
                    f"referenced column '{rule.references_dataset}.{rule.references_column}' "
                    "does not exist",
                )
            )
        else:
            outcomes.append(
                _from_violation(check_referential_integrity(values, valid_references), column_name)
            )

    return [_emit_if_failed(outcome, dataset_id, contract_version_id) for outcome in outcomes]


def _evaluate_column_drift(
    dataset_id: str,
    contract_version_id: UUID,
    column_name: str,
    rule: ColumnRule,
    rows: list[tuple[object, ...]] | None = None,
) -> list[CheckOutcome]:
    detectors = _DRIFT_DETECTORS_BY_SEMANTIC_TYPE.get(rule.semantic_type)
    if not detectors:
        return []

    current = _get_column_values(dataset_id, column_name, rows=rows)
    reference = load_reference_snapshot(dataset_id, column_name)

    if reference is None:
        save_reference_snapshot(dataset_id, column_name, current)
        return [
            _skip(method, column_name, "captured initial reference snapshot")
            for _detector, method in detectors
        ]

    outcomes: list[CheckOutcome] = []
    for detector, method in detectors:
        result = detector.detect(reference, current)
        if result.insufficient_data:
            outcomes.append(
                _skip(method, column_name, str(result.details.get("reason", "insufficient data")))
            )
            continue

        outcome = CheckOutcome(
            check_type=method,
            column=column_name,
            status="failed" if result.drifted else "passed",
            message="Drift detected" if result.drifted else "No drift detected",
            details={"score": result.score, **result.details},
        )
        outcomes.append(_emit_if_failed(outcome, dataset_id, contract_version_id))

    return outcomes


def _resolve_rows(
    dataset_id: str, contract: ParsedContract, incremental: bool
) -> tuple[list[tuple[object, ...]] | None, bool]:
    """Decide which rows this run should check, when running incrementally.

    Returns (rows, should_run). `rows=None` tells every check to fall back
    to its own default full sample -- used both when incremental is off, and
    when there's no timestamp column to slice a window by. `should_run=False`
    only happens when a checkpoint already exists but the window since it
    contains zero new rows -- there's nothing new to check yet.
    """
    if not incremental:
        return None, True

    timestamp_rule = next(
        (rule for rule in contract.columns if rule.semantic_type == "timestamp"), None
    )
    if timestamp_rule is None:
        return None, True

    checkpoint = load_checkpoint(dataset_id)
    now = datetime.now(UTC)

    if checkpoint is None:
        # First-ever incremental check for this dataset -- nothing to be
        # "incremental" from yet, so check whatever's currently there and
        # start tracking from this moment on.
        save_checkpoint(dataset_id, now)
        return None, True

    adapter = get_adapter(dataset_id)
    rows = adapter.query_window(dataset_id, timestamp_rule.name, checkpoint, now)
    save_checkpoint(dataset_id, now)
    return rows, bool(rows)


def evaluate_contract(
    dataset_id: str,
    contract: ParsedContract,
    contract_version_id: UUID,
    *,
    incremental: bool = False,
) -> list[CheckOutcome]:
    """Run every adherence + drift check the contract's rules actually call for.

    Unlike orchestration/definitions.py (which hardcodes checks for one fixed
    "orders" pipeline), this reads which checks apply straight from the
    contract's own ColumnRules -- so it works for any dataset+contract pair,
    which is what an ad-hoc "upload any CSV" interface needs.

    incremental=True checks only rows that arrived since the last check
    (using the contract's timestamp column plus a saved checkpoint) instead
    of re-sampling the whole dataset every time -- this is what Dagster's
    scheduled monitoring uses. incremental=False (the default) always checks
    a fresh full sample, which is what ad-hoc interactive testing wants: a
    "Run checks" click should always show a real result, not "nothing new
    since last time."
    """
    rows, should_run = _resolve_rows(dataset_id, contract, incremental)
    if not should_run:
        return [_skip("incremental_check", None, "no new rows since last check")]

    outcomes: list[CheckOutcome] = []

    actual_schema = get_adapter(dataset_id).get_schema(dataset_id)
    expected_schema = {rule.name: rule.data_type for rule in contract.columns}
    schema_outcome = _from_violation(check_schema(actual_schema, expected_schema), None)
    outcomes.append(_emit_if_failed(schema_outcome, dataset_id, contract_version_id))

    # Columns the contract expects but that are actually missing from live data
    # are already reported by the schema check above -- running per-column
    # checks against them would just crash trying to read values that don't
    # exist, not surface anything new.
    present_columns = [rule for rule in contract.columns if rule.name in actual_schema]

    timestamp_columns = [rule for rule in present_columns if rule.semantic_type == "timestamp"]
    if contract.freshness_sla_seconds is not None and timestamp_columns:
        column = timestamp_columns[0]
        values = _get_column_values(dataset_id, column.name, rows=rows)
        outcome = _from_violation(
            check_freshness_sla(
                values,
                max_age=timedelta(seconds=contract.freshness_sla_seconds),
                now=datetime.now(UTC),
            ),
            column.name,
        )
        outcomes.append(_emit_if_failed(outcome, dataset_id, contract_version_id))

    for rule in present_columns:
        outcomes.extend(
            _evaluate_column_adherence(dataset_id, contract_version_id, rule.name, rule, rows=rows)
        )
        outcomes.extend(
            _evaluate_column_drift(dataset_id, contract_version_id, rule.name, rule, rows=rows)
        )

    return outcomes
