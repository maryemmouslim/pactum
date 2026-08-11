from typing import cast

import lancedb
from sentence_transformers import SentenceTransformer

from pactum.models import Explanation, Incident
from pactum.settings import settings

_TABLE_NAME = "incidents"
_MODEL_NAME = "all-MiniLM-L6-v2"

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Lazily load the embedding model once per process, not once per call."""
    global _model
    if _model is None:
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def _embed(text: str) -> list[float]:
    return cast(list[float], _get_model().encode(text).tolist())


def _build_text(incident: Incident, hypothesis_descriptions: list[str]) -> str:
    parts = [
        incident.check_type,
        incident.column_name or "",
        str(incident.payload),
        *hypothesis_descriptions,
    ]
    return " | ".join(part for part in parts if part)


def _get_table() -> lancedb.table.Table:
    db = lancedb.connect(settings.lancedb_path)
    if _TABLE_NAME in db.list_tables().tables:
        return db.open_table(_TABLE_NAME)

    dim = len(_embed("bootstrap"))
    schema = {
        "id": "",
        "dataset_id": "",
        "check_type": "",
        "text": "",
        "vector": [0.0] * dim,
    }
    table = db.create_table(_TABLE_NAME, data=[schema])
    table.delete("id = ''")
    return table


def index_incident(incident: Incident, explanation: Explanation) -> None:
    """Embed this incident (with its explanation's hypotheses) and upsert it into the index.

    Called once per investigated incident, right after its Explanation is
    persisted -- see pactum/agents/causal_explainer.py's persist_explanation.
    """
    text = _build_text(incident, [h.description for h in explanation.hypotheses])
    row = {
        "id": str(incident.id),
        "dataset_id": incident.dataset_id,
        "check_type": incident.check_type,
        "text": text,
        "vector": _embed(text),
    }
    table = _get_table()
    table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute([row])


def find_similar(incident: Incident, k: int = 5) -> list[dict[str, object]]:
    """Return the k most similar previously-indexed incidents, excluding this one.

    Queries with just the incident's own facts (no explanation yet, since
    it's mid-investigation) against every previously indexed incident's
    embedding (which does include its resolution's hypotheses).
    """
    text = _build_text(incident, [])
    table = _get_table()
    results = cast(list[dict[str, object]], table.search(_embed(text)).limit(k + 1).to_list())
    return [row for row in results if row["id"] != str(incident.id)][:k]
