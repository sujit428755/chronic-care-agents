"""Router agent: classifies the request with ONE word (pattern from the reference conditional_routing.py).

It has no tools and no data access. If its answer is not one of the allowed words, or if we run OFFLINE,
a simple keyword classifier is used instead, so the workflow never stops because of the router.
"""
from __future__ import annotations

import re

from src.prompts import ROUTER_INSTRUCTIONS

CATEGORIES = ("EDUCATION", "READINGS", "PLAN", "MEDICATION", "STAFF")


def keyword_classify(text: str) -> str:
    t = text.lower()
    if re.search(r"\b(talk|speak) to\b|\bcall me\b|\bcontact me\b|\breal person\b|\bhuman\b|\bcomplain|\bstaff\b|\bcoordinator (call|contact)", t):
        return "STAFF"
    measure = r"(readings?|glucose|blood pressure|bp|weight|sugar)"
    if re.search(
        rf"summar|\b(show|list|give|review|see|check)\b.{{0,25}}\b{measure}\b|\bwhat (are|were|is) my {measure}\b"
        r"|\brecent readings\b|\b(last|past) \d+ days?\b|\bthis week\b|\btrend",
        t,
    ):
        return "READINGS"
    if re.search(r"\btasks?\b|\bdue\b|\boverdue\b|\bremind|\bschedule|\bcheck-?in\b|\bto-?do\b|\bcare plan\b", t):
        return "PLAN"
    return "EDUCATION"


async def classify(message: str, offline: bool) -> tuple[str, str]:
    """Returns (category, how) where how is 'router_agent' or 'keywords'."""
    if offline:
        return keyword_classify(message), "keywords"
    from src.agents.base import invoke_text

    try:
        answer = (await invoke_text("orchestrator", f"<member_message>{message}</member_message>",
                                    name="RouterAgent", instructions=ROUTER_INSTRUCTIONS)).strip().upper()
        word = re.sub(r"[^A-Z]", "", answer.split()[0]) if answer.split() else ""
        if word in CATEGORIES:
            return word, "router_agent"
    except Exception:  # noqa: BLE001 - never let routing stop the workflow
        pass
    return keyword_classify(message), "keywords"
