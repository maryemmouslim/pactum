from pactum.contract_schema import ColumnRule
from pactum.eval.fixtures import register_dataset_with_contract


def setup(dataset_id: str) -> dict[str, object]:
    rows: list[dict[str, object]] = [
        {"order_id": "o1", "amount": 10.0},
        {"order_id": "o2", "amount": 20.0},
        {"order_id": "o3", "amount": 30.0},
    ]
    columns = [
        ColumnRule(name="order_id", data_type="VARCHAR", semantic_type="identifier", unique=True),
        ColumnRule(name="amount", data_type="DOUBLE", semantic_type="currency"),
    ]
    return register_dataset_with_contract(dataset_id, rows, columns)
