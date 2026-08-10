import uuid
from datetime import UTC, date, datetime, timedelta
from typing import cast

import psycopg
import psycopg.types.json

from pactum.settings import settings


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


def _to_json_safe(value: object) -> object:
    """Tag date/datetime values so they survive a round trip through JSON.

    A raw date or datetime isn't JSON-serializable at all -- psycopg's Json
    wrapper raises outright (e.g. a "timestamp" column's snapshot, whose
    values come straight from the adapter as real date/datetime objects).
    Tagging lets _from_json_safe reconstruct the original type instead of
    handing a drift detector a bare string it can't do arithmetic on.
    """
    if isinstance(value, datetime):
        return {"__pactum_type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__pactum_type__": "date", "value": value.isoformat()}
    return value


def _from_json_safe(value: object) -> object:
    if isinstance(value, dict):
        if value.get("__pactum_type__") == "datetime":
            return datetime.fromisoformat(cast(str, value["value"]))
        if value.get("__pactum_type__") == "date":
            return date.fromisoformat(cast(str, value["value"]))
    return value


def save_reference_snapshot(dataset_id: str, column: str, values: list[object]) -> None:
    """Persist a reference (baseline) snapshot for a dataset's column, once.

    Uses INSERT ... ON CONFLICT DO NOTHING so the reference stays fixed once
    captured -- it's the "before" baseline drift gets compared against, not
    something that should silently keep moving underneath the comparison.
    """
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO column_snapshots (id, dataset_id, column_name, captured_at, values)
            VALUES (%(id)s, %(dataset_id)s, %(column_name)s, %(captured_at)s, %(values)s)
            ON CONFLICT (dataset_id, column_name) DO NOTHING
            """,
            {
                "id": uuid.uuid4(),
                "dataset_id": dataset_id,
                "column_name": column,
                "captured_at": datetime.now(UTC),
                "values": psycopg.types.json.Json([_to_json_safe(v) for v in values]),
            },
        )


def load_reference_snapshot(dataset_id: str, column: str, *, days: int = 14) -> list[object] | None:
    """Return a reference window for a dataset's column by aggregating any
    `column_snapshots` captured in the last `days` days.

    This returns None if no snapshot exists in that window. The aggregation
    strategy is simple: concatenate the saved `values` lists in chronological
    order to build a reasonable baseline for drift detectors.
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT values FROM column_snapshots
            WHERE dataset_id = %(dataset_id)s AND column_name = %(column_name)s
              AND captured_at >= %(cutoff)s
            ORDER BY captured_at ASC
            """,
            {"dataset_id": dataset_id, "column_name": column, "cutoff": cutoff},
        ).fetchall()
    if not rows:
        return None
    values: list[object] = []
    for (vals,) in rows:
        values.extend([_from_json_safe(v) for v in cast(list[object], vals)])
    return values
