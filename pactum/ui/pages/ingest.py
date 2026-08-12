from pathlib import Path

import streamlit as st

from pactum.agents.contract_generator import build_contract_generator_graph
from pactum.agents.state import ContractGeneratorState
from pactum.contract_schema import parse_contract_yaml
from pactum.registry.contract_registry import activate_version
from pactum.registry.contract_reviews import list_reviews, record_review
from pactum.sources.duckdb_adapter import DuckDBAdapter
from pactum.sources.postgres_adapter import PostgresAdapter
from pactum.sources.registry import list_registered_datasets, register_source
from pactum.ui.components import render_contract

_UPLOAD_DIR = Path(__file__).resolve().parents[3] / "examples" / "data"

st.title("Data & Contracts")
st.caption(
    "Bring in a dataset, let the Contract Generator Agent draft its contract, then "
    "approve or reject the draft. Once approved, find the dataset on the Datasets "
    "page to monitor it, view incidents, and review refinement proposals."
)

if "ingest_dataset_id" not in st.session_state:
    st.session_state.ingest_dataset_id = None
if "ingest_contract" not in st.session_state:
    st.session_state.ingest_contract = None

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
# plus whatever was just uploaded, becomes its own dataset. Also registered
# unconditionally in app.py so the Datasets page works even if this page was
# never visited this session; repeating it here picks up a fresh upload
# immediately within this same rerun.
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
    st.session_state.ingest_dataset_id = dataset_choice

if st.session_state.ingest_dataset_id:
    st.info(f"Active dataset: **{st.session_state.ingest_dataset_id}**")

st.header("2. Generate the contract")
st.caption("Runs the real Contract Generator Agent (calls the real LLM -- takes a few seconds).")

if st.button("Generate contract", disabled=not st.session_state.ingest_dataset_id):
    try:
        with st.spinner(
            "Running understand -> profile -> classify -> draft -> critique -> write..."
        ):
            app = build_contract_generator_graph()
            result = app.invoke(
                ContractGeneratorState(dataset_id=st.session_state.ingest_dataset_id)
            )
            st.session_state.ingest_contract = result["written_contract"]
    except Exception as exc:  # noqa: BLE001
        st.error(f"Contract generation failed: {exc}")
    else:
        st.success(f"Contract v{st.session_state.ingest_contract.version} written.")

if st.session_state.ingest_contract is not None:
    contract = st.session_state.ingest_contract
    parsed = parse_contract_yaml(contract.yaml)

    st.header("3. Contract rules")
    render_contract(contract, parsed)

    st.header("4. Review & approve")
    st.caption(
        "The agent's draft isn't trusted automatically -- it stays a draft "
        "until a human approves it. Approving replaces whatever was active "
        "before for this dataset; only one version can be active at a time."
    )
    status_colors = {"draft": "yellow", "active": "green", "deprecated": "gray"}
    status_labels = {"draft": "draft (unreviewed)", "active": "active"}
    st.badge(
        status_labels.get(contract.status, contract.status),
        color=status_colors.get(contract.status, "gray"),  # type: ignore[arg-type]
    )

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
                    st.session_state.ingest_contract = activated
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
                    st.session_state.ingest_contract = None
                    st.rerun()
