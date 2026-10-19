"""Data-layer and ingestion checks (run on a temporary COPY of the data, never on the real files).

    python tests/test_ingest.py
"""
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402

tmp = Path(tempfile.mkdtemp())
shutil.copytree(config.DATA_DIR, tmp / "data")
shutil.copytree(config.KNOWLEDGE_DIR, tmp / "knowledge")
config.ROOT, config.DATA_DIR, config.KNOWLEDGE_DIR = tmp, tmp / "data", tmp / "knowledge"

from src.ingest import documents, tables  # noqa: E402
from src.ingest.readers import UploadError, read_upload  # noqa: E402
from src.knowledge import load_catalog, load_documents  # noqa: E402
from src.tools import store  # noqa: E402
from src.tools.rules_tools import evaluate_high_risk, is_medication_change_request  # noqa: E402

passed = 0


def check(name, cond):
    global passed
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        sys.exit(1)
    passed += 1


# 1 data integrity
members, readings, tasks = store.load_table("members"), store.load_table("readings"), store.load_table("care_plan_tasks")
ids = {m["member_id"] for m in members}
check("100+ members, 1000+ readings, 100+ tasks", len(members) >= 100 and len(readings) >= 1000 and len(tasks) >= 100)
check("every reading and task belongs to a known member", all(r["member_id"] in ids for r in readings) and all(t["member_id"] in ids for t in tasks))
check("all four consent states are present", {m["consent_status"] for m in members} == {"Active", "Expired", "Pending", "Revoked"})
check("every superseded reading points to an existing reading", all(r["superseded_by"] in {x["reading_id"] for x in readings} for r in readings if r["status"] == "superseded"))
check("every Approved catalog entry has its file", all((tmp / a["file"]).exists() for a in load_catalog()))

# 2 rules come from the editable tables
check("ER-502 matches BP 166/104 and glucose 320, not 128/82", len(evaluate_high_risk([
    {"reading_id": "a", "type": "Blood pressure", "value": "166/104", "unit": ""},
    {"reading_id": "b", "type": "Glucose", "value": "320", "unit": ""},
    {"reading_id": "c", "type": "Blood pressure", "value": "128/82", "unit": ""}])) == 2)
hv = store.load_table("high_risk_values")
for r in hv:
    if r["reading_type"] == "Glucose":
        r["threshold"] = "200"
store.write_table("high_risk_values", hv)
check("editing a rule value changes the rule result (glucose 250 now matches)", len(evaluate_high_risk([{"reading_id": "g", "type": "Glucose", "value": "250", "unit": ""}])) == 1)
check("ER-503 matches 'double my metformin tablets'", is_medication_change_request("Can I double my metformin tablets?"))
check("ER-503 does not match an education question", not is_medication_change_request("What is a home reading?"))

# 3 upload and convert
js = json.dumps({"members": [{"ID": "M-900", "Programme": "diabetes support", "Channel": "sms", "Lang": "Tamil", "Consent": "active"},
                             {"ID": "M-901", "Programme": "nonsense", "Channel": "sms", "Lang": "Tamil", "Consent": "active"}]}).encode()
kind, rows = read_upload("m.json", js)
mp = tables.suggest_mapping("members", list(rows[0]))
plan = tables.plan_merge("members", tables.apply_mapping("members", rows, mp), "append")
check("JSON upload: columns auto-matched, letter case fixed, bad row rejected", plan["added"] == 1 and plan["skipped"] == 1 and plan["ok"])
before = len(store.load_table("members"))
tables.commit("members", plan["final"])
check("commit adds the row and keeps a backup", len(store.load_table("members")) == before + 1 and len(store.list_versions("members")) >= 1)
store.restore_version("members", store.list_versions("members")[0])
check("rollback restores the previous table", len(store.load_table("members")) == before)
plan = tables.plan_merge("members", tables.apply_mapping("members", rows[:1], mp), "append")
tables.commit("members", plan["final"])
plan2 = tables.plan_merge("members", tables.apply_mapping("members", rows[:1], mp), "append")
check("append rejects an existing ID", plan2["added"] == 0 and any("already exists" in p for p in plan2["problems"]))
try:
    read_upload("x.exe", b"abc")
    check("unsupported extension rejected", False)
except UploadError:
    check("unsupported extension rejected", True)
try:
    read_upload("big.csv", b"a" * int(config.MAX_UPLOAD_MB * 1024 * 1024 + 10))
    check("oversize file rejected", False)
except UploadError:
    check("oversize file rejected", True)
try:
    store.write_table("members", [{"member_id": "X"}])
    check("invalid table is never written", False)
except ValueError:
    check("invalid table is never written", True)

# 4 documents
r = documents.save_document(title="Draft note", text="Plain text about reminders.", doc_type="faq", program="All programs", status="Draft")
check("new document gets the next FAQ id", r["article_id"].startswith("FAQ-"))
check("Draft documents are invisible to retrieval", r["article_id"] not in {d["article_id"] for d in load_documents()})
documents.set_status(r["article_id"], "Approved", "QA reviewer")
check("Approved documents become visible", r["article_id"] in {d["article_id"] for d in load_documents()})
r2 = documents.save_document(title="Draft note", text="New text", doc_type="faq", program="All programs", article_id=r["article_id"])
check("editing creates v2 and keeps v1", r2["version"] == "v2" and (tmp / "knowledge/_versions" / r["article_id"] / "v1.md").exists())
try:
    documents.save_document(title="x", text="y", doc_type="faq", program="All programs", status="Approved", approved_by="")
    check("approval needs an approver", False)
except ValueError:
    check("approval needs an approver", True)

print(f"\n{passed} checks passed")
