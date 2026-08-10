from datetime import UTC, datetime
from typing import Literal, cast
from uuid import uuid4

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

from pactum.agents.state import CausalExplainerState
from pactum.llm import get_llm, invoke_structured
from pactum.models import Explanation, Hypothesis, RefinementProposal
from pactum.monitoring.explanation_store import save_explanation
from pactum.monitoring.refinement_store import save_refinement_proposal
from pactum.registry.contract_registry import get_by_id
from pactum.tools.causal_tools import (
    compare_distributions,
    diff_schema,
    fetch_calendar_events,
    fetch_pipeline_logs,
    find_similar_incidents,
    get_lineage,
    query_contract_context,
)

_CONTRACT_ISSUE_KEYWORDS = ("contract", "rule", "sla", "constraint")
_REFINEMENT_CONFIDENCE_THRESHOLD = 0.5


class _HypothesisList(BaseModel):
    hypotheses: list[Hypothesis] = Field(
        description="1-3 ranked hypotheses, most likely cause first."
    )


class _RefinementDraft(BaseModel):
    kind: Literal["relaxation", "tightening", "new_rule", "scoping"]
    proposed_yaml: str = Field(description="The full revised contract YAML to propose.")


def investigate_incident(state: CausalExplainerState) -> CausalExplainerState:
    """Node 1: run the investigation tools that apply to this incident and collect findings."""
    incident = state.incident
    contract_version_id = str(incident.contract_version_id)

    findings: list[dict[str, object]] = [
        {"tool": "lineage", "result": get_lineage.invoke({"dataset_id": incident.dataset_id})},
        {
            "tool": "schema_diff",
            "result": diff_schema.invoke(
                {"dataset_id": incident.dataset_id, "contract_version_id": contract_version_id}
            ),
        },
        {
            "tool": "contract_context",
            "result": query_contract_context.invoke(
                {
                    "dataset_id": incident.dataset_id,
                    "contract_version_id": contract_version_id,
                    "column": incident.column_name,
                }
            ),
        },
        {
            "tool": "similar_incidents",
            "result": find_similar_incidents.invoke(
                {
                    "dataset_id": incident.dataset_id,
                    "check_type": incident.check_type,
                    "incident_id": str(incident.id),
                }
            ),
        },
        {
            "tool": "pipeline_logs",
            "result": fetch_pipeline_logs.invoke({"dataset_id": incident.dataset_id}),
        },
        {
            "tool": "calendar_events",
            "result": fetch_calendar_events.invoke({"dataset_id": incident.dataset_id}),
        },
    ]

    # compare_distributions needs a specific column -- skipped for dataset-level
    # incidents (e.g. a schema check) that have no single column to compare.
    if incident.column_name is not None:
        findings.append(
            {
                "tool": "distribution_compare",
                "result": compare_distributions.invoke(
                    {"dataset_id": incident.dataset_id, "column": incident.column_name}
                ),
            }
        )

    return state.model_copy(update={"findings": findings})


def _build_synthesis_prompt(state: CausalExplainerState) -> str:
    incident = state.incident
    findings_desc = (
        "\n".join(f"- {item['tool']}: {item['result']}" for item in state.findings) or "None"
    )
    return (
        f"An incident was detected on dataset '{incident.dataset_id}':\n"
        f"  check_type: {incident.check_type}\n"
        f"  column: {incident.column_name or 'N/A (dataset-level)'}\n"
        f"  kind: {incident.kind}\n"
        f"  severity: {incident.severity}\n"
        f"  payload: {incident.payload}\n\n"
        f"Investigation findings:\n{findings_desc}\n\n"
        "Based only on the findings above, propose 1-3 ranked hypotheses for what "
        "caused this incident. For each hypothesis, ground the description in a "
        "specific finding, and set confidence (0-1) by weighing: (a) how many "
        "independent findings support it, (b) whether a similar past incident was "
        "found, and (c) whether the timing lines up with a known event. Suggest a "
        "concrete next action for each. If the findings don't point anywhere "
        "specific, say so with low confidence rather than guessing."
    )


