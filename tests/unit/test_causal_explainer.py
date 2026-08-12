import uuid
from datetime import UTC, datetime

import pytest

from pactum.agents.causal_explainer import (
    _build_synthesis_prompt,
    _HypothesisDraft,
    _HypothesisList,
    _RefinementDraft,
    build_causal_explainer_graph,
    investigate_incident,
    persist_explanation,
    propose_refinement,
    route_after_explanation,
    synthesize_hypotheses,
)
from pactum.agents.state import CausalExplainerState
from pactum.lineage.graph import LineageGraph
from pactum.models import Explanation, Incident, RefinementProposal


def _make_incident(**overrides: object) -> Incident:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "dataset_id": "orders",
        "detected_at": datetime.now(UTC),
        "kind": "violation",
        "severity": "high",
        "signature": "abc123",
        "payload": {},
        "contract_version_id": uuid.uuid4(),
        "check_type": "schema",
        "column_name": None,
    }
    defaults.update(overrides)
    return Incident(**defaults)  # type: ignore[arg-type]


class FakeStructuredLLM:
    def __init__(self, result: object) -> None:
        self._result = result

    def invoke(self, prompt: str) -> object:
        return self._result


class FakeLLM:
    def __init__(self, result: object) -> None:
        self._result = result

    def with_structured_output(self, schema: object) -> FakeStructuredLLM:
        return FakeStructuredLLM(self._result)


def test_investigate_incident_collects_findings_from_every_applicable_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pactum.tools.causal_tools.load_graph", lambda: LineageGraph())
    monkeypatch.setattr("pactum.tools.causal_tools.get_by_id", lambda contract_id: None)
    monkeypatch.setattr("pactum.tools.causal_tools.get_incident", lambda incident_id: None)
    monkeypatch.setattr(
        "pactum.tools.causal_tools.load_reference_snapshot", lambda dataset_id, column: None
    )
    monkeypatch.setattr("pactum.tools.causal_tools.list_events_near", lambda dataset_id, around: [])
    monkeypatch.setattr(
        "pactum.tools.causal_tools.fetch_recent_runs",
        lambda dataset_id, around: {"status": "not_configured", "logs": []},
    )

    state = CausalExplainerState(incident=_make_incident(check_type="psi", column_name="amount"))
    result = investigate_incident(state)

    tools_run = {item["tool"] for item in result.findings}
    assert tools_run == {
        "lineage",
        "schema_diff",
        "contract_context",
        "similar_incidents",
        "pipeline_logs",
        "calendar_events",
        "distribution_compare",
    }


def test_investigate_incident_skips_distribution_compare_without_a_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pactum.tools.causal_tools.load_graph", lambda: LineageGraph())
    monkeypatch.setattr("pactum.tools.causal_tools.get_by_id", lambda contract_id: None)
    monkeypatch.setattr("pactum.tools.causal_tools.get_incident", lambda incident_id: None)
    monkeypatch.setattr("pactum.tools.causal_tools.list_events_near", lambda dataset_id, around: [])
    monkeypatch.setattr(
        "pactum.tools.causal_tools.fetch_recent_runs",
        lambda dataset_id, around: {"status": "not_configured", "logs": []},
    )

    state = CausalExplainerState(incident=_make_incident(check_type="schema", column_name=None))
    result = investigate_incident(state)

    tools_run = {item["tool"] for item in result.findings}
    assert "distribution_compare" not in tools_run


def test_synthesis_prompt_reflects_actual_finding_content_not_just_tool_names() -> None:
    # Regression test for the original bug: synthesize_hypotheses used to
    # branch on "did a tool named X run" (always true, since every tool
    # always ran), not on what the tool actually found. This asserts the
    # prompt the LLM sees changes with the finding's *content*.
    incident = _make_incident(check_type="schema", column_name="amount")
    state_with_change = CausalExplainerState(
        incident=incident,
        findings=[{"tool": "schema_diff", "result": {"status": "ok", "added_columns": ["region"]}}],
    )
    state_without_change = CausalExplainerState(
        incident=incident,
        findings=[{"tool": "schema_diff", "result": {"status": "ok", "added_columns": []}}],
    )

    prompt_with_change = _build_synthesis_prompt(state_with_change)
    prompt_without_change = _build_synthesis_prompt(state_without_change)

    assert prompt_with_change != prompt_without_change
    assert "region" in prompt_with_change
    assert "region" not in prompt_without_change


