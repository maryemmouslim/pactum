import psycopg

from pactum.models import Contract
from pactum.settings import settings


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


def create_version(contract: Contract) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO contracts
                (id, dataset_id, version, yaml, status, parent_version_id, created_at, created_by)
            VALUES
                (%(id)s, %(dataset_id)s, %(version)s, %(yaml)s, %(status)s,
                 %(parent_version_id)s, %(created_at)s, %(created_by)s)
            """,
            contract.model_dump(),
        )


def _row_to_contract(row: tuple) -> Contract:
    columns = [
        "id", "dataset_id", "version", "yaml", "status",
        "parent_version_id", "created_at", "created_by",
    ]
    return Contract(**dict(zip(columns, row)))


def get_active(dataset_id: str) -> Contract | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, dataset_id, version, yaml, status,
                   parent_version_id, created_at, created_by
            FROM contracts
            WHERE dataset_id = %(dataset_id)s AND status = 'active'
            ORDER BY version DESC
            LIMIT 1
            """,
            {"dataset_id": dataset_id},
        ).fetchone()
        return _row_to_contract(row) if row else None


def get_version(dataset_id: str, version: int) -> Contract | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, dataset_id, version, yaml, status,
                   parent_version_id, created_at, created_by
            FROM contracts
            WHERE dataset_id = %(dataset_id)s AND version = %(version)s
            """,
            {"dataset_id": dataset_id, "version": version},
        ).fetchone()
        return _row_to_contract(row) if row else None


def list_history(dataset_id: str) -> list[Contract]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, dataset_id, version, yaml, status,
                   parent_version_id, created_at, created_by
            FROM contracts
            WHERE dataset_id = %(dataset_id)s
            ORDER BY version ASC
            """,
            {"dataset_id": dataset_id},
        ).fetchall()
        return [_row_to_contract(row) for row in rows]
