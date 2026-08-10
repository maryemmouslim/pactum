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
                (id, incident_id, contract_id, kind, proposed_yaml, status, created_at)
            VALUES
                (%(id)s, %(incident_id)s, %(contract_id)s, %(kind)s, %(proposed_yaml)s,
                 %(status)s, %(created_at)s)
            """,
            proposal.model_dump(),
        )
    return proposal


def get_refinements_for_incident(incident_id: UUID) -> list[RefinementProposal]:
    """Return persisted refinement proposals for one incident."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, incident_id, contract_id, kind, proposed_yaml, status, created_at
            FROM refinements
            WHERE incident_id = %(incident_id)s
            ORDER BY created_at DESC
            """,
            {"incident_id": incident_id},
        ).fetchall()
    return [_row_to_refinement(row) for row in rows]


def _row_to_refinement(row: tuple[object, ...]) -> RefinementProposal:
    columns = ["id", "incident_id", "contract_id", "kind", "proposed_yaml", "status", "created_at"]
    return RefinementProposal.model_validate(dict(zip(columns, row, strict=True)))
