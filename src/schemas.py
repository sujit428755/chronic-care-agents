"""Canonical table schemas.

DECISION: every table in this project is stored as CSV (one header row, UTF-8).
  * tables  -> CSV   (members, readings, care plan tasks, rule values, article catalog)
  * documents (articles, FAQs, guidance) -> Markdown files with a small front-matter block
The Data Manager converts any uploaded file (CSV, JSON, Excel, text, Word, PDF) into one of these two shapes.

Each schema says: the columns, which are required, the unique key, and the checks applied to every row
before anything is saved (so a bad upload can never corrupt the data the agents read).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

READING_TYPES = ["Glucose", "Blood pressure", "Weight", "Heart rate", "Oxygen saturation", "Body temperature",
                 "Respiratory rate", "HbA1c", "Total cholesterol", "LDL cholesterol", "Triglycerides", "BMI",
                 "Waist circumference", "Peak flow", "Creatinine", "Potassium"]
LIVE_READING_TYPES = ["Glucose", "Blood pressure", "Weight"]   # types the synthetic readings.csv actually contains
MED_GROUPS = ["Insulin", "Oral diabetes medicine", "Blood pressure medicine", "Cholesterol medicine", "Blood thinner",
              "Heart medicine", "General medicine terms"]
CHANNELS = ["App", "SMS", "Email"]
CONSENT = ["Active", "Expired", "Revoked", "Pending"]
PROGRAMS = ["Diabetes Support", "Hypertension Support", "Cardiac Wellness"]
FREQUENCIES = ["Daily", "Weekly", "Monthly", "Once"]
TASK_STATUS = ["Due", "Open", "Overdue", "Scheduled", "Completed"]
ARTICLE_TYPES = ["education", "faq", "careplan_guidance"]
ARTICLE_STATUS = ["Approved", "Draft", "Retired"]
ARTICLE_PROGRAMS = ["All programs"] + PROGRAMS


@dataclass
class Schema:
    name: str
    columns: list[str]
    required: list[str]
    key: list[str]
    allowed: dict[str, list[str]] = field(default_factory=dict)
    patterns: dict[str, str] = field(default_factory=dict)       # column -> regex that the value must match
    dates: dict[str, str] = field(default_factory=dict)          # column -> strptime format
    defaults: dict[str, str] = field(default_factory=dict)       # filled in when the cell is empty
    synonyms: dict[str, list[str]] = field(default_factory=dict)  # for auto column mapping
    title: str = ""
    help: str = ""

    def validate_row(self, row: dict) -> list[str]:
        problems = []
        for c in self.required:
            if not str(row.get(c, "")).strip():
                problems.append(f"{c} is empty")
        for c, options in self.allowed.items():
            v = str(row.get(c, "")).strip()
            if v and v not in options:
                problems.append(f"{c}='{v}' is not one of {options}")
        for c, pat in self.patterns.items():
            v = str(row.get(c, "")).strip()
            if v and not re.fullmatch(pat, v):
                problems.append(f"{c}='{v}' has the wrong format")
        for c, fmt in self.dates.items():
            v = str(row.get(c, "")).strip()
            if v:
                try:
                    datetime.strptime(v, fmt)
                except ValueError:
                    problems.append(f"{c}='{v}' is not a date in format {fmt}")
        return problems


SCHEMAS: dict[str, Schema] = {
    "members": Schema(
        name="members", title="Members",
        columns=["member_id", "program", "preferred_channel", "language", "consent_status", "note"],
        required=["member_id", "program", "preferred_channel", "language", "consent_status"],
        key=["member_id"],
        allowed={"preferred_channel": CHANNELS, "consent_status": CONSENT, "program": PROGRAMS},
        patterns={"member_id": r"M-\d{3,6}"},
        synonyms={
            "member_id": ["id", "memberid", "member", "patient_id", "patientid"],
            "program": ["programme", "care_program", "condition"],
            "preferred_channel": ["channel", "contact_channel", "contact_method"],
            "language": ["lang", "preferred_language"],
            "consent_status": ["consent", "consentstatus"],
        },
        help="One row per synthetic member. Only consent_status = Active is processed (rule ER-501).",
    ),
    "readings": Schema(
        name="readings", title="Self-reported readings",
        columns=["reading_id", "member_id", "type", "value", "unit", "recorded_at", "status", "superseded_by", "corrects", "note"],
        required=["reading_id", "member_id", "type", "value", "unit", "recorded_at"],
        key=["reading_id"],
        allowed={"type": READING_TYPES, "status": ["active", "superseded"]},
        patterns={"reading_id": r"R-\d{3,7}", "member_id": r"M-\d{3,6}", "value": r"\d+(\.\d+)?(/\d+(\.\d+)?)?"},
        dates={"recorded_at": "%Y-%m-%d %H:%M"},
        defaults={"status": "active"},
        synonyms={
            "reading_id": ["id", "readingid"],
            "member_id": ["memberid", "member", "patient_id"],
            "type": ["reading_type", "measurement", "metric"],
            "value": ["reading", "result", "measurement_value"],
            "recorded_at": ["timestamp", "datetime", "date_time", "recorded", "taken_at", "time"],
        },
        help="One row per self-reported reading. To correct a reading, mark the old row status=superseded and set superseded_by.",
    ),
    "care_plan_tasks": Schema(
        name="care_plan_tasks", title="Care plan tasks",
        columns=["task_id", "member_id", "task", "frequency", "next_due", "status"],
        required=["task_id", "member_id", "task", "frequency", "next_due", "status"],
        key=["task_id"],
        allowed={"frequency": FREQUENCIES, "status": TASK_STATUS},
        patterns={"task_id": r"CP-\d{3,7}", "member_id": r"M-\d{3,6}"},
        dates={"next_due": "%Y-%m-%d"},
        synonyms={
            "task_id": ["id", "taskid"],
            "task": ["task_name", "action", "description"],
            "next_due": ["due", "due_date", "next_due_date"],
            "frequency": ["freq", "repeat"],
        },
        help="Care plan records. The status is reported exactly as recorded; the system never recalculates it.",
    ),
    "escalation_rules": Schema(
        name="escalation_rules", title="Escalation rules",
        columns=["rule_id", "condition", "action", "parent_rule", "program", "context", "channel", "queue"],
        required=["rule_id", "condition", "action"],
        key=["rule_id"],
        allowed={"program": PROGRAMS, "channel": CHANNELS},
        patterns={"rule_id": r"ER-\d{3}", "parent_rule": r"ER-50[1-4]"},
        help=("ER-501 to ER-504 are the four rules (their logic is fixed in code). Rows with a parent_rule are ROUTING VARIANTS: "
              "when the parent rule fires, the most specific variant (program / context / channel) decides the staff queue and the action wording. "
              "A blank program, context or channel means 'any'."),
    ),
    "high_risk_values": Schema(
        name="high_risk_values", title="ER-502 configured test values",
        columns=["reading_type", "field", "operator", "threshold", "program", "note"],
        required=["reading_type", "field", "operator", "threshold"],
        key=["reading_type", "field", "operator", "program"],
        allowed={"reading_type": READING_TYPES, "field": ["systolic", "diastolic", "value"], "operator": [">=", ">", "<=", "<"], "program": PROGRAMS},
        patterns={"threshold": r"\d+(\.\d+)?"},
        help="A reading matches ER-502 if ANY (field, operator) check is true; for each check a row for the member's program replaces the general (blank program) row. These are demo placeholders, not clinical thresholds: clinicians must set real values.",
    ),
    "medication_words": Schema(
        name="medication_words", title="ER-503 word lists",
        columns=["kind", "word", "group"],
        required=["kind", "word"],
        key=["kind", "word"],
        allowed={"kind": ["action", "medication"], "group": MED_GROUPS},
        help="A message matches ER-503 when it has at least one action word AND at least one medication word.",
    ),
    "articles_catalog": Schema(
        name="articles_catalog", title="Approved article catalog",
        columns=["article_id", "title", "program", "version", "scope", "type", "file", "status", "approved_by", "updated_at", "note"],
        required=["article_id", "title", "program", "version", "scope", "type", "file", "status"],
        key=["article_id"],
        allowed={"program": ARTICLE_PROGRAMS, "type": ARTICLE_TYPES, "status": ARTICLE_STATUS},
        patterns={"article_id": r"(EDU|FAQ|CPG)-\d{3,5}", "version": r"v\d+"},
        help="Only articles with status Approved are indexed, retrieved and cited.",
    ),
}

# Tables an uploaded CSV / JSON / Excel file can be merged into.
UPLOAD_TARGETS = ["members", "readings", "care_plan_tasks", "high_risk_values", "medication_words", "articles_catalog"]
