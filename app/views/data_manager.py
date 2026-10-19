import pandas as pd
import streamlit as st

import config
from app import services
from app.theme import html, section
from src.ingest import documents, pii, tables
from src.ingest.readers import UploadError, read_upload
from src.schemas import SCHEMAS, UPLOAD_TARGETS
from src.tools import store
from src.tools.rules_tools import evaluate_high_risk, is_medication_change_request

ALL_TABLES = ["members", "readings", "care_plan_tasks", "escalation_rules", "high_risk_values", "medication_words", "articles_catalog"]


def _after_save(msg: str) -> None:
    st.success(msg)
    note = services.maybe_autosync()
    if note:
        st.info(note)


# ------------------------------------------------------------------ Browse
def _browse() -> None:
    name = st.selectbox("Table", ALL_TABLES, format_func=lambda n: f"{SCHEMAS[n].title}  ({n}.csv)")
    st.caption(SCHEMAS[name].help)
    df = services.table_df(name)
    q = st.text_input("Search in this table", placeholder="type any text, e.g. M-102 or Overdue")
    if q:
        mask = df.astype(str).apply(lambda col: col.str.contains(q, case=False, na=False)).any(axis=1)
        df = df[mask]
    st.dataframe(df, hide_index=True, width="stretch", height=380)
    c1, c2 = st.columns([3, 1])
    c1.caption(f"{len(df)} row(s) shown. Columns: {', '.join(SCHEMAS[name].columns)}")
    c2.download_button("Download CSV", store.table_to_csv_text(df.to_dict("records"), SCHEMAS[name].columns), f"{name}.csv", "text/csv", width="stretch")


# ------------------------------------------------------------------ Upload and convert
def _table_wizard(fname: str, rows: list[dict]) -> None:
    st.success(f"Read {len(rows)} row(s) and {len(rows[0]) if rows else 0} column(s) from **{fname}**. This is a preview. Nothing is saved yet.")
    if not rows:
        st.warning("The file has no rows.")
        return
    guess = next((t for t in UPLOAD_TARGETS if t.split("_")[0] in fname.lower()), UPLOAD_TARGETS[0])
    best = max(UPLOAD_TARGETS, key=lambda t: sum(v is not None for v in tables.suggest_mapping(t, list(rows[0])).values()))
    target = st.selectbox("Which table is this?", UPLOAD_TARGETS, index=UPLOAD_TARGETS.index(best if best else guess),
                          format_func=lambda n: f"{SCHEMAS[n].title} ({n}.csv)", key=f"tgt_{fname}")
    schema = SCHEMAS[target]
    src_cols = list(rows[0])
    sugg = tables.suggest_mapping(target, src_cols)
    section("Match the columns")
    st.caption("Columns were matched by name. Change any that are wrong. Required columns are marked with *.")
    mapping: dict[str, str | None] = {}
    cols = st.columns(3)
    for i, c in enumerate(schema.columns):
        opts = ["(none)"] + src_cols
        idx = opts.index(sugg[c]) if sugg[c] in opts else 0
        pick = cols[i % 3].selectbox(c + (" *" if c in schema.required else ""), opts, index=idx, key=f"map_{target}_{c}_{fname}")
        mapping[c] = None if pick == "(none)" else pick
    missing = [c for c in schema.required if not mapping[c] and c not in schema.defaults]
    if missing:
        st.error("Required column(s) not matched: " + ", ".join(missing))
        return

    mode = st.radio("What should happen to existing rows?", list(tables.MODES), format_func=tables.MODES.get, horizontal=False, key=f"mode_{fname}")
    skip = st.checkbox("Skip invalid rows and save the valid ones", value=True, key=f"skip_{fname}")
    mapped = tables.apply_mapping(target, rows, mapping)
    plan = tables.plan_merge(target, mapped, mode, skip_invalid=skip)

    section("Preview of the converted table")
    st.dataframe(pd.DataFrame(mapped[:50]), hide_index=True, width="stretch", height=220)
    for w in pii.warnings_for(pii.scan_rows(rows)):
        st.warning(w)
    for w in plan["warnings"]:
        st.warning(w)
    c = st.columns(4)
    c[0].metric("To add", plan["added"])
    c[1].metric("To update", plan["updated"])
    c[2].metric("Skipped / rejected", plan["skipped"])
    c[3].metric("Rows after", plan.get("after", "-"))
    if plan["problems"]:
        with st.expander(f"{len(plan['problems'])} problem(s) found", expanded=not plan["ok"]):
            for p in plan["problems"][:40]:
                st.markdown(f"- {p}")
    if mode == "replace":
        st.warning("Replace overwrites the whole table. The old version is kept in History and can be restored.")
    if st.button("Save to the data store", type="primary", disabled=not plan["ok"] or (plan["added"] + plan["updated"] == 0 and mode != "replace"), key=f"save_{fname}"):
        try:
            tables.commit(target, plan["final"])
            _after_save(f"Saved {target}.csv: {plan['added']} added, {plan['updated']} updated. A backup of the previous version was kept.")
        except ValueError as exc:
            st.error(str(exc))


