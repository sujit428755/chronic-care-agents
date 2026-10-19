"""Reading tools. Used by the Reading Summary Agent (and by the orchestrator for the safety checks).

Only ACTIVE readings are ever returned. A reading that was corrected (status 'superseded') is never part of an
active summary; only its ID is kept so staff can see that a correction happened.
"""
import json
from datetime import date, datetime, timedelta
from typing import Annotated, Optional

from src.tools.store import load_table, simulate_failure

TS_FORMAT = "%Y-%m-%d %H:%M"


def _ts(reading: dict) -> datetime:
    return datetime.strptime(reading["recorded_at"], TS_FORMAT)


def _all_for_member(member_id: str) -> list[dict]:
    simulate_failure("readings")
    return [r for r in load_table("readings") if r["member_id"] == member_id]


def load_active_readings(
    member_id: str,
    reading_type: Optional[str] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> list[dict]:
    rows = [r for r in _all_for_member(member_id) if (r.get("status") or "active") == "active"]
    if reading_type:
        rows = [r for r in rows if r["type"].lower() == reading_type.lower()]
    if start:
        rows = [r for r in rows if _ts(r).date() >= start]
    if end:
        rows = [r for r in rows if _ts(r).date() <= end]
    return sorted(rows, key=_ts)


def reading_types_for_member(member_id: str) -> list[str]:
    types = []
    for r in _all_for_member(member_id):
        if (r.get("status") or "active") == "active" and r["type"] not in types:
            types.append(r["type"])
    return types


def corrections_for_member(member_id: str, start: Optional[date] = None, end: Optional[date] = None,
                           types: Optional[list[str]] = None) -> list[dict]:
    """IDs only (never the superseded value) so staff can see that a correction was applied."""
    out = []
    for r in _all_for_member(member_id):
        if r.get("status") == "superseded":
            if types and r["type"] not in types:
                continue
            d = _ts(r).date()
            if (start and d < start) or (end and d > end):
                continue
            out.append({"superseded": r["reading_id"], "replaced_by": r.get("superseded_by") or None})
    return out


def days_in_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def find_missing_dates(readings: list[dict], start: date, end: date) -> list[str]:
    have = {_ts(r).date() for r in readings}
    return [d.isoformat() for d in days_in_range(start, end) if d not in have]


def numeric_parts(value: str) -> list[float]:
    return [float(p) for p in value.split("/")]


def _fmt(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else str(n)


def compute_facts(member_id: str, reading_type: str, start: date, end: date) -> dict:
    """Deterministic facts for one reading type and date range. This is the single source of truth for summaries."""
    rows = load_active_readings(member_id, reading_type, start, end)
    unit = rows[0]["unit"] if rows else ""
    facts = {
        "member_id": member_id,
        "reading_type": reading_type,
        "date_range_start": start.isoformat(),
        "date_range_end": end.isoformat(),
        "window_days": (end - start).days + 1,
        "count": len(rows),
        "unit": unit,
        "readings": [
            {"reading_id": r["reading_id"], "recorded_at": r["recorded_at"], "value": r["value"], "unit": r["unit"], "type": r["type"]}
            for r in rows
        ],
        "missing_dates": find_missing_dates(rows, start, end),
        "source_reading_ids": [r["reading_id"] for r in rows],
    }

    if not rows:
        facts["range_description"] = "No readings were recorded in this period."
        facts["trend_description"] = "No trend can be described because there are no readings."
        return facts

    values = [r["value"] for r in rows]
    if "/" in values[0]:  # blood pressure style "128/82"
        sys_vals = [numeric_parts(v)[0] for v in values]
        dia_vals = [numeric_parts(v)[1] for v in values]
        facts["range_description"] = (
            f"Top number ranged from {_fmt(min(sys_vals))} to {_fmt(max(sys_vals))}; "
            f"bottom number ranged from {_fmt(min(dia_vals))} to {_fmt(max(dia_vals))} {unit}."
        )
        facts["trend_description"] = "Values in date order: " + "; ".join(values) + f" {unit}."
    else:
        nums = [float(v) for v in values]
        facts["range_description"] = f"Lowest entry {_fmt(min(nums))} {unit}; highest entry {_fmt(max(nums))} {unit}."
        trend = "Values in date order: " + ", ".join(_fmt(n) for n in nums) + f" {unit}."
        if len(nums) >= 2:
            diff = nums[-1] - nums[0]
            if diff == 0:
                trend += " The latest entry equals the first entry."
            else:
                direction = "higher" if diff > 0 else "lower"
                trend += f" The latest entry is {_fmt(abs(diff))} {unit} {direction} than the first entry."
        else:
            trend += " Only one reading, so no trend is described."
        facts["trend_description"] = trend
    return facts


def fallback_narrative(facts: dict) -> str:
    """Template wording used in OFFLINE mode, and whenever an agent's wording fails validation."""
    t = facts["reading_type"].lower()
    if facts["count"] == 0:
        text = f"No {t} readings were recorded between {facts['date_range_start']} and {facts['date_range_end']}."
    else:
        ids = ", ".join(facts["source_reading_ids"])
        text = (
            f"Between {facts['date_range_start']} and {facts['date_range_end']} there {'is' if facts['count'] == 1 else 'are'} "
            f"{facts['count']} recorded {t} reading{'s' if facts['count'] != 1 else ''} ({ids}). "
            f"{facts['range_description']} {facts['trend_description']}"
        )
    if facts["missing_dates"]:
        text += " No entry was recorded on: " + ", ".join(facts["missing_dates"]) + "."
    return text


# ----------------------------------------------------------------------------
# Tool exposed to the Reading Summary Agent (Agent Framework function tool)
# ----------------------------------------------------------------------------
def get_reading_facts(
    member_id: Annotated[str, "Member ID, e.g. 'M-101'"],
    reading_type: Annotated[str, "One of: Glucose, Blood pressure, Weight"],
    start_date: Annotated[str, "Start date YYYY-MM-DD (inclusive)"],
    end_date: Annotated[str, "End date YYYY-MM-DD (inclusive)"],
) -> str:
    """Returns the member's ACTIVE self-reported readings for a date range as JSON, with count, range and missing dates."""
    facts = compute_facts(member_id, reading_type, date.fromisoformat(start_date), date.fromisoformat(end_date))
    return json.dumps(facts)
