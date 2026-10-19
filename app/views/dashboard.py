import pandas as pd
import streamlit as st

import config
from app import services
from app.theme import flow, kpi_row, section, html


def render() -> None:
    members = services.table_df("members")
    readings = services.table_df("readings")
    tasks = services.table_df("care_plan_tasks")
    catalog = services.table_df("articles_catalog")
    queue = [q for q in services.queue_items() if not q["review"]]
    active_readings = readings[readings["status"].fillna("active").replace("", "active") == "active"]

    kpi_row([
        ("Registered members", len(members), f"{(members.consent_status == 'Active').sum()} with active consent", "#0E7C86"),
        ("Active readings", len(active_readings), f"{(readings.status == 'superseded').sum()} corrected entries kept for audit", "#2A8FC7"),
        ("Tasks needing action", int(tasks.status.isin(["Due", "Overdue"]).sum()), f"{(tasks.status == 'Overdue').sum()} overdue", "#E65100"),
        ("Open in review queue", len(queue), "waiting for a person", "#C62828"),
        ("Approved articles", int((catalog.status == "Approved").sum()), f"{(catalog.status != 'Approved').sum()} draft or retired", "#2E7D32"),
    ])

    section("How a request moves through the hospital desk")
    flow([("1 Consent check (ER-501)", "#0E7C86"), ("2 Safety checks (ER-503)", "#C62828"), ("3 Router", "#2A8FC7"),
          ("4 Specialist agent", "#0E7C86"), ("5 Rules ER-502 / ER-504", "#E65100"), ("6 Member answer + staff packet", "#2E7D32")])
    st.caption("Code decides the facts. Agents only word them. Anything risky goes to a person.")

    c1, c2 = st.columns(2)
    with c1:
        section("Consent status")
        st.bar_chart(members.consent_status.value_counts(), color="#0E7C86", height=240)
        section("Members per program")
        st.bar_chart(members.program.value_counts(), color="#2A8FC7", height=240)
    with c2:
        section("Self-reported readings per day (all members)")
        per_day = active_readings.assign(day=active_readings.recorded_at.str[:10]).groupby("day").size()
        st.line_chart(per_day, color="#0E7C86", height=240)
        section("Care plan task status")
        st.bar_chart(tasks.status.value_counts(), color="#E65100", height=240)

    section("Data tables in use")
    rows = []
    for t in ["members", "readings", "care_plan_tasks", "escalation_rules", "high_risk_values", "medication_words", "articles_catalog"]:
        rows.append({"Table": t, "Rows": len(services.table_df(t)), "File": f"data/{t}.csv"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
