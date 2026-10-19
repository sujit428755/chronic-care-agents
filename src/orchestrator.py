"""Care Orchestrator.

Fixed workflow. The safety steps are plain code, not LLM decisions:

  1. verify member + consent            -> ER-501 stops everything
  2. input guard + medication check     -> ER-503 declines
  3. classify the request               -> Router agent (keyword fallback)
  4. read the data window and apply the configured rules (ER-502, ER-504)
  5. call the right specialist agent(s)
  6. build TWO separate outputs: member response + coordinator packet (plus an audit record)
  7. keep only the minimum case context (no message text is stored)
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

import config
from src.agents import careplan_agent, education_agent, engagement_agent, escalation_agent, reading_agent, router_agent
from src.middleware.audit_logging import AuditTrail, mask_id
from src.middleware.input_guard import contains_injection, is_clinical_advice_request
from src.middleware.output_guard import check_text
from src.models import (
    CoordinatorPacket, EscalationRecord, MemberResponse, OrchestratorResult, SourceRef,
)
from src.tools import careplan_tools, reading_tools, rules_tools
from src.tools.member_tools import check_consent
from src.tools.store import ToolFailure

log = logging.getLogger("orchestrator")

TYPE_KEYWORDS = {
    "Glucose": ["glucose", "sugar"],
    "Blood pressure": ["blood pressure", "bp"],
    "Weight": ["weight"],
    "Heart rate": ["heart rate", "pulse"],
    "Oxygen saturation": ["oxygen", "spo2"],
    "Body temperature": ["temperature"],
    "HbA1c": ["hba1c", "a1c"],
}

NOTICES = {
    "ER-502": (
        "A recent entry in your record matches a rule the program uses to ask staff to take a look. "
        "I have created a review request for your care team. This is a routine step and not an interpretation of your entry. "
        "If you have urgent concerns, contact your care team or local emergency services."
    ),
    "ER-504": (
        "Some information in your record or sources looked inconsistent, so I have not drawn any conclusions from it. "
        "I have asked program staff to review it."
    ),
}


SMALL_TALK_RE = re.compile(
    r"^\s*(hi+|hello+|hey+|hiya|good (morning|afternoon|evening)|thanks?( you)?|thank you( so much)?|ok(ay)?|bye|goodbye|help|menu|test)\W*$"
    r"|^\s*M-\d{3,6}\s*$",
    re.IGNORECASE,
)


def is_small_talk(message: str) -> bool:
    """A bare greeting, thanks, 'help' or a member ID typed as a message: answer politely, do not bother staff."""
    return bool(SMALL_TALK_RE.match(message or ""))


def parse_window(message: str) -> tuple[date, date]:
    t = message.lower()
    days = config.DEFAULT_WINDOW_DAYS
    m = re.search(r"(?:last|past)\s+(\d+)\s+days?", t)
    if m:
        days = int(m.group(1))
    elif re.search(r"\btoday\b", t):
        days = 1
    elif re.search(r"\bmonth\b", t):
        days = 30
    days = max(1, min(days, config.MAX_WINDOW_DAYS))
    end = config.REFERENCE_DATE
    return end - timedelta(days=days - 1), end


def detect_types(message: str) -> list[str]:
    t = message.lower()
    return [name for name, kws in TYPE_KEYWORDS.items() if any(re.search(rf"\b{re.escape(k)}\b", t) for k in kws)]


def _source_label(s: SourceRef) -> str:
    return f"{s.source_id}:{s.version}" if s.version else s.source_id


class CareOrchestrator:
    def __init__(self, offline: Optional[bool] = None):
        self.offline = config.OFFLINE if offline is None else offline

    # ------------------------------------------------------------------ public
    async def handle(self, member_id: str, message: str) -> OrchestratorResult:
        member_id = (member_id or "").strip().upper()
        audit = AuditTrail(member_id)
        audit.agent("CareOrchestrator")
        try:
            return await self._handle(member_id, message, audit)
        except ToolFailure as exc:
            log.warning("tool failure for %s: %s", mask_id(member_id), exc)
            audit.note("tool_failure")
            return self._finish(
                audit, member_id=member_id, category="UNKNOWN", disposition="tool_failure",
                text=(
                    "I could not retrieve the information needed for this request right now, so I have not given an answer "
                    "and I have not guessed any values. Please try again in a few minutes, or contact program staff."
                ),
                request_summary="Request could not be completed because a data source was unavailable",
                missing=[f"Data source unavailable ({exc}). No values were generated."],
            )

    # ------------------------------------------------------------------ main flow
    async def _handle(self, member_id: str, message: str, audit: AuditTrail) -> OrchestratorResult:
        # 1. member + consent (ER-501)
        consent = check_consent(member_id)
        if not consent["member_found"]:
            audit.consent_check = "member_not_found"
            return self._finish(
                audit, member_id=member_id, category="UNKNOWN", disposition="unknown_member",
                text="I could not find that member ID in the program. Please check the ID or contact program staff.",
                request_summary="Member ID not found; request not processed",
            )
        audit.consent_check = consent["consent_status"] or "unknown"
        member = consent["member"]
        window = (config.REFERENCE_DATE, config.REFERENCE_DATE)

        if not consent["active"]:
            esc = await self._escalate(audit, member_id, ["ER-501"], [], window, default_urgency="staff_contact")
            return self._finish(
                audit, member_id=member_id, category="BLOCKED", disposition="stopped_consent",
                text=(
                    "Your program consent is not active, so I cannot process this request or look at your information. "
                    "Please contact program staff to renew your consent."
                ),
                request_summary="Request not processed: consent is not active", escalation=esc,
            )

        # 2. input guard + medication rule (ER-503)
        if contains_injection(message):
            audit.note("blocked_input:prompt_injection")
            return self._finish(
                audit, member_id=member_id, category="BLOCKED", disposition="blocked_input",
                text="I cannot act on that request. If you need help, please contact program staff.",
                request_summary="Request blocked by the input guard (details not stored)",
            )

        if is_small_talk(message):
            audit.note("category=SMALLTALK")
            return self._finish(
                audit, member_id=member_id, category="SMALLTALK", disposition="greeting",
                text=(
                    "Hello. I can explain approved program information, summarise your recorded readings for a period "
                    "(for example: \"Summarize my glucose readings for the last 7 days\"), list your care plan tasks, "
                    "or ask program staff to follow up. What would you like help with?"
                ),
                request_summary="Greeting or message with no request; no action taken",
            )

        if rules_tools.is_medication_change_request(message):
            return await self._medication_decline(audit, member_id, member, window, message)

        # 3. classify
        category, how = await router_agent.classify(message, self.offline)
        audit.agent("RouterAgent" if how == "router_agent" else "KeywordClassifier")
        if category == "MEDICATION":
            return await self._medication_decline(audit, member_id, member, window, message)
        clinical_advice = is_clinical_advice_request(message)
        if clinical_advice:
            category = "STAFF"
        audit.note(f"category={category}")

        # 4. data window + configured rules (ER-502, ER-504). A ToolFailure here is handled in handle().
        start, end = parse_window(message)
        window = (start, end)
        checks = rules_tools.check_readings_against_rules(member_id, start, end)
        high, contra = checks["high_risk"], checks["contradictions"]

        rule_ids: list[str] = []
        escalation_sources: list[str] = []
        escalation_extra = ""
        flagged_ids: set[str] = set()
        if high:
            rule_ids.append("ER-502")
            ids = [h["reading_id"] for h in high]
            escalation_sources += ids
            flagged_ids.update(ids)
        if contra:
            rule_ids.append("ER-504")
            for c in contra:
                escalation_sources += c["reading_ids"]
                flagged_ids.update(c["reading_ids"])
            escalation_extra = " ".join(c["detail"] for c in contra)

        # 5. specialist agents
        part = await self._run_specialists(category, member_id, member, message, start, end, audit, clinical_advice)
        if part.get("rule_ids"):
            rule_ids += [r for r in part["rule_ids"] if r not in rule_ids]
            escalation_sources += part.get("escalation_sources", [])
            escalation_extra = f"{escalation_extra} {part.get('escalation_extra', '')}".strip()

        # 6. escalation record, member notice, outputs
        esc: Optional[EscalationRecord] = None
        notice_parts = [NOTICES[r] for r in rule_ids if r in NOTICES]
        if rule_ids or part.get("staff_followup"):
            esc = await self._escalate(
                audit, member_id, rule_ids, sorted(set(escalation_sources)), window,
                extra=escalation_extra or part.get("escalation_extra", ""),
                default_urgency="staff_followup",
            )
        disposition = part.get("disposition") or ("answered_with_staff_review" if rule_ids else "answered")

        relevant = part.get("readings", [])
        flagged_rows = [r for r in checks["readings"] if r["reading_id"] in flagged_ids]
        seen = {r["reading_id"] for r in relevant}
        relevant += [r for r in flagged_rows if r["reading_id"] not in seen]

        return self._finish(
            audit, member_id=member_id, category=category, disposition=disposition,
            text=part["text"], sources=part.get("sources", []), notice=" ".join(notice_parts) or part.get("notice"),
            request_summary=part["request_summary"], readings=relevant,
            corrections=part.get("corrections", []), due_actions=part.get("due_actions", []),
            escalation=esc, missing=part.get("missing", []), reminder=part.get("reminder"),
        )

    # ------------------------------------------------------------------ specialists
    async def _run_specialists(self, category, member_id, member, message, start, end, audit, clinical_advice) -> dict:
        notes = audit.notes

        if category == "READINGS":
            audit.agent("ReadingSummaryAgent")
            types = detect_types(message) or reading_tools.reading_types_for_member(member_id)
            if not types:
                return {
                    "text": "I do not see any recorded readings in your record, so there is nothing to summarise.",
                    "request_summary": "Reading summary requested; no readings on file",
                    "missing": ["No readings on file for this member."],
                }
            summaries, rows = [], []
            for t in types:
                facts = reading_tools.compute_facts(member_id, t, start, end)
                summaries.append(await reading_agent.summarise(facts, self.offline, notes))
                rows += [
                    {k: r[k] for k in ("reading_id", "type", "value", "unit", "recorded_at")} for r in facts["readings"]
                ]
            text = "\n\n".join(f"{s.reading_type}\n{s.narrative}\n({s.label})" for s in summaries)
            ids = [i for s in summaries for i in s.source_reading_ids]
            audit.sources(ids)
            return {
                "text": text,
                "sources": [SourceRef(source_id=i) for i in ids],
                "request_summary": f"Reading summary requested ({', '.join(types)}; {start} to {end})",
                "readings": rows,
                "corrections": reading_tools.corrections_for_member(member_id, start, end, types),
                "missing": [f"{s.reading_type}: no entry on {d}" for s in summaries for d in s.missing_dates],
            }

        if category == "PLAN":
            audit.agent("CarePlanAgent")
            tasks = careplan_tools.get_tasks(member_id)
            cp = await careplan_agent.build_result(member_id, tasks, self.offline, notes)
            audit.sources(cp.source_ids)
            text = cp.narrative
            reminder_text = None
            action_tasks = [t for t in tasks if t["status"] in careplan_tools.ACTION_NEEDED_STATUSES]
            if action_tasks:
                audit.agent("EngagementAgent")
                rem = await engagement_agent.draft(member, action_tasks, self.offline, notes)
                if rem:
                    text += f"\n\nReminder draft ({rem.channel}, {rem.language}):\n{rem.reminder_text}\nCheck-in question: {rem.followup_question}"
                    reminder_text = f"[{rem.channel}/{rem.language}] {rem.english_text} Check-in: {rem.followup_question}"
            return {
                "text": text,
                "sources": [SourceRef(source_id=i) for i in cp.source_ids],
                "request_summary": "Care plan tasks and reminder requested",
                "due_actions": [t.model_dump() for t in cp.action_needed + cp.upcoming],
                "missing": [] if tasks else ["No care plan tasks on file."],
                "reminder": reminder_text,
            }

        if category == "EDUCATION":
            audit.agent("EducationRAGAgent")
            try:
                raw = await education_agent.ask(message, member["program"], self.offline)
            except Exception as exc:  # noqa: BLE001
                raise ToolFailure(f"approved knowledge base unavailable ({type(exc).__name__})") from exc
            info = education_agent.interpret(raw, member["program"])
            violations = check_text(info["answer"]) if info["answer"] else []
            if violations:
                notes.append(f"education_wording_rejected:{','.join(violations)}")
                info["gap"] = True
            if info["version_conflicts"]:
                c = info["version_conflicts"][0]
                return {
                    "text": (
                        "I found conflicting version information for the source of this answer, so I have not given an answer. "
                        "I have asked program staff to review it."
                    ),
                    "request_summary": "General education question; source version conflict (question text not stored)",
                    "rule_ids": ["ER-504"],
                    "escalation_sources": [c["article_id"]],
                    "escalation_extra": f"Answer cited {c['article_id']} {c['cited_version']} but approved version is {c['approved_version']}.",
                    "missing": ["Source version could not be confirmed."],
                    "disposition": "answered_with_staff_review",
                }
            if info["gap"]:
                notes.append(f"knowledge_gap rejected={','.join(info['rejected']) or 'none'}")
                return {
                    "text": (
                        "I could not find an approved article that answers this question, so I will not guess. "
                        "I have asked program staff to follow up with you."
                    ),
                    "request_summary": "General education question; no approved article found (question text not stored)",
                    "staff_followup": True,
                    "escalation_extra": "Knowledge gap: no approved article matched the question. Staff follow-up requested.",
                    "missing": ["No approved article found for the question."],
                    "disposition": "knowledge_gap_staff_followup",
                }
            audit.sources([_source_label(s) for s in info["sources"]])
            return {
                "text": info["answer"],
                "sources": info["sources"],
                "request_summary": "General education question answered from approved articles (question text not stored)",
            }

        # STAFF (also used for requests for clinical advice)
        extra = "Member asked for clinical advice or interpretation; none was given." if clinical_advice else "Member asked for staff follow-up or the request is outside the approved scope."
        text = (
            "I cannot tell you what a reading means or give medical advice, because I am not a clinician. "
            "I have asked program staff to follow up with you through your preferred channel "
            f"({member['preferred_channel']})."
            if clinical_advice else
            "I have asked program staff to follow up with you through your preferred channel "
            f"({member['preferred_channel']})."
        )
        return {
            "text": text,
            "request_summary": "Clinical-advice request routed to staff" if clinical_advice else "Staff follow-up requested",
            "staff_followup": True,
            "escalation_extra": extra,
            "disposition": "staff_followup",
        }

    # ------------------------------------------------------------------ helpers
    async def _medication_decline(self, audit, member_id, member, window, message="") -> OrchestratorResult:
        esc = await self._escalate(audit, member_id, ["ER-503"], [], window, default_urgency="clinician_referral", message=message)
        return self._finish(
            audit, member_id=member_id, category="MEDICATION", disposition="declined_medication",
            text=(
                "I cannot help with starting, stopping, skipping or changing any medicine or dose. "
                "Please speak to your doctor or another qualified clinician. "
                "I have also let program staff know that you have a question about your treatment so they can follow up."
            ),
            request_summary="Member asked about changing medication (details not stored)", escalation=esc,
        )

    async def _escalate(self, audit, member_id, rule_ids, source_ids, window, extra="", default_urgency="staff_followup", message="") -> EscalationRecord:
        audit.agent("EscalationAgent")
        audit.rules(rule_ids)
        routing = rules_tools.routing_for(rule_ids, member_id, source_ids, message)
        return await escalation_agent.build_record(
            rule_ids, source_ids, member_id, (window[0].isoformat(), window[1].isoformat()),
            self.offline, audit.notes, extra, default_urgency, routing,
        )

    def _finish(
        self, audit: AuditTrail, *, member_id: str, category: str, disposition: str, text: str, request_summary: str,
        sources: Optional[list[SourceRef]] = None, notice: Optional[str] = None, readings: Optional[list[dict]] = None,
        corrections: Optional[list[dict]] = None, due_actions: Optional[list[dict]] = None,
        escalation: Optional[EscalationRecord] = None, missing: Optional[list[str]] = None, reminder: Optional[str] = None,
    ) -> OrchestratorResult:
        sources = sources or []
        # Final safety net on the member-facing wording.
        if check_text(text):
            audit.note("final_wording_replaced_by_safe_message")
            text = "I am not able to provide that. I have asked program staff to follow up with you."
            sources = []

        escalation = escalation or EscalationRecord(triggered=False, rule_ids=[], urgency="none", reason="")
        if escalation.triggered:
            self._queue_for_staff(member_id, escalation, disposition)

        audit.sources([_source_label(s) for s in sources])
        record = audit.finish(category, disposition)

        member_response = MemberResponse(text=text, sources=sources, escalation_notice=notice, disclaimer=config.DISCLAIMER)
        packet = CoordinatorPacket(
            member_id=member_id,
            generated_for_date=config.REFERENCE_DATE.isoformat(),
            request_summary=request_summary,
            category=category,
            relevant_readings=readings or [],
            corrections_applied=corrections or [],
            due_actions=due_actions or [],
            retrieved_sources=sources,
            escalation_reason=escalation.reason if escalation.triggered else "",
            routing_queue=escalation.queue if escalation.triggered else "",
            rule_ids=escalation.rule_ids,
            urgency=escalation.urgency,
            missing_information=missing or [],
            disposition=disposition,
            reminder_draft=reminder,
        )
        return OrchestratorResult(member_response=member_response, coordinator_packet=packet, audit=record)

    @staticmethod
    def _queue_for_staff(member_id: str, esc: EscalationRecord, disposition: str) -> None:
        """Staff-review queue. This file is for staff, so it holds the (synthetic) member ID. It is git-ignored."""
        try:
            config.LOG_DIR.mkdir(exist_ok=True)
            entry = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "member_id": member_id,
                "urgency": esc.urgency,
                "rule_ids": esc.rule_ids,
                "source_ids": esc.source_ids,
                "reason": esc.reason,
                "queue": esc.queue,
                "disposition": disposition,
            }
            with open(config.LOG_DIR / "staff_review_queue.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            log.warning("could not write staff review queue entry")
