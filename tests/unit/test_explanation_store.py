import uuid
from datetime import UTC, datetime

import pytest

from pactum.models import Explanation, Hypothesis
from pactum.monitoring.explanation_store import (
    get_explanations_for_incident,
    list_explanations_for_dataset,
    save_explanation,
)


class FakeConnection:
    def __init__(self, rows: list[tuple[object, ...]] | None = None) -> None:
        self.executed: list[tuple[str, dict[str, object]]] = []
        self._rows = rows or []

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def execute(self, sql: str, params: dict[str, object] | None = None) -> "FakeConnection":
        self.executed.append((sql, params or {}))
        return self

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


def _make_explanation(**overrides: object) -> Explanation:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "incident_id": uuid.uuid4(),
        "hypotheses": [Hypothesis(description="a cause", confidence=0.7)],
        "reasoning_trace": [{"tool": "schema_diff", "result": {"status": "ok"}}],
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return Explanation(**defaults)  # type: ignore[arg-type]


def _row_for(explanation: Explanation) -> tuple[object, ...]:
    return (
        explanation.id,
        explanation.incident_id,
        [h.model_dump(mode="json") for h in explanation.hypotheses],
        explanation.reasoning_trace,
        explanation.created_at,
    )


def test_save_explanation_wraps_json_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn = FakeConnection()
    monkeypatch.setattr("pactum.monitoring.explanation_store._connect", lambda: fake_conn)

    explanation = _make_explanation()
    result = save_explanation(explanation)

    assert result is explanation
    sql, params = fake_conn.executed[0]
    assert "INSERT INTO explanations" in sql
    assert params["id"] == explanation.id


def test_get_explanations_for_incident_returns_matching_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explanation = _make_explanation()
    fake_conn = FakeConnection(rows=[_row_for(explanation)])
    monkeypatch.setattr("pactum.monitoring.explanation_store._connect", lambda: fake_conn)

    results = get_explanations_for_incident(explanation.incident_id)

    assert results == [explanation]


def test_list_explanations_for_dataset_joins_against_incidents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explanation = _make_explanation()
    fake_conn = FakeConnection(rows=[_row_for(explanation)])
    monkeypatch.setattr("pactum.monitoring.explanation_store._connect", lambda: fake_conn)

    results = list_explanations_for_dataset("orders", limit=10)

    assert results == [explanation]
    sql, params = fake_conn.executed[0]
    assert "JOIN incidents" in sql
    assert params["dataset_id"] == "orders"
    assert params["limit"] == 10
