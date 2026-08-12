from pathlib import Path

from pactum.eval.fixtures import write_csv


def inject(context: dict[str, object]) -> None:
    path = Path(str(context["data_dir"])) / f"{context['dataset_id']}.csv"
    rows: list[dict[str, object]] = [
        {"order_id": "o1", "customer_id": "c1"},
        {"order_id": "o2", "customer_id": "c99"},  # c99 doesn't exist in customers
    ]
    write_csv(path, rows)
