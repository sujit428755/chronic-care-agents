import streamlit as st

from app import services
from app.theme import URGENCY, esc, html, section, urgency_badge


def _card(e: dict) -> None:
    c = URGENCY.get(e["urgency"], URGENCY["none"])[0]
    rv = e.get("review")
    done = f'<span class="badge soft" style="--c:#2E7D32;--bg:#E8F5E9">REVIEWED by {esc(rv["reviewer"])}</span>' if rv else ""
    html(f'<div class="triage" style="--c:{c}"><div class="t"><span class="mid">{esc(e["member_id"])}</span>{urgency_badge(e["urgency"])}{done}'
         f'<span class="when">{esc(e["timestamp"].replace("T", " "))}</span></div>'
         f'<div class="why">{esc(e["reason"])}</div>'
         f'<div class="muted" style="margin-top:4px">Rules: {esc(", ".join(e.get("rule_ids") or []) or "none")} &middot; '
         f'Sources: {esc(", ".join(e.get("source_ids") or []) or "none")} &middot; Disposition: {esc(e.get("disposition"))}'
         + (f' &middot; Queue: <b>{esc(e["queue"])}</b>' if e.get("queue") else "")
         + (f' &middot; Note: {esc(rv["note"])}' if rv and rv.get("note") else "") + '</div></div>')


def render() -> None:
    items = services.queue_items()
    items.sort(key=lambda e: (URGENCY.get(e["urgency"], URGENCY["none"])[3], e["timestamp"]))
    open_items = [e for e in items if not e["review"]]
    done_items = [e for e in items if e["review"]]

    c1, c2 = st.columns([2, 1])
    with c2:
        reviewer = st.text_input("Your name or role (for the review record)", value="Care coordinator")
    with c1:
        flt = st.multiselect("Filter by triage level", [v[2] for v in URGENCY.values()], default=[])
    keep = {k for k, v in URGENCY.items() if v[2] in flt} if flt else set(URGENCY)

    t1, t2 = st.tabs([f"Open ({len(open_items)})", f"Reviewed ({len(done_items)})"])
    with t1:
        shown = [e for e in open_items if e["urgency"] in keep]
        if not shown:
            st.success("Nothing is waiting. Ask the assistant a risky question to create an entry.")
        for e in shown[:60]:
            _card(e)
            with st.expander("Mark as reviewed", expanded=False):
                note = st.text_input("Action taken / note (do not enter real patient data)", key=f"n{e['key']}")
                if st.button("Mark reviewed", key=f"b{e['key']}", type="primary"):
                    services.mark_reviewed(e["key"], reviewer, note)
                    st.rerun()
        if len(shown) > 60:
            st.caption(f"Showing the first 60 of {len(shown)}.")
    with t2:
        if not done_items:
            st.info("No reviewed items yet.")
        for e in done_items[::-1][:60]:
            _card(e)
    st.caption("This queue holds the full synthetic member ID (staff only). The audit log holds only masked IDs.")
