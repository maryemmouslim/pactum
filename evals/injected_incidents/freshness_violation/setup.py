from datetime import UTC, datetime, timedelta

from pactum.contract_schema import ColumnRule
from pactum.eval.fixtures import register_dataset_with_contract


def setup(dataset_id: str) -> dict[str, object]:
    now = datetime.now(UTC)
    rows: list[dict[str, object]] = [
        {"order_id": "o1", "created_at": (now - timedelta(minutes=5)).isoformat()},
        {"order_id": "o2", "created_at": (now - timedelta(minutes=10)).isoformat()},
    ]
    columns = [
        ColumnRule(name="order_id", data_type="VARCHAR", semantic_type="identifier"),
        ColumnRule(
            name="created_at", data_type="TIMESTAMP WITH TIME ZONE", semantic_type="timestamp"
        ),
    ]
    return register_dataset_with_contract(dataset_id, rows, columns, freshness_sla_seconds=3600.0)
