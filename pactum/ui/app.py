from pathlib import Path

import streamlit as st

from pactum.agents.contract_generator import build_contract_generator_graph
from pactum.agents.state import ContractGeneratorState
from pactum.contract_schema import parse_contract_yaml
from pactum.monitoring.runner import evaluate_contract
from pactum.registry.contract_registry import activate_version
from pactum.registry.contract_reviews import list_reviews, record_review
from pactum.sources.duckdb_adapter import DuckDBAdapter
from pactum.sources.postgres_adapter import PostgresAdapter
from pactum.sources.registry import list_registered_datasets, register_source
from pactum.tools.profile_columns import profile_column, sample_data

_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "examples" / "data"

st.set_page_config(page_title="Pactum", page_icon="\U0001f4cb", layout="wide")
st.title("Pactum")
st.caption("Upload a dataset, let the agent draft its contract, then check live data against it.")

if "dataset_id" not in st.session_state:
    st.session_state.dataset_id = None
if "contract" not in st.session_state:
    st.session_state.contract = None

st.header("1. Bring in your data")
st.caption(
    "Bring in data from files and/or a database, together -- everything you load "
    "becomes available at once, so rules that reference another dataset "
    "(like a customer_id foreign key) have something real to check against."
)

st.subheader("Files (CSV or JSON)")
uploaded_files = st.file_uploader(
    "Upload file(s)", type=["csv", "json"], accept_multiple_files=True
)
for uploaded in uploaded_files:
    (_UPLOAD_DIR / uploaded.name).write_bytes(uploaded.getvalue())
if uploaded_files:
    st.success(f"Saved {len(uploaded_files)} file(s) to examples/data/")

# Registering scans the whole directory -- every CSV/JSON file already there,
# plus whatever was just uploaded, becomes its own dataset.
register_source(DuckDBAdapter(str(_UPLOAD_DIR)))

st.subheader("...or a Postgres database")
connection_url = st.text_input(
    "Connection URL", type="password", placeholder="postgresql://user:password@host:5432/dbname"
)
if st.button("Connect", disabled=not connection_url):
    try:
        adapter = PostgresAdapter(connection_url)
        register_source(adapter)
        st.success(f"Connected. Found tables: {', '.join(adapter.list_datasets()) or '(none)'}")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not connect: {exc}")

# Pulled from the registry, not just the upload directory, so it reflects
# everything loaded so far -- files and any connected database's tables.
available_datasets = list_registered_datasets()
if available_datasets:
    st.write(f"Currently loaded datasets: {', '.join(available_datasets)}")

dataset_choice = st.selectbox(
    "Which dataset should the agent generate a contract for?",
    ["(choose one)", *available_datasets],
)
if dataset_choice != "(choose one)":
    st.session_state.dataset_id = dataset_choice

if st.session_state.dataset_id:
    st.info(f"Active dataset: **{st.session_state.dataset_id}**")

st.header("2. Generate the contract")
st.caption("Runs the real Contract Generator Agent (calls the real LLM -- takes a few seconds).")

if st.button("Generate contract", disabled=not st.session_state.dataset_id):
    try:
        with st.spinner(
            "Running understand -> profile -> classify -> draft -> critique -> write..."
        ):
            app = build_contract_generator_graph()
            result = app.invoke(ContractGeneratorState(dataset_id=st.session_state.dataset_id))
            st.session_state.contract = result["written_contract"]
    except Exception as exc:  # noqa: BLE001
        st.error(f"Contract generation failed: {exc}")
    else:
        st.success(f"Contract v{st.session_state.contract.version} written.")

if st.session_state.contract is not None:
    contract = st.session_state.contract
    parsed = parse_contract_yaml(contract.yaml)

    st.header("3. Contract rules")
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
        use_container_width=True,
    )
    st.caption(
        f"Dataset-level: freshness SLA = {parsed.freshness_sla_seconds}s, "
        f"completeness SLA = {parsed.completeness_sla}"
    )

    st.header("4. Review & approve")
    st.caption(
        "The agent's draft isn't trusted automatically -- it stays a draft "
        "until a human approves it. Approving replaces whatever was active "
        "before for this dataset; only one version can be active at a time."
    )
    status_labels = {"draft": "\U0001f7e1 draft (unreviewed)", "active": "\U0001f7e2 active"}
    st.write(f"Status: **{status_labels.get(contract.status, contract.status)}**")

    try:
        past_reviews = list_reviews(contract.id)
    except Exception as exc:  # noqa: BLE001
        past_reviews = []
        st.error(f"Could not load review history: {exc}")
    for review in past_reviews:
        reason_suffix = f' -- "{review.reason}"' if review.reason else ""
        st.caption(
            f"{review.decision} by {review.reviewed_by} at {review.reviewed_at}{reason_suffix}"
        )

    if contract.status == "draft":
        approve_col, reject_col = st.columns(2)
        with approve_col:
            if st.button("Approve"):
                try:
                    activated = activate_version(contract.dataset_id, contract.version)
                    record_review(contract.id, "approved", reviewed_by="ui-user")
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
                else:
                    st.session_state.contract = activated
                    st.rerun()
        with reject_col:
            rejection_reason = st.text_input(
                "Reason for rejecting (required)", key="rejection_reason"
            )
            if st.button("Reject", disabled=not rejection_reason):
                try:
                    record_review(
                        contract.id, "rejected", reviewed_by="ui-user", reason=rejection_reason
                    )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Could not record rejection: {exc}")
                else:
                    st.session_state.contract = None
                    st.rerun()

    st.header("5. Metadata")
    profiles = profile_column.invoke({"dataset_id": st.session_state.dataset_id})
    st.dataframe(
        [{"column": name, **stats} for name, stats in profiles.items()],
        use_container_width=True,
    )
    with st.expander("Sample rows"):
        st.dataframe(sample_data.invoke({"dataset_id": st.session_state.dataset_id}))

    st.header("6. Run checks")
    if st.button("Run checks"):
        try:
            with st.spinner("Evaluating adherence + drift checks..."):
                outcomes = evaluate_contract(st.session_state.dataset_id, parsed, contract.id)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Running checks failed: {exc}")
        else:
            failed = [o for o in outcomes if o.status == "failed"]
            passed = [o for o in outcomes if o.status == "passed"]
            skipped = [o for o in outcomes if o.status == "skipped"]
            st.write(f"**{len(failed)} failed** · {len(passed)} passed · {len(skipped)} skipped")

            st.dataframe(
                [
                    {
                        "status": {"failed": "❌", "passed": "✅", "skipped": "⏭"}[o.status],
                        "check_type": o.check_type,
                        "column": o.column,
                        "message": o.message,
                    }
                    for o in outcomes
                ],
                use_container_width=True,
            )
