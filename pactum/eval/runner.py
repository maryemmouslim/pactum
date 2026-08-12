import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import psycopg
import yaml

from pactum.agents.causal_explainer import build_causal_explainer_graph
from pactum.agents.state import CausalExplainerState
from pactum.contract_schema import parse_contract_yaml
from pactum.eval.judge import judge_hypothesis
from pactum.monitoring.incident_store import build_signature, find_open_incident
from pactum.monitoring.runner import evaluate_contract
from pactum.registry.contract_registry import get_active
from pactum.settings import settings
from pactum.sources.registry import load_persisted_registrations


@dataclass
class ScenarioResult:
    name: str
    passed: bool
    reasoning: str
    confidence: float | None = None
    hypothesis: str | None = None


def _import(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _cleanup(dataset_id: str) -> None:
    """Delete every row an eval scenario may have created for this dataset_id.

    Runs both before and after each scenario so a rerun always starts clean
    instead of accumulating rows across runs (e.g. tripping the
    single-active-contract-version constraint or an incident signature clash).
    """
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as conn:
        conn.execute(
            "DELETE FROM refinements WHERE incident_id IN "
            "(SELECT id FROM incidents WHERE dataset_id = %(id)s)",
            {"id": dataset_id},
        )
        conn.execute(
            "DELETE FROM explanations WHERE incident_id IN "
            "(SELECT id FROM incidents WHERE dataset_id = %(id)s)",
            {"id": dataset_id},
        )
        conn.execute("DELETE FROM incidents WHERE dataset_id = %(id)s", {"id": dataset_id})
        conn.execute("DELETE FROM contracts WHERE dataset_id = %(id)s", {"id": dataset_id})


def run_scenario(scenario_dir: Path) -> ScenarioResult:
    setup_mod = _import(scenario_dir / "setup.py")
    inject_mod = _import(scenario_dir / "inject.py")
    expected = yaml.safe_load((scenario_dir / "expected.yaml").read_text())

    dataset_id = f"eval_{scenario_dir.name}"
    _cleanup(dataset_id)  # clear any leftover state from a previous run before starting

    try:
        context = setup_mod.setup(dataset_id)
        inject_mod.inject(context)

        contract = get_active(dataset_id)
        if contract is None:
            return ScenarioResult(scenario_dir.name, False, "setup() left no active contract")

        parsed = parse_contract_yaml(contract.yaml)
        evaluate_contract(dataset_id, parsed, contract.id, incremental=False)

        signature = build_signature(dataset_id, expected["check_type"], expected.get("column"))
        incident = find_open_incident(signature)
        if incident is None:
            return ScenarioResult(
                scenario_dir.name, False, "injection did not produce the expected incident"
            )

        app = build_causal_explainer_graph()
        result = app.invoke(CausalExplainerState(incident=incident))
        explanation = result["explanation"]
        if not explanation.hypotheses:
            return ScenarioResult(scenario_dir.name, False, "agent produced no hypotheses")

        top = explanation.hypotheses[0]
        verdict = judge_hypothesis(expected["expected_cause"], top.description)
        return ScenarioResult(
            scenario_dir.name, verdict.correct, verdict.reasoning, top.confidence, top.description
        )
    finally:
        _cleanup(dataset_id)


def print_report(results: list[ScenarioResult]) -> None:
    passed = sum(r.passed for r in results)
    print(f"\n{passed}/{len(results)} scenarios passed\n")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        confidence = f" (confidence={r.confidence:.2f})" if r.confidence is not None else ""
        print(f"[{status}] {r.name}{confidence}")
        if r.hypothesis is not None:
            print(f"    agent said: {r.hypothesis}")
        print(f"    judge said: {r.reasoning}")


def _run_scenario_safely(scenario_dir: Path) -> ScenarioResult:
    try:
        return run_scenario(scenario_dir)
    except Exception as exc:  # noqa: BLE001
        # One broken scenario (a bug in its setup.py, a transient API error)
        # shouldn't prevent the rest of the batch from running.
        return ScenarioResult(scenario_dir.name, False, f"scenario crashed: {exc}")


def run_eval(scenarios_dir: str) -> None:
    load_persisted_registrations()
    scenario_dirs = sorted(d for d in Path(scenarios_dir).iterdir() if d.is_dir())
    results = [_run_scenario_safely(scenario_dir) for scenario_dir in scenario_dirs]
    print_report(results)
