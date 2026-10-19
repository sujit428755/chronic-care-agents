"""Pydantic models.

Two kinds live here:
  * models used as agent `response_format` (what an LLM is allowed to return), and
  * models for the final outputs (member response, coordinator packet, audit record).

Design rule used everywhere: FACTS (numbers, dates, IDs, rule matches) are computed by code.
Agents only supply WORDING, and that wording is checked against the facts before it is used.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

NON_DIAGNOSTIC_LABEL = "Descriptive summary only - not a diagnosis, not medical advice."


# ----------------------------------------------------------------------------
# What an LLM agent may return (response_format)
# ----------------------------------------------------------------------------
class ReadingNarrative(BaseModel):
    narrative: str = Field(description="Plain-language, purely descriptive summary of the supplied facts.")


class CarePlanNarrative(BaseModel):
    narrative: str = Field(description="Plain-language list of due and upcoming tasks, from the supplied records only.")


class ReminderDraft(BaseModel):
    channel: str
    language: str
    reminder_text: str = Field(description="Neutral reminder in the member's language, no medical advice.")
    english_text: str = Field(description="English version of the same reminder, for staff.")
    followup_question: str = Field(description="One neutral check-in question.")


class EscalationNarrative(BaseModel):
    reason_text: str = Field(description="One or two neutral sentences for staff saying why the case was routed. No interpretation.")


# ----------------------------------------------------------------------------
# Final outputs
# ----------------------------------------------------------------------------
class ReadingSummary(BaseModel):
    member_id: str
    reading_type: str
    date_range_start: str
    date_range_end: str
    count: int
    range_description: str
    trend_description: str
    missing_dates: list[str]
    source_reading_ids: list[str]
    narrative: str
    label: str = NON_DIAGNOSTIC_LABEL


class TaskItem(BaseModel):
    task_id: str
    task: str
    frequency: str
    next_due: str
    status: str


class CarePlanResult(BaseModel):
    action_needed: list[TaskItem]   # records whose status is Due or Overdue
    upcoming: list[TaskItem]        # records whose status is Open or Scheduled
    source_ids: list[str]
    narrative: str


class EscalationRecord(BaseModel):
    triggered: bool
    rule_ids: list[str]
    urgency: str                    # none | urgent_staff_review | human_review | staff_contact | clinician_referral | staff_followup
    reason: str
    source_ids: list[str] = []
    queue: str = ""                      # staff queue chosen by the routing variant (blank if none applies)
    variant_ids: list[str] = []          # routing variant rows used (e.g. ER-531)
    interpretation: str = "None. No clinical interpretation is made by this system."


class SourceRef(BaseModel):
    source_id: str
    version: Optional[str] = None

    def label(self) -> str:
        return f"{self.source_id} ({self.version})" if self.version else self.source_id


class MemberResponse(BaseModel):
    text: str
    sources: list[SourceRef] = []
    escalation_notice: Optional[str] = None
    disclaimer: str

    def render(self) -> str:
        parts = [self.text.strip()]
        if self.sources:
            parts.append("Sources: " + ", ".join(s.label() for s in self.sources))
        if self.escalation_notice:
            parts.append(self.escalation_notice)
        parts.append(self.disclaimer)
        return "\n\n".join(parts)


class CoordinatorPacket(BaseModel):
    member_id: str
    generated_for_date: str
    request_summary: str
    category: str
    relevant_readings: list[dict]
    corrections_applied: list[dict]
    due_actions: list[dict]
    retrieved_sources: list[SourceRef]
    escalation_reason: str
    rule_ids: list[str]
    urgency: str
    missing_information: list[str]
    disposition: str
    reminder_draft: Optional[str] = None
    routing_queue: str = ""

    def render(self) -> str:
        lines = [
            f"Member ID        : {self.member_id}",
            f"Request summary  : {self.request_summary}",
            f"Category         : {self.category}",
            f"Disposition      : {self.disposition}",
            f"Escalation       : {self.escalation_reason or 'None'}",
            f"Rule IDs         : {', '.join(self.rule_ids) or 'None'}",
            f"Urgency          : {self.urgency}",
        ]
        if self.routing_queue:
            lines.append(f"Routing queue    : {self.routing_queue}")
        if self.relevant_readings:
            lines.append("Relevant readings (active values only):")
            for r in self.relevant_readings:
                lines.append(f"   - {r['reading_id']}: {r['type']} {r['value']} {r['unit']} at {r['recorded_at']}")
        if self.corrections_applied:
            lines.append("Corrections applied (superseded values not shown):")
            for c in self.corrections_applied:
                lines.append(f"   - {c['superseded']} replaced by {c['replaced_by']}")
        if self.due_actions:
            lines.append("Due / upcoming actions:")
            for a in self.due_actions:
                lines.append(f"   - {a['task_id']}: {a['task']} ({a['status']}, next due {a['next_due']})")
        if self.retrieved_sources:
            lines.append("Retrieved sources: " + ", ".join(s.label() for s in self.retrieved_sources))
        if self.missing_information:
            lines.append("Missing information:")
            for m in self.missing_information:
                lines.append(f"   - {m}")
        if self.reminder_draft:
            lines.append(f"Reminder draft   : {self.reminder_draft}")
        lines.append(f"Reference date   : {self.generated_for_date}")
        return "\n".join(lines)


class AuditRecord(BaseModel):
    timestamp: str
    member: str                     # masked, e.g. M-1**
    consent_check: str
    category: str
    agents_called: list[str]
    rule_ids: list[str]
    source_versions: list[str]
    disposition: str
    notes: list[str] = []


class OrchestratorResult(BaseModel):
    member_response: MemberResponse
    coordinator_packet: CoordinatorPacket
    audit: AuditRecord
