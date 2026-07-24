from typing import cast

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

from pactum.agents.state import ContractGeneratorState
from pactum.llm import get_llm
from pactum.registry.contract_registry import create_version
from pactum.tools.classify_semantics import classify_semantic_type
from pactum.tools.profile_columns import profile_column, sample_data
from pactum.tools.understand_source import (
    fetch_business_context,
    fetch_upstream_contract,
    inspect_schema,
)


class CritiqueResult(BaseModel):
    approved: bool = Field(description="True if the draft contract has no significant gaps.")
    feedback: str = Field(description="What is missing or wrong, if not approved.")


def understand_source(state: ContractGeneratorState) -> ContractGeneratorState:
    """Node 1: gather schema, upstream contracts, and business context for a dataset."""
    return state.model_copy(
        update={
            "columns": inspect_schema.invoke({"dataset_id": state.dataset_id}),
            "upstream_contracts": fetch_upstream_contract.invoke({"dataset_id": state.dataset_id}),
            "business_context": fetch_business_context.invoke({"dataset_id": state.dataset_id}),
        }
    )


def profile_columns(state: ContractGeneratorState) -> ContractGeneratorState:
    """Node 2: sample rows and compute per-column statistics for a dataset."""
    return state.model_copy(
        update={
            "samples": sample_data.invoke({"dataset_id": state.dataset_id}),
            "column_profiles": profile_column.invoke({"dataset_id": state.dataset_id}),
        }
    )


def classify_semantics(state: ContractGeneratorState) -> ContractGeneratorState:
    """Node 3: classify the semantic type of each column using an LLM."""
    classifications = {}
    for column_name, data_type in (state.columns or {}).items():
        classifications[column_name] = classify_semantic_type.invoke(
            {
                "column_name": column_name,
                "data_type": data_type,
                "profile": state.column_profiles.get(column_name, {}),
                "samples": [row.get(column_name) for row in state.samples],
            }
        )
    return state.model_copy(update={"semantic_classifications": classifications})


def _build_draft_prompt(state: ContractGeneratorState) -> str:
    columns_desc = "\n".join(
        f"- {name} ({data_type}): semantic type = "
        f"{state.semantic_classifications.get(name, {}).get('label', 'unknown')}, "
        f"null% = {state.column_profiles.get(name, {}).get('null_percent', 'unknown')}"
        for name, data_type in (state.columns or {}).items()
    )
    upstream_desc = "\n".join(c.yaml for c in state.upstream_contracts) or "None"
    feedback_desc = (
        f"\nThe previous draft was rejected during review. Fix this specific issue:\n"
        f"{state.critique_feedback}\n"
        if state.critique_feedback
        else ""
    )
    return (
        f"Dataset: {state.dataset_id}\n"
        f"Business context: {state.business_context or 'None provided'}\n\n"
        f"Columns:\n{columns_desc}\n\n"
        f"Upstream contracts:\n{upstream_desc}\n"
        f"{feedback_desc}\n"
        "Write a data contract for this dataset in ODCS (Open Data Contract Standard) "
        "YAML format. Add an 'x-pactum:sensitivity: true' field on any column classified "
        "as pii. Output only the YAML, no explanation."
    )


def draft_contract(state: ContractGeneratorState) -> ContractGeneratorState:
    """Node 4: draft an ODCS contract in YAML from everything gathered so far."""
    llm = get_llm("reasoning")
    response = llm.invoke(_build_draft_prompt(state))
    return state.model_copy(update={"draft_yaml": cast(str, response.content)})


def self_critique(state: ContractGeneratorState) -> ContractGeneratorState:
    """Node 5: have the LLM re-read the draft and flag any gaps."""
    llm = get_llm("fast").with_structured_output(CritiqueResult)
    prompt = (
        f"Here is a draft data contract:\n\n{state.draft_yaml}\n\n"
        "Does it have any significant gaps (missing constraints, dropped upstream "
        "rules, no SLA where one is clearly needed)? Fill in the form."
    )
    result = cast(CritiqueResult, llm.invoke(prompt))

    update: dict[str, object] = {"critique_approved": result.approved}
    if not result.approved:
        update["critique_feedback"] = result.feedback
        update["revision_count"] = state.revision_count + 1
    return state.model_copy(update=update)


def route_after_critique(state: ContractGeneratorState) -> str:
    """Decide the next node after self_critique: revise the draft or write it."""
    if state.critique_approved or state.revision_count >= 2:
        return "write_contract"
    return "draft_contract"


def write_contract(state: ContractGeneratorState) -> ContractGeneratorState:
    """Node 6: persist the drafted contract as a new draft version in the registry."""
    contract = create_version(
        dataset_id=state.dataset_id,
        yaml=state.draft_yaml or "",
        created_by="contract-generator-agent",
    )
    return state.model_copy(update={"written_contract": contract})


def build_contract_generator_graph() -> CompiledStateGraph[
    ContractGeneratorState, None, ContractGeneratorState, ContractGeneratorState
]:
    """Wire the 6 nodes into a runnable LangGraph state machine."""
    graph = StateGraph(ContractGeneratorState)

    graph.add_node("understand_source", understand_source)
    graph.add_node("profile_columns", profile_columns)
    graph.add_node("classify_semantics", classify_semantics)
    graph.add_node("draft_contract", draft_contract)
    graph.add_node("self_critique", self_critique)
    graph.add_node("write_contract", write_contract)

    graph.set_entry_point("understand_source")
    graph.add_edge("understand_source", "profile_columns")
    graph.add_edge("profile_columns", "classify_semantics")
    graph.add_edge("classify_semantics", "draft_contract")
    graph.add_edge("draft_contract", "self_critique")
    graph.add_conditional_edges(
        "self_critique",
        route_after_critique,
        {"draft_contract": "draft_contract", "write_contract": "write_contract"},
    )
    graph.add_edge("write_contract", END)

    return graph.compile()
