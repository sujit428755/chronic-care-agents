"""Hospital-style Streamlit UI.   Run:  streamlit run app/streamlit_app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

import config  # noqa: E402
from app import theme  # noqa: E402
from app.views import about, assistant, azure_sync, dashboard, data_manager, knowledge, review_queue, tests_page  # noqa: E402
from src.middleware.audit_logging import setup_logging  # noqa: E402

st.set_page_config(page_title=f"{theme.DESK} · {theme.HOSPITAL}", page_icon="🏥", layout="wide")
theme.inject_css()
if "logging" not in st.session_state:
    setup_logging()
    st.session_state["logging"] = True

PAGES = {
    "Ward Overview": ("Ward overview", "Live summary of members, readings, tasks and the review queue", dashboard),
    "Care Assistant": ("Care assistant", "Ask on behalf of a synthetic member. See the member view and the staff packet", assistant),
    "Staff Review Queue": ("Staff review queue", "Cases the system handed to people, sorted by triage level", review_queue),
    "Data Manager": ("Data manager", "Add, convert, edit and roll back data and rules", data_manager),
    "Knowledge Base": ("Knowledge base", "Approved, versioned articles used for answers", knowledge),
    "Azure Sync": ("Azure sync", "Blob Storage, AI Search and Foundry connections", azure_sync),
    "Tests & Evidence": ("Tests and evidence", "Run the scenarios and produce the evidence document", tests_page),
    "About & Safety": ("About and safety", "Scope, safety rules and limits", about),
}
ICON = {"Ward Overview": "🩺", "Care Assistant": "💬", "Staff Review Queue": "🚑", "Data Manager": "🗂️", "Knowledge Base": "📚",
        "Azure Sync": "☁️", "Tests & Evidence": "✅", "About & Safety": "🛡️"}

with st.sidebar:
    theme.html(f'<div class="side-brand">{theme.CROSS_SVG.replace("#ffffff", "#E3F4F5")}<div class="n">{theme.DESK}<small>{theme.HOSPITAL}</small></div></div>')
    page = st.radio("Navigate", list(PAGES), format_func=lambda p: f"{ICON[p]}  {p}", label_visibility="collapsed")
    st.divider()
    offline = st.toggle("Offline mode (templates, no Azure)", value=config.OFFLINE, help="Same rules and workflow. Only the wording is template based.")
    if offline != config.OFFLINE:
        config.set_offline(offline)
    st.caption("Synthetic data only. Not for clinical use.")

title, sub, module = PAGES[page]
if "startup_done" not in st.session_state:
    st.session_state["startup_done"] = True
    from app import services
    from src.agents import foundry_runtime
    from src.azure_integration import blob
    if config.PULL_ON_START and blob.is_configured():
        try:
            blob.pull()
        except Exception as exc:  # noqa: BLE001
            st.session_state["startup_warning"] = f"Could not download from Blob Storage: {type(exc).__name__}: {str(exc)[:160]}"
    warn = foundry_runtime.ensure_registered()
    if warn:
        st.session_state["startup_warning"] = warn

theme.topbar(title, sub)
from app import services as _services  # noqa: E402
theme.pipeline_strip(_services.pipeline_status())
if st.session_state.get("startup_warning"):
    st.warning(st.session_state["startup_warning"])
module.render()
