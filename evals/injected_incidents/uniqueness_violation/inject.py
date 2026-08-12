from pathlib import Path

from pactum.eval.fixtures import write_csv


def inject(context: dict[str, object]) -> None:
    path = Path(str(context["data_dir"])) / f"{context['dataset_id']}.csv"
    rows: list[dict[str, object]] = [
        {"order_id": "o1", "amount": 10.0},
        {"order_id": "o1", "amount": 10.0},  # duplicate order_id
        {"order_id": "o3", "amount": 30.0},
    ]
    write_csv(path, rows)
