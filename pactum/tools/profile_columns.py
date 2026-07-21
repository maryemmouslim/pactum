from pactum.profiler import profile_columns as compute_profiles
from pactum.sources.registry import get_adapter
from pactum.tools import tool


@tool
def sample_data(dataset_id: str, n: int = 10) -> list[dict[str, object]]:
    """Return up to n example rows from a dataset as column-name-keyed dicts.

    Args:
        dataset_id: Fully-qualified dataset identifier.
        n: Maximum number of rows to return. Default 10.

    Returns:
        List of rows, each a mapping of column name to value.
    """
    adapter = get_adapter(dataset_id)
    columns = list(adapter.get_schema(dataset_id).keys())
    rows = adapter.sample(dataset_id, n)
    return [dict(zip(columns, row, strict=True)) for row in rows]


@tool
def profile_column(dataset_id: str, n: int = 1000) -> dict[str, dict[str, object]]:
    """Return per-column statistics for a dataset: null %, distinct count, min/max.

    Args:
        dataset_id: Fully-qualified dataset identifier.
        n: How many rows to sample for computing statistics. Default 1000.

    Returns:
        Mapping of column name to its stats dict.
    """
    adapter = get_adapter(dataset_id)
    columns = list(adapter.get_schema(dataset_id).keys())
    rows = adapter.sample(dataset_id, n)
    return compute_profiles(rows, columns)