def _text_wizard(fname: str, text: str) -> None:
    st.success(f"Read {len(text):,} characters of text from **{fname}**. Edit it below, then save it as a knowledge document.")
    stem = fname.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()
    _document_form(f"up_{fname}", stem, text)


def _document_form(key: str, title: str = "", text: str = "", existing: dict | None = None) -> None:
    c1, c2 = st.columns(2)
    title = c1.text_input("Title", value=title, key=f"{key}_title")
    if existing:
        c2.text_input("Document", value=f"{existing['article_id']} (new version of {existing['version']})", disabled=True, key=f"{key}_id")
        dtype = existing["type"]
    else:
        dtype = c2.selectbox("Document type", list(documents.PREFIX), format_func=documents.TYPE_LABEL.get, key=f"{key}_type")
    c3, c4, c5 = st.columns(3)
    from src.schemas import ARTICLE_PROGRAMS
    prog_default = ARTICLE_PROGRAMS.index(existing["program"]) if existing else 0
    program = c3.selectbox("Applies to", ARTICLE_PROGRAMS, index=prog_default, key=f"{key}_prog")
    scope = c4.text_input("Scope", value=(existing or {}).get("scope", "General education only"), key=f"{key}_scope")
    status = c5.selectbox("Status", ["Draft", "Approved"], key=f"{key}_status", help="Only Approved documents are indexed and cited by the assistant.")
    approver = st.text_input("Approved by (name or role, required when Approved)", key=f"{key}_appr")
    body = st.text_area("Document text", value=text, height=240, key=f"{key}_body")
    for w in documents.review_text(body):
        st.warning(w)
    if st.button("Save document", type="primary", key=f"{key}_save"):
        try:
            res = documents.save_document(title=title, text=body, doc_type=dtype, program=program, scope=scope, status=status,
                                          approved_by=approver, article_id=existing["article_id"] if existing else None)
            _after_save(f"Saved {res['article_id']} {res['version']} as {res['status']}." + (" It is not used by the assistant until it is Approved." if res["status"] != "Approved" else ""))
        except ValueError as exc:
            st.error(str(exc))


