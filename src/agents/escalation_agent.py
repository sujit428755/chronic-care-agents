"""Escalation Agent (Agent Framework).

Tool access: ONLY the rules (get_escalation_rules, check_rules_for_member). No articles, no care plan.
WHICH rules matched is decided by code (src/tools/rules_tools.py). The agent only words the note for staff;
if its wording is not acceptable, a fixed template is used. It never makes a clinical decision.
"""
from __future__ import annotations

from src.middleware.output_guard import check_text
from src.models import EscalationNarrative, EscalationRecord
from src.prompts import ESCALATION_INSTRUCTIONS
from src.tools.rules_tools import check_rules_for_member, get_escalation_rules

URGENCY_BY_RULE = {
    "ER-501": "staff_contact",
    "ER-502": "urgent_staff_review",
    "ER-503": "clinician_referral",
    "ER-504": "human_review",
}
URGENCY_ORDER = ["urgent_staff_review", "clinician_referral", "human_review", "staff_contact", "staff_followup", "none"]


def template_reason(rule_ids: list[str], source_ids: list[str], extra: str = "") -> str:
    base = f"Routed to staff under rule(s) {', '.join(rule_ids) if rule_ids else 'none (staff follow-up policy)'}"
    if source_ids:
        base += f"; records involved: {', '.join(source_ids)}"
    base += ". No clinical interpretation has been made."
    return f"{base} {extra}".strip()


def pick_urgency(rule_ids: list[str], default: str = "staff_followup") -> str:
    levels = [URGENCY_BY_RULE[r] for r in rule_ids if r in URGENCY_BY_RULE] or [default]
    return sorted(levels, key=URGENCY_ORDER.index)[0]


async def build_record(
    rule_ids: list[str], source_ids: list[str], member_id: str, window: tuple[str, str],
    offline: bool, notes: list[str], extra: str = "", default_urgency: str = "staff_followup",
    routing: list[dict] | None = None,
) -> EscalationRecord:
    routing = routing or []
    reason = template_reason(rule_ids, source_ids, extra)
    queues = list(dict.fromkeys(r["queue"] for r in routing if r.get("queue")))
    if queues:
        reason = reason.replace(" No clinical interpretation has been made.", f" Suggested staff queue: {'; '.join(queues)}. No clinical interpretation has been made.", 1)
    if not offline:
        from src.agents.base import invoke_structured
        from src.tools.rules_tools import load_rules

        configured = [r for rid, r in load_rules().items() if rid in rule_ids]
        prompt = (
            f"Member {member_id}. Matched rule IDs (decided by code, do not change): {', '.join(rule_ids) or 'none'}. "
            f"Involved record IDs: {', '.join(source_ids) or 'none'}. Review window: {window[0]} to {window[1]}. "
            f"Extra context: {extra or 'none'}. Write the staff note."
        )
        try:
            result = await invoke_structured(
                "escalation", prompt, EscalationNarrative, name="EscalationAgent", instructions=ESCALATION_INSTRUCTIONS,
                tools=[get_escalation_rules, check_rules_for_member], facts={"matched_rules": configured, "routing_variants": routing})
            text = result.reason_text.strip()
            if check_text(text):
                notes.append("escalation_agent_wording_rejected")
            elif not all(r in text for r in rule_ids):
                notes.append("escalation_agent_wording_rejected:rule_missing")
            else:
                reason = text
        except Exception as exc:  # noqa: BLE001
            notes.append(f"escalation_agent_unavailable:{type(exc).__name__}")

    return EscalationRecord(
        triggered=True,
        rule_ids=rule_ids,
        urgency=pick_urgency(rule_ids, default_urgency),
        reason=reason,
        source_ids=source_ids,
        queue="; ".join(queues),
        variant_ids=[r["variant_id"] for r in routing],
    )
