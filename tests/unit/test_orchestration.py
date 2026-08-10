import uuid
from datetime import UTC, datetime, timedelta

import pytest
from dagster import materialize

from pactum.agents.contract_generator import CritiqueResult
from pactum.contract_schema import ColumnRule, ParsedContract, render_contract_yaml
from pactum.lineage.graph import LineageGraph
from pactum.models import Contract
from pactum.monitoring.runner import CheckOutcome
from pactum.orchestration.definitions import contract, contract_checks, source_data
from pactum.sources import registry as source_registry
from pactum.tools.classify_semantics import SemanticClassification

EMAIL_PATTERN = r"[^@\s]+@[^@\s]+\.[^@\s]+"


class FakeAdapter:
    def __init__(
        self,
        dataset_id: str,
        schema: dict[str, str],
        rows: list[tuple[object, ...]] | None = None,
    ) -> None:
        self._dataset_id = dataset_id
        self._schema = schema
        self._rows = rows if rows is not None else [("o1",), ("o2",)]

    def list_datasets(self) -> list[str]:
        return [self._dataset_id]

    def get_schema(self, dataset: str) -> dict[str, str]:
        return self._schema

    def sample(self, dataset: str, n: int = 10) -> list[tuple[object, ...]]:
        return self._rows


class FakeStructuredLLM:
    def __init__(self, result: object) -> None:
        self._result = result

    def invoke(self, prompt: str) -> object:
        return self._result


class FakeLLM:
    def __init__(self, result: object) -> None:
        self._result = result

    def with_structured_output(self, schema: object) -> FakeStructuredLLM:
        return FakeStructuredLLM(self._result)


def _contract_dict(columns: list[ColumnRule], **kwargs: object) -> dict[str, object]:
    parsed = ParsedContract(dataset_id="orders", columns=columns, **kwargs)  # type: ignore[arg-type]
    return {
        "id": uuid.uuid4(),
        "dataset_id": "orders",
        "version": 1,
        "yaml": render_contract_yaml(parsed),
    }


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    source_registry._adapters.clear()


def test_source_data_returns_the_registered_schema() -> None:
    source_registry.register_source(FakeAdapter("orders", {"order_id": "TEXT", "amount": "DOUBLE"}))

    assert source_data() == {"order_id": "TEXT", "amount": "DOUBLE"}


def _fake_active_contract() -> Contract:
    parsed = ParsedContract(dataset_id="orders", columns=[])
    return Contract(
        id=uuid.uuid4(),
        dataset_id="orders",
        version=1,
        yaml=render_contract_yaml(parsed),
        status="active",
        parent_version_id=None,
        created_at=datetime.now(UTC),
        created_by="test",
    )


def test_contract_checks_skips_when_no_contract_is_active(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pactum.orchestration.definitions.get_active", lambda dataset_id: None)
    monkeypatch.setattr(
        "pactum.orchestration.definitions.evaluate_contract",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("should not evaluate checks with no approved contract")
        ),
    )

    result = contract_checks(_contract_dict(columns=[]))

    assert result.passed is True
    assert "no approved contract" in str(result.metadata["skipped"].value)


def test_contract_checks_passes_when_no_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pactum.orchestration.definitions.get_active", lambda dataset_id: _fake_active_contract()
    )
    monkeypatch.setattr(
        "pactum.orchestration.definitions.evaluate_contract",
        lambda dataset_id, parsed, contract_version_id, incremental=False: [
            CheckOutcome(check_type="schema", status="passed", message="ok"),
            CheckOutcome(
                check_type="psi", column="amount", status="skipped", message="captured baseline"
            ),
        ],
    )

    result = contract_checks(_contract_dict(columns=[]))

    assert result.passed is True
    assert result.metadata["failed"].value == 0
    assert result.metadata["passed"].value == 1
    assert result.metadata["skipped"].value == 1


def test_contract_checks_fails_when_evaluate_contract_reports_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pactum.orchestration.definitions.get_active", lambda dataset_id: _fake_active_contract()
    )
    monkeypatch.setattr(
        "pactum.orchestration.definitions.evaluate_contract",
        lambda dataset_id, parsed, contract_version_id, incremental=False: [
            CheckOutcome(
                check_type="uniqueness",
                column="order_id",
                status="failed",
                message="253 duplicate value(s) found",
            ),
        ],
    )

    result = contract_checks(_contract_dict(columns=[]))

    assert result.passed is False
    assert result.metadata["failed"].value == 1
    assert "uniqueness" in result.metadata["failures"].value
    assert "order_id" in result.metadata["failures"].value


