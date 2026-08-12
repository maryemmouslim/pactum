import random
from pathlib import Path

from pactum.eval.fixtures import write_csv


def inject(context: dict[str, object]) -> None:
    path = Path(str(context["data_dir"])) / f"{context['dataset_id']}.csv"
    rng = random.Random(99)
    shifted_amounts = [round(rng.uniform(500, 1000), 2) for _ in range(200)]
    rows: list[dict[str, object]] = [
        {"order_id": f"o{i}", "amount": amount} for i, amount in enumerate(shifted_amounts)
    ]
    write_csv(path, rows)
