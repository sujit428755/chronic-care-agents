"""Retry and safe-failure middleware (reference error_handling_retries.py pattern).

* RetryMiddleware     - retries a whole agent call when it fails (network glitch, rate limit).
* SafeToolMiddleware  - retries a failing tool; if it still fails, hands the agent a clear message instead of crashing,
                        so the agent reports the failure instead of inventing data.
"""
from __future__ import annotations

import asyncio
import logging

try:
    from agent_framework import AgentMiddleware, FunctionMiddleware, MiddlewareTermination
except ImportError:  # OFFLINE mode does not need the framework
    AgentMiddleware = FunctionMiddleware = object  # type: ignore

    class MiddlewareTermination(Exception):  # type: ignore
        pass

log = logging.getLogger("resilience")


class RetryMiddleware(AgentMiddleware):  # type: ignore[misc]
    def __init__(self, max_retries: int = 2, delay_seconds: float = 1.0):
        self.max_retries = max_retries
        self.delay_seconds = delay_seconds

    async def process(self, context, call_next):
        for attempt in range(1, self.max_retries + 1):
            try:
                await call_next()
                return
            except Exception as exc:  # noqa: BLE001
                if attempt == self.max_retries:
                    log.error("agent call failed after %d attempts: %s", attempt, exc)
                    raise
                log.warning("agent call attempt %d failed (%s); retrying", attempt, exc)
                await asyncio.sleep(self.delay_seconds)


class SafeToolMiddleware(FunctionMiddleware):  # type: ignore[misc]
    def __init__(self, max_retries: int = 2, delay_seconds: float = 0.3):
        self.max_retries = max_retries
        self.delay_seconds = delay_seconds

    async def process(self, context, call_next):
        for attempt in range(1, self.max_retries + 1):
            try:
                await call_next()
                return
            except Exception as exc:  # noqa: BLE001
                name = context.function.name
                if attempt == self.max_retries:
                    context.result = (
                        f"[Tool '{name}' failed: {exc}. Do not guess or invent any data. "
                        f"Tell the user the information could not be retrieved and that program staff can help.]"
                    )
                    raise MiddlewareTermination()
                log.warning("tool %s attempt %d failed (%s); retrying", name, attempt, exc)
                await asyncio.sleep(self.delay_seconds)
