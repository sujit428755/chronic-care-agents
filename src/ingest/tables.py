"""Turn an uploaded table into rows of a canonical table: map columns, clean values, validate, merge.

Nothing here writes to disk except `commit()`. The Data Manager shows the result of `plan_merge()` as a preview first.
"""
from __future__ import annotations

import re
from datetime import datetime

from src.schemas import SCHEMAS, Schema
from src.tools.store import load_table, write_table

MODES = {
    "append": "Add new rows only (rows whose key already exists are rejected)",
    "upsert": "Add new rows and update existing rows with the same key",
    "replace": "Replace the whole table with this file",
}
_DATE_INPUTS = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y %H:%M",
                "%d/%m/%Y %H:%M", "%Y/%m/%d %H:%M", "%m/%d/%Y %H:%M", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"]


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def suggest_mapping(target: str, source_columns: list[str]) -> dict[str, str | None]:
    """schema column -> best matching source column (or None). Exact name first, then known synonyms."""
    schema = SCHEMAS[target]
    by_norm = {_norm(c): c for c in source_columns}
    used: set[str] = set()
    mapping: dict[str, str | None] = {}
    for col in schema.columns:
        cands = [_norm(col)] + [_norm(s) for s in schema.synonyms.get(col, [])]
        hit = next((by_norm[c] for c in cands if c in by_norm and by_norm[c] not in used), None)
        mapping[col] = hit
        if hit:
            used.add(hit)
    return mapping


def _clean_value(schema: Schema, col: str, val) -> str:
    s = "" if val is None else str(val).strip()
    if s.lower() in ("nan", "none", "null", "nat"):
        return ""
    if col in schema.allowed and s:                    # tolerate wrong letter case: "active" -> "Active"
        for opt in schema.allowed[col]:
            if s.lower() == opt.lower():
                return opt
    if col in schema.dates and s:
        want = schema.dates[col]
        for fmt in [want] + _DATE_INPUTS:
            try:
                return datetime.strptime(s, fmt).strftime(want)
            except ValueError:
                continue
    if col == "value" and s.endswith(".0") and s[:-2].isdigit():   # 118.0 from Excel -> 118
        return s[:-2]
    if col == "version" and s.isdigit():
        return "v" + s
    return s


def apply_mapping(target: str, rows: list[dict], mapping: dict[str, str | None]) -> list[dict]:
    schema = SCHEMAS[target]
    out = []
    for row in rows:
        r = {c: _clean_value(schema, c, row.get(src) if src else "") for c, src in mapping.items()}
        for c, d in schema.defaults.items():
            if not r[c]:
                r[c] = d
        out.append(r)
    return out


def plan_merge(target: str, new_rows: list[dict], mode: str, skip_invalid: bool = True) -> dict:
    """Dry run. Returns a dict the UI can show: counts, problems, warnings and the final table if committed."""
    schema = SCHEMAS[target]
    existing = load_table(target)
    key = lambda r: tuple(r[k] for k in schema.key)  # noqa: E731
    problems: list[str] = []
    valid: list[dict] = []
    seen: set[tuple] = set()
    for i, r in enumerate(new_rows, start=1):
        errs = schema.validate_row(r)
        if key(r) in seen:
            errs.append(f"duplicate key {key(r)} inside the uploaded file")
        seen.add(key(r))
        if errs:
            problems.append(f"file row {i}: " + "; ".join(errs))
        else:
            valid.append(r)

    if problems and not skip_invalid:
        return {"ok": False, "problems": problems, "warnings": [], "added": 0, "updated": 0, "skipped": len(new_rows), "final": None}

    by_key = {key(r): r for r in existing}
    added = updated = skipped = 0
    if mode == "replace":
        final = valid
        added = len(valid)
    else:
        final = list(existing)
        index = {key(r): i for i, r in enumerate(final)}
        for r in valid:
            k = key(r)
            if k in index:
                if mode == "upsert":
                    if final[index[k]] != {c: r.get(c, "") for c in schema.columns}:
                        final[index[k]] = r
                        updated += 1
                    else:
                        skipped += 1
                else:
                    problems.append(f"{schema.key[0]} {k[0]} already exists (use 'update existing' to change it)")
                    skipped += 1
            else:
                index[k] = len(final)
                final.append(r)
                added += 1
    skipped += len(new_rows) - len(valid)

    warnings = _integrity_warnings(target, final)
    problems_blocking = []
    if target == "articles_catalog":
        from src.knowledge import config as _c
        for r in final:
            if not (_c.ROOT / r["file"]).exists():
                problems_blocking.append(f"{r['article_id']}: file '{r['file']}' does not exist. Add the document first.")
    if problems_blocking:
        return {"ok": False, "problems": problems + problems_blocking, "warnings": warnings, "added": 0, "updated": 0, "skipped": len(new_rows), "final": None}
    return {"ok": True, "problems": problems, "warnings": warnings, "added": added, "updated": updated,
            "skipped": skipped, "final": final, "before": len(existing), "after": len(final)}


def _integrity_warnings(target: str, final: list[dict]) -> list[str]:
    warns = []
    if target in ("readings", "care_plan_tasks"):
        members = {m["member_id"] for m in (final if target == "members" else load_table("members"))}
        missing = sorted({r["member_id"] for r in final if r["member_id"] not in members})
        if missing:
            warns.append(f"{len(missing)} member_id value(s) are not in the members table (e.g. {', '.join(missing[:5])}). "
                         "Those rows will be ignored by the agents until the member exists.")
    if target == "members":
        ids = {r["member_id"] for r in final}
        for other, label in (("readings", "readings"), ("care_plan_tasks", "tasks")):
            orphans = {r["member_id"] for r in load_table(other)} - ids
            if orphans:
                warns.append(f"{len(orphans)} member(s) that have {label} are no longer in the members table.")
    if target == "readings":
        sup = {r["reading_id"] for r in final}
        bad = [r["reading_id"] for r in final if r.get("superseded_by") and r["superseded_by"] not in sup]
        if bad:
            warns.append(f"superseded_by points to a missing reading for: {', '.join(bad[:5])}")
    return warns


def commit(target: str, final_rows: list[dict]) -> None:
    write_table(target, final_rows)      # validates again, backs up the old version, writes atomically