def _upload() -> None:
    html('<div class="card"><h4>Add or update anything in one place</h4>Upload a <b>CSV, JSON or Excel</b> file to add rows to a table, or a <b>Word, PDF, text or Markdown</b> file to add a knowledge document. '
         'Everything is converted into the two project formats: <b>CSV tables</b> and <b>Markdown documents</b>. You always see a preview before anything is saved.</div>')
    up = st.file_uploader("Choose a file", type=[e.lstrip(".") for e in config.ALLOWED_UPLOAD_EXTENSIONS], key="uploader")
    sub = st.radio("Or", ["Use the uploaded file", "Type rows by hand", "Write a new document"], horizontal=True, label_visibility="collapsed")
    if sub == "Use the uploaded file":
        if not up:
            st.info(f"Allowed: {', '.join(config.ALLOWED_UPLOAD_EXTENSIONS)}. Maximum {config.MAX_UPLOAD_MB:g} MB.")
            return
        try:
            kind, payload = read_upload(up.name, up.getvalue())
        except UploadError as exc:
            st.error(str(exc))
            return
        (_table_wizard if kind == "table" else _text_wizard)(up.name, payload)
    elif sub == "Type rows by hand":
        target = st.selectbox("Table", UPLOAD_TARGETS, format_func=lambda n: SCHEMAS[n].title, key="hand_t")
        schema = SCHEMAS[target]
        st.caption(schema.help)
        empty = pd.DataFrame([{c: "" for c in schema.columns}])
        edited = st.data_editor(empty, num_rows="dynamic", hide_index=True, width="stretch", key=f"hand_{target}")
        rows = [r for r in edited.to_dict("records") if any(str(v).strip() for v in r.values())]
        mode = st.radio("If the ID already exists", ["upsert", "append"], format_func=lambda m: {"upsert": "Update it", "append": "Reject it"}[m], horizontal=True, key="hand_m")
        if rows:
            plan = tables.plan_merge(target, tables.apply_mapping(target, rows, {c: c for c in schema.columns}), mode, skip_invalid=False)
            for p in plan["problems"]:
                st.error(p)
            for w in plan["warnings"]:
                st.warning(w)
            if st.button("Save rows", type="primary", disabled=not plan["ok"], key="hand_save"):
                tables.commit(target, plan["final"])
                _after_save(f"Saved {plan['added']} new and {plan['updated']} updated row(s) in {target}.csv.")
    else:
        _document_form("new")


