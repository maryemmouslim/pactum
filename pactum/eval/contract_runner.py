import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import psycopg

from pactum.agents.contract_generator import build_contract_generator_graph
from pactum.agents.state import ContractGeneratorState
from pactum.contract_schema import ColumnRule, ParsedContract, parse_contract_yaml
from pactum.settings import settings
from pactum.sources.duckdb_adapter import DuckDBAdapter
from pactum.sources.registry import register_source

# Fields the generator's classification tool should reasonably get right --
# these are what get scored. min/max/allowed_values/regex_pattern/references
# are reported for context but not scored: they're either more open-ended
# judgment calls, or (for references_*) something no tool in the generator's
# graph is actually capable of discovering, so failing them isn't a defect.
_GRADED_FIELDS = ("semantic_type", "nullable", "unique", "sensitivity")


@dataclass
class ColumnComparison:
    column: str
    in_generated: bool
    gold: ColumnRule | None
    generated: ColumnRule | None
    matched_fields: list[str] = field(default_factory=list)
    mismatched_fields: list[str] = field(default_factory=list)


@dataclass
class GoldContractResult:
    dataset_id: str
    missing_columns: list[str]
    extra_columns: list[str]
    columns: list[ColumnComparison]

    @property
    def score(self) -> tuple[int, int]:
        matched = sum(len(c.matched_fields) for c in self.columns)
        total = sum(len(c.matched_fields) + len(c.mismatched_fields) for c in self.columns)
        return matched, total


def compare_contracts(gold: ParsedContract, generated: ParsedContract) -> GoldContractResult:
    """Diff a hand-written gold contract against a generated one, field by field."""
    gold_by_name = {rule.name: rule for rule in gold.columns}
    generated_by_name = {rule.name: rule for rule in generated.columns}

    missing_columns = sorted(set(gold_by_name) - set(generated_by_name))
    extra_columns = sorted(set(generated_by_name) - set(gold_by_name))

    columns: list[ColumnComparison] = []
    for name, gold_rule in gold_by_name.items():
        generated_rule = generated_by_name.get(name)
        comparison = ColumnComparison(
            column=name,
            in_generated=generated_rule is not None,
            gold=gold_rule,
            generated=generated_rule,
        )
        if generated_rule is None:
            comparison.mismatched_fields = list(_GRADED_FIELDS)
        else:
            for f in _GRADED_FIELDS:
                if getattr(gold_rule, f) == getattr(generated_rule, f):
                    comparison.matched_fields.append(f)
                else:
                    comparison.mismatched_fields.append(f)
        columns.append(comparison)

    return GoldContractResult(
        dataset_id=gold.dataset_id,
        missing_columns=missing_columns,
        extra_columns=extra_columns,
        columns=columns,
    )


def _cleanup_gold(eval_dataset_id: str) -> None:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as conn:
        conn.execute("DELETE FROM contracts WHERE dataset_id = %(id)s", {"id": eval_dataset_id})


def run_gold_contract(yaml_path: Path) -> GoldContractResult:
    """Run the real Contract Generator Agent against a gold contract's dataset and compare."""
    real_dataset_id = yaml_path.stem
    eval_dataset_id = f"eval_gold_{real_dataset_id}"
    gold = parse_contract_yaml(yaml_path.read_text())

    _cleanup_gold(eval_dataset_id)
    try:
        data_dir = Path(tempfile.mkdtemp(prefix="pactum-eval-gold-"))
        source_csv = Path("examples") / "data" / f"{real_dataset_id}.csv"
        shutil.copy(source_csv, data_dir / f"{eval_dataset_id}.csv")
        register_source(DuckDBAdapter(str(data_dir)))

        app = build_contract_generator_graph()
        result = app.invoke(ContractGeneratorState(dataset_id=eval_dataset_id))
        generated = parse_contract_yaml(result["written_contract"].yaml)
        return compare_contracts(gold, generated)
    finally:
        _cleanup_gold(eval_dataset_id)


def print_gold_report(result: GoldContractResult) -> None:
    matched, total = result.score
    print(f"\n{result.dataset_id}: {matched}/{total} graded fields matched")
    if result.missing_columns:
        print(f"  missing columns (in gold, not generated): {result.missing_columns}")
    if result.extra_columns:
        print(f"  extra columns (generated, not in gold): {result.extra_columns}")
    for comparison in result.columns:
        status = "OK" if not comparison.mismatched_fields else "MISMATCH"
        print(f"  [{status}] {comparison.column}")
        for f in comparison.mismatched_fields:
            gold_value = getattr(comparison.gold, f) if comparison.gold else None
            generated_value = getattr(comparison.generated, f) if comparison.generated else None
            print(f"      {f}: gold={gold_value!r} generated={generated_value!r}")


def run_gold_contracts(gold_dir: str) -> None:
    yaml_paths = sorted(Path(gold_dir).rglob("*.yaml"))
    for yaml_path in yaml_paths:
        result = run_gold_contract(yaml_path)
        print_gold_report(result)
