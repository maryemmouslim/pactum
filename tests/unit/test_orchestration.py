from datetime import UTC, datetime, timedelta

import pytest
from dagster import materialize

from pactum.agents.contract_generator import CritiqueResult
from pactum.lineage.graph import LineageGraph
from pactum.orchestration.definitions import (
    _evaluate_completeness,
    _evaluate_enum,
    _evaluate_freshness_sla,
    _evaluate_range,
    _evaluate_referential_integrity,
    _evaluate_regex,
    _evaluate_schema_adherence,
    _evaluate_uniqueness,
    completeness_check,
    contract,
    enum_check,
    freshness_sla_check,
    range_check,
    referential_integrity_check,
    regex_check,
    schema_adherence_check,
    source_data,
    uniqueness_check,
)
from pactum.sources import registry as source_registry
from pactum.tools.classify_semantics import SemanticClassification


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


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeDraftLLM:
    def __init__(self, content: str) -> None:
        self._content = content

    def invoke(self, prompt: str) -> FakeMessage:
        return FakeMessage(self._content)


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    source_registry._adapters.clear()


def _no_incident(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pactum.orchestration.definitions.emit_incident",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not emit an incident")),
    )


def _capture_incidents(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    captured: list[dict[str, object]] = []
    monkeypatch.setattr(
        "pactum.orchestration.definitions.emit_incident",
        lambda **kwargs: captured.append(kwargs),
    )
    return captured


def test_evaluate_schema_adherence_passes_when_schema_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry.register_source(FakeAdapter("orders", {"order_id": "TEXT"}))
    _no_incident(monkeypatch)

    result = _evaluate_schema_adherence({"columns": {"order_id": "TEXT"}, "version": 1})

    assert result.passed is True


def test_evaluate_schema_adherence_fails_and_emits_incident_when_schema_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Live schema is now missing the "amount" column the contract was built with --
    # a genuine break (unlike an *extra* column, which check_schema tolerates).
    source_registry.register_source(FakeAdapter("orders", {"order_id": "TEXT"}))
    captured = _capture_incidents(monkeypatch)

    result = _evaluate_schema_adherence(
        {"columns": {"order_id": "TEXT", "amount": "DOUBLE"}, "version": 1}
    )

    assert result.passed is False
    assert len(captured) == 1
    assert captured[0]["check_type"] == "schema"


def test_evaluate_uniqueness_passes_for_distinct_order_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry.register_source(FakeAdapter("orders", {"order_id": "TEXT"}, [("o1",), ("o2",)]))
    _no_incident(monkeypatch)

    result = _evaluate_uniqueness({"version": 1})

    assert result.passed is True


def test_evaluate_uniqueness_fails_for_duplicate_order_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry.register_source(FakeAdapter("orders", {"order_id": "TEXT"}, [("o1",), ("o1",)]))
    captured = _capture_incidents(monkeypatch)

    result = _evaluate_uniqueness({"version": 1})

    assert result.passed is False
    assert captured[0]["check_type"] == "uniqueness"


def test_evaluate_completeness_passes_when_mostly_filled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows: list[tuple[object, ...]] = [(10.0,)] * 99 + [(None,)]
    source_registry.register_source(FakeAdapter("orders", {"amount": "DOUBLE"}, rows))
    _no_incident(monkeypatch)

    result = _evaluate_completeness({"version": 1})

    assert result.passed is True


def test_evaluate_completeness_fails_when_too_many_nulls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows: list[tuple[object, ...]] = [(10.0,)] * 50 + [(None,)] * 50
    source_registry.register_source(FakeAdapter("orders", {"amount": "DOUBLE"}, rows))
    captured = _capture_incidents(monkeypatch)

    result = _evaluate_completeness({"version": 1})

    assert result.passed is False
    assert captured[0]["check_type"] == "completeness_sla"


def test_evaluate_range_passes_for_non_negative_amounts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry.register_source(FakeAdapter("orders", {"amount": "DOUBLE"}, [(10.0,), (20.0,)]))
    _no_incident(monkeypatch)

    result = _evaluate_range({"version": 1})

    assert result.passed is True


def test_evaluate_range_fails_for_negative_amount(monkeypatch: pytest.MonkeyPatch) -> None:
    source_registry.register_source(FakeAdapter("orders", {"amount": "DOUBLE"}, [(10.0,), (-5.0,)]))
    captured = _capture_incidents(monkeypatch)

    result = _evaluate_range({"version": 1})

    assert result.passed is False
    assert captured[0]["check_type"] == "range"


def test_evaluate_enum_passes_for_known_status(monkeypatch: pytest.MonkeyPatch) -> None:
    source_registry.register_source(
        FakeAdapter("orders", {"status": "TEXT"}, [("pending",), ("shipped",)])
    )
    _no_incident(monkeypatch)

    result = _evaluate_enum({"version": 1})

    assert result.passed is True


def test_evaluate_enum_fails_for_unknown_status(monkeypatch: pytest.MonkeyPatch) -> None:
    source_registry.register_source(
        FakeAdapter("orders", {"status": "TEXT"}, [("pending",), ("refunded",)])
    )
    captured = _capture_incidents(monkeypatch)

    result = _evaluate_enum({"version": 1})

    assert result.passed is False
    assert captured[0]["check_type"] == "enum"


def test_evaluate_regex_passes_for_valid_emails(monkeypatch: pytest.MonkeyPatch) -> None:
    source_registry.register_source(
        FakeAdapter("orders", {"email": "TEXT"}, [("a@example.com",), ("b@example.com",)])
    )
    _no_incident(monkeypatch)

    result = _evaluate_regex({"version": 1})

    assert result.passed is True


def test_evaluate_regex_fails_for_invalid_email(monkeypatch: pytest.MonkeyPatch) -> None:
    source_registry.register_source(
        FakeAdapter("orders", {"email": "TEXT"}, [("a@example.com",), ("not-an-email",)])
    )
    captured = _capture_incidents(monkeypatch)

    result = _evaluate_regex({"version": 1})

    assert result.passed is False
    assert captured[0]["check_type"] == "regex"


def test_evaluate_freshness_sla_passes_for_recent_data(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC)
    source_registry.register_source(
        FakeAdapter("orders", {"created_at": "TIMESTAMP"}, [(now - timedelta(minutes=10),)])
    )
    _no_incident(monkeypatch)

    result = _evaluate_freshness_sla({"version": 1})

    assert result.passed is True


def test_evaluate_freshness_sla_fails_for_stale_data(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC)
    source_registry.register_source(
        FakeAdapter("orders", {"created_at": "TIMESTAMP"}, [(now - timedelta(hours=6),)])
    )
    captured = _capture_incidents(monkeypatch)

    result = _evaluate_freshness_sla({"version": 1})

    assert result.passed is False
    assert captured[0]["check_type"] == "freshness_sla"


def test_evaluate_referential_integrity_passes_for_known_customer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry.register_source(
        FakeAdapter("orders", {"customer_id": "TEXT"}, [("c1",), ("c2",)])
    )
    source_registry.register_source(FakeAdapter("customers", {"id": "TEXT"}, [("c1",), ("c2",)]))
    _no_incident(monkeypatch)

    result = _evaluate_referential_integrity({"version": 1})

    assert result.passed is True


def test_evaluate_referential_integrity_fails_for_unknown_customer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_registry.register_source(
        FakeAdapter("orders", {"customer_id": "TEXT"}, [("c1",), ("c999",)])
    )
    source_registry.register_source(FakeAdapter("customers", {"id": "TEXT"}, [("c1",)]))
    captured = _capture_incidents(monkeypatch)

    result = _evaluate_referential_integrity({"version": 1})

    assert result.passed is False
    assert captured[0]["check_type"] == "referential_integrity"


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

    monkeypatch.setattr("pactum.tools.understand_source.load_graph", lambda: LineageGraph())
    monkeypatch.setattr(
        "pactum.tools.classify_semantics.get_llm",
        lambda role="fast": FakeLLM(SemanticClassification(label="identifier", confidence=0.9)),
    )
    monkeypatch.setattr("pactum.agents.contract_generator.list_history", lambda dataset_id: [])
    monkeypatch.setattr("pactum.agents.contract_generator.create_version", lambda contract: None)

    draft_then_critique_llms = iter(
        [
            FakeDraftLLM("apiVersion: v3\nkind: DataContract"),
            FakeLLM(CritiqueResult(approved=True, feedback="")),
        ]
    )
    monkeypatch.setattr(
        "pactum.agents.contract_generator.get_llm",
        lambda role="reasoning": next(draft_then_critique_llms),
    )

    result = materialize(
        [
            source_data,
            contract,
            schema_adherence_check,
            uniqueness_check,
            completeness_check,
            range_check,
            enum_check,
            regex_check,
            freshness_sla_check,
            referential_integrity_check,
        ]
    )

    assert result.success
    check_evaluations = result.get_asset_check_evaluations()
    assert len(check_evaluations) == 8
    assert all(evaluation.passed for evaluation in check_evaluations)
