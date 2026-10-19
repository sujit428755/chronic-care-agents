"""Escalation rules (ER-501 to ER-504), applied exactly as configured in data/escalation_rules.csv, high_risk_values.csv and medication_words.csv.

These checks are plain code on purpose: a safety rule must give the same answer every time.
The Escalation Agent may WORD the staff note, but it can never add, remove or change a rule match.
"""
import json
import re
from datetime import date
from typing import Annotated, Optional

from src.tools.member_tools import get_member
from src.tools.reading_tools import load_active_readings, numeric_parts
from src.tools.store import load_table


def load_rules() -> dict:
    """The base rules only (ER-501..ER-504 style rows). Routing variants are looked up by resolve_variant()."""
    return {r["rule_id"]: r for r in load_table("escalation_rules") if not (r.get("parent_rule") or "").strip()}


def _words(kind: str) -> list[str]:
    return [r["word"].strip().lower() for r in load_table("medication_words") if r["kind"] == kind]


# ----------------------------- ER-503 -----------------------------
def is_medication_change_request(text: str) -> bool:
    """At least one action word AND at least one medication word (both lists editable in the Data Manager)."""
    t = " " + re.sub(r"[^a-z0-9' ]+", " ", text.lower()) + " "
    has_action = any(f" {w} " in t or f" {w}s " in t or f" {w}ing " in t for w in _words("action"))
    has_med = any(f" {w} " in t for w in _words("medication"))
    return has_action and has_med


def medication_group(text: str) -> str:
    """Group of the first listed medication word found in the text (for routing only; never for advice)."""
    t = " " + re.sub(r"[^a-z0-9' ]+", " ", text.lower()) + " "
    for r in load_table("medication_words"):
        if r["kind"] == "medication" and r.get("group") and f" {r['word'].strip().lower()} " in t:
            return r["group"]
    return ""


# ----------------------------- ER-502 -----------------------------
_OPS = {">=": lambda a, b: a >= b, ">": lambda a, b: a > b, "<=": lambda a, b: a <= b, "<": lambda a, b: a < b}


def _effective_rows(params: list[dict], reading_type: str, program: Optional[str]) -> list[dict]:
    """Rows for this reading type. For each (field, operator) check, a row for the member's program replaces the general row."""
    chosen: dict[tuple, dict] = {}
    for p in params:
        if p["reading_type"] != reading_type:
            continue
        scope = (p.get("program") or "").strip()
        if scope and scope != (program or ""):
            continue
        k = (p["field"], p["operator"])
        if k not in chosen or (scope and not (chosen[k].get("program") or "").strip()):
            chosen[k] = p
    return list(chosen.values())


def _matches_test_value(reading: dict, params: list[dict], program: Optional[str] = None) -> Optional[str]:
    """True if ANY effective check for this reading type is satisfied (see _effective_rows)."""
    mine = _effective_rows(params, reading["type"], program)
    if not mine:
        return None
    parts = numeric_parts(reading["value"])
    sys_v, dia_v = parts[0], (parts[1] if len(parts) > 1 else None)
    for p in mine:
        actual = {"systolic": sys_v, "diastolic": dia_v, "value": sys_v}[p["field"]]
        if actual is not None and _OPS[p["operator"]](actual, float(p["threshold"])):
            label = {"systolic": "top number", "diastolic": "bottom number", "value": "value"}[p["field"]]
            return f"configured test value: {label} {p['operator']} {p['threshold']}"
    return None


def evaluate_high_risk(readings: list[dict], program: Optional[str] = None) -> list[dict]:
    params = load_table("high_risk_values")
    matches = []
    for r in readings:
        why = _matches_test_value(r, params, program)
        if why:
            matches.append({"rule_id": "ER-502", "reading_id": r["reading_id"], "detail": why})
    return matches


