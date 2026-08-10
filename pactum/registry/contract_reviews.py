import uuid
from datetime import UTC, datetime
from typing import Literal

import psycopg

from pactum.models import ContractReview
from pactum.settings import settings


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


def record_review(
    contract_id: uuid.UUID,
    decision: Literal["approved", "rejected"],
    reviewed_by: str,
    reason: str | None = None,
) -> ContractReview:
    """Record a human's approve/reject decision on a contract draft.

    This is deliberately a separate append-only log from the contract's own
    `status` field: `status` drives which version is in force (draft/active/
    deprecated), while this answers "did a human look at this, when, and
    why" -- a rejected draft stays `status="draft"` forever (never promoted),
    but is now distinguishable from a draft nobody has reviewed at all.
    """
    review = ContractReview(
        id=uuid.uuid4(),
        contract_id=contract_id,
        decision=decision,
        reason=reason,
        reviewed_by=reviewed_by,
        reviewed_at=datetime.now(UTC),
    )
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO contract_reviews
                (id, contract_id, decision, reason, reviewed_by, reviewed_at)
            VALUES
                (%(id)s, %(contract_id)s, %(decision)s, %(reason)s,
                 %(reviewed_by)s, %(reviewed_at)s)
            """,
            review.model_dump(),
        )
    return review


def list_reviews(contract_id: uuid.UUID) -> list[ContractReview]:
    """Return every review recorded for a contract version, oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, contract_id, decision, reason, reviewed_by, reviewed_at
            FROM contract_reviews
            WHERE contract_id = %(contract_id)s
            ORDER BY reviewed_at ASC
            """,
            {"contract_id": contract_id},
        ).fetchall()
    columns = ["id", "contract_id", "decision", "reason", "reviewed_by", "reviewed_at"]
    return [ContractReview.model_validate(dict(zip(columns, row, strict=True))) for row in rows]
