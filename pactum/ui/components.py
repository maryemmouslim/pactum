import streamlit as st

from pactum.contract_schema import ParsedContract
from pactum.models import Contract


def render_contract(contract: Contract, parsed: ParsedContract) -> None:
    """Show a contract as both raw YAML text and a structured rules table.

    Shared by the ingest page (reviewing a freshly drafted contract before
    approving it) and the datasets page (viewing any dataset's current
    contract), so both stay in sync instead of drifting into two renderings.
    """
    st.code(contract.yaml, language="yaml")
    st.dataframe(
        [
            {
                "column": rule.name,
                "data_type": rule.data_type,
                "semantic_type": rule.semantic_type,
                "sensitive": rule.sensitivity,
                "nullable": rule.nullable,
                "unique": rule.unique,
                "min": rule.min_value,
                "max": rule.max_value,
                "allowed_values": rule.allowed_values,
                "regex_pattern": rule.regex_pattern,
                "references": (
                    f"{rule.references_dataset}.{rule.references_column}"
                    if rule.references_dataset
                    else None
                ),
            }
            for rule in parsed.columns
        ],
        width="stretch",
    )
    st.caption(
        f"Dataset-level: freshness SLA = {parsed.freshness_sla_seconds}s, "
        f"completeness SLA = {parsed.completeness_sla}"
    )
