"""Run the six agents as Microsoft Foundry agents (visible in the Foundry portal).

* register(key)      creates a new version of the agent in your Foundry project (agents.create_version), like the reference agent_v2.py
* register_all()     registers all six; skips agents whose definition did not change (see logs/foundry_agents.json)
* acall(key, prompt) sends one message to the agent by name (responses.create + agent_reference) and returns its text

If anything here fails, the specialist modules keep their template wording, so the workflow never stops.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from typing import Optional

import config
from src.agents import registry
from src.middleware.input_guard import contains_injection

log = logging.getLogger("agent")
STATE_FILE = config.LOG_DIR / "foundry_agents.json"
_registered_this_process = False
_client = None


def _project_client():
    global _client
    if _client is None:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        if not config.FOUNDRY_PROJECT_ENDPOINT:
            raise RuntimeError("FOUNDRY_PROJECT_ENDPOINT is not set in .env (or set AGENT_RUNTIME=framework / OFFLINE=1).")
        _client = AIProjectClient(endpoint=config.FOUNDRY_PROJECT_ENDPOINT, credential=DefaultAzureCredential())
    return _client


# ---------------------------------------------------------------- registration state (no secrets)
def read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(state: dict) -> None:
    config.LOG_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def status_rows() -> list[dict]:
    """One row per agent for the UI: name, registered?, version, up to date?"""
    state = read_state()
    rows = []
    for key in registry.ORDER:
        s = state.get(key)
        fp = registry.definition_fingerprint(key)
        rows.append({
            "key": key, "agent": registry.LABELS[key], "foundry_name": registry.agent_name(key),
            "registered": bool(s), "version": (s or {}).get("version", "-"),
            "up_to_date": bool(s) and s.get("fingerprint") == fp,
            "registered_at": (s or {}).get("registered_at", "-"),
            "mode": (s or {}).get("mode", ""),
        })
    return rows


# ---------------------------------------------------------------- register
def register(key: str, force: bool = False) -> dict:
    """Create (a new version of) one agent in Foundry. Returns {key, name, version, skipped}."""
    state = read_state()
    fp = registry.definition_fingerprint(key)
    if not force and state.get(key, {}).get("fingerprint") == fp:
        return {"key": key, "name": registry.agent_name(key), "version": state[key].get("version"), "skipped": True}

    if key == "education":
        from src.agents import education_agent
        agent = education_agent.register_agent()
        mode = config.EDUCATION_RETRIEVAL
    else:
        from azure.ai.projects.models import PromptAgentDefinition

        agent = _project_client().agents.create_version(
            agent_name=registry.agent_name(key),
            definition=PromptAgentDefinition(model=config.MODEL_DEPLOYMENT_NAME, instructions=registry.foundry_instructions(key)),
        )
        mode = "no tools, facts in message"
    state[key] = {"name": registry.agent_name(key), "version": str(getattr(agent, "version", "")), "id": str(getattr(agent, "id", "")),
                  "fingerprint": fp, "registered_at": datetime.now().isoformat(timespec="seconds"), "mode": mode}
    _write_state(state)
    return {"key": key, "name": registry.agent_name(key), "version": state[key]["version"], "skipped": False}


def register_all(force: bool = False, only: Optional[list[str]] = None, progress=lambda m: None) -> list[dict]:
    if not config.MODEL_DEPLOYMENT_NAME:
        raise RuntimeError("MODEL_DEPLOYMENT_NAME is not set in .env")
    out = []
    for key in registry.ORDER:
        if only and key not in only:
            continue
        r = register(key, force=force)
        progress(f"{r['name']}: " + ("already up to date" if r["skipped"] else f"registered, version {r['version']}"))
        out.append(r)
    return out


def ensure_registered(progress=lambda m: None) -> Optional[str]:
    """Called when the app / client starts. Registers agents that are missing or changed. Returns a warning text or None."""
    global _registered_this_process
    if _registered_this_process or not config.foundry_agents_enabled() or not config.AUTO_REGISTER_AGENTS:
        return None
    _registered_this_process = True
    try:
        register_all(progress=progress)
        return None
    except Exception as exc:  # noqa: BLE001 - never stop the app because registration failed
        log.warning("could not register Foundry agents: %s", exc)
        return f"Could not register the agents in Foundry ({type(exc).__name__}: {str(exc)[:200]}). Wording will use safe templates. Check .env, or set AGENT_RUNTIME=framework."


# ---------------------------------------------------------------- call
def _call_sync(key: str, prompt: str) -> str:
    client = _project_client().get_openai_client()
    conversation = client.conversations.create()   # new conversation every time: nothing is remembered between requests
    last: Exception | None = None
    for attempt in (1, 2):
        try:
            resp = client.responses.create(
                conversation=conversation.id, input=prompt,
                extra_body={"agent_reference": {"name": registry.agent_name(key), "type": "agent_reference"}},
            )
            return (resp.output_text or "").strip()
        except Exception as exc:  # noqa: BLE001
            last = exc
            log.warning("agent=%s attempt %d failed (%s)", registry.agent_name(key), attempt, type(exc).__name__)
            time.sleep(1.0)
    raise RuntimeError(f"Foundry agent {registry.agent_name(key)} failed: {last}")


async def acall(key: str, prompt: str) -> str:
    if contains_injection(prompt):
        raise RuntimeError("blocked by the input guard")
    start = time.time()
    log.info("agent=%s started", registry.agent_name(key))
    text = await asyncio.to_thread(_call_sync, key, prompt)
    log.info("agent=%s finished in %.2fs", registry.agent_name(key), time.time() - start)
    return text


def facts_block(facts) -> str:
    return "\n\nFACTS (JSON):\n" + json.dumps(facts, ensure_ascii=False, default=str)


def parse_model(text: str, model):
    """Pull the JSON object out of the agent's reply (it may be wrapped in fences) and validate it."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("agent reply contained no JSON object")
    return model.model_validate_json(m.group(0))