def test_synthesis_prompt_foregrounds_the_incidents_own_payload_as_evidence() -> None:
    # Regression test: the payload used to sit alongside plain metadata lines
    # (kind, severity) with no indication it counts as evidence, while the
    # prompt told the LLM to ground hypotheses only in "the findings above" --
    # for check types with no dedicated investigation tool (e.g. uniqueness,
    # where nothing re-confirms the duplicate values found), every finding
    # comes back empty and the LLM had nothing it was told to ground on, even
    # though the payload itself already answers what went wrong.
    incident = _make_incident(check_type="uniqueness", column_name="order_id")
    incident.payload["duplicate_values"] = ["o1"]
    state = CausalExplainerState(incident=incident, findings=[])

    prompt = _build_synthesis_prompt(state)

    assert "duplicate_values" in prompt
    assert "direct evidence" in prompt
    assert "must be grounded in the check's own payload or a technical finding" in prompt


def test_synthesis_prompt_separates_technical_findings_from_contextual_signals() -> None:
    # Regression test: a calendar note describing a plausible-sounding cause
    # used to sit in the same "Investigation findings" bucket as schema_diff's
    # actual live-data confirmation, with no signal that one is verified and
    # the other is just someone's unverified description -- the LLM ended up
    # citing the narrative note over the harder technical evidence even when
    # both were available and agreed. Technical and contextual findings must
    # render in visibly separate sections.
    incident = _make_incident(check_type="schema", column_name=None)
    state = CausalExplainerState(
        incident=incident,
        findings=[
            {"tool": "schema_diff", "result": {"removed_columns": ["status"]}},
            {
                "tool": "calendar_events",
                "result": {"events": [{"description": "deployed v2.3, dropped status field"}]},
            },
        ],
    )

    prompt = _build_synthesis_prompt(state)

    assert "Technical findings" in prompt
    assert "Contextual signals" in prompt
    technical_section = prompt.split("Technical findings")[1].split("Contextual signals")[0]
    contextual_section = prompt.split("Contextual signals")[1]
    assert "removed_columns" in technical_section
    assert "removed_columns" not in contextual_section
    assert "deployed v2.3" in contextual_section
    assert "deployed v2.3" not in technical_section
    assert "not sufficient grounding" in prompt


def test_synthesize_hypotheses_sorts_by_confidence_descending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_result = _HypothesisList(
        hypotheses=[
            _HypothesisDraft(
                cited_evidence="evidence A", description="low confidence cause", confidence=0.2
            ),
            _HypothesisDraft(
                cited_evidence="evidence B", description="high confidence cause", confidence=0.9
            ),
        ]
    )
    monkeypatch.setattr(
        "pactum.agents.causal_explainer.get_llm", lambda role="reasoning": FakeLLM(fake_result)
    )

    state = CausalExplainerState(incident=_make_incident())
    result = synthesize_hypotheses(state)

    assert [h["description"] for h in result.hypotheses] == [
        "high confidence cause",
        "low confidence cause",
    ]


def test_persist_explanation_builds_and_saves_explanation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_save_explanation(explanation: Explanation) -> Explanation:
        captured["explanation"] = explanation
        return explanation

    monkeypatch.setattr("pactum.agents.causal_explainer.save_explanation", fake_save_explanation)
    monkeypatch.setattr(
        "pactum.agents.causal_explainer.index_incident", lambda incident, explanation: None
    )

    incident = _make_incident()
    state = CausalExplainerState(
        incident=incident,
        findings=[{"tool": "schema_diff", "result": {"status": "ok"}}],
        hypotheses=[{"description": "cause", "confidence": 0.8}],
    )
    result = persist_explanation(state)

    assert result.explanation is not None
    assert result.explanation.incident_id == incident.id
    assert result.explanation.hypotheses[0].description == "cause"
    assert result.explanation.reasoning_trace == state.findings
    assert captured["explanation"] is result.explanation


@pytest.mark.parametrize(
    ("description", "confidence", "expected"),
    [
        ("A schema change or contract mismatch is the likely cause", 0.7, "propose_refinement"),
        ("A schema change or contract mismatch is the likely cause", 0.3, "end"),
        ("An upstream job silently failed to run", 0.9, "end"),
    ],
)
def test_route_after_explanation(description: str, confidence: float, expected: str) -> None:
    state = CausalExplainerState(
        incident=_make_incident(),
        hypotheses=[{"description": description, "confidence": confidence}],
    )
    assert route_after_explanation(state) == expected


def test_route_after_explanation_ends_when_no_hypotheses() -> None:
    state = CausalExplainerState(incident=_make_incident(), hypotheses=[])
    assert route_after_explanation(state) == "end"


