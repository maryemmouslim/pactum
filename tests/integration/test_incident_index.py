import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pactum.models import Explanation, Hypothesis, Incident
from pactum.monitoring.incident_index import find_similar, index_incident
from pactum.settings import settings


def _make_incident(check_type: str, column_name: str, payload: dict[str, object]) -> Incident:
    return Incident(
        id=uuid.uuid4(),
        dataset_id="orders",
        detected_at=datetime.now(UTC),
        kind="violation",
        severity="high",
        signature=str(uuid.uuid4()),
        payload=payload,
        contract_version_id=uuid.uuid4(),
        check_type=check_type,
        column_name=column_name,
    )


def _make_explanation(incident_id: uuid.UUID, description: str) -> Explanation:
    return Explanation(
        id=uuid.uuid4(),
        incident_id=incident_id,
        hypotheses=[Hypothesis(description=description, confidence=0.8)],
        reasoning_trace=[],
        created_at=datetime.now(UTC),
    )


@pytest.fixture(autouse=True)
def _isolated_lancedb_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Real embedding model + real local LanceDB directory -- this is the one
    # test in the suite that needs network on first run (to download the
    # model) and real, if lightweight, I/O. Isolated in tmp_path so it never
    # touches the developer's real .lancedb/ or leaves state behind.
    monkeypatch.setattr(settings, "lancedb_path", str(tmp_path / "lancedb"))
    yield
    shutil.rmtree(tmp_path / "lancedb", ignore_errors=True)


def test_find_similar_ranks_semantically_related_incidents_above_unrelated_ones() -> None:
    freshness_a = _make_incident(
        "freshness_sla", "created_at", {"message": "data is stale, pipeline delayed"}
    )
    index_incident(freshness_a, _make_explanation(freshness_a.id, "ingestion pipeline was delayed"))

    freshness_b = _make_incident(
        "freshness_sla", "created_at", {"message": "data is stale again, pipeline delayed"}
    )
    index_incident(
        freshness_b, _make_explanation(freshness_b.id, "ingestion pipeline was delayed again")
    )

    unrelated = _make_incident("uniqueness", "order_id", {"duplicate_values": ["a", "b"]})
    index_incident(unrelated, _make_explanation(unrelated.id, "upstream dedup bug"))

    query = _make_incident(
        "freshness_sla", "created_at", {"message": "stale data, delayed ingestion"}
    )
    matches = find_similar(query, k=2)

    matched_ids = {m["id"] for m in matches}
    assert matched_ids == {str(freshness_a.id), str(freshness_b.id)}
    assert str(unrelated.id) not in matched_ids


def test_index_incident_upsert_replaces_the_previous_embedding_for_the_same_id() -> None:
    incident = _make_incident("psi", "amount", {"score": 0.5})
    index_incident(incident, _make_explanation(incident.id, "first pass"))
    index_incident(incident, _make_explanation(incident.id, "revised explanation"))

    other = _make_incident("psi", "amount", {"score": 0.6})
    matches = find_similar(other, k=5)

    # the same incident id should appear at most once, not duplicated by the second index call
    assert sum(1 for m in matches if m["id"] == str(incident.id)) <= 1
