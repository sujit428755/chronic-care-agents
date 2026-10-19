"""Care plan tools (Care Plan Agent). Read-only access to care plan records and approved care-plan guidance."""
import json
from typing import Annotated

from src.knowledge import search_local
from src.tools.store import load_table, simulate_failure

ACTION_NEEDED_STATUSES = ("Due", "Overdue")
UPCOMING_STATUSES = ("Open", "Scheduled")


def get_tasks(member_id: str) -> list[dict]:
    simulate_failure("careplan")
    return [t for t in load_table("care_plan_tasks") if t["member_id"] == member_id]


def split_tasks(tasks: list[dict]) -> dict:
    """Group by the status recorded in the care plan. The status is reported as recorded, never recalculated."""
    return {
        "action_needed": [t for t in tasks if t["status"] in ACTION_NEEDED_STATUSES],
        "upcoming": [t for t in tasks if t["status"] in UPCOMING_STATUSES],
    }


def get_care_plan_tasks(member_id: Annotated[str, "Member ID, e.g. 'M-102'"]) -> str:
    """Returns the member's care plan tasks (task_id, task, frequency, next_due, status) as JSON."""
    return json.dumps(get_tasks(member_id))


def get_care_plan_guidance(topic: Annotated[str, "Short topic, e.g. 'overdue tasks'"]) -> str:
    """Returns approved care-plan guidance text (CPG-xxx) matching the topic, or says that none was found."""
    hits = search_local(topic, ("careplan_guidance",), min_score=1)
    if not hits:
        return "No approved care-plan guidance found for this topic."
    top = hits[0]
    return f"[{top['article_id']} {top['version']}] {top['content']}"
