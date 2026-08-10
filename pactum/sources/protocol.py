from datetime import datetime
from typing import Protocol


class SourceAdapter(Protocol):
    def list_datasets(self) -> list[str]:
        """Return the names of datasets available from this source."""
        ...

    def get_schema(self, dataset: str) -> dict[str, str]:
        """Return {column_name: data_type} for a dataset."""
        ...

    def sample(self, dataset: str, n: int = 10) -> list[tuple[object, ...]]:
        """Return up to n example rows from a dataset."""
        ...

    def query_window(
        self, dataset: str, timestamp_column: str, start: datetime, end: datetime
    ) -> list[tuple[object, ...]]:
        """Return all rows where timestamp_column falls in [start, end), ordered by it.

        Needed for anything that compares two specific time periods (drift's
        reference vs current window, freshness/completeness over a real
        range) -- unlike sample(), which has no ordering or time semantics.
        """
        ...

    def to_registration_config(self) -> dict[str, object]:
        """Return {"adapter_type": ..., **constructor kwargs} to reconstruct this adapter.

        Lets the registry persist *how* to rebuild this adapter (not the live
        connection itself) so registrations survive a process restart.
        """
        ...
