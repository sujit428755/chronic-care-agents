import streamlit as st

import config
from app import services
from app.theme import html, section


def render() -> None:
    html('<div class="card"><h4>What this system will never do</h4>'
         '<b>It never diagnoses, never gives medical advice and never changes medicines.</b> Its job is to organise information '
         'and hand risky cases to people.</div>')
    c1, c2 = st.columns(2)
    with c1:
        section("What it does")
        st.markdown("- Checks consent first (ER-501)\n- Summarises self-reported readings, describing only (no judgement)\n- Lists care plan tasks and drafts a reminder in the member's channel\n"
                    "- Answers education questions only from approved, versioned articles, with citations\n- Sends rule matches and unclear cases to the staff review queue")
    with c2:
        section("How safety is enforced")
        st.markdown("- Facts are computed by code. Agents only word them.\n- Wording with diagnosis, judgement or medication advice is rejected and replaced by a template\n"
                    "- Numbers in the wording must come from the facts\n- Each agent can use only its own tools\n- Audit log has masked IDs and no message text")
    section("Rules")
    st.dataframe(services.table_df("escalation_rules"), hide_index=True, width="stretch")
    st.caption("ER-502 values are demo placeholders, not clinical thresholds. Clinicians must set real values before any real use.")
    st.warning(config.DISCLAIMER)
