from pathlib import Path

from pactum.eval.fixtures import write_csv


def inject(context: dict[str, object]) -> None:
    # check_schema() deliberately tolerates *added* columns (additive changes
    # are fine); a *missing* column is what it actually flags -- simulating
    # an upstream job that stopped populating a column the contract expects.
    path = Path(str(context["data_dir"])) / f"{context['dataset_id']}.csv"
    rows = [
        {"order_id": "o1", "amount": 49.99},
        {"order_id": "o2", "amount": 12.50},
        {"order_id": "o3", "amount": 100.00},
    ]
    write_csv(path, rows)
