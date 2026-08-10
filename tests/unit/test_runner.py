import uuid
from datetime import UTC, datetime, timedelta

import pytest

from pactum.contract_schema import ColumnRule, ParsedContract
from pactum.monitoring.runner import evaluate_contract
from pactum.sources import registry as source_registry


class FakeAdapter:
    def __init__(
        self,
        dataset_id: str,
        schema: dict[str, str],
        rows: list[tuple[object, ...]],
    ) -> None:
        self._dataset_id = dataset_id
        self._schema = schema
        self._rows = rows

    def list_datasets(self) -> list[str]:
        return [self._dataset_id]

    def get_schema(self, dataset: str) -> dict[str, str]:
        return self._schema

    def sample(self, dataset: str, n: int = 1000) -> list[tuple[object, ...]]:
        return self._rows[:n]

    def query_window(
        self, dataset: str, timestamp_column: str, start: datetime, end: datetime
    ) -> list[tuple[object, ...]]:
        index = list(self._schema.keys()).index(timestamp_column)
        return [row for row in self._rows if start <= row[index] < end]


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    source_registry._adapters.clear()


def _no_incident(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pactum.monitoring.runner.emit_incident",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not emit an incident")),
    )


def _capture_incidents(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    captured: list[dict[str, object]] = []
    monkeypatch.setattr(
        "pactum.monitoring.runner.emit_incident",
        lambda **kwargs: captured.append(kwargs),
    )
    return captured


def _no_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pactum.monitoring.runner.load_reference_snapshot", lambda dataset_id, column: None
    )
    monkeypatch.setattr(
        "pactum.monitoring.runner.save_reference_snapshot",
        lambda dataset_id, column, values: None,
    )


def test_evaluate_contract_runs_schema_check(monkeypatch: pytest.MonkeyPatch) -> None:
    source_registry.register_source(FakeAdapter("orders", {"order_id": "TEXT"}, [("o1",)]))
    _no_incident(monkeypatch)
    _no_snapshot(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[ColumnRule(name="order_id", data_type="TEXT", semantic_type="identifier")],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4())

    schema_outcomes = [o for o in outcomes if o.check_type == "schema"]
    assert len(schema_outcomes) == 1
    assert schema_outcomes[0].status == "passed"


def test_evaluate_contract_flags_schema_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    source_registry.register_source(FakeAdapter("orders", {"order_id": "TEXT"}, [("o1",)]))
    captured = _capture_incidents(monkeypatch)
    _no_snapshot(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(name="order_id", data_type="TEXT", semantic_type="identifier"),
            ColumnRule(name="amount", data_type="DOUBLE", semantic_type="currency"),
        ],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4())

    schema_outcomes = [o for o in outcomes if o.check_type == "schema"]
    assert schema_outcomes[0].status == "failed"
    assert any(c["check_type"] == "schema" for c in captured)


def test_evaluate_contract_checks_uniqueness_when_rule_says_unique(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry.register_source(FakeAdapter("orders", {"order_id": "TEXT"}, [("o1",), ("o1",)]))
    captured = _capture_incidents(monkeypatch)
    _no_snapshot(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(name="order_id", data_type="TEXT", semantic_type="identifier", unique=True)
        ],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4())

    uniqueness_outcomes = [o for o in outcomes if o.check_type == "uniqueness"]
    assert len(uniqueness_outcomes) == 1
    assert uniqueness_outcomes[0].status == "failed"
    assert any(c["check_type"] == "uniqueness" for c in captured)


def test_evaluate_contract_skips_uniqueness_when_rule_does_not_require_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry.register_source(FakeAdapter("orders", {"order_id": "TEXT"}, [("o1",), ("o1",)]))
    _no_incident(monkeypatch)
    _no_snapshot(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[ColumnRule(name="order_id", data_type="TEXT", semantic_type="identifier")],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4())

    assert not [o for o in outcomes if o.check_type == "uniqueness"]


