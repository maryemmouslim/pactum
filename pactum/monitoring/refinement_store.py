from typing import Literal
from uuid import UUID

import psycopg

from pactum.models import RefinementProposal
from pactum.settings import settings


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


def save_refinement_proposal(proposal: RefinementProposal) -> RefinementProposal:
    """Persist a contract refinement proposal to Postgres for later review."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO refinements
                (id, incident_id, contract_id, kind, proposed_yaml, status, reason, created_at)
            VALUES
                (%(id)s, %(incident_id)s, %(contract_id)s, %(kind)s, %(proposed_yaml)s,
                 %(status)s, %(reason)s, %(created_at)s)
            """,
            proposal.model_dump(),
        )
    return proposal


def get_refinements_for_incident(incident_id: UUID) -> list[RefinementProposal]:
    """Return persisted refinement proposals for one incident."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, incident_id, contract_id, kind, proposed_yaml, status, reason, created_at
            FROM refinements
            WHERE incident_id = %(incident_id)s
            ORDER BY created_at DESC
            """,
            {"incident_id": incident_id},
        ).fetchall()
    return [_row_to_refinement(row) for row in rows]


def list_pending_refinements() -> list[RefinementProposal]:
    """Return every refinement proposal still awaiting review, oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, incident_id, contract_id, kind, proposed_yaml, status, reason, created_at
            FROM refinements
            WHERE status = 'pending'
            ORDER BY created_at ASC
            """
        ).fetchall()
    return [_row_to_refinement(row) for row in rows]


def list_pending_refinements_for_dataset(dataset_id: str) -> list[RefinementProposal]:
    """Return pending refinement proposals for one dataset's incidents, oldest first.

    Joins against incidents (refinements don't carry dataset_id themselves)
    -- used by the UI's per-dataset review section and its signal badge.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.incident_id, r.contract_id, r.kind, r.proposed_yaml, r.status,
                   r.reason, r.created_at
            FROM refinements r
            JOIN incidents i ON i.id = r.incident_id
            WHERE i.dataset_id = %(dataset_id)s AND r.status = 'pending'
            ORDER BY r.created_at ASC
            """,
            {"dataset_id": dataset_id},
        ).fetchall()
    return [_row_to_refinement(row) for row in rows]


def update_refinement_status(
    refinement_id: UUID,
    status: Literal["accepted", "rejected"],
    reason: str | None = None,
) -> RefinementProposal:
    """Transition a pending proposal to accepted or rejected, recording an optional reason."""
    with _connect() as conn:
        row = conn.execute(
            """
            UPDATE refinements
            SET status = %(status)s, reason = %(reason)s
            WHERE id = %(id)s
            RETURNING id, incident_id, contract_id, kind, proposed_yaml, status, reason, created_at
            """,
            {"id": refinement_id, "status": status, "reason": reason},
        ).fetchone()
    if row is None:
        raise ValueError(f"No refinement proposal found with id {refinement_id!r}")
    return _row_to_refinement(row)


def _row_to_refinement(row: tuple[object, ...]) -> RefinementProposal:
    columns = [
        "id",
        "incident_id",
        "contract_id",
        "kind",
        "proposed_yaml",
        "status",
        "reason",
        "created_at",
    ]
    return RefinementProposal.model_validate(dict(zip(columns, row, strict=True)))
