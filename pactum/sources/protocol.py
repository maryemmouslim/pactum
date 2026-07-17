 
from typing import Protocol


class SourceAdapter(Protocol):
    def list_datasets(self) -> list[str]:
        """Return the names of datasets available from this source."""
        ...

    def get_schema(self, dataset: str) -> dict[str, str]:
        """Return {column_name: data_type} for a dataset."""
        ...

    def sample(self, dataset: str, n: int = 10) -> list[tuple]:
        """Return up to n example rows from a dataset."""
        ...
