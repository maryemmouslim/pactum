from pactum.contract_schema import ColumnRule
from pactum.eval.fixtures import register_dataset_with_contract

_EMAIL_PATTERN = r"[^@\s]+@[^@\s]+\.[^@\s]+"


def setup(dataset_id: str) -> dict[str, object]:
    rows: list[dict[str, object]] = [
        {"order_id": "o1", "email": "alice@example.com"},
        {"order_id": "o2", "email": "bob@example.com"},
    ]
    columns = [
        ColumnRule(name="order_id", data_type="VARCHAR", semantic_type="identifier"),
        ColumnRule(
            name="email",
            data_type="VARCHAR",
            semantic_type="pii",
            regex_pattern=_EMAIL_PATTERN,
        ),
    ]
    return register_dataset_with_contract(dataset_id, rows, columns)
