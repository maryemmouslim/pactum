from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import streamlit as st
import streamlit.components.v1 as components

from pactum.contract_schema import parse_contract_yaml
from pactum.monitoring.explanation_store import (
    get_explanations_for_incident,
    list_explanations_for_dataset,
)
from pactum.monitoring.incident_store import list_incidents_for_dataset
from pactum.monitoring.refinement_store import (
    list_pending_refinements_for_dataset,
    update_refinement_status,
)
from pactum.monitoring.runner import evaluate_contract
from pactum.registry.contract_registry import (
    activate_version,
    create_version,
    get_active,
    get_by_id,
    list_history,
)
from pactum.sources.registry import list_registered_datasets
from pactum.tools.profile_columns import profile_column, sample_data
from pactum.ui.components import render_contract

_RECENT_WINDOW = timedelta(days=7)


@dataclass
class DatasetStatus:
    dataset_id: str
    pending_proposals: int
    recent_incidents: int

    @property
    def needs_attention(self) -> bool:
        return self.pending_proposals > 0 or self.recent_incidents > 0


def _dataset_status(dataset_id: str) -> DatasetStatus:
    try:
        pending = len(list_pending_refinements_for_dataset(dataset_id))
    except Exception:  # noqa: BLE001
        pending = 0
    try:
        incidents = list_incidents_for_dataset(dataset_id, limit=50)
    except Exception:  # noqa: BLE001
        incidents = []
    cutoff = datetime.now(UTC) - _RECENT_WINDOW
    recent = sum(1 for i in incidents if i.detected_at >= cutoff)
    return DatasetStatus(dataset_id, pending, recent)


st.title("Datasets")
st.caption(
    "Pick a dataset to see its contract, metadata, incidents, and any pending "
    "refinement proposals -- all fetched fresh, not tied to what you last generated."
)

datasets = list_registered_datasets()
if not datasets:
    st.info("No datasets registered yet -- go to \U0001f4e5 Data & Contracts to bring one in.")
    st.stop()

statuses = [_dataset_status(dataset_id) for dataset_id in datasets]

with st.container(border=True):
    metric_cols = st.columns(3)
    metric_cols[0].metric("Datasets", len(datasets))
    metric_cols[1].metric("Pending proposals", sum(s.pending_proposals for s in statuses))
    metric_cols[2].metric("Incidents (7d)", sum(s.recent_incidents for s in statuses))

st.subheader("Overview")
if "selected_dataset_id" not in st.session_state:
    st.session_state.selected_dataset_id = datasets[0]

for status in statuses:
    with st.container(border=True):
        name_col, badge_col, action_col = st.columns([3, 3, 1])
        is_selected = status.dataset_id == st.session_state.selected_dataset_id
        name_col.write(f"**{status.dataset_id}**" + ("  \U0001f4cd" if is_selected else ""))
        with badge_col:
            if status.pending_proposals:
                st.badge(f"{status.pending_proposals} pending", icon="\U0001f534", color="red")
            if status.recent_incidents:
                st.badge(
                    f"{status.recent_incidents} incident(s), 7d",
                    icon="⚠️",
                    color="orange",
                )
            if not status.needs_attention:
                st.badge("all clear", icon="✅", color="green")
        with action_col:
            if st.button(
                "Open", key=f"open-{status.dataset_id}", disabled=is_selected, width="stretch"
            ):
                st.session_state.selected_dataset_id = status.dataset_id
                st.session_state.scroll_to_detail = True
                st.rerun()

selected = st.session_state.selected_dataset_id

st.divider()
st.markdown('<div id="dataset-detail"></div>', unsafe_allow_html=True)
st.header(selected)

if st.session_state.pop("scroll_to_detail", False):
    # Overview list above pushes this section below the fold every time a
    # dataset is opened -- without this, switching datasets silently leaves
    # the user scrolled at the top of the page, behind the whole list.
    components.html(
        """<script>
        // A delayed retry, not a single immediate call -- content still
        // settling above the anchor (badges, buttons finishing their paint)
        // can shift it after one scroll, so re-assert the position twice.
        function scrollToDetail() {
            window.parent.document.getElementById("dataset-detail")
                ?.scrollIntoView({behavior: "instant", block: "start"});
        }
        scrollToDetail();
        setTimeout(scrollToDetail, 250);
        setTimeout(scrollToDetail, 700);
        </script>""",
        height=0,
    )

active_contract = get_active(selected)
contract = active_contract
if contract is None:
    history = list_history(selected)
    if history:
        contract = history[-1]
        st.warning(
            f"No active contract for '{selected}' -- showing the latest draft "
            f"(v{contract.version}). Go to \U0001f4e5 Data & Contracts to review and approve it."
        )
    else:
        st.info(
            f"No contract generated yet for '{selected}'. Go to \U0001f4e5 Data & "
            "Contracts to generate one."
        )

