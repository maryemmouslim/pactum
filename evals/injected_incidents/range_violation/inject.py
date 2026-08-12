from pathlib import Path

from pactum.eval.fixtures import write_csv


def inject(context: dict[str, object]) -> None:
    path = Path(str(context["data_dir"])) / f"{context['dataset_id']}.csv"
    rows: list[dict[str, object]] = [
        {"order_id": "o1", "amount": 49.99},
        {"order_id": "o2", "amount": -75.00},  # negative -- outside [0.0, 1000.0]
        {"order_id": "o3", "amount": 100.00},
    ]
    write_csv(path, rows)
