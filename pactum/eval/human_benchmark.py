from dataclasses import dataclass
from pathlib import Path

import yaml

from pactum.agents.causal_explainer import build_causal_explainer_graph
from pactum.agents.state import CausalExplainerState
from pactum.contract_schema import parse_contract_yaml
from pactum.eval._shared import cleanup_eval_dataset, import_module
from pactum.eval.judge import judge_hypothesis
from pactum.monitoring.incident_store import list_incidents_for_dataset
from pactum.monitoring.runner import evaluate_contract
from pactum.registry.contract_registry import get_active
from pactum.sources.registry import load_persisted_registrations


@dataclass
class HumanBenchmarkResult:
    name: str
    human_correct: bool
    human_reasoning: str
    agent_correct: bool
    agent_reasoning: str
    agent_confidence: float | None = None
    error: str | None = None


def run_scenario(scenario_dir: Path, human_hypothesis: str) -> HumanBenchmarkResult:
    """Run one injected-incident scenario for real, then judge both the live
    agent's top hypothesis and a frozen human hypothesis against the same
    ground truth.

    `human_hypothesis` is not derived from anything in this function -- it's
    a human's diagnosis recorded once, ahead of time, from reading the same
    investigation evidence the agent's tools gather (see
    evals/human_benchmark/README.md). There is no way to regenerate a human
    judgment call from code, so it's passed in rather than computed here.
    """
    setup_mod = import_module(scenario_dir / "setup.py")
    inject_mod = import_module(scenario_dir / "inject.py")
    expected = yaml.safe_load((scenario_dir / "expected.yaml").read_text())
    expected_cause = expected["expected_cause"]

    dataset_id = f"eval_{scenario_dir.name}"
    cleanup_eval_dataset(dataset_id)

    try:
        context = setup_mod.setup(dataset_id)
        inject_mod.inject(context)

        contract = get_active(dataset_id)
        if contract is None:
            return HumanBenchmarkResult(
                scenario_dir.name, False, "", False, "", error="setup() left no active contract"
            )

        parsed = parse_contract_yaml(contract.yaml)
        evaluate_contract(dataset_id, parsed, contract.id, incremental=False)

        incidents = list_incidents_for_dataset(dataset_id)
        if not incidents:
            return HumanBenchmarkResult(
                scenario_dir.name, False, "", False, "", error="injection produced no incident"
            )
        incident = incidents[0]

        app = build_causal_explainer_graph()
        result = app.invoke(CausalExplainerState(incident=incident))
        explanation = result["explanation"]
        if not explanation.hypotheses:
            return HumanBenchmarkResult(
                scenario_dir.name, False, "", False, "", error="agent produced no hypotheses"
            )
        top = explanation.hypotheses[0]

        agent_verdict = judge_hypothesis(expected_cause, top.description)
        human_verdict = judge_hypothesis(expected_cause, human_hypothesis)

        return HumanBenchmarkResult(
            name=scenario_dir.name,
            human_correct=human_verdict.correct,
            human_reasoning=human_verdict.reasoning,
            agent_correct=agent_verdict.correct,
            agent_reasoning=agent_verdict.reasoning,
            agent_confidence=top.confidence,
        )
    finally:
        cleanup_eval_dataset(dataset_id)


def print_report(results: list[HumanBenchmarkResult]) -> None:
    scored = [r for r in results if r.error is None]
    human_score = sum(r.human_correct for r in scored)
    agent_score = sum(r.agent_correct for r in scored)
    print(f"\nHuman: {human_score}/{len(scored)}   Agent: {agent_score}/{len(scored)}\n")
    for r in results:
        if r.error is not None:
            print(f"[ERROR] {r.name}: {r.error}")
            continue
        human_mark = "PASS" if r.human_correct else "FAIL"
        agent_mark = "PASS" if r.agent_correct else "FAIL"
        print(f"{r.name}")
        print(f"  human [{human_mark}]: {r.human_reasoning}")
        print(f"  agent [{agent_mark}] (confidence={r.agent_confidence:.2f}): {r.agent_reasoning}")


def run_human_benchmark(scenarios_dir: str, hypotheses_path: str) -> None:
    load_persisted_registrations()
    hypotheses = yaml.safe_load(Path(hypotheses_path).read_text())
    scenario_dirs = sorted(d for d in Path(scenarios_dir).iterdir() if d.is_dir())

    results = []
    for scenario_dir in scenario_dirs:
        if scenario_dir.name not in hypotheses:
            results.append(
                HumanBenchmarkResult(
                    scenario_dir.name,
                    False,
                    "",
                    False,
                    "",
                    error=f"no recorded human hypothesis for '{scenario_dir.name}'",
                )
            )
            continue
        try:
            results.append(run_scenario(scenario_dir, hypotheses[scenario_dir.name]))
        except Exception as exc:  # noqa: BLE001
            results.append(
                HumanBenchmarkResult(
                    scenario_dir.name, False, "", False, "", error=f"scenario crashed: {exc}"
                )
            )

    print_report(results)