def test_evaluate_contract_checks_non_nullable_as_completeness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows: list[tuple[object, ...]] = [(10.0,)] * 5 + [(None,)] * 5
    source_registry.register_source(FakeAdapter("orders", {"amount": "DOUBLE"}, rows))
    captured = _capture_incidents(monkeypatch)
    _no_snapshot(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(name="amount", data_type="DOUBLE", semantic_type="currency", nullable=False)
        ],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4())

    completeness_outcomes = [o for o in outcomes if o.check_type == "completeness_sla"]
    assert completeness_outcomes[0].status == "failed"
    assert any(c["check_type"] == "completeness_sla" for c in captured)


def test_evaluate_contract_checks_range(monkeypatch: pytest.MonkeyPatch) -> None:
    source_registry.register_source(FakeAdapter("orders", {"amount": "DOUBLE"}, [(10.0,), (-5.0,)]))
    captured = _capture_incidents(monkeypatch)
    _no_snapshot(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(name="amount", data_type="DOUBLE", semantic_type="currency", min_value=0.0)
        ],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4())

    range_outcomes = [o for o in outcomes if o.check_type == "range"]
    assert range_outcomes[0].status == "failed"
    assert any(c["check_type"] == "range" for c in captured)


def test_evaluate_contract_checks_enum(monkeypatch: pytest.MonkeyPatch) -> None:
    source_registry.register_source(
        FakeAdapter("orders", {"status": "TEXT"}, [("pending",), ("bogus",)])
    )
    captured = _capture_incidents(monkeypatch)
    _no_snapshot(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(
                name="status",
                data_type="TEXT",
                semantic_type="categorical",
                allowed_values=["pending", "shipped"],
            )
        ],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4())

    enum_outcomes = [o for o in outcomes if o.check_type == "enum"]
    assert enum_outcomes[0].status == "failed"
    assert any(c["check_type"] == "enum" for c in captured)


def test_evaluate_contract_checks_regex(monkeypatch: pytest.MonkeyPatch) -> None:
    source_registry.register_source(
        FakeAdapter("orders", {"email": "TEXT"}, [("a@example.com",), ("not-an-email",)])
    )
    captured = _capture_incidents(monkeypatch)
    _no_snapshot(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(
                name="email",
                data_type="TEXT",
                semantic_type="pii",
                sensitivity=True,
                regex_pattern=r"[^@\s]+@[^@\s]+\.[^@\s]+",
            )
        ],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4())

    regex_outcomes = [o for o in outcomes if o.check_type == "regex"]
    assert regex_outcomes[0].status == "failed"
    assert any(c["check_type"] == "regex" for c in captured)


def test_evaluate_contract_skips_referential_integrity_when_target_not_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry.register_source(
        FakeAdapter("orders", {"customer_id": "TEXT"}, [("c1",), ("c2",)])
    )
    _no_incident(monkeypatch)
    _no_snapshot(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(
                name="customer_id",
                data_type="TEXT",
                semantic_type="identifier",
                references_dataset="customers",
                references_column="id",
            )
        ],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4())

    ref_outcomes = [o for o in outcomes if o.check_type == "referential_integrity"]
    assert ref_outcomes[0].status == "skipped"


def test_evaluate_contract_checks_referential_integrity_when_target_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry.register_source(
        FakeAdapter("orders", {"customer_id": "TEXT"}, [("c1",), ("c999",)])
    )
    source_registry.register_source(FakeAdapter("customers", {"id": "TEXT"}, [("c1",)]))
    captured = _capture_incidents(monkeypatch)
    _no_snapshot(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(
                name="customer_id",
                data_type="TEXT",
                semantic_type="identifier",
                references_dataset="customers",
                references_column="id",
            )
        ],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4())

    ref_outcomes = [o for o in outcomes if o.check_type == "referential_integrity"]
    assert ref_outcomes[0].status == "failed"
    assert any(c["check_type"] == "referential_integrity" for c in captured)


