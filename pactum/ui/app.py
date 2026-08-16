from pathlib import Path

import streamlit as st

from pactum.sources.duckdb_adapter import DuckDBAdapter
from pactum.sources.registry import register_source

_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "examples" / "data"

st.set_page_config(page_title="Pactum", page_icon="\U0001f4cb", layout="wide")

# Dark sidebar against the light theme in .streamlit/config.toml -- config.toml
# alone can't target just the sidebar (secondaryBackgroundColor bleeds into
# other widgets too), so this uses Streamlit's own stable data-testid hooks.
st.html(
    """
    <style>
    [data-testid="stSidebar"] { background-color: #111827; }
    [data-testid="stSidebar"] * { color: #E5E7EB; }
    [data-testid="stSidebarNavLink"][aria-current="page"] {
        background-color: #6366F1;
        border-radius: 0.5rem;
    }
    [data-testid="stSidebarNavLink"][aria-current="page"] * { color: #FFFFFF; }
    </style>
    """
)

# Rendered before st.navigation() so it lands above the nav links in the
# sidebar -- the app otherwise has no identity anywhere but the browser tab.
with st.sidebar:
    st.markdown(
        "### \U0001f4cb Pactum\n"
        "<span style='color:#9CA3AF;font-size:0.85rem;'>"
        "Living data contracts</span>",
        unsafe_allow_html=True,
    )
    st.markdown("")

# Registered here, not just on the ingest page -- so the Datasets page works
# correctly even if a user opens it directly without visiting Data &
# Contracts first this session.
register_source(DuckDBAdapter(str(_UPLOAD_DIR)))

pages = {
    "Setup": [st.Page("pages/ingest.py", title="Data & Contracts", icon="\U0001f4e5")],
    "Monitor": [st.Page("pages/datasets.py", title="Datasets", icon="\U0001f4ca")],
}
navigation = st.navigation(pages)
navigation.run()
