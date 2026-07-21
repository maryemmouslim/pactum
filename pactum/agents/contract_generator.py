from pactum.agents.state import ContractGeneratorState
from pactum.tools.understand_source import (
    fetch_business_context,
    fetch_upstream_contract,
    inspect_schema,
)


def understand_source(state: ContractGeneratorState) -> ContractGeneratorState:
    """Node 1: gather schema, upstream contracts, and business context for a dataset."""
    return state.model_copy(
        update={
            "columns": inspect_schema.invoke({"dataset_id": state.dataset_id}),
            "upstream_contracts": fetch_upstream_contract.invoke({"dataset_id": state.dataset_id}),
            "business_context": fetch_business_context.invoke({"dataset_id": state.dataset_id}),
        }
    )
