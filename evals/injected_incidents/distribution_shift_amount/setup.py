import random

from pactum.contract_schema import ColumnRule
from pactum.eval.fixtures import register_dataset_with_contract
from pactum.monitoring.snapshot_store import save_reference_snapshot


def setup(dataset_id: str) -> dict[str, object]:
    rng = random.Random(42)
    baseline_amounts = [round(rng.uniform(10, 50), 2) for _ in range(200)]
    rows: list[dict[str, object]] = [
        {"order_id": f"o{i}", "amount": amount} for i, amount in enumerate(baseline_amounts)
    ]
    columns = [
        ColumnRule(name="order_id", data_type="VARCHAR", semantic_type="identifier"),
        ColumnRule(name="amount", data_type="DOUBLE", semantic_type="currency"),
    ]
    context = register_dataset_with_contract(dataset_id, rows, columns)
    save_reference_snapshot(dataset_id, "amount", list(baseline_amounts))
    return context
