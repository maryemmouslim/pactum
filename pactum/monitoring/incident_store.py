import hashlib
import uuid
from datetime import UTC, datetime
from typing import Literal

import psycopg
import psycopg.types.json

from pactum.models import Incident
from pactum.settings import settings


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


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
                   contract_version
            FROM incidents
            WHERE signature = %(signature)s
            ORDER BY detected_at DESC
            LIMIT 1
            """,
            {"signature": signature},
        ).fetchone()
        return _row_to_incident(row) if row else None


def emit_incident(
    dataset_id: str,
    kind: Literal["drift", "violation"],
    severity: Literal["low", "medium", "high"],
    check_type: str,
    payload: dict[str, object],
    contract_version: str,
    column: str | None = None,
) -> Incident:
    """Emit an incident, atomically reusing an existing one with the same signature.

    Uses INSERT ... ON CONFLICT DO NOTHING instead of a separate check-then-insert
    (find_open_incident followed by a plain INSERT), so two simultaneous detections
    of the same problem can never both insert -- the database's unique constraint
    on `signature` is what actually enforces this, not application-level timing.
    """
    signature = build_signature(dataset_id, check_type, column)

    incident = Incident(
        id=uuid.uuid4(),
        dataset_id=dataset_id,
        detected_at=datetime.now(UTC),
        kind=kind,
        severity=severity,
        signature=signature,
        payload=payload,
        contract_version=contract_version,
    )

    params = incident.model_dump()
    params["payload"] = psycopg.types.json.Json(incident.payload)

    with _connect() as conn:
        row = conn.execute(
            """
            INSERT INTO incidents
                (id, dataset_id, detected_at, kind, severity, signature, payload,
                 contract_version)
            VALUES
                (%(id)s, %(dataset_id)s, %(detected_at)s, %(kind)s, %(severity)s,
                 %(signature)s, %(payload)s, %(contract_version)s)
            ON CONFLICT (signature) DO NOTHING
            RETURNING id, dataset_id, detected_at, kind, severity, signature, payload,
                      contract_version
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
        "contract_version",
    ]
    return Incident.model_validate(dict(zip(columns, row, strict=True)))
