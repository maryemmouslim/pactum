import csv
import tempfile
from pathlib import Path

from pactum.contract_schema import ColumnRule, ParsedContract, render_contract_yaml
from pactum.registry.contract_registry import activate_version, create_version
from pactum.sources.duckdb_adapter import DuckDBAdapter
from pactum.sources.registry import register_source


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def register_dataset_with_contract(
    dataset_id: str,
    rows: list[dict[str, object]],
    columns: list[ColumnRule],
    *,
    freshness_sla_seconds: float | None = None,
    completeness_sla: float | None = None,
) -> dict[str, object]:
    """Write `rows` as dataset_id.csv in a fresh temp dir, register it, and
    create + activate a hand-authored contract for it.

    Used by eval scenario setup.py files so each one only needs to describe
    its data and rules -- not go through the LLM-based Contract Generator
    Agent, which would make scenarios non-deterministic and test the wrong
    agent.
    """
    data_dir = Path(tempfile.mkdtemp(prefix="pactum-eval-"))
    write_csv(data_dir / f"{dataset_id}.csv", rows)
    register_source(DuckDBAdapter(str(data_dir)))

    parsed = ParsedContract(
        dataset_id=dataset_id,
        columns=columns,
        freshness_sla_seconds=freshness_sla_seconds,
        completeness_sla=completeness_sla,
    )
    contract = create_version(dataset_id, render_contract_yaml(parsed), created_by="eval-harness")
    activate_version(dataset_id, contract.version)

    return {"dataset_id": dataset_id, "contract_id": contract.id, "data_dir": str(data_dir)}
