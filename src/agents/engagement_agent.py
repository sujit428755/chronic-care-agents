"""Engagement Agent (Agent Framework).

Inputs only: due tasks + the member's channel and language. It has NO data tools, so it cannot read readings or articles.
"""
from __future__ import annotations

from src.middleware.output_guard import check_text
from src.models import ReminderDraft
from src.prompts import ENGAGEMENT_INSTRUCTIONS


def template_reminder(member: dict, due_tasks: list[dict]) -> ReminderDraft:
    names = ", ".join(t["task"] for t in due_tasks)
    english = f"Reminder from your care program: please complete your task(s): {names}."
    note = ""
    if member["language"] != "English":
        note = f" (Template is English only. Preferred language on file: {member['language']}.)"
    return ReminderDraft(
        channel=member["preferred_channel"],
        language=member["language"],
        reminder_text=english + note,
        english_text=english,
        followup_question="Is there anything that is making it hard to complete this task, so program staff can help?",
    )


async def draft(member: dict, due_tasks: list[dict], offline: bool, notes: list[str]) -> ReminderDraft | None:
    if not due_tasks:
        return None
    result = template_reminder(member, due_tasks)
    if offline:
        return result

    from src.agents.base import invoke_structured

    lines = "\n".join(f"- {t['task_id']}: {t['task']} ({t['frequency']}), due {t['next_due']}, status {t['status']}" for t in due_tasks)
    prompt = (
        f"Channel: {member['preferred_channel']}\nLanguage: {member['language']}\nTasks needing attention:\n{lines}\n"
        "Draft the reminder and one check-in question."
    )
    try:
        draft_ = await invoke_structured("engagement", prompt, ReminderDraft, name="EngagementAgent", instructions=ENGAGEMENT_INSTRUCTIONS)
        combined = f"{draft_.reminder_text} {draft_.english_text} {draft_.followup_question}"
        limit = 320 if member["preferred_channel"] == "SMS" else 1200
        if check_text(combined):
            notes.append("engagement_agent_wording_rejected")
        elif len(draft_.reminder_text) > limit:
            notes.append("engagement_agent_wording_rejected:too_long_for_channel")
        elif not all(t["task"].lower() in draft_.english_text.lower() for t in due_tasks):
            notes.append("engagement_agent_wording_rejected:task_missing")
        else:
            result = draft_.model_copy(update={"channel": member["preferred_channel"], "language": member["language"]})
    except Exception as exc:  # noqa: BLE001
        notes.append(f"engagement_agent_unavailable:{type(exc).__name__}")
    return result
