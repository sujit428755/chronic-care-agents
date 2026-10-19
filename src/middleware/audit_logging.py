"""Audit trail and telemetry masking.

* Audit records contain: consent check, agents called, rule IDs, source versions and the final disposition.
  They NEVER contain the member's message text or reading values.
* Member IDs are masked (M-101 -> M-1**) in the audit file and in all general log output.
* The full (synthetic) member ID is kept only in the staff-review queue file, which is meant for staff.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime

import config
from src.models import AuditRecord

MEMBER_ID_RE = re.compile(r"\bM-(\d)\d\d\b")


def mask_id(text: str) -> str:
    """M-101 -> M-1**"""
    return MEMBER_ID_RE.sub(lambda m: f"M-{m.group(1)}**", text)


class MaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_id(str(record.msg))
        if record.args:
            record.args = tuple(mask_id(str(a)) if isinstance(a, str) else a for a in record.args)
        return True


def setup_logging(level: int = logging.WARNING) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    if not any(isinstance(f, MaskingFilter) for h in root.handlers for f in h.filters):
        handler = logging.StreamHandler()
        handler.addFilter(MaskingFilter())
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)


class AuditTrail:
    """Collects audit facts while one request is processed, then writes one line to logs/audit.jsonl."""

    def __init__(self, member_id: str):
        self.member_id = member_id
        self.consent_check = "not_checked"
        self.agents_called: list[str] = []
        self.rule_ids: list[str] = []
        self.source_versions: list[str] = []
        self.notes: list[str] = []

    def agent(self, name: str) -> None:
        if name not in self.agents_called:
            self.agents_called.append(name)

    def rules(self, ids: list[str]) -> None:
        for i in ids:
            if i not in self.rule_ids:
                self.rule_ids.append(i)

    def sources(self, items: list[str]) -> None:
        for i in items:
            if i not in self.source_versions:
                self.source_versions.append(i)

    def note(self, text: str) -> None:
        self.notes.append(text)

    def finish(self, category: str, disposition: str) -> AuditRecord:
        record = AuditRecord(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            member=mask_id(self.member_id),
            consent_check=self.consent_check,
            category=category,
            agents_called=self.agents_called,
            rule_ids=self.rule_ids,
            source_versions=self.source_versions,
            disposition=disposition,
            notes=self.notes,
        )
        try:
            config.LOG_DIR.mkdir(exist_ok=True)
            with open(config.LOG_DIR / "audit.jsonl", "a", encoding="utf-8") as f:
                f.write(record.model_dump_json() + "\n")
        except OSError:
            logging.getLogger(__name__).warning("could not write audit record")
        return record


try:
    from agent_framework import agent_middleware
except ImportError:  # OFFLINE mode does not need the framework
    def agent_middleware(fn):  # type: ignore
        return fn


@agent_middleware
async def logging_middleware(context, call_next) -> None:
    """Agent middleware (reference middleware_demo.py pattern): logs agent name and timing, never message content."""
    log = logging.getLogger("agent")
    start = time.time()
    log.info("agent=%s started", context.agent.name)
    await call_next()
    log.info("agent=%s finished in %.2fs", context.agent.name, time.time() - start)
