"""Seed data for the rule tables (escalation variants, ER-502 test values, ER-503 word lists).
All numbers are DEMO PLACEHOLDERS for a demo, never clinical thresholds."""
from __future__ import annotations

PROGRAMS = ["Diabetes Support", "Hypertension Support", "Cardiac Wellness"]
CHANNELS = ["App", "SMS", "Email"]

# ----------------------------------------------------------------- ER-503 words
ACTION_WORDS = [
    "change", "increase", "decrease", "reduce", "raise", "lower", "stop", "skip", "double", "halve", "switch",
    "adjust", "start", "quit", "take more", "take less", "take extra", "take earlier", "take later", "instead of",
    "triple", "pause", "discontinue", "cancel", "replace", "swap", "cut down", "cut back", "taper", "boost",
    "stop taking", "start taking", "give up", "go off", "come off", "drop", "add", "remove", "extra", "half",
    "twice as much", "fewer", "split", "crush", "mix", "stretch", "delay", "bring forward", "up the", "wean off",
    "reset", "modify",
]
MEDS = {
    "Insulin": ["insulin", "glargine", "lispro", "aspart", "detemir", "degludec", "novorapid", "lantus", "humalog",
                "levemir", "tresiba", "basal", "bolus", "pen needle", "insulin pen"],
    "Oral diabetes medicine": ["metformin", "glipizide", "glimepiride", "gliclazide", "sitagliptin", "vildagliptin",
                               "linagliptin", "empagliflozin", "dapagliflozin", "canagliflozin", "pioglitazone",
                               "liraglutide", "semaglutide", "dulaglutide", "acarbose", "voglibose", "glucophage",
                               "januvia", "jardiance", "ozempic"],
    "Blood pressure medicine": ["amlodipine", "telmisartan", "losartan", "olmesartan", "valsartan", "ramipril",
                                "enalapril", "lisinopril", "atenolol", "metoprolol", "bisoprolol", "carvedilol",
                                "nebivolol", "hydrochlorothiazide", "chlorthalidone", "indapamide", "furosemide",
                                "torsemide", "spironolactone", "nifedipine", "diltiazem", "verapamil", "clonidine",
                                "prazosin", "labetalol", "norvasc", "bp tablet", "bp tablets", "water pill", "water pills"],
    "Cholesterol medicine": ["atorvastatin", "rosuvastatin", "simvastatin", "pravastatin", "fenofibrate", "ezetimibe",
                             "statin", "statins", "lipitor", "crestor"],
    "Blood thinner": ["warfarin", "apixaban", "rivaroxaban", "dabigatran", "clopidogrel", "ticagrelor", "aspirin",
                      "heparin", "blood thinner", "blood thinners", "eliquis", "xarelto"],
    "Heart medicine": ["digoxin", "amiodarone", "isosorbide", "nitroglycerin", "ranolazine", "ivabradine", "sacubitril",
                       "heart tablet", "heart tablets", "heart medicine", "heart medication"],
    "General medicine terms": ["medication", "medications", "medicine", "medicines", "meds", "dose", "doses", "dosage",
                               "dosing", "tablet", "tablets", "pill", "pills", "capsule", "capsules", "syrup", "injection",
                               "injections", "inhaler", "patch", "drug", "drugs", "prescription", "prescriptions", "mg",
                               "mcg", "refill", "supplement", "supplements", "antibiotic", "antibiotics", "painkiller",
                               "painkillers", "tablet strip"],
}


def medication_rows():
    rows = [("action", w, "") for w in ACTION_WORDS]
    seen = set()
    for g, words in MEDS.items():
        for w in words:
            if w not in seen:
                seen.add(w)
                rows.append(("medication", w, g))
    return rows


