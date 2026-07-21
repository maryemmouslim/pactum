from pactum.sources.protocol import SourceAdapter

_adapters: dict[str, SourceAdapter] = {}


def register_source(adapter: SourceAdapter) -> None:
    """Register every dataset exposed by a source adapter."""
    for dataset_id in adapter.list_datasets():
        _adapters[dataset_id] = adapter


def get_adapter(dataset_id: str) -> SourceAdapter:
    """Return the adapter that owns a given dataset_id."""
    try:
        return _adapters[dataset_id]
    except KeyError:
        raise KeyError(f"No source registered for dataset '{dataset_id}'") from None
