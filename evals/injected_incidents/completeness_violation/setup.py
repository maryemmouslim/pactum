from pactum.contract_schema import ColumnRule
from pactum.eval.fixtures import register_dataset_with_contract


def setup(dataset_id: str) -> dict[str, object]:
    rows: list[dict[str, object]] = [
        {"order_id": "o1", "customer_id": "c1"},
        {"order_id": "o2", "customer_id": "c2"},
        {"order_id": "o3", "customer_id": "c3"},
        {"order_id": "o4", "customer_id": "c4"},
    ]
    columns = [
        ColumnRule(name="order_id", data_type="VARCHAR", semantic_type="identifier"),
        ColumnRule(
            name="customer_id",
            data_type="VARCHAR",
            semantic_type="identifier",
            nullable=False,
        ),
    ]
    return register_dataset_with_contract(dataset_id, rows, columns)
