"""Data-access layer: CSV tables with schema checks, atomic writes and version history.

Every write first copies the current file into data/_versions/<table>/<timestamp>.csv, so any change made in the
Data Manager can be rolled back.
"""
from __future__ import annotations

import csv
import io
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import config
from src.schemas import SCHEMAS

MAX_VERSIONS = 25


class ToolFailure(Exception):
    """Raised when a data tool is unavailable. The orchestrator turns this into a clear, recoverable message."""


def simulate_failure(group: str) -> None:
    """If SIMULATE_TOOL_FAILURE=<group> is set (test T10), behave as if that data source is down."""
    if os.getenv("SIMULATE_TOOL_FAILURE", "").strip().lower() == group:
        raise ToolFailure(f"{group} data source is unavailable (simulated failure)")


def table_path(name: str) -> Path:
    return config.DATA_DIR / f"{name}.csv"


def load_table(name: str) -> list[dict]:
    """Read a canonical CSV table into a list of dicts (empty cells stay as empty strings)."""
    try:
        with open(table_path(name), encoding="utf-8-sig", newline="") as f:
            return [dict(r) for r in csv.DictReader(f)]
    except (OSError, csv.Error) as exc:
        raise ToolFailure(f"could not read table '{name}': {exc}") from exc


def _backup(name: str) -> None:
    src = table_path(name)
    if not src.exists():
        return
    vdir = config.DATA_DIR / "_versions" / name
    vdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    shutil.copy2(src, vdir / f"{stamp}.csv")
    for old in sorted(vdir.glob("*.csv"))[:-MAX_VERSIONS]:
        old.unlink()


def write_table(name: str, rows: list[dict], backup: bool = True) -> None:
    """Validate and write a table. Raises ValueError listing the problems if any row is invalid."""
    schema = SCHEMAS[name]
    clean, problems, seen = [], [], set()
    for i, row in enumerate(rows, start=1):
        r = {c: ("" if row.get(c) is None else str(row.get(c)).strip()) for c in schema.columns}
        for c, d in schema.defaults.items():
            if not r[c]:
                r[c] = d
        errs = schema.validate_row(r)
        key = tuple(r[k] for k in schema.key)
        if key in seen:
            errs.append(f"duplicate key {key}")
        seen.add(key)
        if errs:
            problems.append(f"row {i}: " + "; ".join(errs))
        clean.append(r)
    if problems:
        raise ValueError("\n".join(problems[:50]) + (f"\n... and {len(problems) - 50} more" if len(problems) > 50 else ""))

    if backup:
        _backup(name)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=config.DATA_DIR, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=schema.columns, lineterminator="\n")
        w.writeheader()
        w.writerows(clean)
    os.replace(tmp, table_path(name))


def list_versions(name: str) -> list[Path]:
    vdir = config.DATA_DIR / "_versions" / name
    return sorted(vdir.glob("*.csv"), reverse=True) if vdir.exists() else []


def restore_version(name: str, version_file: Path) -> None:
    _backup(name)
    shutil.copy2(version_file, table_path(name))


def table_to_csv_text(rows: list[dict], columns: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()