# ------------------------------------------------------------------ Rules
def _rules() -> None:
    html('<div class="card"><h4>Edit rule values without touching code</h4>The <b>logic</b> of each rule (what it does) is fixed in code and tested. '
         'You can change the <b>values and words</b> it uses. Every save keeps a backup and can be rolled back in History.</div>')
    section("Rule wording (ER-501 to ER-504)")
    all_rules = store.load_table("escalation_rules")
    base = [r for r in all_rules if not (r.get("parent_rule") or "").strip()]
    variants = [r for r in all_rules if (r.get("parent_rule") or "").strip()]
    ed = st.data_editor(pd.DataFrame(base)[["rule_id", "condition", "action"]], hide_index=True, width="stretch",
                        disabled=["rule_id"], num_rows="fixed", key="ed_rules")
    if st.button("Save rule wording", key="sv_rules"):
        try:
            edited = {r["rule_id"]: r for r in ed.fillna("").to_dict("records")}
            merged = [{**r, **edited.get(r["rule_id"], {})} for r in base] + variants
            store.write_table("escalation_rules", merged)
            _after_save("Rule wording saved.")
        except ValueError as exc:
            st.error(str(exc))

    section(f"Routing variants ({len(variants)} rows)")
    st.caption("When a rule fires, the most specific variant (program, context, channel) chooses the staff queue and the action wording. "
               "A blank cell means 'any'. The rule logic itself does not change.")
    parent = st.selectbox("Show variants of", ["ER-501", "ER-502", "ER-503", "ER-504"], key="var_parent")
    shown = [r for r in variants if r["parent_rule"] == parent]
    ve = st.data_editor(pd.DataFrame(shown, columns=SCHEMAS["escalation_rules"].columns), hide_index=True, width="stretch", num_rows="dynamic", key=f"ed_var_{parent}", height=300,
                        column_config={"parent_rule": st.column_config.SelectboxColumn("parent_rule", options=["ER-501", "ER-502", "ER-503", "ER-504"], required=True),
                                       "program": st.column_config.SelectboxColumn("program", options=SCHEMAS["members"].allowed["program"]),
                                       "channel": st.column_config.SelectboxColumn("channel", options=["App", "SMS", "Email"])})
    if st.button("Save variants", key="sv_var"):
        try:
            others = [r for r in all_rules if r.get("parent_rule") != parent]
            store.write_table("escalation_rules", others + ve.fillna("").to_dict("records"))
            _after_save(f"Variants of {parent} saved.")
        except ValueError as exc:
            st.error(str(exc))

    section("ER-502 test values (reading → urgent staff review)")
    st.caption("A reading matches if ANY check is true. A row with a program replaces the general row (blank program) for members of that program. These are demo placeholders, NOT clinical thresholds. Real values must come from clinicians.")
    hv = st.data_editor(services.table_df("high_risk_values"), hide_index=True, width="stretch", num_rows="dynamic", key="ed_hv",
                        column_config={"reading_type": st.column_config.SelectboxColumn("reading_type", options=SCHEMAS["high_risk_values"].allowed["reading_type"], required=True),
                                       "field": st.column_config.SelectboxColumn("field", options=["systolic", "diastolic", "value"], required=True),
                                       "operator": st.column_config.SelectboxColumn("operator", options=[">=", ">", "<=", "<"], required=True),
                                       "program": st.column_config.SelectboxColumn("program", options=SCHEMAS["members"].allowed["program"])},
                        height=300)
    if st.button("Save ER-502 values", key="sv_hv"):
        try:
            store.write_table("high_risk_values", hv.fillna("").to_dict("records"))
            _after_save("ER-502 values saved.")
        except ValueError as exc:
            st.error(str(exc))

    section("ER-503 word lists (medication change requests)")
    st.caption("A message matches when it has at least one action word AND at least one medication word.")
    mw = st.data_editor(services.table_df("medication_words"), hide_index=True, width="stretch", num_rows="dynamic", key="ed_mw", height=260,
                        column_config={"kind": st.column_config.SelectboxColumn("kind", options=["action", "medication"], required=True),
                                       "group": st.column_config.SelectboxColumn("group", options=SCHEMAS["medication_words"].allowed["group"])})
    if st.button("Save ER-503 words", key="sv_mw"):
        try:
            store.write_table("medication_words", mw.fillna("").to_dict("records"))
            _after_save("ER-503 word lists saved.")
        except ValueError as exc:
            st.error(str(exc))

    section("Try the rules")
    c1, c2 = st.columns(2)
    msg = c1.text_input("Type a message to test ER-503", value="Can I double my metformin tablets?")
    if msg:
        (c1.error if is_medication_change_request(msg) else c1.success)("ER-503 matches: this request would be declined and sent to a clinician." if is_medication_change_request(msg) else "ER-503 does not match.")
    rt = c2.selectbox("Reading type", SCHEMAS["high_risk_values"].allowed["reading_type"])
    val = c2.text_input("Value (blood pressure as 150/95)", value="166/104" if rt == "Blood pressure" else "320")
    try:
        hit = evaluate_high_risk([{"reading_id": "TEST", "type": rt, "value": val, "unit": ""}])
        (c2.error if hit else c2.success)(f"ER-502 matches: {hit[0]['detail']}" if hit else "ER-502 does not match.")
    except (ValueError, IndexError):
        c2.warning("Enter a valid number.")


# ------------------------------------------------------------------ History
def _history() -> None:
    name = st.selectbox("Table", ALL_TABLES, key="hist_t")
    versions = store.list_versions(name)
    if not versions:
        st.info("No earlier versions yet. A backup is created automatically before every change.")
        return
    rows = [{"Saved at": v.stem[:4] + "-" + v.stem[4:6] + "-" + v.stem[6:8] + " " + v.stem[9:11] + ":" + v.stem[11:13] + ":" + v.stem[13:15],
             "Rows": sum(1 for _ in open(v, encoding="utf-8")) - 1, "File": v.name} for v in versions]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    pick = st.selectbox("Restore this version", [r["File"] for r in rows])
    if st.button("Restore selected version", key="restore"):
        store.restore_version(name, next(v for v in versions if v.name == pick))
        _after_save(f"Restored {name}.csv from {pick}. The version it replaced was also kept.")


def render() -> None:
    t = st.tabs(["Browse tables", "Add / convert data", "Edit rules", "Version history"])
    with t[0]:
        _browse()
    with t[1]:
        _upload()
    with t[2]:
        _rules()
    with t[3]:
        _history()