def test_propose_refinement_persists_proposal_against_incidents_contract_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_draft = _RefinementDraft(kind="relaxation", proposed_yaml="dataset_id: orders")
    monkeypatch.setattr(
        "pactum.agents.causal_explainer.get_llm", lambda role="reasoning": FakeLLM(fake_draft)
    )
    monkeypatch.setattr("pactum.agents.causal_explainer.get_by_id", lambda contract_id: None)
    captured: dict[str, object] = {}

    def fake_save_refinement_proposal(proposal: RefinementProposal) -> RefinementProposal:
        captured["proposal"] = proposal
        return proposal

    monkeypatch.setattr(
        "pactum.agents.causal_explainer.save_refinement_proposal", fake_save_refinement_proposal
    )

    incident = _make_incident()
    state = CausalExplainerState(
        incident=incident,
        hypotheses=[{"description": "contract rule too strict", "confidence": 0.7}],
    )
    result = propose_refinement(state)

    assert result.refinement_proposal is not None
    assert result.refinement_proposal.incident_id == incident.id
    assert result.refinement_proposal.contract_id == incident.contract_version_id
    assert result.refinement_proposal.kind == "relaxation"
    assert result.refinement_proposal.status == "pending"
    assert captured["proposal"] is result.refinement_proposal


def test_full_graph_runs_end_to_end_and_proposes_a_refinement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pactum.tools.causal_tools.load_graph", lambda: LineageGraph())
    monkeypatch.setattr("pactum.tools.causal_tools.get_by_id", lambda contract_id: None)
    monkeypatch.setattr("pactum.agents.causal_explainer.get_by_id", lambda contract_id: None)
    monkeypatch.setattr("pactum.tools.causal_tools.get_incident", lambda incident_id: None)
    monkeypatch.setattr("pactum.tools.causal_tools.list_events_near", lambda dataset_id, around: [])
    monkeypatch.setattr(
        "pactum.tools.causal_tools.fetch_recent_runs",
        lambda dataset_id, around: {"status": "not_configured", "logs": []},
    )

    fake_hypotheses = _HypothesisList(
        hypotheses=[
            _HypothesisDraft(
                cited_evidence="contract rule",
                description="contract rule too strict for this column",
                confidence=0.8,
            )
        ]
    )
    fake_refinement = _RefinementDraft(kind="relaxation", proposed_yaml="dataset_id: orders")
    llms = iter([FakeLLM(fake_hypotheses), FakeLLM(fake_refinement)])
    monkeypatch.setattr(
        "pactum.agents.causal_explainer.get_llm", lambda role="reasoning": next(llms)
    )

    saved_explanations: list[Explanation] = []
    monkeypatch.setattr(
        "pactum.agents.causal_explainer.save_explanation",
        lambda explanation: saved_explanations.append(explanation) or explanation,
    )
    saved_refinements: list[RefinementProposal] = []
    monkeypatch.setattr(
        "pactum.agents.causal_explainer.save_refinement_proposal",
        lambda proposal: saved_refinements.append(proposal) or proposal,
    )
    monkeypatch.setattr(
        "pactum.agents.causal_explainer.index_incident", lambda incident, explanation: None
    )

    incident = _make_incident(check_type="schema", column_name=None)
    app = build_causal_explainer_graph()
    result = app.invoke(CausalExplainerState(incident=incident))

    assert result["explanation"].hypotheses[0].description.startswith("contract rule")
    assert result["refinement_proposal"].kind == "relaxation"
    assert len(saved_explanations) == 1
    assert len(saved_refinements) == 1


def test_full_graph_omits_refinement_proposal_key_when_routed_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression test: a real end-to-end run against Postgres crashed with
    # KeyError('refinement_proposal') because LangGraph's compiled-graph
    # output dict only contains keys that some node actually wrote on the
    # executed path -- a field that stays at its Pydantic default (never
    # written, because propose_refinement was skipped) is simply absent, not
    # present-with-None. Callers must use result.get(...), never result[...].
    monkeypatch.setattr("pactum.tools.causal_tools.load_graph", lambda: LineageGraph())
    monkeypatch.setattr("pactum.tools.causal_tools.get_by_id", lambda contract_id: None)
    monkeypatch.setattr("pactum.tools.causal_tools.get_incident", lambda incident_id: None)
    monkeypatch.setattr("pactum.tools.causal_tools.list_events_near", lambda dataset_id, around: [])
    monkeypatch.setattr(
        "pactum.tools.causal_tools.fetch_recent_runs",
        lambda dataset_id, around: {"status": "not_configured", "logs": []},
    )

    fake_hypotheses = _HypothesisList(
        hypotheses=[
            _HypothesisDraft(
                cited_evidence="unrelated finding",
                description="an unrelated upstream job failure",
                confidence=0.6,
            )
        ]
    )
    monkeypatch.setattr(
        "pactum.agents.causal_explainer.get_llm", lambda role="reasoning": FakeLLM(fake_hypotheses)
    )
    monkeypatch.setattr(
        "pactum.agents.causal_explainer.save_explanation", lambda explanation: explanation
    )
    monkeypatch.setattr(
        "pactum.agents.causal_explainer.index_incident", lambda incident, explanation: None
    )

    incident = _make_incident(check_type="schema", column_name=None)
    app = build_causal_explainer_graph()
    result = app.invoke(CausalExplainerState(incident=incident))

    assert "refinement_proposal" not in result
    assert result.get("refinement_proposal") is None
