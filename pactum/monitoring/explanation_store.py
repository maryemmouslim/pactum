import math
from uuid import UUID

import psycopg
import psycopg.types.json

from pactum.models import Explanation
from pactum.settings import settings


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


def _json_safe(value: object) -> object:
    """Recursively replace non-finite floats (inf, -inf, nan) with JSON-safe strings.

    Same problem incident_store._json_safe solves: a reasoning trace can
    embed a drift detector's DriftResult, whose PSI details legitimately
    contain +-inf bin edges, and Postgres's json/jsonb column rejects those.
    """
    if isinstance(value, float):
        return str(value) if math.isinf(value) or math.isnan(value) else value
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def save_explanation(explanation: Explanation) -> Explanation:
    """Persist a causal explanation to Postgres for later review."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO explanations (id, incident_id, hypotheses, reasoning_trace, created_at)
            VALUES (%(id)s, %(incident_id)s, %(hypotheses)s, %(reasoning_trace)s, %(created_at)s)
            """,
            {
                "id": explanation.id,
                "incident_id": explanation.incident_id,
                "hypotheses": psycopg.types.json.Json(
                    _json_safe([h.model_dump(mode="json") for h in explanation.hypotheses])
                ),
                "reasoning_trace": psycopg.types.json.Json(_json_safe(explanation.reasoning_trace)),
                "created_at": explanation.created_at,
            },
        )
    return explanation


def get_explanations_for_incident(incident_id: UUID) -> list[Explanation]:
    """Return persisted explanations for one incident."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, incident_id, hypotheses, reasoning_trace, created_at
            FROM explanations
            WHERE incident_id = %(incident_id)s
            ORDER BY created_at DESC
            """,
            {"incident_id": incident_id},
        ).fetchall()
    return [_row_to_explanation(row) for row in rows]


def list_explanations_for_dataset(dataset_id: str, *, limit: int = 20) -> list[Explanation]:
    """Return the most recent explanations for any incident on this dataset.

    Joins against incidents (explanations don't carry dataset_id themselves)
    -- used by the UI's "investigated incidents" viewer.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT e.id, e.incident_id, e.hypotheses, e.reasoning_trace, e.created_at
            FROM explanations e
            JOIN incidents i ON i.id = e.incident_id
            WHERE i.dataset_id = %(dataset_id)s
            ORDER BY e.created_at DESC
            LIMIT %(limit)s
            """,
            {"dataset_id": dataset_id, "limit": limit},
        ).fetchall()
    return [_row_to_explanation(row) for row in rows]


def _row_to_explanation(row: tuple[object, ...]) -> Explanation:
    columns = ["id", "incident_id", "hypotheses", "reasoning_trace", "created_at"]
    return Explanation.model_validate(dict(zip(columns, row, strict=True)))
