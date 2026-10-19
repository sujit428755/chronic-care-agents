"""Shared factory for the Agent Framework agents (pattern from the reference agent_instructiondemo.py,
structure_outputdemo.py, tool_callingdemo.py and error_handling_retries.py).

Every specialist is created through `make_agent`, so they all get the same safety middleware.
Each agent gets ONLY the tools it needs (least privilege).
"""
from __future__ import annotations

import config

_client = None


def get_client():
    """One shared chat client for all Agent Framework agents (same constructor as the reference demos)."""
    global _client
    if _client is None:
        from agent_framework.openai import OpenAIChatClient

        missing = [
            n for n, v in {
                "AZURE_OPENAI_API_KEY": config.AZURE_OPENAI_API_KEY,
                "AZURE_OPENAI_ENDPOINT": config.AZURE_OPENAI_ENDPOINT,
                "AZURE_OPENAI_DEPLOYMENT_NAME": config.AZURE_OPENAI_DEPLOYMENT_NAME,
            }.items() if not v
        ]
        if missing:
            raise RuntimeError(f"Missing settings in .env: {', '.join(missing)}. Fill them in, or run with OFFLINE=1.")
        _client = OpenAIChatClient(
            base_url=config.AZURE_OPENAI_ENDPOINT,
            model=config.AZURE_OPENAI_DEPLOYMENT_NAME,
            api_key=config.AZURE_OPENAI_API_KEY,
        )
    return _client


def make_agent(name: str, instructions: str, tools: list | None = None, response_model=None):
    from agent_framework import Agent

    from src.middleware.audit_logging import logging_middleware
    from src.middleware.input_guard import input_guard_middleware
    from src.middleware.safe_tools import RetryMiddleware, SafeToolMiddleware

    kwargs = dict(
        client=get_client(),
        name=name,
        instructions=instructions,
        middleware=[logging_middleware, input_guard_middleware, RetryMiddleware(max_retries=2), SafeToolMiddleware(max_retries=2)],
    )
    if tools:
        kwargs["tools"] = tools
    if response_model is not None:
        kwargs["default_options"] = {"response_format": response_model}
    return Agent(**kwargs)


async def run_structured(agent, prompt: str, model):
    """Run an agent that was created with a response_model and parse its JSON into that model."""
    response = await agent.run(prompt)
    return model.model_validate_json(response.text)


async def run_text(agent, prompt: str) -> str:
    response = await agent.run(prompt)
    return (response.text or "").strip()


# ----------------------------------------------------------------------------
# One entry point for the specialist modules. It picks the runtime:
#   AGENT_RUNTIME=foundry   -> the agent lives in Foundry; facts are sent in the message
#   AGENT_RUNTIME=framework -> the agent runs in Python (Agent Framework) with its own tools
# ----------------------------------------------------------------------------
_framework_agents: dict = {}


def _framework_agent(key: str, name: str, instructions: str, tools, model):
    if key not in _framework_agents:
        _framework_agents[key] = make_agent(name, instructions, tools=tools, response_model=model)
    return _framework_agents[key]


async def invoke_structured(key: str, prompt: str, model, *, name: str, instructions: str, tools=None, facts=None):
    if config.foundry_agents_enabled():
        from src.agents import foundry_runtime

        text = await foundry_runtime.acall(key, prompt + (foundry_runtime.facts_block(facts) if facts is not None else ""))
        return foundry_runtime.parse_model(text, model)
    agent = _framework_agent(key, name, instructions, tools, model)
    return await run_structured(agent, prompt, model)


async def invoke_text(key: str, prompt: str, *, name: str, instructions: str) -> str:
    if config.foundry_agents_enabled():
        from src.agents import foundry_runtime

        return await foundry_runtime.acall(key, prompt)
    return await run_text(_framework_agent(key, name, instructions, None, None), prompt)
