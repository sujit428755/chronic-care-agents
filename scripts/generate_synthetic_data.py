"""Generate the synthetic data set (CSV tables + extra Markdown articles).  Seeded, so the output is identical every run.

* The original seed records (M-101..M-105, R-201..R-209, CP-301..CP-304, EDU-401..404, FAQ-701/702, CPG-801/802)
  are kept EXACTLY as they were, so tests T1 to T13 still behave the same.
* New synthetic members start at M-106, readings at R-210, tasks at CP-305.
* The new members include every situation the agents must handle: expired / pending / revoked consent, readings that
  match the ER-502 test values, contradictory readings (ER-504), corrected readings, missing days and overdue tasks.

Usage:  python scripts/generate_synthetic_data.py [--members 100] [--seed 2026] [--no-articles]
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402
from src.schemas import SCHEMAS  # noqa: E402
sys.path.insert(0, str(ROOT / "scripts"))
import seed_articles  # noqa: E402
import seed_rules  # noqa: E402

REF = config.REFERENCE_DATE if isinstance(config.REFERENCE_DATE, date) else date.fromisoformat(config.REFERENCE_DATE)

# --------------------------------------------------------------------- original records (verbatim)
MEMBERS = [
    ("M-101", "Diabetes Support", "App", "English", "Active", ""),
    ("M-102", "Hypertension Support", "SMS", "Hindi", "Active", ""),
    ("M-103", "Diabetes Support", "Email", "Kannada", "Expired", ""),
    ("M-104", "Cardiac Wellness", "App", "English", "Active", ""),
    ("M-105", "Diabetes Support", "App", "English", "Active", "ADDED TEST MEMBER (synthetic) - used for the contradictory-readings test (ER-504)."),
]
READINGS = [
    ("R-201", "M-101", "Glucose", "118", "mg/dL", "2026-10-01 08:00", "active", "", "", ""),
    ("R-202", "M-101", "Glucose", "142", "mg/dL", "2026-10-03 08:15", "active", "", "", ""),
    ("R-203", "M-102", "Blood pressure", "128/82", "mmHg", "2026-10-02 19:00", "active", "", "", ""),
    ("R-204", "M-102", "Blood pressure", "166/104", "mmHg", "2026-10-05 07:30", "active", "", "", ""),
    ("R-205", "M-104", "Weight", "74.2", "kg", "2026-10-04 07:00", "active", "", "", ""),
    ("R-206", "M-101", "Glucose", "150", "mg/dL", "2026-10-04 08:05", "superseded", "R-207", "", "ADDED TEST RECORD: member corrected this entry; kept only so the correction can be audited (value never shown in active summaries)."),
    ("R-207", "M-101", "Glucose", "125", "mg/dL", "2026-10-04 08:05", "active", "", "R-206", "ADDED TEST RECORD: corrected value replacing R-206."),
    ("R-208", "M-105", "Glucose", "110", "mg/dL", "2026-10-02 08:00", "active", "", "", "ADDED TEST RECORD: conflicts with R-209 (same type and timestamp, different value)."),
    ("R-209", "M-105", "Glucose", "190", "mg/dL", "2026-10-02 08:00", "active", "", "", "ADDED TEST RECORD: conflicts with R-208."),
]
TASKS = [
    ("CP-301", "M-101", "Record morning reading", "Daily", "2026-10-06", "Due"),
    ("CP-302", "M-101", "Education module 2", "Once", "2026-10-10", "Open"),
    ("CP-303", "M-102", "Record evening reading", "Daily", "2026-10-05", "Overdue"),
    ("CP-304", "M-104", "Coordinator check-in", "Monthly", "2026-10-20", "Scheduled"),
]
RULES = [
    ("ER-501", "Consent is not active", "Stop processing and direct member to program staff."),
    ("ER-502", "Reading matches configured high-risk test value", "Create urgent staff-review record; do not interpret."),
    ("ER-503", "User asks to change medication", "Decline and direct to qualified clinician."),
    ("ER-504", "Source or reading is contradictory", "Mark uncertainty and request human review."),
]
HIGH_RISK = [
    ("Blood pressure", "systolic", ">=", "160", "DEMO PLACEHOLDER chosen so the rule can be demonstrated. NOT a clinical threshold; clinicians must set real values."),
    ("Blood pressure", "diastolic", ">=", "100", "DEMO PLACEHOLDER. NOT a clinical threshold."),
    ("Glucose", "value", ">=", "300", "DEMO PLACEHOLDER. NOT a clinical threshold."),
]
ACTION_WORDS = ["change", "increase", "decrease", "reduce", "raise", "lower", "stop", "skip", "double", "halve", "switch",
                "adjust", "start", "quit", "take more", "take less", "take extra", "take earlier", "take later", "instead of"]
MED_WORDS = ["medication", "medicines", "medicine", "dose", "dosage", "tablet", "tablets", "pill", "pills", "insulin",
             "metformin", "drug", "drugs", "prescription"]
CATALOG = [
    ("EDU-401", "Understanding Home Readings", "All programs", "v4", "General education only", "education", "Approved", ""),
    ("EDU-402", "Building a Daily Routine", "Diabetes Support", "v3", "Habit support", "education", "Approved", ""),
    ("EDU-403", "Preparing for a Care Call", "All programs", "v2", "Checklist", "education", "Approved", ""),
    ("EDU-404", "When the Program Contacts You", "All programs", "v5", "Escalation process", "education", "Approved", ""),
    ("FAQ-701", "How do I change my reminder channel?", "All programs", "v1", "Program FAQ", "faq", "Approved", "ADDED synthetic FAQ"),
    ("FAQ-702", "What happens to the readings I enter?", "All programs", "v1", "Program FAQ", "faq", "Approved", "ADDED synthetic FAQ"),
    ("CPG-801", "How care plan tasks and statuses work", "All programs", "v1", "Care plan guidance", "careplan_guidance", "Approved", "ADDED synthetic guidance"),
    ("CPG-802", "What to do about overdue tasks", "All programs", "v1", "Care plan guidance", "careplan_guidance", "Approved", "ADDED synthetic guidance"),
]

# --------------------------------------------------------------------- new articles (neutral, no medical advice)
NEW_ARTICLES = [
    # id, title, program, version, scope, type, body paragraphs
    ("EDU-405", "Using the Reading Log in the App", "All programs", "v1", "How-to", "education",
     "The reading log is the place in the app where your entries are kept in date order.\n\n## Adding an entry\n- Choose the type of entry, such as glucose, blood pressure or weight.\n- Type the number exactly as your device shows it.\n- Check the date and time before you save.\n\n## Fixing a mistake\nIf you typed the wrong number, enter the correct one and tell program staff. The old entry is marked as replaced so only the corrected number is used."),
    ("EDU-406", "Keeping Your Contact Details Up to Date", "All programs", "v1", "Checklist", "education",
     "Program messages reach you only if your contact details are current.\n\n## Checklist\n- Your phone number and email address.\n- Your preferred language.\n- Your preferred channel: App, SMS or Email.\n\nTo update any of these, contact program staff. They change your profile for you."),
    ("EDU-407", "Questions to Note Before a Clinic Visit", "All programs", "v1", "Checklist", "education",
     "A short written list helps you use your clinic visit well.\n\n## Ideas\n- Write down questions as they come to mind.\n- Bring your device or your list of entries.\n- Note anything you want your clinician to explain in their own words.\n\nThe program does not answer clinical questions. Your clinician does."),
    ("EDU-408", "Understanding Your Care Plan Tasks", "All programs", "v1", "Care plan basics", "education",
     "Your care plan is a list of tasks set up by your care team. Each task has a name, how often it repeats, a due date and a status.\n\n## Statuses\n- Due or Overdue: the task needs your attention.\n- Open or Scheduled: the task is coming up.\n- Completed: the task is done.\n\nThe status is shown exactly as recorded by your care team."),
    ("EDU-409", "Sharing Information with Your Care Team", "All programs", "v1", "Privacy basics", "education",
     "You decide what the program may use. Your consent is recorded in your profile.\n\n## Good to know\n- The program uses only the information you have shared.\n- Staff see a summary packet when a follow-up is needed.\n- If you wish to change your consent, contact program staff."),
    ("EDU-410", "Getting Started with Hypertension Support", "Hypertension Support", "v1", "Program orientation", "education",
     "Welcome to Hypertension Support. This program helps you stay in touch with your care team.\n\n## What to expect\n- Reminders for the tasks in your care plan.\n- A place to enter your blood pressure entries.\n- Staff follow-up when something needs a person to look at it.\n\nQuestions about your treatment are for your clinician."),
    ("FAQ-703", "Who can see my information?", "All programs", "v1", "Program FAQ", "faq",
     "Only program staff who need your information for follow-up can see your summary. Member identifiers are masked in the activity log."),
    ("FAQ-704", "How do I change my language?", "All programs", "v1", "Program FAQ", "faq",
     "Contact program staff. They update the language saved in your profile."),
    ("FAQ-705", "What does a Due task mean?", "All programs", "v1", "Program FAQ", "faq",
     "A Due task is a care plan task whose date has arrived and that has not been marked as completed. The status is the one recorded in your care plan."),
    ("FAQ-706", "How do I correct a wrong entry?", "All programs", "v1", "Program FAQ", "faq",
     "Enter the correct value and tell program staff. The earlier entry is marked as replaced and is not used in your summaries."),
    ("FAQ-707", "Can I ask the assistant about my treatment?", "All programs", "v1", "Program FAQ", "faq",
     "No. The assistant organises information. It does not give medical advice, diagnose or change treatment. Please ask your clinician."),
    ("FAQ-708", "What if I miss entering my information for a few days?", "All programs", "v1", "Program FAQ", "faq",
     "Nothing is filled in for you. A summary simply lists the dates with no entry. Staff may send a friendly reminder."),
    ("CPG-803", "Writing a friendly reminder", "All programs", "v1", "Care plan guidance", "careplan_guidance",
     "A reminder names the task, its due date and its recorded status, uses the member's preferred channel, and never mentions values, interpretations or advice."),
    ("CPG-804", "When a task has no due date", "All programs", "v1", "Care plan guidance", "careplan_guidance",
     "A task without a due date is reported as recorded. Staff are asked to review the care plan record. The system never invents a date."),
    ("CPG-805", "Reminder timing and channels", "All programs", "v1", "Care plan guidance", "careplan_guidance",
     "Reminders go through the channel saved for the member: App, SMS or Email. A change of channel is made by program staff."),
    ("CPG-806", "Handing a case to staff", "All programs", "v1", "Care plan guidance", "careplan_guidance",
     "Cases with a configured rule match, contradictory entries or a knowledge gap are placed in the staff review queue with the facts and no interpretation."),
]
FOLDER = {"education": "education", "faq": "faq", "careplan_guidance": "careplan_guidance"}


def write_csv(name: str, rows: list[dict | tuple]) -> None:
    cols = SCHEMAS[name].columns
    out = []
    for r in rows:
        d = dict(zip(cols, r)) if isinstance(r, tuple) else r
        out.append({c: d.get(c, "") for c in cols})
    path = config.DATA_DIR / f"{name}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    bad = [p for i, d in enumerate(out, 1) for p in [f"row {i}: {e}" for e in SCHEMAS[name].validate_row(d)] if p]
    if bad:
        raise SystemExit(f"generated {name} failed validation: {bad[:5]}")
    print(f"  {name}.csv: {len(out)} rows")


def article_md(a: tuple) -> str:
    aid, title, prog, ver, scope, typ, body = a
    return (f"---\narticle_id: {aid}\ntitle: {title}\nprogram: {prog}\nversion: {ver}\nscope: {scope}\n---\n"
            f"Article ID: {aid} | Version: {ver} | Scope: {scope} (synthetic content)\n\n# {title}\n\n{body}\n")


def generate(n_members: int, seed: int, articles: bool) -> None:
    rnd = random.Random(seed)
    programs = ["Diabetes Support", "Hypertension Support", "Cardiac Wellness"]
    langs = ["English"] * 5 + ["Hindi"] * 2 + ["Kannada", "Tamil", "Telugu", "Marathi"]
    channels = ["App", "App", "SMS", "Email"]
    members = list(MEMBERS)
    # consent mix for generated members: ~80% Active, rest Expired/Pending/Revoked
    consent_pool = ["Active"] * int(n_members * 0.80)
    rest = n_members - len(consent_pool)
    consent_pool += (["Expired", "Pending", "Revoked"] * rest)[:rest]
    rnd.shuffle(consent_pool)
    for i in range(n_members):
        mid = f"M-{106 + i}"
        members.append((mid, rnd.choice(programs), rnd.choice(channels), rnd.choice(langs), consent_pool[i], ""))

    gen_members = members[len(MEMBERS):]
    active = [m for m in gen_members if m[4] == "Active"]
    rid = 210
    readings = list(READINGS)

    def add(mid, typ, val, unit, ts, status="active", sup="", cor="", note=""):
        nonlocal rid
        readings.append((f"R-{rid}", mid, typ, val, unit, ts.strftime("%Y-%m-%d %H:%M"), status, sup, cor, note))
        rid += 1
        return f"R-{rid - 1}"

    days = [REF - timedelta(days=d) for d in range(27, -1, -1)]
    special = {m[0]: k for m, k in zip(rnd.sample(active, 14), ["high_bp"] * 3 + ["high_glu"] * 3 + ["conflict"] * 4 + ["correct"] * 4)}
    for m in active:
        mid, prog = m[0], m[1]
        types = {"Diabetes Support": ["Glucose"], "Hypertension Support": ["Blood pressure"],
                 "Cardiac Wellness": ["Blood pressure", "Weight"]}[prog]
        if special.get(mid) == "high_bp" and "Blood pressure" not in types:
            special[mid] = None
        if special.get(mid) == "high_glu" and "Glucose" not in types:
            special[mid] = None
        base_w = rnd.uniform(58, 95)
        coverage = rnd.choice([0.95, 0.85, 0.7, 0.5])
        for d in days:
            for t in types:
                if rnd.random() > coverage:
                    continue
                ts = datetime.combine(d, datetime.min.time()) + timedelta(hours=rnd.choice([6, 7, 8, 19, 20]), minutes=rnd.randrange(0, 60))
                if t == "Glucose":
                    add(mid, t, str(rnd.randint(86, 168)), "mg/dL", ts)
                elif t == "Blood pressure":
                    add(mid, t, f"{rnd.randint(108, 148)}/{rnd.randint(68, 92)}", "mmHg", ts)
                else:
                    add(mid, t, f"{base_w + rnd.uniform(-0.6, 0.6):.1f}", "kg", ts)
        k = special.get(mid)
        when = datetime.combine(REF - timedelta(days=rnd.randint(0, 4)), datetime.min.time()) + timedelta(hours=9, minutes=rnd.randrange(0, 50))
        if k == "high_bp":
            add(mid, "Blood pressure", f"{rnd.randint(162, 178)}/{rnd.randint(98, 112)}", "mmHg", when, note="SYNTHETIC: matches the ER-502 test value.")
        elif k == "high_glu":
            add(mid, "Glucose", str(rnd.randint(305, 345)), "mg/dL", when, note="SYNTHETIC: matches the ER-502 test value.")
        elif k == "conflict":
            typ, unit = ("Glucose", "mg/dL") if "Glucose" in types else ("Blood pressure", "mmHg")
            when = when.replace(hour=11, minute=15)
            v1, v2 = ((str(rnd.randint(95, 120)), str(rnd.randint(150, 175))) if typ == "Glucose" else ("118/76", "136/88"))
            a = add(mid, typ, v1, unit, when, note="SYNTHETIC: conflicts with the next reading (ER-504).")
            add(mid, typ, v2, unit, when, note=f"SYNTHETIC: conflicts with {a} (ER-504).")
        elif k == "correct":
            typ, unit = ("Glucose", "mg/dL") if "Glucose" in types else ("Blood pressure", "mmHg")
            when = when.replace(hour=12, minute=5)
            wrong, right = ((str(rnd.randint(170, 190)), str(rnd.randint(100, 130))) if typ == "Glucose" else ("152/94", "126/80"))
            nxt = f"R-{rid + 1}"
            old = add(mid, typ, wrong, unit, when, status="superseded", sup=nxt, note="SYNTHETIC: member corrected this entry.")
            add(mid, typ, right, unit, when, cor=old, note=f"SYNTHETIC: corrected value replacing {old}.")

    # tasks
    task_names = {
        "Diabetes Support": [("Record morning reading", "Daily"), ("Education module", "Once"), ("Coordinator check-in", "Monthly")],
        "Hypertension Support": [("Record evening reading", "Daily"), ("Education module", "Once"), ("Coordinator check-in", "Monthly")],
        "Cardiac Wellness": [("Record weight", "Weekly"), ("Record evening reading", "Daily"), ("Coordinator check-in", "Monthly")],
    }
    tasks, cp = list(TASKS), 305
    for m in gen_members:
        for name, freq in rnd.sample(task_names[m[1]], rnd.choice([2, 3, 3])):
            offset = rnd.randint(-6, 14)
            due = REF + timedelta(days=offset)
            if offset < -1:
                status = "Overdue"
            elif offset <= 0:
                status = "Due"
            elif freq == "Monthly":
                status = "Scheduled"
            else:
                status = rnd.choice(["Open", "Scheduled"])
            if rnd.random() < 0.08:
                status = "Completed"
            tasks.append((f"CP-{cp}", m[0], name, freq, due.isoformat(), status))
            cp += 1

    print("Writing CSV tables:")
    write_csv("members", members)
    write_csv("readings", readings)
    write_csv("care_plan_tasks", tasks)
    write_csv("escalation_rules", seed_rules.variant_rows())
    write_csv("high_risk_values", seed_rules.high_risk_rows())
    write_csv("medication_words", seed_rules.medication_rows())

    cat = []
    stamp = REF.isoformat()
    for a in CATALOG:
        aid, title, prog, ver, scope, typ, status, note = a
        cat.append((aid, title, prog, ver, scope, typ, f"knowledge/{FOLDER[typ]}/{aid}.md", status, "Content Lead (synthetic)", stamp, note))
    if articles:
        for a in NEW_ARTICLES:
            aid, title, prog, ver, scope, typ, _ = a
            path = config.KNOWLEDGE_DIR / FOLDER[typ] / f"{aid}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(article_md(a), encoding="utf-8")
            cat.append((aid, title, prog, ver, scope, typ, f"knowledge/{FOLDER[typ]}/{aid}.md", "Approved", "Content Lead (synthetic)", stamp, "Synthetic article"))
        for aid, title, prog, scope, typ, status, body in seed_articles.build():
            path = config.KNOWLEDGE_DIR / FOLDER[typ] / f"{aid}.md"
            path.write_text(article_md((aid, title, prog, "v1", scope, typ, body)), encoding="utf-8")
            cat.append((aid, title, prog, "v1", scope, typ, f"knowledge/{FOLDER[typ]}/{aid}.md", status, "Content Lead (synthetic)", stamp, "Synthetic article"))
        print(f"Wrote {len(NEW_ARTICLES) + len(seed_articles.build())} new articles under knowledge/")
    write_csv("articles_catalog", cat)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--members", type=int, default=245)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--no-articles", action="store_true")
    a = ap.parse_args()
    generate(a.members, a.seed, not a.no_articles)
