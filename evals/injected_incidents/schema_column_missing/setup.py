from pactum.contract_schema import ColumnRule
from pactum.eval.fixtures import register_dataset_with_contract


def setup(dataset_id: str) -> dict[str, object]:
    rows = [
        {"order_id": "o1", "amount": 49.99, "status": "pending"},
        {"order_id": "o2", "amount": 12.50, "status": "shipped"},
        {"order_id": "o3", "amount": 100.00, "status": "pending"},
    ]
    columns = [
        ColumnRule(name="order_id", data_type="VARCHAR", semantic_type="identifier", unique=True),
        ColumnRule(name="amount", data_type="DOUBLE", semantic_type="currency", min_value=0.0),
        ColumnRule(
            name="status",
            data_type="VARCHAR",
            semantic_type="categorical",
            allowed_values=["pending", "shipped"],
        ),
    ]
    return register_dataset_with_contract(dataset_id, rows, columns)
