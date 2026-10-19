"""Warn (never block) when an upload looks like it contains real personal data. This project is synthetic-only."""
from __future__ import annotations

import re

PATTERNS = {
    "email address": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "phone number": re.compile(r"(?<!\d)(?:\+?\d{1,3}[ -]?)?(?:\d[ -]?){10}(?!\d)"),
    "12-digit ID number": re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)"),
    "date of birth label": re.compile(r"\b(dob|date of birth)\b", re.I),
}


def scan_text(text: str) -> list[str]:
    return [name for name, pat in PATTERNS.items() if pat.search(text)]


def scan_rows(rows: list[dict], limit: int = 2000) -> list[str]:
    blob = "\n".join(" ".join(str(v) for v in r.values()) for r in rows[:limit])
    return scan_text(blob)


def warnings_for(found: list[str]) -> list[str]:
    return [f"Possible {f} found. Use synthetic data only; remove real personal information before saving." for f in found]
