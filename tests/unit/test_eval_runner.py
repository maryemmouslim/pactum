import textwrap
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from pactum.contract_schema import ParsedContract, render_contract_yaml
from pactum.eval.judge import JudgeVerdict
from pactum.eval.runner import _run_scenario_safely, run_scenario
from pactum.models import Contract, Explanation, Hypothesis, Incident


def _write_scenario(tmp_path: Path, name: str = "my_scenario") -> Path:
    scenario_dir = tmp_path / name
    scenario_dir.mkdir()
    (scenario_dir / "setup.py").write_text(
        textwrap.dedent(
            """
            def setup(dataset_id):
                return {"dataset_id": dataset_id, "contract_id": "c1", "data_dir": "/tmp/x"}
            """
        )
    )
    (scenario_dir / "inject.py").write_text(
        textwrap.dedent(
            """
            def inject(context):
                pass
            """
        )
    )
    (scenario_dir / "expected.yaml").write_text(
        "check_type: schema\ncolumn: null\nexpected_cause: something happened\n"
    )
    return scenario_dir


def _make_contract(dataset_id: str) -> Contract:
    parsed = ParsedContract(dataset_id=dataset_id, columns=[])
    return Contract(
        id=uuid4(),
        dataset_id=dataset_id,
        version=1,
        yaml=render_contract_yaml(parsed),
        status="active",
        parent_version_id=None,
        created_at=datetime.now(UTC),
        created_by="test",
    )


def _make_incident(dataset_id: str) -> Incident:
    return Incident(
        id=uuid4(),
        dataset_id=dataset_id,
        detected_at=datetime.now(UTC),
        kind="violation",
        severity="high",
        signature="sig",
        payload={},
        contract_version_id=uuid4(),
        check_type="schema",
        column_name=None,
    )


class FakeApp:
    def __init__(self, explanation: Explanation) -> None:
        self._explanation = explanation

    def invoke(self, state: object) -> dict[str, object]:
        return {"explanation": self._explanation}


def _patch_happy_path(monkeypatch: pytest.MonkeyPatch, dataset_id: str) -> list[str]:
    cleanup_calls: list[str] = []
    monkeypatch.setattr(
        "pactum.eval.runner._cleanup", lambda dataset_id: cleanup_calls.append(dataset_id)
    )
    monkeypatch.setattr(
        "pactum.eval.runner.get_active", lambda dataset_id: _make_contract(dataset_id)
    )
    monkeypatch.setattr("pactum.eval.runner.evaluate_contract", lambda *a, **k: [])
    incident = _make_incident(dataset_id)
    monkeypatch.setattr("pactum.eval.runner.find_open_incident", lambda sig: incident)
    explanation = Explanation(
        id=uuid4(),
        incident_id=incident.id,
        hypotheses=[Hypothesis(description="a cause", confidence=0.8)],
        reasoning_trace=[],
        created_at=datetime.now(UTC),
    )
    monkeypatch.setattr(
        "pactum.eval.runner.build_causal_explainer_graph", lambda: FakeApp(explanation)
    )
    return cleanup_calls


def test_run_scenario_passes_when_judge_says_correct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario_dir = _write_scenario(tmp_path)
    cleanup_calls = _patch_happy_path(monkeypatch, "eval_my_scenario")
    monkeypatch.setattr(
        "pactum.eval.runner.judge_hypothesis",
        lambda expected, actual: JudgeVerdict(correct=True, reasoning="matches"),
    )

    result = run_scenario(scenario_dir)

    assert result.passed is True
    assert result.reasoning == "matches"
    assert result.confidence == 0.8
    # cleanup runs both before setup and after (finally), even on success
    assert cleanup_calls == ["eval_my_scenario", "eval_my_scenario"]


def test_run_scenario_fails_when_judge_says_incorrect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario_dir = _write_scenario(tmp_path)
    _patch_happy_path(monkeypatch, "eval_my_scenario")
    monkeypatch.setattr(
        "pactum.eval.runner.judge_hypothesis",
        lambda expected, actual: JudgeVerdict(correct=False, reasoning="wrong cause"),
    )

    result = run_scenario(scenario_dir)

    assert result.passed is False
    assert result.reasoning == "wrong cause"


def test_run_scenario_fails_without_crashing_when_no_active_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario_dir = _write_scenario(tmp_path)
    cleanup_calls: list[str] = []
    monkeypatch.setattr(
        "pactum.eval.runner._cleanup", lambda dataset_id: cleanup_calls.append(dataset_id)
    )
    monkeypatch.setattr("pactum.eval.runner.get_active", lambda dataset_id: None)

    result = run_scenario(scenario_dir)

    assert result.passed is False
    assert "no active contract" in result.reasoning
    assert cleanup_calls == ["eval_my_scenario", "eval_my_scenario"]


def test_run_scenario_fails_without_crashing_when_no_incident_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario_dir = _write_scenario(tmp_path)
    monkeypatch.setattr("pactum.eval.runner._cleanup", lambda dataset_id: None)
    monkeypatch.setattr(
        "pactum.eval.runner.get_active", lambda dataset_id: _make_contract(dataset_id)
    )
    monkeypatch.setattr("pactum.eval.runner.evaluate_contract", lambda *a, **k: [])
    monkeypatch.setattr("pactum.eval.runner.find_open_incident", lambda sig: None)

    result = run_scenario(scenario_dir)

    assert result.passed is False
    assert "did not produce the expected incident" in result.reasoning


def test_cleanup_runs_even_when_inject_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario_dir = tmp_path / "broken_scenario"
    scenario_dir.mkdir()
    (scenario_dir / "setup.py").write_text(
        "def setup(dataset_id):\n    return {'dataset_id': dataset_id}\n"
    )
    (scenario_dir / "inject.py").write_text(
        "def inject(context):\n    raise RuntimeError('boom')\n"
    )
    (scenario_dir / "expected.yaml").write_text(
        "check_type: schema\ncolumn: null\nexpected_cause: x\n"
    )
    cleanup_calls: list[str] = []
    monkeypatch.setattr(
        "pactum.eval.runner._cleanup", lambda dataset_id: cleanup_calls.append(dataset_id)
    )

    with pytest.raises(RuntimeError, match="boom"):
        run_scenario(scenario_dir)

    assert cleanup_calls == ["eval_broken_scenario", "eval_broken_scenario"]


def test_run_scenario_safely_converts_a_crash_into_a_failed_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario_dir = tmp_path / "broken_scenario"
    scenario_dir.mkdir()
    (scenario_dir / "setup.py").write_text(
        "def setup(dataset_id):\n    raise RuntimeError('setup exploded')\n"
    )
    (scenario_dir / "inject.py").write_text("def inject(context):\n    pass\n")
    (scenario_dir / "expected.yaml").write_text(
        "check_type: schema\ncolumn: null\nexpected_cause: x\n"
    )
    monkeypatch.setattr("pactum.eval.runner._cleanup", lambda dataset_id: None)

    result = _run_scenario_safely(scenario_dir)

    assert result.passed is False
    assert "scenario crashed" in result.reasoning
    assert "setup exploded" in result.reasoning
