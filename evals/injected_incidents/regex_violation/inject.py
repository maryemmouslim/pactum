from pathlib import Path

from pactum.eval.fixtures import write_csv


def inject(context: dict[str, object]) -> None:
    path = Path(str(context["data_dir"])) / f"{context['dataset_id']}.csv"
    rows: list[dict[str, object]] = [
        {"order_id": "o1", "email": "alice@example.com"},
        {"order_id": "o2", "email": "not-a-valid-email"},
    ]
    write_csv(path, rows)