def test_evaluate_contract_captures_baseline_on_first_drift_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry.register_source(FakeAdapter("orders", {"amount": "DOUBLE"}, [(10.0,), (20.0,)]))
    monkeypatch.setattr(
        "pactum.monitoring.runner.load_reference_snapshot", lambda dataset_id, column: None
    )
    captured_snapshot: dict[str, object] = {}
    monkeypatch.setattr(
        "pactum.monitoring.runner.save_reference_snapshot",
        lambda dataset_id, column, values: captured_snapshot.update(
            dataset_id=dataset_id, column=column
        ),
    )
    _no_incident(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[ColumnRule(name="amount", data_type="DOUBLE", semantic_type="currency")],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4())

    drift_outcomes = [o for o in outcomes if o.check_type in ("psi", "ks")]
    assert len(drift_outcomes) == 2
    assert all(o.status == "skipped" for o in drift_outcomes)
    assert captured_snapshot == {"dataset_id": "orders", "column": "amount"}


def test_evaluate_contract_detects_drift_against_existing_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = [float(v) for v in range(1, 1001)]
    current = [v + 500 for v in reference]
    source_registry.register_source(
        FakeAdapter("orders", {"amount": "DOUBLE"}, [(v,) for v in current])
    )
    monkeypatch.setattr(
        "pactum.monitoring.runner.load_reference_snapshot",
        lambda dataset_id, column: reference,
    )
    captured = _capture_incidents(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[ColumnRule(name="amount", data_type="DOUBLE", semantic_type="currency")],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4())

    psi_outcome = next(o for o in outcomes if o.check_type == "psi")
    ks_outcome = next(o for o in outcomes if o.check_type == "ks")
    assert psi_outcome.status == "failed"
    assert ks_outcome.status == "failed"
    assert {c["check_type"] for c in captured} == {"psi", "ks"}


def test_evaluate_contract_skips_drift_for_semantic_types_without_a_detector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry.register_source(
        FakeAdapter("orders", {"description": "TEXT"}, [("a widget",), ("another widget",)])
    )
    _no_incident(monkeypatch)
    _no_snapshot(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(name="description", data_type="TEXT", semantic_type="free_text"),
        ],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4())

    assert not [o for o in outcomes if o.column == "description"]


def test_evaluate_contract_runs_dataset_level_freshness_sla_on_timestamp_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    source_registry.register_source(
        FakeAdapter("orders", {"created_at": "TIMESTAMP"}, [(now - timedelta(hours=6),)])
    )
    captured = _capture_incidents(monkeypatch)
    _no_snapshot(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[ColumnRule(name="created_at", data_type="TIMESTAMP", semantic_type="timestamp")],
        freshness_sla_seconds=3600,
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4())

    freshness_outcomes = [o for o in outcomes if o.check_type == "freshness_sla"]
    assert freshness_outcomes[0].status == "failed"
    assert any(c["check_type"] == "freshness_sla" for c in captured)


def _no_checkpoint(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    saved: dict[str, object] = {}
    monkeypatch.setattr("pactum.monitoring.runner.load_checkpoint", lambda dataset_id: None)
    monkeypatch.setattr(
        "pactum.monitoring.runner.save_checkpoint",
        lambda dataset_id, checked_through: saved.update(
            dataset_id=dataset_id, checked_through=checked_through
        ),
    )
    return saved


def test_incremental_defaults_to_off_and_checks_the_full_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry.register_source(FakeAdapter("orders", {"order_id": "TEXT"}, [("o1",), ("o1",)]))
    monkeypatch.setattr(
        "pactum.monitoring.runner.load_checkpoint",
        lambda dataset_id: (_ for _ in ()).throw(
            AssertionError("should not touch the checkpoint store when incremental=False")
        ),
    )
    captured = _capture_incidents(monkeypatch)
    _no_snapshot(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(name="order_id", data_type="TEXT", semantic_type="identifier", unique=True)
        ],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4())

    uniqueness_outcomes = [o for o in outcomes if o.check_type == "uniqueness"]
    assert uniqueness_outcomes[0].status == "failed"
    assert any(c["check_type"] == "uniqueness" for c in captured)


