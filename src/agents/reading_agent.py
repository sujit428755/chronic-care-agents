"""Reading Summary Agent (Agent Framework).

Tool access: ONLY get_reading_facts (the member's active readings). No care plan, no articles.
Facts are always computed by code (src/tools/reading_tools.compute_facts). The agent only writes the wording,
and its wording is rejected if it contains a number that is not in the facts or any forbidden language.
"""
from __future__ import annotations

import json

from src.middleware.output_guard import check_text, numbers_are_grounded
from src.models import NON_DIAGNOSTIC_LABEL, ReadingNarrative, ReadingSummary
from src.prompts import READING_INSTRUCTIONS
from src.tools.reading_tools import fallback_narrative, get_reading_facts


def _allowed_numbers(facts: dict) -> set[float]:
    allowed = {float(facts["count"]), float(facts["window_days"]), float(len(facts["missing_dates"]))}
    for r in facts["readings"]:
        allowed.update(float(p) for p in r["value"].split("/"))
    return allowed


async def summarise(facts: dict, offline: bool, notes: list[str]) -> ReadingSummary:
    narrative = fallback_narrative(facts)
    if not offline:
        from src.agents.base import invoke_structured

        prompt = (
            f"Summarise the readings for member {facts['member_id']}, reading type '{facts['reading_type']}', "
            f"from {facts['date_range_start']} to {facts['date_range_end']}."
        )
        try:
            result = await invoke_structured("reading", prompt, ReadingNarrative, name="ReadingSummaryAgent",
                                             instructions=READING_INSTRUCTIONS, tools=[get_reading_facts], facts=facts)
            text = result.narrative.strip()
            problems = check_text(text)
            if problems:
                notes.append(f"reading_agent_wording_rejected:{','.join(problems)}")
            elif not numbers_are_grounded(text, _allowed_numbers(facts)):
                notes.append("reading_agent_wording_rejected:ungrounded_number")
            elif facts["missing_dates"] and not all(d in text for d in facts["missing_dates"]):
                notes.append("reading_agent_wording_rejected:missing_dates_not_listed")
            else:
                narrative = text
        except Exception as exc:  # noqa: BLE001
            notes.append(f"reading_agent_unavailable:{type(exc).__name__}")

    return ReadingSummary(
        member_id=facts["member_id"],
        reading_type=facts["reading_type"],
        date_range_start=facts["date_range_start"],
        date_range_end=facts["date_range_end"],
        count=facts["count"],
        range_description=facts["range_description"],
        trend_description=facts["trend_description"],
        missing_dates=facts["missing_dates"],
        source_reading_ids=facts["source_reading_ids"],
        narrative=narrative,
        label=NON_DIAGNOSTIC_LABEL,
    )
