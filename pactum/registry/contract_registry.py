import uuid
from datetime import UTC, datetime
from typing import Literal

import psycopg

from pactum.models import Contract
from pactum.settings import settings


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


def create_version(
    dataset_id: str,
    yaml: str,
    created_by: str,
    status: Literal["draft", "active", "deprecated"] = "draft",
) -> Contract:
    """Allocate the next version atomically and persist a new contract.

    Serialized per dataset_id via a Postgres advisory lock, so two
    concurrent calls for the same dataset never compute the same version
    or lose track of the parent link -- including the very first version,
    when there is no existing row to lock.
    """
    with _connect() as conn:
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%(dataset_id)s))",
            {"dataset_id": dataset_id},
        )

        latest = conn.execute(
            """
            SELECT id, version FROM contracts
            WHERE dataset_id = %(dataset_id)s
            ORDER BY version DESC
            LIMIT 1
            """,
            {"dataset_id": dataset_id},
        ).fetchone()

        parent_version_id, next_version = (latest[0], latest[1] + 1) if latest else (None, 1)

        contract = Contract(
            id=uuid.uuid4(),
            dataset_id=dataset_id,
            version=next_version,
            yaml=yaml,
            status=status,
            parent_version_id=parent_version_id,
            created_at=datetime.now(UTC),
            created_by=created_by,
        )

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

        return contract


def _row_to_contract(row: tuple[object, ...]) -> Contract:
    columns = [
        "id",
        "dataset_id",
        "version",
        "yaml",
        "status",
        "parent_version_id",
        "created_at",
        "created_by",
    ]
    return Contract.model_validate(dict(zip(columns, row)))


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
