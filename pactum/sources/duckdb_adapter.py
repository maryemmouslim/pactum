from pathlib import Path

import duckdb


class DuckDBAdapter:
    """Reads CSV/Parquet files from a directory; each file is one dataset."""

    def __init__(self, directory: str):
        self._dir = Path(directory)
        self._conn = duckdb.connect()

    def _path_for(self, dataset: str) -> Path:
        matches = list(self._dir.glob(f"{dataset}.*"))
        if not matches:
            raise FileNotFoundError(f"No file found for dataset '{dataset}' in {self._dir}")
        return matches[0]

    def list_datasets(self) -> list[str]:
        return [p.stem for p in self._dir.iterdir() if p.suffix in (".csv", ".parquet")]

    def get_schema(self, dataset: str) -> dict[str, str]:
        path = self._path_for(dataset)
        rows = self._conn.execute(f"DESCRIBE SELECT * FROM '{path}'").fetchall()
        return {row[0]: row[1] for row in rows}

    def sample(self, dataset: str, n: int = 10) -> list[tuple]:
        path = self._path_for(dataset)
        return self._conn.execute(f"SELECT * FROM '{path}' LIMIT {n}").fetchall()
