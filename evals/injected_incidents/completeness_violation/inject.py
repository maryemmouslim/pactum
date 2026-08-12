from pathlib import Path

from pactum.eval.fixtures import write_csv


def inject(context: dict[str, object]) -> None:
    path = Path(str(context["data_dir"])) / f"{context['dataset_id']}.csv"
    rows: list[dict[str, object]] = [
        {"order_id": "o1", "customer_id": ""},
        {"order_id": "o2", "customer_id": ""},
        {"order_id": "o3", "customer_id": ""},
        {"order_id": "o4", "customer_id": "c4"},
    ]
    write_csv(path, rows)
