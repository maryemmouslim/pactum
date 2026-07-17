import psycopg


class PostgresAdapter:
    """Reads tables from a Postgres database; each table is one dataset."""

    def __init__(self, connection_url: str):
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

    def sample(self, dataset: str, n: int = 10) -> list[tuple]:
        return self._conn.execute(
            psycopg.sql.SQL("SELECT * FROM {} LIMIT %(n)s").format(psycopg.sql.Identifier(dataset)),
            {"n": n},
        ).fetchall()
