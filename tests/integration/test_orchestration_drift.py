import uuid

import psycopg
import pytest

from pactum.contract_schema import ColumnRule, ParsedContract
from pactum.monitoring.runner import evaluate_contract
from pactum.registry.contract_registry import create_version
from pactum.settings import settings
from pactum.sources import registry as source_registry


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


class FakeAdapter:
    def __init__(
        self, dataset_id: str, schema: dict[str, str], rows: list[tuple[object, ...]]
    ) -> None:
        self._dataset_id = dataset_id
        self._schema = schema
        self._rows = rows

    def list_datasets(self) -> list[str]:
        return [self._dataset_id]

    def get_schema(self, dataset: str) -> dict[str, str]:
        return self._schema

    def sample(self, dataset: str, n: int = 10) -> list[tuple[object, ...]]:
        return self._rows


@pytest.fixture
def dataset_id() -> str:
    return f"test_orders_{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _cleanup(dataset_id: str):  # type: ignore[no-untyped-def]
    source_registry._adapters.clear()
    yield
    source_registry._adapters.clear()
    with _connect() as conn:
        conn.execute("DELETE FROM column_snapshots WHERE dataset_id = %(d)s", {"d": dataset_id})
        conn.execute("DELETE FROM incidents WHERE dataset_id = %(d)s", {"d": dataset_id})
        conn.execute("DELETE FROM contracts WHERE dataset_id = %(d)s", {"d": dataset_id})


def test_psi_drift_check_captures_then_compares_against_real_snapshot_store(
    dataset_id: str,
) -> None:
    baseline_values = [float(v) for v in range(1, 1001)]
    source_registry.register_source(
        FakeAdapter(dataset_id, {"amount": "DOUBLE"}, [(v,) for v in baseline_values])
    )
    # contract_version_id is a real foreign key -- emitting an incident needs
    # an actual contracts row to point at.
    contract = create_version(dataset_id=dataset_id, yaml="apiVersion: v3", created_by="test")
    parsed = ParsedContract(
        dataset_id=dataset_id,
        columns=[ColumnRule(name="amount", data_type="DOUBLE", semantic_type="currency")],
    )

    # First run: no reference snapshot exists yet -- should capture the
    # current data as the baseline and skip (nothing to compare against).
    first_outcomes = evaluate_contract(dataset_id, parsed, contract.id)
    assert all(o.status != "failed" for o in first_outcomes)

    with _connect() as conn:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM column_snapshots "
            "WHERE dataset_id = %(d)s AND column_name = 'amount'",
            {"d": dataset_id},
        ).fetchone()
    assert count == 1

    # Second run: same adapter, same data -- reference now exists, should
    # genuinely compare and find no drift.
    second_outcomes = evaluate_contract(dataset_id, parsed, contract.id)
    assert all(o.status != "failed" for o in second_outcomes)

    # Third run: current data has genuinely shifted -- should now detect
    # drift against the *original* baseline captured on the first run, and
    # write a real incident.
    shifted_adapter = FakeAdapter(
        dataset_id, {"amount": "DOUBLE"}, [(v + 500,) for v in baseline_values]
    )
    source_registry.register_source(shifted_adapter)

    third_outcomes = evaluate_contract(dataset_id, parsed, contract.id)
    psi_outcome = next(o for o in third_outcomes if o.check_type == "psi")
    assert psi_outcome.status == "failed"

    with _connect() as conn:
        (incident_count,) = conn.execute(
            "SELECT COUNT(*) FROM incidents WHERE dataset_id = %(d)s",
            {"d": dataset_id},
        ).fetchone()
    assert incident_count >= 1