def synthesize_hypotheses(state: CausalExplainerState) -> CausalExplainerState:
    """Node 2: have the LLM synthesize ranked hypotheses grounded in the findings."""
    llm = get_llm("reasoning").with_structured_output(_HypothesisList)
    result = cast(_HypothesisList, invoke_structured(llm, _build_synthesis_prompt(state)))
    hypotheses = sorted(result.hypotheses, key=lambda h: h.confidence, reverse=True)
    return state.model_copy(update={"hypotheses": [h.model_dump() for h in hypotheses]})


def persist_explanation(state: CausalExplainerState) -> CausalExplainerState:
    """Node 3: build the Explanation from the ranked hypotheses and persist it."""
    hypotheses = [Hypothesis.model_validate(h) for h in state.hypotheses]
    explanation = Explanation(
        id=uuid4(),
        incident_id=state.incident.id,
        hypotheses=hypotheses,
        reasoning_trace=state.findings,
        created_at=datetime.now(UTC),
    )
    saved = save_explanation(explanation)
    return state.model_copy(update={"explanation": saved})


def route_after_explanation(state: CausalExplainerState) -> str:
    """Decide whether the top hypothesis warrants a contract refinement proposal."""
    if not state.hypotheses:
        return "end"
    top = state.hypotheses[0]
    description = str(top.get("description", "")).lower()
    confidence = float(cast(float, top.get("confidence", 0.0)))
    is_contract_issue = any(keyword in description for keyword in _CONTRACT_ISSUE_KEYWORDS)
    if is_contract_issue and confidence >= _REFINEMENT_CONFIDENCE_THRESHOLD:
        return "propose_refinement"
    return "end"


def _build_refinement_prompt(state: CausalExplainerState, current_contract_yaml: str) -> str:
    incident = state.incident
    top_hypothesis = state.hypotheses[0] if state.hypotheses else {}
    return (
        f"An incident on dataset '{incident.dataset_id}' (check_type={incident.check_type}, "
        f"column={incident.column_name}) was most likely caused by:\n"
        f"{top_hypothesis.get('description', '')}\n\n"
        f"Here is the exact current contract YAML for this dataset:\n\n"
        f"{current_contract_yaml}\n\n"
        "Propose a specific refinement to prevent this from recurring: choose one kind "
        "(relaxation, tightening, new_rule, scoping), then write the FULL revised "
        "contract YAML -- copy the structure above exactly (same top-level keys: "
        "dataset_id, columns, freshness_sla_seconds, completeness_sla; same fields per "
        "column) and change only the specific value(s) that address the cause above. "
        "Do not invent new top-level keys and do not drop any existing column."
    )


def propose_refinement(state: CausalExplainerState) -> CausalExplainerState:
    """Node 4: draft and persist a contract refinement proposal for the top hypothesis."""
    contract = get_by_id(state.incident.contract_version_id)
    current_contract_yaml = contract.yaml if contract is not None else ""

    llm = get_llm("reasoning").with_structured_output(_RefinementDraft)
    draft = cast(
        _RefinementDraft,
        invoke_structured(llm, _build_refinement_prompt(state, current_contract_yaml)),
    )

    proposal = RefinementProposal(
        id=uuid4(),
        incident_id=state.incident.id,
        contract_id=state.incident.contract_version_id,
        kind=draft.kind,
        proposed_yaml=draft.proposed_yaml,
        status="pending",
        created_at=datetime.now(UTC),
    )
    saved = save_refinement_proposal(proposal)
    return state.model_copy(update={"refinement_proposal": saved})


def build_causal_explainer_graph() -> CompiledStateGraph[
    CausalExplainerState, None, CausalExplainerState, CausalExplainerState
]:
    """Wire the 4 nodes into a runnable LangGraph state machine."""
    graph = StateGraph(CausalExplainerState)

    graph.add_node("investigate_incident", investigate_incident)
    graph.add_node("synthesize_hypotheses", synthesize_hypotheses)
    graph.add_node("persist_explanation", persist_explanation)
    graph.add_node("propose_refinement", propose_refinement)

    graph.set_entry_point("investigate_incident")
    graph.add_edge("investigate_incident", "synthesize_hypotheses")
    graph.add_edge("synthesize_hypotheses", "persist_explanation")
    graph.add_conditional_edges(
        "persist_explanation",
        route_after_explanation,
        {"propose_refinement": "propose_refinement", "end": END},
    )
    graph.add_edge("propose_refinement", END)

    return graph.compile()
