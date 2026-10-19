"""The six Foundry agents: names, instructions and the JSON shape each one must return.

agent        -> Foundry agent name          -> job
Care Orchestrator (LLM) -> care-orchestrator-agent     -> classifies the request (the workflow itself is plain Python)
Reading Summary         -> reading-summary-agent       -> wording of the reading summary
Care Plan               -> care-plan-agent             -> wording of the task list
Education RAG           -> education-rag-agent         -> grounded answers (index mode OR knowledge-base mode)
Engagement              -> engagement-agent            -> reminder draft + check-in question
Escalation              -> escalation-agent            -> staff note

In Foundry mode the agents have no Python tools: the code computes the facts and sends them in the message.
"""
from __future__ import annotations

import hashlib

import config
from src import prompts
from src.models import CarePlanNarrative, EscalationNarrative, ReadingNarrative, ReminderDraft

# key -> (instructions, output model or None for plain text)
SPECS = {
    "orchestrator": (prompts.ROUTER_INSTRUCTIONS, None),
    "reading": (prompts.READING_INSTRUCTIONS, ReadingNarrative),
    "careplan": (prompts.CAREPLAN_INSTRUCTIONS, CarePlanNarrative),
    "engagement": (prompts.ENGAGEMENT_INSTRUCTIONS, ReminderDraft),
    "escalation": (prompts.ESCALATION_INSTRUCTIONS, EscalationNarrative),
}
ORDER = ["orchestrator", "reading", "careplan", "education", "engagement", "escalation"]
LABELS = {
    "orchestrator": "Care Orchestrator (routing)", "reading": "Reading Summary", "careplan": "Care Plan",
    "education": "Education RAG", "engagement": "Engagement", "escalation": "Escalation",
}


def agent_name(key: str) -> str:
    return config.FOUNDRY_AGENT_NAMES[key]


def foundry_instructions(key: str) -> str:
    """Instructions stored in Foundry. For structured agents they say: no tools, facts in the message, reply as JSON."""
    base, model = SPECS[key]
    if model is None:
        return base
    return base + prompts.FOUNDRY_NOTE.format(keys=", ".join(model.model_fields))


def education_instructions() -> str:
    return prompts.EDUCATION_KB_INSTRUCTIONS if config.EDUCATION_RETRIEVAL == "knowledge_base" else prompts.EDUCATION_INSTRUCTIONS


def definition_fingerprint(key: str) -> str:
    """Changes whenever the instructions, model or retrieval setup change, so we only re-register when needed."""
    if key == "education":
        parts = [education_instructions(), config.MODEL_DEPLOYMENT_NAME or "", config.EDUCATION_RETRIEVAL,
                 config.KNOWLEDGE_BASE_NAME, config.SEARCH_SERVICE_PROJECT_CONNECTION_NAME,
                 config.SEARCH_INDEX_EDU, config.SEARCH_INDEX_FAQ]
    else:
        parts = [foundry_instructions(key), config.MODEL_DEPLOYMENT_NAME or ""]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]
