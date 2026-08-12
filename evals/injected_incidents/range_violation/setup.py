from pactum.contract_schema import ColumnRule
from pactum.eval.fixtures import register_dataset_with_contract


def setup(dataset_id: str) -> dict[str, object]:
    rows: list[dict[str, object]] = [
        {"order_id": "o1", "amount": 49.99},
        {"order_id": "o2", "amount": 12.50},
        {"order_id": "o3", "amount": 100.00},
    ]
    columns = [
        ColumnRule(name="order_id", data_type="VARCHAR", semantic_type="identifier"),
        ColumnRule(
            name="amount",
            data_type="DOUBLE",
            semantic_type="currency",
            min_value=0.0,
            max_value=1000.0,
        ),
    ]
    return register_dataset_with_contract(dataset_id, rows, columns)