def test_incremental_first_run_checks_everything_and_saves_a_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry.register_source(
        FakeAdapter(
            "orders",
            {"order_id": "TEXT", "created_at": "TIMESTAMP"},
            [("o1", datetime(2026, 1, 1, tzinfo=UTC)), ("o1", datetime(2026, 1, 2, tzinfo=UTC))],
        )
    )
    saved = _no_checkpoint(monkeypatch)
    captured = _capture_incidents(monkeypatch)
    _no_snapshot(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(name="order_id", data_type="TEXT", semantic_type="identifier", unique=True),
            ColumnRule(name="created_at", data_type="TIMESTAMP", semantic_type="timestamp"),
        ],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4(), incremental=True)

    uniqueness_outcomes = [o for o in outcomes if o.check_type == "uniqueness"]
    assert uniqueness_outcomes[0].status == "failed"
    assert any(c["check_type"] == "uniqueness" for c in captured)
    assert saved["dataset_id"] == "orders"


def test_incremental_second_run_only_checks_rows_after_the_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = datetime(2026, 1, 2, tzinfo=UTC)
    source_registry.register_source(
        FakeAdapter(
            "orders",
            {"order_id": "TEXT", "created_at": "TIMESTAMP"},
            [
                # Before the checkpoint: a duplicate that should NOT be seen.
                ("dup", datetime(2026, 1, 1, tzinfo=UTC)),
                ("dup", datetime(2026, 1, 1, 12, 0, tzinfo=UTC)),
                # After the checkpoint: distinct, should pass uniqueness.
                ("new1", datetime(2026, 1, 3, tzinfo=UTC)),
                ("new2", datetime(2026, 1, 4, tzinfo=UTC)),
            ],
        )
    )
    monkeypatch.setattr("pactum.monitoring.runner.load_checkpoint", lambda dataset_id: checkpoint)
    monkeypatch.setattr(
        "pactum.monitoring.runner.save_checkpoint", lambda dataset_id, checked_through: None
    )
    _no_incident(monkeypatch)
    _no_snapshot(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(name="order_id", data_type="TEXT", semantic_type="identifier", unique=True),
            ColumnRule(name="created_at", data_type="TIMESTAMP", semantic_type="timestamp"),
        ],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4(), incremental=True)

    uniqueness_outcomes = [o for o in outcomes if o.check_type == "uniqueness"]
    assert uniqueness_outcomes[0].status == "passed"


def test_incremental_skips_cleanly_when_no_new_rows_since_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry.register_source(
        FakeAdapter("orders", {"order_id": "TEXT", "created_at": "TIMESTAMP"}, [])
    )
    monkeypatch.setattr(
        "pactum.monitoring.runner.load_checkpoint",
        lambda dataset_id: datetime(2026, 1, 1, tzinfo=UTC),
    )
    monkeypatch.setattr(
        "pactum.monitoring.runner.save_checkpoint", lambda dataset_id, checked_through: None
    )
    _no_incident(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(name="order_id", data_type="TEXT", semantic_type="identifier", unique=True),
            ColumnRule(name="created_at", data_type="TIMESTAMP", semantic_type="timestamp"),
        ],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4(), incremental=True)

    assert len(outcomes) == 1
    assert outcomes[0].status == "skipped"
    assert outcomes[0].check_type == "incremental_check"


def test_incremental_falls_back_to_full_sample_without_a_timestamp_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry.register_source(FakeAdapter("orders", {"order_id": "TEXT"}, [("o1",), ("o1",)]))
    monkeypatch.setattr(
        "pactum.monitoring.runner.load_checkpoint",
        lambda dataset_id: (_ for _ in ()).throw(
            AssertionError("no timestamp column -- should never consult the checkpoint store")
        ),
    )
    captured = _capture_incidents(monkeypatch)
    _no_snapshot(monkeypatch)

    contract = ParsedContract(
        dataset_id="orders",
        columns=[
            ColumnRule(name="order_id", data_type="TEXT", semantic_type="identifier", unique=True)
        ],
    )
    outcomes = evaluate_contract("orders", contract, uuid.uuid4(), incremental=True)

    uniqueness_outcomes = [o for o in outcomes if o.check_type == "uniqueness"]
    assert uniqueness_outcomes[0].status == "failed"
    assert any(c["check_type"] == "uniqueness" for c in captured)