# ----------------------------------------------------------------- ER-502 test values
# (reading_type, field, operator, general_threshold, unit_hint)
CHECKS = [
    ("Glucose", "value", ">=", 300), ("Glucose", "value", "<=", 54),
    ("Blood pressure", "systolic", ">=", 160), ("Blood pressure", "systolic", "<=", 90),
    ("Blood pressure", "diastolic", ">=", 100), ("Blood pressure", "diastolic", "<=", 55),
    ("Weight", "value", ">=", 200), ("Weight", "value", "<=", 30),
    ("Heart rate", "value", ">=", 130), ("Heart rate", "value", "<=", 40),
    ("Oxygen saturation", "value", "<=", 90),
    ("Body temperature", "value", ">=", 39.5), ("Body temperature", "value", "<=", 35),
    ("Respiratory rate", "value", ">=", 30), ("Respiratory rate", "value", "<=", 8),
    ("HbA1c", "value", ">=", 11), ("Total cholesterol", "value", ">=", 300), ("LDL cholesterol", "value", ">=", 190),
    ("Triglycerides", "value", ">=", 500), ("BMI", "value", ">=", 45), ("BMI", "value", "<=", 15),
    ("Waist circumference", "value", ">=", 130), ("Peak flow", "value", "<=", 150),
    ("Creatinine", "value", ">=", 3), ("Potassium", "value", ">=", 6), ("Potassium", "value", "<=", 3),
]
# Program rows are never LESS sensitive than the general row; Cardiac is the most sensitive (placeholder choice).
FACTOR_HIGH = {"Diabetes Support": 0.98, "Hypertension Support": 0.96, "Cardiac Wellness": 0.94}
FACTOR_LOW = {"Diabetes Support": 1.03, "Hypertension Support": 1.05, "Cardiac Wellness": 1.07}
ORIGINAL_NOTE = {
    ("Blood pressure", "systolic", ">="): "DEMO PLACEHOLDER chosen so the rule can be demonstrated. NOT a clinical threshold; clinicians must set real values.",
    ("Blood pressure", "diastolic", ">="): "DEMO PLACEHOLDER. NOT a clinical threshold.",
    ("Glucose", "value", ">="): "DEMO PLACEHOLDER. NOT a clinical threshold.",
}


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.1f}"


def high_risk_rows():
    rows = []
    for rtype, field, op, thr in CHECKS:
        rows.append((rtype, field, op, _fmt(thr), "", ORIGINAL_NOTE.get((rtype, field, op), "DEMO PLACEHOLDER. NOT a clinical threshold; clinicians must set real values.")))
        for prog in PROGRAMS:
            f = FACTOR_HIGH[prog] if op == ">=" else FACTOR_LOW[prog]
            v = thr * f
            v = round(v) if thr >= 20 else round(v, 1)
            rows.append((rtype, field, op, _fmt(v), prog, f"DEMO PLACEHOLDER for {prog}. NOT a clinical threshold."))
    return rows


# ----------------------------------------------------------------- escalation rules + routing variants
BASE_RULES = [
    ("ER-501", "Consent is not active", "Stop processing and direct member to program staff."),
    ("ER-502", "Reading matches configured high-risk test value", "Create urgent staff-review record; do not interpret."),
    ("ER-503", "User asks to change medication", "Decline and direct to qualified clinician."),
    ("ER-504", "Source or reading is contradictory", "Mark uncertainty and request human review."),
]
TEAM = {"Diabetes Support": "Diabetes care team", "Hypertension Support": "Hypertension care team", "Cardiac Wellness": "Cardiac care team"}
CONSENT_ACTION = {
    "Expired": "Stop processing; ask staff to renew the expired consent",
    "Pending": "Stop processing; ask staff to complete the pending consent",
    "Revoked": "Stop processing; staff confirm the withdrawal and make no further contact except to confirm it",
}


def variant_rows():
    rows, n = [], 505
    def add(parent, cond, action, program="", context="", channel="", queue=""):
        nonlocal n
        rows.append((f"ER-{n}", cond, action, parent, program, context, channel, queue)); n += 1
    for status, act in CONSENT_ACTION.items():
        for prog in PROGRAMS:
            for ch in CHANNELS:
                add("ER-501", f"Consent is {status} ({prog}, {ch})", f"{act}; contact the member by {ch}.", prog, status, ch, "Enrolment and consent desk")
    for rtype in __import__("src.schemas", fromlist=["READING_TYPES"]).READING_TYPES:
        for prog in PROGRAMS:
            add("ER-502", f"{rtype} entry matches a configured test value ({prog})",
                f"Create an urgent staff-review record for the {TEAM[prog]}; do not interpret.", prog, rtype, "", f"{TEAM[prog]} - urgent review")
    for grp in ["Insulin", "Oral diabetes medicine", "Blood pressure medicine", "Cholesterol medicine", "Blood thinner", "Heart medicine", "General medicine terms"]:
        for prog in PROGRAMS:
            add("ER-503", f"Member asks to change medication ({grp}, {prog})",
                f"Decline and direct to a qualified clinician; notify the {TEAM[prog]} desk.", prog, grp, "", f"Clinician referral desk - {prog}")
    for ctx, act in [("Contradictory readings", "Mark the uncertainty and ask a person to check the two entries with the member"),
                     ("Conflicting article versions", "Mark the uncertainty and ask the content lead to resolve the document versions")]:
        for prog in PROGRAMS:
            add("ER-504", f"{ctx} ({prog})", f"{act}.", prog, ctx, "", "Data quality review" if "readings" in ctx else "Content review")
    return BASE_RULES_FULL + rows


BASE_RULES_FULL = [r + ("", "", "", "", "") for r in BASE_RULES]
