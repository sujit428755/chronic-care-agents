"""Member lookup and consent check (used by the Care Orchestrator only)."""
from typing import Optional

from src.tools.store import load_table, simulate_failure


def get_member(member_id: str) -> Optional[dict]:
    simulate_failure("members")
    for m in load_table("members"):
        if m["member_id"].upper() == member_id.strip().upper():
            return {k: (v or None) for k, v in m.items()}
    return None


def check_consent(member_id: str) -> dict:
    """Step 1 of the workflow. Consent must be exactly 'Active' (rule ER-501 otherwise)."""
    member = get_member(member_id)
    if member is None:
        return {"member_found": False, "consent_status": None, "active": False, "member": None}
    status = member.get("consent_status")
    return {"member_found": True, "consent_status": status, "active": status == "Active", "member": member}
