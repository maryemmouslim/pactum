import uuid
from datetime import UTC, datetime

import pytest

from pactum.models import Explanation, Hypothesis, Incident
from pactum.monitoring.incident_index import find_similar, index_incident


class FakeMergeInsertBuilder:
    def __init__(self, table: "FakeTable") -> None:
        self._table = table

    def when_matched_update_all(self) -> "FakeMergeInsertBuilder":
        return self

    def when_not_matched_insert_all(self) -> "FakeMergeInsertBuilder":
        return self

    def execute(self, rows: list[dict[str, object]]) -> None:
        for row in rows:
            self._table.rows = [r for r in self._table.rows if r["id"] != row["id"]]
            self._table.rows.append(row)


class FakeSearch:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def limit(self, k: int) -> "FakeSearch":
        self._rows = self._rows[:k]
        return self

    def to_list(self) -> list[dict[str, object]]:
        return [{**row, "_distance": 0.1} for row in self._rows]


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def merge_insert(self, on: str) -> FakeMergeInsertBuilder:
        return FakeMergeInsertBuilder(self)

    def search(self, vector: list[float]) -> FakeSearch:
        return FakeSearch(list(self.rows))


def _make_incident(**overrides: object) -> Incident:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "dataset_id": "orders",
        "detected_at": datetime.now(UTC),
        "kind": "violation",
        "severity": "high",
        "signature": "abc123",
        "payload": {"score": 0.5},
        "contract_version_id": uuid.uuid4(),
        "check_type": "psi",
        "column_name": "amount",
    }
    defaults.update(overrides)
    return Incident(**defaults)  # type: ignore[arg-type]


def _make_explanation(incident_id: uuid.UUID, descriptions: list[str]) -> Explanation:
    return Explanation(
        id=uuid.uuid4(),
        incident_id=incident_id,
        hypotheses=[Hypothesis(description=d, confidence=0.7) for d in descriptions],
        reasoning_trace=[],
        created_at=datetime.now(UTC),
    )


def test_index_incident_inserts_a_row_with_an_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_table = FakeTable()
    monkeypatch.setattr("pactum.monitoring.incident_index._get_table", lambda: fake_table)
    monkeypatch.setattr(
        "pactum.monitoring.incident_index._embed", lambda text: [len(text) * 1.0, 0.0]
    )

    incident = _make_incident()
    explanation = _make_explanation(incident.id, ["a schema drift caused this"])

    index_incident(incident, explanation)

    assert len(fake_table.rows) == 1
    row = fake_table.rows[0]
    assert row["id"] == str(incident.id)
    assert row["dataset_id"] == "orders"
    assert "a schema drift caused this" in row["text"]  # type: ignore[operator]


def test_index_incident_upserts_by_id_instead_of_duplicating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_table = FakeTable()
    monkeypatch.setattr("pactum.monitoring.incident_index._get_table", lambda: fake_table)
    monkeypatch.setattr("pactum.monitoring.incident_index._embed", lambda text: [0.0])

    incident = _make_incident()
    index_incident(incident, _make_explanation(incident.id, ["first"]))
    index_incident(incident, _make_explanation(incident.id, ["second, updated"]))

    assert len(fake_table.rows) == 1
    assert "second, updated" in fake_table.rows[0]["text"]  # type: ignore[operator]


def test_find_similar_excludes_the_queried_incident_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident = _make_incident()
    other = _make_incident()
    fake_table = FakeTable()
    fake_table.rows = [
        {"id": str(incident.id), "dataset_id": "orders", "check_type": "psi", "text": "x"},
        {"id": str(other.id), "dataset_id": "orders", "check_type": "psi", "text": "y"},
    ]
    monkeypatch.setattr("pactum.monitoring.incident_index._get_table", lambda: fake_table)
    monkeypatch.setattr("pactum.monitoring.incident_index._embed", lambda text: [0.0])

    results = find_similar(incident)

    assert len(results) == 1
    assert results[0]["id"] == str(other.id)
    assert "_distance" in results[0]


def test_find_similar_respects_k(monkeypatch: pytest.MonkeyPatch) -> None:
    incident = _make_incident()
    others = [_make_incident() for _ in range(10)]
    fake_table = FakeTable()
    fake_table.rows = [
        {"id": str(incident.id), "dataset_id": "orders", "check_type": "psi", "text": "x"},
        *(
            {"id": str(o.id), "dataset_id": "orders", "check_type": "psi", "text": "y"}
            for o in others
        ),
    ]
    monkeypatch.setattr("pactum.monitoring.incident_index._get_table", lambda: fake_table)
    monkeypatch.setattr("pactum.monitoring.incident_index._embed", lambda text: [0.0])

    results = find_similar(incident, k=3)

    assert len(results) == 3