if contract is not None:
    parsed = parse_contract_yaml(contract.yaml)

    try:
        incidents = list_incidents_for_dataset(selected)
    except Exception as exc:  # noqa: BLE001
        incidents = []
        st.error(f"Could not load incidents: {exc}")
    incidents_by_id = {incident.id: incident for incident in incidents}

    def _incident_label(incident_id: UUID) -> str:
        incident = incidents_by_id.get(incident_id)
        if incident is None:
            return f"incident {incident_id}"
        target = f" on `{incident.column_name}`" if incident.column_name else " (dataset-level)"
        return f"{incident.check_type}{target} — detected {incident.detected_at}"

    try:
        explanations = list_explanations_for_dataset(selected)
    except Exception as exc:  # noqa: BLE001
        explanations = []
        st.error(f"Could not load investigated incidents: {exc}")

    try:
        pending_proposals = list_pending_refinements_for_dataset(selected)
    except Exception as exc:  # noqa: BLE001
        pending_proposals = []
        st.error(f"Could not load pending refinement proposals: {exc}")

    tab_contract, tab_metadata, tab_checks, tab_incidents, tab_investigated, tab_proposals = (
        st.tabs(
            [
                "\U0001f4c4 Contract",
                "\U0001f4ca Metadata",
                "✅ Run checks",
                f"\U0001f6a8 Incidents ({len(incidents)})",
                f"\U0001f50d Investigated ({len(explanations)})",
                f"\U0001f501 Proposals ({len(pending_proposals)})",
            ]
        )
    )

    with tab_contract:
        contract_status_colors = {"draft": "yellow", "active": "green", "deprecated": "gray"}
        st.badge(
            contract.status,
            color=contract_status_colors.get(contract.status, "gray"),  # type: ignore[arg-type]
        )
        render_contract(contract, parsed)

    with tab_metadata:
        profiles = profile_column.invoke({"dataset_id": selected})
        st.dataframe(
            [{"column": name, **stats} for name, stats in profiles.items()],
            width="stretch",
        )
        with st.expander("Sample rows"):
            st.dataframe(sample_data.invoke({"dataset_id": selected}))

    with tab_checks:
        if st.button("Run checks", key=f"run-checks-{selected}"):
            try:
                with st.spinner("Evaluating adherence + drift checks..."):
                    outcomes = evaluate_contract(selected, parsed, contract.id)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Running checks failed: {exc}")
            else:
                failed = [o for o in outcomes if o.status == "failed"]
                passed = [o for o in outcomes if o.status == "passed"]
                skipped = [o for o in outcomes if o.status == "skipped"]
                st.write(
                    f"**{len(failed)} failed** · {len(passed)} passed · {len(skipped)} skipped"
                )
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
                    width="stretch",
                )

    with tab_incidents:
        if not incidents:
            st.caption("No incidents recorded for this dataset.")
        severity_colors = {"low": "gray", "medium": "orange", "high": "red"}
        for incident in incidents:
            with st.container(border=True):
                column_suffix = f" on `{incident.column_name}`" if incident.column_name else ""
                cols = st.columns([1, 4])
                with cols[0]:
                    st.badge(
                        incident.severity,
                        color=severity_colors.get(incident.severity, "gray"),  # type: ignore[arg-type]
                    )
                with cols[1]:
                    st.write(f"**{incident.check_type}**{column_suffix}")
                    st.caption(f"detected {incident.detected_at}")

    with tab_investigated:
        st.caption(
            "Ranked hypotheses and the full reasoning trace behind each incident the "
            "Causal Explanation Agent has investigated for this dataset."
        )
        if not explanations:
            st.caption("No incidents investigated yet for this dataset.")
        for explanation in explanations:
            with st.expander(_incident_label(explanation.incident_id)):
                for hypothesis in explanation.hypotheses:
                    st.write(
                        f"**{hypothesis.confidence:.0%} confidence** -- {hypothesis.description}"
                    )
                    if hypothesis.cited_evidence:
                        st.caption(f"Cited evidence: {hypothesis.cited_evidence}")
                    if hypothesis.suggested_action:
                        st.caption(f"Suggested action: {hypothesis.suggested_action}")
                with st.expander("Reasoning trace"):
                    st.json(explanation.reasoning_trace)

    with tab_proposals:
        st.caption(
            "Contract changes the Causal Explanation Agent proposed after investigating "
            "an incident on this dataset. Proposals never auto-apply -- accepting one "
            "activates a new contract version."
        )
        if not pending_proposals:
            st.caption("No proposals waiting for review.")
        for proposal in pending_proposals:
            with st.container(border=True):
                st.badge(proposal.kind, color="violet")
                st.caption(_incident_label(proposal.incident_id))

                try:
                    proposal_explanations = get_explanations_for_incident(proposal.incident_id)
                except Exception as exc:  # noqa: BLE001
                    proposal_explanations = []
                    st.error(f"Could not load the reasoning behind this proposal: {exc}")

                if proposal_explanations:
                    st.write("*Why this was proposed:*")
                    for hypothesis in proposal_explanations[0].hypotheses:
                        st.write(
                            f"- **{hypothesis.confidence:.0%} confidence** -- "
                            f"{hypothesis.description}"
                        )
                        if hypothesis.cited_evidence:
                            st.caption(f"Cited evidence: {hypothesis.cited_evidence}")

                st.code(proposal.proposed_yaml, language="yaml")
                accept_col, reject_col = st.columns(2)
                with accept_col:
                    if st.button("Accept", key=f"accept-{proposal.id}"):
                        try:
                            proposal_contract = get_by_id(proposal.contract_id)
                            if proposal_contract is None:
                                raise ValueError(
                                    f"Contract {proposal.contract_id} no longer exists"
                                )
                            new_version = create_version(
                                proposal_contract.dataset_id,
                                proposal.proposed_yaml,
                                created_by="refinement-proposal",
                            )
                            activate_version(new_version.dataset_id, new_version.version)
                            update_refinement_status(proposal.id, "accepted")
                        except Exception as exc:  # noqa: BLE001
                            st.error(str(exc))
                        else:
                            st.rerun()
                with reject_col:
                    rejection_reason = st.text_input(
                        "Reason for rejecting (required)", key=f"reject-reason-{proposal.id}"
                    )
                    if st.button(
                        "Reject", key=f"reject-{proposal.id}", disabled=not rejection_reason
                    ):
                        try:
                            update_refinement_status(
                                proposal.id, "rejected", reason=rejection_reason
                            )
                        except Exception as exc:  # noqa: BLE001
                            st.error(str(exc))
                        else:
                            st.rerun()
