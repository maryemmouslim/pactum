from pactum.lineage.graph import load_graph
from pactum.models import Contract
from pactum.registry.contract_registry import get_active
from pactum.sources.business_context import get_business_context
from pactum.sources.registry import get_adapter
from pactum.tools import tool


@tool
def inspect_schema(dataset_id: str) -> dict[str, str]:
    """Return {column_name: data_type} for a dataset.

    Args:
        dataset_id: Fully-qualified dataset identifier.

    Returns:
        Mapping of column name to its source data type.
    """
    adapter = get_adapter(dataset_id)
    return adapter.get_schema(dataset_id)


@tool
def fetch_upstream_contract(dataset_id: str) -> list[Contract]:
    """Return the active contracts of any datasets upstream of this one.

    Args:
        dataset_id: Fully-qualified dataset identifier.

    Returns:
        The active Contract for each upstream dataset that has one. Empty
        if no lineage is known or no upstream dataset has an active contract.
    """
    graph = load_graph()
    contracts = []
    for upstream_id in graph.upstream_of(dataset_id):
        contract = get_active(upstream_id)
        if contract is not None:
            contracts.append(contract)
    return contracts


@tool
def fetch_business_context(dataset_id: str) -> str | None:
    """Return human-written context describing what this dataset means.

    Args:
        dataset_id: Fully-qualified dataset identifier.

    Returns:
        Free-text description if one has been registered, else None.
    """
    return get_business_context(dataset_id)