# ----------------------------- ER-504 -----------------------------
def find_contradictions(readings: list[dict]) -> list[dict]:
    """Two ACTIVE readings of the same type at the same timestamp with different values contradict each other."""
    groups: dict[tuple, list[dict]] = {}
    for r in readings:
        groups.setdefault((r["type"], r["recorded_at"]), []).append(r)
    out = []
    for (rtype, ts), rows in groups.items():
        if len({r["value"] for r in rows}) > 1:
            out.append({
                "rule_id": "ER-504",
                "reading_ids": [r["reading_id"] for r in rows],
                "detail": f"Two active {rtype} readings share the timestamp {ts} but have different values.",
            })
    return out


def check_readings_against_rules(member_id: str, start: date, end: date) -> dict:
    readings = load_active_readings(member_id, start=start, end=end)
    program = (get_member(member_id) or {}).get("program")
    return {
        "readings": readings,
        "high_risk": evaluate_high_risk(readings, program),
        "contradictions": find_contradictions(readings),
    }


# ------------------- Tools exposed to the Escalation Agent -------------------
def get_escalation_rules() -> str:
    """Returns the configured escalation rules (rule_id, condition, action) as JSON."""
    rules = list(load_rules().values())
    return json.dumps(rules)


def check_rules_for_member(
    member_id: Annotated[str, "Member ID, e.g. 'M-102'"],
    start_date: Annotated[str, "Start date YYYY-MM-DD"],
    end_date: Annotated[str, "End date YYYY-MM-DD"],
) -> str:
    """Runs the configured reading rules (ER-502, ER-504) for a member and date range. Returns matches as JSON."""
    res = check_readings_against_rules(member_id, date.fromisoformat(start_date), date.fromisoformat(end_date))
    return json.dumps({"high_risk": res["high_risk"], "contradictions": res["contradictions"]})


# ------------------- Routing variants (which staff queue, which wording) -------------------
def resolve_variant(parent: str, program: str = "", context: str = "", channel: str = "") -> Optional[dict]:
    """Most specific routing variant of a base rule. A blank cell in the table means 'any'.
    A variant whose program / context / channel is set but different is skipped. Ties: lowest rule_id.
    Returns None when no variant fits (the base rule wording is then used)."""
    best, best_score = None, -1
    for r in sorted(load_table("escalation_rules"), key=lambda x: x["rule_id"]):
        if (r.get("parent_rule") or "") != parent:
            continue
        score = 0
        ok = True
        for col, val in (("program", program), ("context", context), ("channel", channel)):
            want = (r.get(col) or "").strip()
            if not want:
                continue
            if want.lower() != (val or "").strip().lower():
                ok = False
                break
            score += 1
        if ok and score > best_score:
            best, best_score = r, score
    return best


def routing_for(rule_ids: list[str], member_id: str, source_ids: list[str], message: str = "") -> list[dict]:
    """For each fired base rule, the routing variant that applies (rule_id, variant_id, queue, action). Never raises."""
    try:
        m = get_member(member_id) or {}
        program, channel, consent = m.get("program") or "", m.get("preferred_channel") or "", m.get("consent_status") or ""
        rtypes: list[str] = []
        ids = {i for i in source_ids if i.startswith("R-")}
        if ids:
            rtypes = [r["type"] for r in load_table("readings") if r["reading_id"] in ids]
        out = []
        for rid in rule_ids:
            if rid == "ER-501":
                ctxs, ch = [consent], channel
            elif rid == "ER-502":
                ctxs, ch = rtypes or [""], ""
            elif rid == "ER-503":
                ctxs, ch = [medication_group(message) or "General medicine terms"], ""
            else:  # ER-504
                ctxs, ch = (["Contradictory readings"] if ids else ["Conflicting article versions"]), ""
            for ctx in dict.fromkeys(ctxs):
                v = resolve_variant(rid, program, ctx, ch)
                if v:
                    out.append({"rule_id": rid, "variant_id": v["rule_id"], "queue": v.get("queue", ""), "action": v["action"]})
                    break
        return out
    except Exception:  # noqa: BLE001  routing is a convenience; a failure must never block an escalation
        return []
