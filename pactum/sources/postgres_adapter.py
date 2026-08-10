from datetime import datetime

import psycopg


class PostgresAdapter:
    """Reads tables from a Postgres database; each table is one dataset."""

    def __init__(self, connection_url: str):
        self._connection_url = connection_url
        url = connection_url.replace("postgresql+psycopg://", "postgresql://")
        self._conn = psycopg.connect(url)

    def list_datasets(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
        return [row[0] for row in rows]

    def get_schema(self, dataset: str) -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = %(dataset)s",
            {"dataset": dataset},
        ).fetchall()
        return dict(rows)

    def sample(self, dataset: str, n: int = 10) -> list[tuple[object, ...]]:
        return self._conn.execute(
            psycopg.sql.SQL("SELECT * FROM {} LIMIT %(n)s").format(psycopg.sql.Identifier(dataset)),
            {"n": n},
        ).fetchall()

    def to_registration_config(self) -> dict[str, object]:
        return {"adapter_type": "postgres", "connection_url": self._connection_url}

    def query_window(
        self, dataset: str, timestamp_column: str, start: datetime, end: datetime
    ) -> list[tuple[object, ...]]:
        return self._conn.execute(
            psycopg.sql.SQL(
                "SELECT * FROM {table} WHERE {column} >= %(start)s AND {column} < %(end)s "
                "ORDER BY {column}"
            ).format(
                table=psycopg.sql.Identifier(dataset),
                column=psycopg.sql.Identifier(timestamp_column),
            ),
            {"start": start, "end": end},
        ).fetchall()
