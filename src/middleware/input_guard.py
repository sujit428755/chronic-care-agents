"""Input guard: detects prompt-injection attempts and requests for clinical advice.

* `contains_injection()` and `is_clinical_advice_request()` are plain functions used by the orchestrator.
* `input_guard_middleware` is the same injection check attached to every Agent Framework agent
  (the "content safety middleware" pattern from the reference middleware_demo.py).

The medication-change check (ER-503) lives in src/tools/rules_tools.py because it is a configured rule.
"""
from __future__ import annotations

import re

INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|your) (instructions|rules)",
    r"disregard (all |any |the )?(previous |prior |your )?(instructions|rules)",
    r"bypass (your|the) (rules|safety|guardrails)",
    r"\bjailbreak\b",
    r"reveal (your|the) (system )?(prompt|instructions)",
    r"\bsystem prompt\b",
    r"you are now\b",
    r"(act|pretend|behave) (as|like|to be) (a |an |if you were )?(doctor|clinician|nurse|physician)",
    r"pretend (that )?you are (a |an )?(doctor|clinician|nurse|physician)",
]

CLINICAL_ADVICE_PATTERNS = [
    r"\bis (?:this|that|it|my[\w\s/]{0,40}?)\s+(?:normal|abnormal|high|low|dangerous|bad|ok|okay|safe|serious|healthy|worrying|concerning|fine|alright|good)\b",
    r"\bwhat (?:do|does) (?:my|this|these|that)\b.{0,40}\bmean\b",
    r"\b(?:should|do) i (?:be )?(?:worry|worried|panic|panicking|go to|see a|call a|visit)\b",
    r"\bam i (?:ok|okay|sick|diabetic|in danger|at risk|getting worse)\b",
    r"\bdo i have (?:diabetes|hypertension|a problem|high|low)\b",
    r"\bdiagnos(?:e|is)\b",
    r"\bwhat should i do about my\b",
    r"\bis it (?:safe|dangerous|serious)\b",
    r"\bwill my\b.{0,30}\b(?:get worse|worsen|improve)\b",
]


def contains_injection(text: str) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in INJECTION_PATTERNS)


def is_clinical_advice_request(text: str) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in CLINICAL_ADVICE_PATTERNS)


try:
    from agent_framework import agent_middleware
except ImportError:  # OFFLINE mode does not need the framework
    def agent_middleware(fn):  # type: ignore
        return fn


@agent_middleware
async def input_guard_middleware(context, call_next) -> None:
    """Agent middleware: stop an agent run if the latest message looks like a prompt-injection attempt."""
    from agent_framework import AgentResponse, Message  # imported here so OFFLINE mode needs no framework

    last = context.messages[-1].text if context.messages else ""
    if contains_injection(last or ""):
        context.result = AgentResponse(
            messages=[Message("assistant", ["BLOCKED: this request cannot be processed. Please contact program staff."])]
        )
        return
    await call_next()
