import json

import pandas as pd
import streamlit as st

import config
from app import services
from app.theme import kpi_row, section


def render() -> None:
    st.caption("Runs the 14 scenarios (T1 to T6 core scenarios plus 8 extra) and writes docs/test_evidence.md. "
               "For submission run the ONLINE suite once your endpoints are in .env.")
    mode = st.radio("Mode", ["Offline (templates, no Azure)", "Online (Foundry agents)"], horizontal=True, index=0 if config.OFFLINE else 1)
    if st.button("Run all tests", type="primary"):
        with st.spinner("Running 14 scenarios …"):
            code, out = services.run_test_suite(mode.startswith("Offline"))
        st.session_state["test_out"] = out
    res_file = config.DOCS_DIR / "test_results.json"
    if res_file.exists():
        data = json.loads(res_file.read_text(encoding="utf-8"))
        results = data["results"] if isinstance(data, dict) and "results" in data else data
        if isinstance(results, list) and results:
            passed = sum(1 for r in results if r.get("passed"))
            kpi_row([("Scenarios", len(results), "T1 to T13", "#0E7C86"), ("Passed", passed, "", "#2E7D32"), ("Failed", len(results) - passed, "", "#C62828" if len(results) - passed else "#2E7D32")])
            st.dataframe(pd.DataFrame([{"ID": r.get("id"), "Scenario": r.get("title"), "Result": "PASS" if r.get("passed") else "FAIL",
                                        "Disposition": r.get("disposition", "")} for r in results]), hide_index=True, width="stretch")
    ev = config.DOCS_DIR / "test_evidence.md"
    if ev.exists():
        with st.expander("Full test evidence (docs/test_evidence.md)"):
            st.markdown(ev.read_text(encoding="utf-8"))
        st.download_button("Download test evidence", ev.read_bytes(), "test_evidence.md")
    if "test_out" in st.session_state:
        with st.expander("Runner output"):
            st.code(st.session_state["test_out"][-4000:])
