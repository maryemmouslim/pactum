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
from pactum.monitoring.incident_index import index_incident
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

_REFINEMENT_CONFIDENCE_THRESHOLD = 0.5


class _HypothesisDraft(BaseModel):
    cited_evidence: str = Field(
        description="The exact value(s) or fact(s) from the evidence above that support "
        "this hypothesis -- quote them directly, do not paraphrase. Write this BEFORE "
        "the description, so the description is built from a specific citation rather "
        "than a generic restatement of the check_type."
    )
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    implies_contract_issue: bool = Field(
        description="True only if the evidence says the CONTRACT's rule itself is wrong "
        "-- too strict, too loose, missing, or based on a stale assumption. False for "
        "the ordinary case: the data or upstream pipeline broke and the contract's rule "
        "was right to flag it. Do not set this true just because your description "
        "happens to mention a rule or SLA by name while describing what the check "
        "detected -- it must be an actual claim that the rule needs to change."
    )
    suggested_action: str | None = None


class _HypothesisList(BaseModel):
    hypotheses: list[_HypothesisDraft] = Field(
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
            "result": find_similar_incidents.invoke({"incident_id": str(incident.id)}),
        },
        {
            "tool": "pipeline_logs",
            "result": fetch_pipeline_logs.invoke(
                {"dataset_id": incident.dataset_id, "around": incident.detected_at.isoformat()}
            ),
        },
        {
            "tool": "calendar_events",
            "result": fetch_calendar_events.invoke(
                {"dataset_id": incident.dataset_id, "around": incident.detected_at.isoformat()}
            ),
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


_TECHNICAL_TOOLS = {
    "lineage",
    "schema_diff",
    "contract_context",
    "distribution_compare",
    "pipeline_logs",
}


def _build_synthesis_prompt(state: CausalExplainerState) -> str:
    incident = state.incident
    technical = [f for f in state.findings if f["tool"] in _TECHNICAL_TOOLS]
    contextual = [f for f in state.findings if f["tool"] not in _TECHNICAL_TOOLS]
    technical_desc = (
        "\n".join(f"- {item['tool']}: {item['result']}" for item in technical) or "None"
    )
    contextual_desc = (
        "\n".join(f"- {item['tool']}: {item['result']}" for item in contextual) or "None"
    )
    return (
        f"An incident was detected on dataset '{incident.dataset_id}':\n"
        f"  check_type: {incident.check_type}\n"
        f"  column: {incident.column_name or 'N/A (dataset-level)'}\n"
        f"  kind: {incident.kind}\n"
        f"  severity: {incident.severity}\n\n"
        f"What the check itself found -- this is direct evidence of what's wrong, "
        f"not just background metadata:\n"
        f"  {incident.payload}\n\n"
        f"Technical findings -- queried directly from the live system (schema, "
        f"data, lineage, contract, run history). Treat these as verified fact "
        f"about the current state, and prefer them as your primary grounding "
        f"(a tool coming back empty is informative too: it rules that angle "
        f"out, it doesn't mean there's nothing to explain):\n{technical_desc}\n\n"
        f"Contextual signals -- calendar notes and similar past incidents. "
        f"These are NOT verified against this specific incident. A calendar "
        f"note is someone's description of what they believe happened -- it "
        f"could be incomplete, about something unrelated, or simply wrong. Use "
        f"these only to help explain WHY a technical finding occurred, never "
        f"as a replacement for one. An unconfirmed signal that no technical "
        f"finding corroborates is a lead worth mentioning, not a "
        f"cause:\n{contextual_desc}\n\n"
        "Propose 1-3 ranked hypotheses for what caused this incident. For each "
        "hypothesis, first write cited_evidence: the exact value(s) or fact(s) "
        "from above that support it, quoted directly -- not a paraphrase, not "
        "just the check_type restated. cited_evidence must be grounded in the "
        "check's own payload or a technical finding -- a contextual signal "
        "alone is not sufficient grounding, even if it sounds like a complete "
        "explanation. If a contextual signal corroborates a technical finding, "
        "cite the technical finding and mention the contextual signal as "
        "supporting detail, not the other way around. Then write description "
        "as an actual causal explanation, not a restatement of what the check "
        "detected (e.g. 'the newest record exceeds the freshness SLA' just "
        "repeats the check's own definition; 'ingestion stopped, so no new "
        "rows arrived' explains why that's true). Set confidence (0-1) by "
        "weighing: (a) how many independent technical findings support it, "
        "(b) whether a similar past incident was found, and (c) whether the "
        "timing lines up with a known event -- (b) and (c) alone, without (a), "
        "should not push confidence above what the technical evidence "
        "justifies. Suggest a concrete next action for each. Only fall back to "
        "a vague, low-confidence hypothesis if the check's payload itself is "
        "uninformative -- do not do so just because the investigation tools "
        "found nothing. Also set implies_contract_issue: true only when the "
        "evidence says the contract's rule itself needs to change, false for "
        "the ordinary case where the data or pipeline broke and the rule was "
        "right to catch it. This drives whether a contract-change proposal "
        "gets drafted afterward, so get it right -- most incidents are "
        "pipeline/data problems, not contract problems."
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
    index_incident(state.incident, saved)
    return state.model_copy(update={"explanation": saved})


def route_after_explanation(state: CausalExplainerState) -> str:
    """Decide whether the top hypothesis warrants a contract refinement proposal.

    Reads the LLM's own explicit implies_contract_issue judgment from
    synthesis time, not a keyword guess made after the fact -- keyword
    matching on the description used to false-trigger whenever a hypothesis
    merely *mentioned* "SLA"/"contract" while describing the symptom (e.g.
    "the freshness SLA was violated"), regardless of whether it was actually
    arguing the rule itself was wrong.
    """
    if not state.hypotheses:
        return "end"
    top = state.hypotheses[0]
    implies_contract_issue = bool(top.get("implies_contract_issue", False))
    confidence = float(cast(float, top.get("confidence", 0.0)))
    if implies_contract_issue and confidence >= _REFINEMENT_CONFIDENCE_THRESHOLD:
        return "propose_refinement"
    return "end"


def _build_refinement_prompt(state: CausalExplainerState, current_contract_yaml: str) -> str:
    incident = state.incident
    top_hypothesis = state.hypotheses[0] if state.hypotheses else {}
    return (
        f"An incident on dataset '{incident.dataset_id}' (check_type={incident.check_type}, "
        f"column={incident.column_name}) was most likely caused by:\n"
        f"{top_hypothesis.get('description', '')}\n\n"
        f"The specific evidence that conclusion is grounded in (not just the "
        f"description above -- base your fix on this directly):\n"
        f"{top_hypothesis.get('cited_evidence', '')}\n\n"
        f"Here is the exact current contract YAML for this dataset:\n\n"
        f"{current_contract_yaml}\n\n"
        "Propose a specific refinement to prevent this from recurring, grounded in the "
        "evidence above: choose one kind (relaxation, tightening, new_rule, scoping), "
        "then write the FULL revised contract YAML -- copy the structure above exactly "
        "(same top-level keys: dataset_id, columns, freshness_sla_seconds, "
        "completeness_sla; same fields per column) and change only the specific "
        "value(s) that the evidence actually justifies changing. Do not invent new "
        "top-level keys and do not drop any existing column."
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
