import pandas as pd
import streamlit as st

import config
from app import services
from app.theme import flow, html, section
from src.agents import foundry_runtime
from src.azure_integration import blob, search, status


def _log_box():
    box = st.empty()
    msgs: list[str] = []

    def progress(m):
        msgs.append(m)
        box.code("\n".join(msgs[-12:]))
    return progress


def render() -> None:
    kb = config.EDUCATION_RETRIEVAL == "knowledge_base"
    section("Pipeline")
    flow([("Data Manager (CSV + Markdown)", "#0E7C86"), ("Azure Blob Storage (approved docs only)", "#2A8FC7"),
          ("Knowledge base" if kb else "Azure AI Search indexes", "#1F6FB2"), ("Foundry agents (6)", "#0E7C86"), ("Care Assistant", "#2E7D32")])
    st.caption(f"Education retrieval mode: **{'Foundry knowledge base' if kb else 'Azure AI Search index'}**  ·  agent runtime: **{config.AGENT_RUNTIME}**  ·  "
               f"auto-upload on save: **{'on' if config.AUTO_UPLOAD else 'off'}**  ·  auto-refresh search: **{'on' if config.AUTO_SYNC else 'off'}**. "
               "Change these in `.env` and restart. If something goes wrong see the switch table in the guide (Part 4).")

    section("Configuration (values are never shown)")
    st.dataframe(pd.DataFrame(status.settings_overview()), hide_index=True, width="stretch")

    section("Connection tests")
    c = st.columns(3)
    for col, label, fn in zip(c, ["Blob Storage", "AI Search", "Foundry project"], [status.test_blob, status.test_search, status.test_foundry]):
        if col.button(f"Test {label}", width="stretch"):
            ok, msg = fn()
            (col.success if ok else col.error)(msg)

    section("The six Foundry agents")
    rows = foundry_runtime.status_rows()
    st.dataframe(pd.DataFrame([{"Agent": r["agent"], "Name in Foundry": r["foundry_name"], "Registered": "yes" if r["registered"] else "no",
                                "Version": r["version"], "Up to date": "yes" if r["up_to_date"] else "no", "How": r["mode"]} for r in rows]),
                 hide_index=True, width="stretch")
    b1, b2 = st.columns(2)
    progress = _log_box()
    try:
        if b1.button("Register / update agents in Foundry", type="primary", width="stretch"):
            with st.spinner("Registering …"):
                foundry_runtime.register_all(progress=progress)
            st.success("Done. Open the Foundry portal > Agents to see them.")
        if b2.button("New version of every agent", width="stretch"):
            with st.spinner("Registering …"):
                foundry_runtime.register_all(force=True, progress=progress)
            st.success("Done.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"{type(exc).__name__}: {str(exc)[:300]}")

    section("Blob Storage (cloud copy)")
    st.caption("Only **Approved** documents are placed in `knowledge/` (what the knowledge base reads). Drafts and retired documents go to `knowledge-unapproved/`, and are removed from `knowledge/` on upload.")
    d1, d2, d3, d4 = st.columns(4)
    try:
        if d1.button("Compare with cloud", width="stretch"):
            st.dataframe(pd.DataFrame(blob.compare()), hide_index=True, width="stretch", height=300)
        if d2.button("Upload to Blob", width="stretch", type="primary"):
            with st.spinner("Uploading …"):
                st.success(str(blob.push(progress)))
        if d3.button("Download from Blob", width="stretch"):
            with st.spinner("Downloading …"):
                r = blob.pull(progress)
            st.success(f"Downloaded {r['downloaded']} file(s).")
            for x in r["rejected"]:
                st.warning("Rejected (invalid table): " + x)
        if d4.button("Refresh search side", width="stretch"):
            with st.spinner("Working …"):
                st.success(str(search.sync_for_current_mode(progress)))
    except blob.AzureNotConfigured as exc:
        st.warning(str(exc))
    except Exception as exc:  # noqa: BLE001
        st.error(f"{type(exc).__name__}: {str(exc)[:300]}")

    section("What is currently approved (would be searched)")
    plan = search.plan()
    st.dataframe(pd.DataFrame([{"Folder": f, "Index (index mode)": search.FOLDER_TO_INDEX[f], "Approved documents": len(d),
                                "IDs": ", ".join(x["article_id"] for x in d)} for f, d in plan.items()]), hide_index=True, width="stretch")
    st.caption("The Education agent reads education + FAQ only. Care-plan guidance is never attached to it.")
