from pactum.monitoring.snapshot_store import save_reference_snapshot
from pactum.sources.registry import (
    get_adapter,
    list_registered_datasets,
    load_persisted_registrations,
)


def main() -> None:
    restored = load_persisted_registrations()
    print(f"restored={restored}")
    results = {}
    for dataset_id in list_registered_datasets():
        adapter = get_adapter(dataset_id)
        schema = list(adapter.get_schema(dataset_id).keys())
        rows = adapter.sample(dataset_id, n=1000)
        for col_idx, col_name in enumerate(schema):
            values = [row[col_idx] for row in rows]
            save_reference_snapshot(dataset_id, col_name, values)
        results[dataset_id] = len(rows)
    print(results)


if __name__ == "__main__":
    main()
