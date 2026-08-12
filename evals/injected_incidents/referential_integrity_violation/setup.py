import tempfile
from pathlib import Path

from pactum.contract_schema import ColumnRule
from pactum.eval.fixtures import register_dataset_with_contract, write_csv
from pactum.sources.duckdb_adapter import DuckDBAdapter
from pactum.sources.registry import register_source


def setup(dataset_id: str) -> dict[str, object]:
    customers_id = f"{dataset_id}_customers"
    customers_dir = Path(tempfile.mkdtemp(prefix="pactum-eval-"))
    write_csv(
        customers_dir / f"{customers_id}.csv",
        [
            {"customer_id": "c1", "name": "Alice"},
            {"customer_id": "c2", "name": "Bob"},
        ],
    )
    register_source(DuckDBAdapter(str(customers_dir)))

    rows: list[dict[str, object]] = [
        {"order_id": "o1", "customer_id": "c1"},
        {"order_id": "o2", "customer_id": "c2"},
    ]
    columns = [
        ColumnRule(name="order_id", data_type="VARCHAR", semantic_type="identifier"),
        ColumnRule(
            name="customer_id",
            data_type="VARCHAR",
            semantic_type="identifier",
            references_dataset=customers_id,
            references_column="customer_id",
        ),
    ]
    context = register_dataset_with_contract(dataset_id, rows, columns)
    context["customers_id"] = customers_id
    return context
