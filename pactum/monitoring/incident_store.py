import hashlib
import math
import uuid
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

import psycopg
import psycopg.types.json

from pactum.models import Incident
from pactum.settings import settings


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


def _json_safe(value: object) -> object:
    """Recursively replace non-finite floats (inf, -inf, nan) with JSON-safe strings.

    Standard JSON has no representation for these. Python's json.dumps emits
    them anyway as a non-standard extension, but Postgres's json/jsonb column
    type rejects them outright -- e.g. PSI's bin_edges legitimately contains
    +-inf for its outermost bins, so any payload could contain one of these.
    """
    if isinstance(value, float):
        return str(value) if math.isinf(value) or math.isnan(value) else value
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def build_signature(dataset_id: str, check_type: str, column: str | None = None) -> str:
    """Build a stable signature so repeat occurrences of the same problem cluster together.

    Deliberately excludes anything that changes run-to-run (timestamps, scores,
    offending values) -- only the identifying facts about *what* is broken.
    """
    raw = f"{dataset_id}:{check_type}:{column or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def find_open_incident(signature: str) -> Incident | None:
    """Return the most recent incident with this signature, if one exists."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, dataset_id, detected_at, kind, severity, signature, payload,
                   contract_version_id, check_type, column_name
            FROM incidents
            WHERE signature = %(signature)s
            ORDER BY detected_at DESC
            LIMIT 1
            """,
            {"signature": signature},
        ).fetchone()
        return _row_to_incident(row) if row else None


def get_incident(incident_id: UUID) -> Incident | None:
    """Return a single incident by id, if it exists."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, dataset_id, detected_at, kind, severity, signature, payload,
                   contract_version_id, check_type, column_name
            FROM incidents
            WHERE id = %(id)s
            """,
            {"id": incident_id},
        ).fetchone()
        return _row_to_incident(row) if row else None


def find_related_incidents(
    dataset_id: str, check_type: str, exclude_id: UUID, *, limit: int = 5
) -> list[Incident]:
    """Return past incidents with the same (dataset_id, check_type), most recent first.

    Used by the causal explanation agent to find precedent -- has this exact
    kind of problem happened before on this dataset. Deliberately not
    embedding-based retrieval (no vector store in this project yet); an exact
    (dataset_id, check_type) match is a reasonable first cut.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, dataset_id, detected_at, kind, severity, signature, payload,
                   contract_version_id, check_type, column_name
            FROM incidents
            WHERE dataset_id = %(dataset_id)s AND check_type = %(check_type)s
              AND id != %(exclude_id)s
            ORDER BY detected_at DESC
            LIMIT %(limit)s
            """,
            {
                "dataset_id": dataset_id,
                "check_type": check_type,
                "exclude_id": exclude_id,
                "limit": limit,
            },
        ).fetchall()
        return [_row_to_incident(row) for row in rows]


def list_incidents_for_dataset(dataset_id: str, *, limit: int = 20) -> list[Incident]:
    """Return the most recent incidents for one dataset, newest first.

    Used by the UI's per-dataset view (and its "needs attention" signal
    badge) -- unlike list_incidents_since, which is global and cursor-based
    for the sensor's polling loop.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, dataset_id, detected_at, kind, severity, signature, payload,
                   contract_version_id, check_type, column_name
            FROM incidents
            WHERE dataset_id = %(dataset_id)s
            ORDER BY detected_at DESC
            LIMIT %(limit)s
            """,
            {"dataset_id": dataset_id, "limit": limit},
        ).fetchall()
    return [_row_to_incident(row) for row in rows]


def list_incidents_since(since: datetime | None, *, limit: int = 50) -> list[Incident]:
    """Return incidents detected after `since`, oldest first (for cursor-based polling).

    Used by the causal explainer's Dagster sensor to pick up new incidents
    without reprocessing ones it's already seen. `since=None` returns the
    most recent incidents overall (used only for one-off inspection, not by
    the sensor itself -- it always has a cursor after its first tick).
    """
    with _connect() as conn:
        if since is None:
            rows = conn.execute(
                """
                SELECT id, dataset_id, detected_at, kind, severity, signature, payload,
                       contract_version_id, check_type, column_name
                FROM incidents
                ORDER BY detected_at ASC
                LIMIT %(limit)s
                """,
                {"limit": limit},
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, dataset_id, detected_at, kind, severity, signature, payload,
                       contract_version_id, check_type, column_name
                FROM incidents
                WHERE detected_at > %(since)s
                ORDER BY detected_at ASC
                LIMIT %(limit)s
                """,
                {"since": since, "limit": limit},
            ).fetchall()
        return [_row_to_incident(row) for row in rows]


def emit_incident(
    dataset_id: str,
    kind: Literal["drift", "violation"],
    severity: Literal["low", "medium", "high"],
    check_type: str,
    payload: dict[str, object],
    contract_version_id: UUID,
    column: str | None = None,
) -> Incident:
    """Emit an incident, atomically reusing an existing one with the same signature.

    Uses INSERT ... ON CONFLICT DO NOTHING instead of a separate check-then-insert
    (find_open_incident followed by a plain INSERT), so two simultaneous detections
    of the same problem can never both insert -- the database's unique constraint
    on `signature` is what actually enforces this, not application-level timing.

    contract_version_id must reference a real row in `contracts` -- the
    database enforces this with a foreign key, so a dangling or made-up
    reference is rejected outright instead of silently accepted.
    """
    signature = build_signature(dataset_id, check_type, column)

    incident = Incident(
        id=uuid.uuid4(),
        dataset_id=dataset_id,
        detected_at=datetime.now(UTC),
        kind=kind,
        severity=severity,
        signature=signature,
        payload=cast(dict[str, object], _json_safe(payload)),
        contract_version_id=contract_version_id,
        check_type=check_type,
        column_name=column,
    )

    params = incident.model_dump()
    params["payload"] = psycopg.types.json.Json(incident.payload)

    with _connect() as conn:
        row = conn.execute(
            """
            INSERT INTO incidents
                (id, dataset_id, detected_at, kind, severity, signature, payload,
                 contract_version_id, check_type, column_name)
            VALUES
                (%(id)s, %(dataset_id)s, %(detected_at)s, %(kind)s, %(severity)s,
                 %(signature)s, %(payload)s, %(contract_version_id)s, %(check_type)s,
                 %(column_name)s)
            ON CONFLICT (signature) DO NOTHING
            RETURNING id, dataset_id, detected_at, kind, severity, signature, payload,
                      contract_version_id, check_type, column_name
            """,
            params,
        ).fetchone()

    if row is not None:
        return _row_to_incident(row)

    existing = find_open_incident(signature)
    if existing is None:
        raise RuntimeError(
            f"Insert conflicted on signature {signature!r} but no existing row was found"
        )
    return existing


def _row_to_incident(row: tuple[object, ...]) -> Incident:
    columns = [
        "id",
        "dataset_id",
        "detected_at",
        "kind",
        "severity",
        "signature",
        "payload",
        "contract_version_id",
        "check_type",
        "column_name",
    ]
    return Incident.model_validate(dict(zip(columns, row, strict=True)))