def test_full_pipeline_materializes_successfully(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC)
    orders_schema = {
        "order_id": "TEXT",
        "amount": "DOUBLE",
        "status": "TEXT",
        "email": "TEXT",
        "created_at": "TIMESTAMP",
        "customer_id": "TEXT",
    }
    orders_rows: list[tuple[object, ...]] = [
        ("o1", 10.0, "pending", "a@example.com", now - timedelta(minutes=5), "c1"),
        ("o2", 20.0, "shipped", "b@example.com", now - timedelta(minutes=10), "c2"),
    ]
    source_registry.register_source(FakeAdapter("orders", orders_schema, orders_rows))
    source_registry.register_source(FakeAdapter("customers", {"id": "TEXT"}, [("c1",), ("c2",)]))

    # Drift's snapshot storage, the incremental checkpoint, and incident
    # emission are all real-Postgres-backed -- keep this a genuine unit test
    # by faking all three. First run always has no baseline/checkpoint yet,
    # so drift checks should just skip (capture-and-skip), never emit.
    monkeypatch.setattr("pactum.monitoring.runner.load_checkpoint", lambda dataset_id: None)
    monkeypatch.setattr(
        "pactum.monitoring.runner.save_checkpoint", lambda dataset_id, checked_through: None
    )
    monkeypatch.setattr(
        "pactum.monitoring.runner.load_reference_snapshot", lambda dataset_id, column: None
    )
    monkeypatch.setattr(
        "pactum.monitoring.runner.save_reference_snapshot",
        lambda dataset_id, column, values: None,
    )
    monkeypatch.setattr(
        "pactum.monitoring.runner.emit_incident",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError(f"should not emit an incident, got {kwargs}")
        ),
    )

    monkeypatch.setattr("pactum.tools.understand_source.load_graph", lambda: LineageGraph())
    monkeypatch.setattr(
        "pactum.tools.classify_semantics.get_llm",
        lambda role="fast": FakeLLM(SemanticClassification(label="identifier", confidence=0.9)),
    )

    # Simulates a human having already approved the draft this run generates --
    # contract_checks only checks against get_active(), never the fresh draft.
    created_contracts: list[Contract] = []

    def fake_create_version(
        dataset_id: str, yaml: str, created_by: str, status: str = "draft"
    ) -> Contract:
        written = Contract(
            id=uuid.uuid4(),
            dataset_id=dataset_id,
            version=1,
            yaml=yaml,
            status=status,
            parent_version_id=None,
            created_at=datetime.now(UTC),
            created_by=created_by,
        )
        created_contracts.append(written)
        return written

    monkeypatch.setattr("pactum.agents.contract_generator.create_version", fake_create_version)
    monkeypatch.setattr(
        "pactum.orchestration.definitions.get_active",
        lambda dataset_id: created_contracts[-1] if created_contracts else None,
    )

    fake_parsed_contract = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(
                name="order_id",
                data_type="TEXT",
                semantic_type="identifier",
                unique=True,
                nullable=False,
            ),
            ColumnRule(name="amount", data_type="DOUBLE", semantic_type="currency", min_value=0.0),
            ColumnRule(
                name="status",
                data_type="TEXT",
                semantic_type="categorical",
                allowed_values=["pending", "shipped", "cancelled"],
            ),
            ColumnRule(
                name="email",
                data_type="TEXT",
                semantic_type="pii",
                sensitivity=True,
                regex_pattern=EMAIL_PATTERN,
            ),
            ColumnRule(name="created_at", data_type="TIMESTAMP", semantic_type="timestamp"),
            ColumnRule(
                name="customer_id",
                data_type="TEXT",
                semantic_type="identifier",
                references_dataset="customers",
                references_column="id",
            ),
        ],
        freshness_sla_seconds=3600,
        completeness_sla=0.95,
    )
    draft_then_critique_llms = iter(
        [
            FakeLLM(fake_parsed_contract),
            FakeLLM(CritiqueResult(approved=True, feedback="")),
        ]
    )
    monkeypatch.setattr(
        "pactum.agents.contract_generator.get_llm",
        lambda role="reasoning": next(draft_then_critique_llms),
    )

    result = materialize([source_data, contract, contract_checks])

    assert result.success
    check_evaluations = result.get_asset_check_evaluations()
    assert len(check_evaluations) == 1
    assert check_evaluations[0].passed is True
