"""Checks on the larger synthetic data set and the rule logic that uses it.   python tests/test_data_scale.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from src.schemas import SCHEMAS  # noqa: E402
from src.tools import rules_tools as rt  # noqa: E402
from src.tools.store import load_table  # noqa: E402

fails = []
def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok: fails.append(name)

MIN = {"articles_catalog": 100, "care_plan_tasks": 500, "escalation_rules": 100, "high_risk_values": 100, "medication_words": 100, "members": 200}
for t, n in MIN.items():
    rows = load_table(t)
    bad = [e for r in rows for e in SCHEMAS[t].validate_row(r)]
    keys = [tuple(r[k] for k in SCHEMAS[t].key) for r in rows]
    check(f"{t}: >= {n} rows, valid, unique keys", len(rows) >= n and not bad and len(set(keys)) == len(keys), f"{len(rows)} rows {bad[:2]}")

# every Approved article has its file; ids match
cat = load_table("articles_catalog")
check("catalog files exist", all((config.BASE_DIR / r["file"]).exists() for r in cat) if hasattr(config, "BASE_DIR") else all(Path(config.KNOWLEDGE_DIR.parent / r["file"]).exists() for r in cat))
check("catalog has Approved, Draft and Retired", {r["status"] for r in cat} == {"Approved", "Draft", "Retired"})
members = {m["member_id"] for m in load_table("members")}
check("tasks point to real members", all(t["member_id"] in members for t in load_table("care_plan_tasks")))

# ER-502: program row replaces the general row; original placeholders unchanged
base = [{"reading_id": "T", "type": "Blood pressure", "value": "152/80", "unit": "mmHg"}]
check("general row: 152/80 does not match", not rt.evaluate_high_risk(base, None))
check("Cardiac row (more sensitive) matches 152/80", bool(rt.evaluate_high_risk(base, "Cardiac Wellness")))
check("original 166/104 still matches", bool(rt.evaluate_high_risk([{"reading_id": "T", "type": "Blood pressure", "value": "166/104", "unit": ""}], "Hypertension Support")))
check("normal glucose 150 does not match", not rt.evaluate_high_risk([{"reading_id": "T", "type": "Glucose", "value": "150", "unit": ""}], "Diabetes Support"))
check("low glucose 50 matches the low row", bool(rt.evaluate_high_risk([{"reading_id": "T", "type": "Glucose", "value": "50", "unit": ""}], None)))
check("new type Oxygen saturation 85 matches", bool(rt.evaluate_high_risk([{"reading_id": "T", "type": "Oxygen saturation", "value": "85", "unit": ""}], None)))

# ER-503: more words, still no false alarms on ordinary program questions
hit = ["Can I stop taking my amlodipine?", "I want to double my insulin pen dose", "Should I skip my atorvastatin tonight", "can i halve the warfarin tablets"]
miss = ["What are home readings?", "Summarize my glucose readings for the last 7 days", "Remind me about my tasks", "How do I change my reminder channel?",
        "Can you explain how to build a daily routine?", "Please add a note to my entry", "Show my blood pressure for the last 14 days", "I want to switch to SMS"]
check("ER-503 matches medication change requests", all(rt.is_medication_change_request(m) for m in hit), str([m for m in hit if not rt.is_medication_change_request(m)]))
check("ER-503 ignores ordinary requests", not any(rt.is_medication_change_request(m) for m in miss), str([m for m in miss if rt.is_medication_change_request(m)]))
check("medication group found", rt.medication_group("double my insulin") == "Insulin" and rt.medication_group("skip my aspirin") == "Blood thinner")

# routing variants: most specific wins, base rows have no queue
v = rt.resolve_variant("ER-501", "Diabetes Support", "Expired", "SMS")
check("ER-501 variant resolved (program+status+channel)", v is not None and "SMS" in v["action"] and v["queue"])
check("unknown context falls back to None", rt.resolve_variant("ER-501", "Diabetes Support", "Nonsense", "SMS") is None)
r = rt.routing_for(["ER-503"], "M-101", [], "double my metformin")
check("routing for ER-503 uses the medicine group", bool(r) and "Clinician referral desk" in r[0]["queue"] and "Diabetes" in r[0]["queue"])
check("base rules loaded without variants", set(rt.load_rules()) == {"ER-501", "ER-502", "ER-503", "ER-504"})
print(f"\n{'ALL OK' if not fails else str(len(fails)) + ' FAILED'}")
sys.exit(1 if fails else 0)
