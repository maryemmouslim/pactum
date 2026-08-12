from datetime import UTC, datetime

from pactum.contract_schema import ColumnRule
from pactum.eval.fixtures import register_dataset_with_contract
from pactum.monitoring.calendar_store import add_event

# Deliberately the same shape as the schema_column_missing scenario -- same
# columns, same injected break -- so the *only* difference between the two
# is this recorded deployment event. That isolates one variable: does
# corroborating evidence (here, a deployment right around the incident's
# detection time) actually move the agent's confidence, or is confidence a
# fixed number regardless of how much evidence supports it?


def setup(dataset_id: str) -> dict[str, object]:
    rows: list[dict[str, object]] = [
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
    context = register_dataset_with_contract(dataset_id, rows, columns)

    add_event(
        event_type="deployment",
        description="Deployed v2.3 of the ingestion pipeline, which dropped the legacy "
        "'status' field from its output schema",
        event_at=datetime.now(UTC),
        dataset_id=dataset_id,
    )

    return context
