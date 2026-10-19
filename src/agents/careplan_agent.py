"""Care Plan Agent (Agent Framework).

Tool access: ONLY care plan tasks and approved care-plan guidance. No readings, no education articles.
The task lists come from code; the agent supplies the plain-language wording, which must mention every task ID.
"""
from __future__ import annotations

from src.middleware.output_guard import check_text
from src.models import CarePlanNarrative, CarePlanResult, TaskItem
from src.prompts import CAREPLAN_INSTRUCTIONS
from src.tools.careplan_tools import get_care_plan_guidance, get_care_plan_tasks, split_tasks


def _line(t: dict) -> str:
    return f"{t['task_id']}: {t['task']} ({t['frequency']}), next due {t['next_due']}, status {t['status']}"


def fallback_narrative(groups: dict) -> str:
    parts = []
    if groups["action_needed"]:
        parts.append("Needs your attention: " + "; ".join(_line(t) for t in groups["action_needed"]) + ".")
    if groups["upcoming"]:
        parts.append("Coming up: " + "; ".join(_line(t) for t in groups["upcoming"]) + ".")
    if not parts:
        parts.append("There are no tasks in your care plan record.")
    return " ".join(parts)


async def build_result(member_id: str, tasks: list[dict], offline: bool, notes: list[str]) -> CarePlanResult:
    groups = split_tasks(tasks)
    narrative = fallback_narrative(groups)

    if not offline and tasks:
        from src.agents.base import invoke_structured

        try:
            result = await invoke_structured(
                "careplan", f"List the care plan tasks for member {member_id}.", CarePlanNarrative, name="CarePlanAgent",
                instructions=CAREPLAN_INSTRUCTIONS, tools=[get_care_plan_tasks, get_care_plan_guidance], facts={"tasks": tasks})
            text = result.narrative.strip()
            if check_text(text):
                notes.append("careplan_agent_wording_rejected")
            elif not all(t["task_id"] in text for t in tasks):
                notes.append("careplan_agent_wording_rejected:task_missing")
            else:
                narrative = text
        except Exception as exc:  # noqa: BLE001
            notes.append(f"careplan_agent_unavailable:{type(exc).__name__}")

    return CarePlanResult(
        action_needed=[TaskItem(**{k: t[k] for k in TaskItem.model_fields}) for t in groups["action_needed"]],
        upcoming=[TaskItem(**{k: t[k] for k in TaskItem.model_fields}) for t in groups["upcoming"]],
        source_ids=[t["task_id"] for t in tasks],
        narrative=narrative,
    )
