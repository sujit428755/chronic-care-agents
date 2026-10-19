import streamlit as st

import config
from app import services
from app.theme import esc, html, section
from app.views.data_manager import _after_save, _document_form
from src.ingest import documents
from src.knowledge import search_local
from src.tools.store import load_table


def render() -> None:
    cat = services.table_df("articles_catalog")
    t = st.tabs(["Catalog", "Read / edit a document", "Try retrieval"])
    with t[0]:
        c1, c2, c3 = st.columns(3)
        typ = c1.multiselect("Type", sorted(cat.type.unique()))
        stat = c2.multiselect("Status", sorted(cat.status.unique()))
        prog = c3.multiselect("Program", sorted(cat.program.unique()))
        df = cat
        if typ: df = df[df.type.isin(typ)]
        if stat: df = df[df.status.isin(stat)]
        if prog: df = df[df.program.isin(prog)]
        st.dataframe(df.drop(columns=["file"]), hide_index=True, width="stretch", height=420)
        st.caption("Only Approved documents are indexed in Azure AI Search and cited by the assistant. "
                   "EDU = education, FAQ = program FAQ, CPG = care plan guidance (three separate indexes).")
    with t[1]:
        pick = st.selectbox("Document", list(cat.article_id), format_func=lambda a: f"{a} · {cat.set_index('article_id').loc[a, 'title']}")
        row, body = documents.read_article(pick)
        html(f'<div class="card"><h4>{esc(row["title"])}</h4><span class="src-chip">{esc(pick)} {esc(row["version"])}</span>'
             f'<span class="src-chip">{esc(row["status"])}</span><span class="src-chip">{esc(row["program"])}</span></div>')
        st.markdown(body)
        c1, c2 = st.columns(2)
        who = c1.text_input("Approver (name or role)", key="kb_who")
        new_status = c2.selectbox("Change status", ["Approved", "Draft", "Retired"], index=["Approved", "Draft", "Retired"].index(row["status"]))
        if st.button("Apply status", key="kb_status"):
            try:
                documents.set_status(pick, new_status, who)
                _after_save(f"{pick} is now {new_status}.")
            except ValueError as exc:
                st.error(str(exc))
        with st.expander("Edit this document (creates a new version)"):
            _document_form(f"edit_{pick}", row["title"], body, existing=row)
    with t[2]:
        st.caption("This is the offline keyword search. Online, the Foundry agent uses Azure AI Search (hybrid + semantic + vector).")
        c1, c2 = st.columns([3, 1])
        q = c1.text_input("Ask a question", value="What is a home reading?")
        program = c2.selectbox("Member program", ["Diabetes Support", "Hypertension Support", "Cardiac Wellness"])
        hits = search_local(q, ("education", "faq"), program=program) if q else []
        if not hits:
            st.warning("No approved article matches. The assistant would state a knowledge gap and offer staff follow-up.")
        for h in hits[:4]:
            st.markdown(f"**{h['article_id']} {h['version']}**, {h['title']}  (score {h['score']})")
            st.caption(h["content"][:240].replace("\n", " ") + "…")
