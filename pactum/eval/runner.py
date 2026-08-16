from dataclasses import dataclass
from pathlib import Path

import yaml

from pactum.agents.causal_explainer import build_causal_explainer_graph
from pactum.agents.state import CausalExplainerState
from pactum.contract_schema import parse_contract_yaml
from pactum.eval._shared import cleanup_eval_dataset, import_module
from pactum.eval.judge import judge_hypothesis
from pactum.monitoring.incident_store import build_signature, find_open_incident
from pactum.monitoring.runner import evaluate_contract
from pactum.registry.contract_registry import get_active
from pactum.sources.registry import load_persisted_registrations


@dataclass
class ScenarioResult:
    name: str
    passed: bool
    reasoning: str
    confidence: float | None = None
    hypothesis: str | None = None


def run_scenario(scenario_dir: Path) -> ScenarioResult:
    setup_mod = import_module(scenario_dir / "setup.py")
    inject_mod = import_module(scenario_dir / "inject.py")
    expected = yaml.safe_load((scenario_dir / "expected.yaml").read_text())

    dataset_id = f"eval_{scenario_dir.name}"
    cleanup_eval_dataset(dataset_id)  # clear any leftover state from a previous run

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
        cleanup_eval_dataset(dataset_id)


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
