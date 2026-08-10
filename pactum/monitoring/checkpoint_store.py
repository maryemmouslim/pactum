from datetime import datetime

import psycopg

from pactum.settings import settings


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


def save_checkpoint(dataset_id: str, checked_through: datetime) -> None:
    """Record how far a dataset's incremental checks have progressed.

    Upserts rather than appending -- there's only ever one "how far have we
    checked" marker per dataset, unlike contracts or incidents, which keep
    full history on purpose.
    """
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO dataset_checkpoints (dataset_id, checked_through)
            VALUES (%(dataset_id)s, %(checked_through)s)
            ON CONFLICT (dataset_id) DO UPDATE SET checked_through = EXCLUDED.checked_through
            """,
            {"dataset_id": dataset_id, "checked_through": checked_through},
        )


def load_checkpoint(dataset_id: str) -> datetime | None:
    """Return how far a dataset's incremental checks have progressed, if ever checked before."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT checked_through FROM dataset_checkpoints WHERE dataset_id = %(dataset_id)s",
            {"dataset_id": dataset_id},
        ).fetchone()
    return row[0] if row else None
