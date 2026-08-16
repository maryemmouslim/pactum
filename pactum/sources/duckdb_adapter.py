from datetime import datetime
from pathlib import Path

import duckdb


class DuckDBAdapter:
    """Reads CSV/Parquet/JSON files from a directory; each file is one dataset."""

    def __init__(self, directory: str):
        self._dir = Path(directory)
        self._conn = duckdb.connect()

    def _path_for(self, dataset: str) -> Path:
        matches = list(self._dir.glob(f"{dataset}.*"))
        if not matches:
            raise FileNotFoundError(f"No file found for dataset '{dataset}' in {self._dir}")
        return matches[0]

    def _from_clause(self, path: Path) -> str:
        if path.suffix == ".csv":
            # Bare `SELECT * FROM 'file.csv'` uses DuckDB's CSV auto-detection,
            # which silently falls back to reading the whole file as one VARCHAR
            # column if any row in its sample has a different field count than
            # the header (e.g. one truncated row from a real-world export).
            # null_padding=true pads short rows with NULL instead of giving up,
            # so a single ragged row doesn't break schema detection for the
            # entire dataset -- this matters because arbitrary user-uploaded
            # CSVs (see the ingest page) are exactly the kind of file this hits.
            return f"read_csv('{path}', null_padding=true)"
        return f"'{path}'"

    def list_datasets(self) -> list[str]:
        return [p.stem for p in self._dir.iterdir() if p.suffix in (".csv", ".parquet", ".json")]

    def get_schema(self, dataset: str) -> dict[str, str]:
        path = self._path_for(dataset)
        rows = self._conn.execute(f"DESCRIBE SELECT * FROM {self._from_clause(path)}").fetchall()
        return {row[0]: row[1] for row in rows}

    def sample(self, dataset: str, n: int = 10) -> list[tuple[object, ...]]:
        path = self._path_for(dataset)
        return self._conn.execute(f"SELECT * FROM {self._from_clause(path)} LIMIT {n}").fetchall()

    def to_registration_config(self) -> dict[str, object]:
        return {"adapter_type": "duckdb", "directory": str(self._dir)}

    def query_window(
        self, dataset: str, timestamp_column: str, start: datetime, end: datetime
    ) -> list[tuple[object, ...]]:
        path = self._path_for(dataset)
        return self._conn.execute(
            f'SELECT * FROM {self._from_clause(path)} WHERE "{timestamp_column}" >= ? '
            f'AND "{timestamp_column}" < ? ORDER BY "{timestamp_column}"',
            [start, end],
        ).fetchall()
