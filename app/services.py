"""Glue between the Streamlit pages and the project code (no UI here)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
from datetime import datetime

import config
from src.orchestrator import CareOrchestrator
from src.tools.store import load_table

QUEUE = config.LOG_DIR / "staff_review_queue.jsonl"
ACTIONS = config.LOG_DIR / "staff_review_actions.jsonl"
AUDIT = config.LOG_DIR / "audit.jsonl"


def run_orchestrator(member_id: str, message: str):
    """The orchestrator is async; Streamlit is not. A fresh event loop per request keeps them apart."""
    return asyncio.run(CareOrchestrator(offline=config.OFFLINE).handle(member_id, message))


def _read_jsonl(path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def entry_key(e: dict) -> str:
    return hashlib.sha1(f"{e.get('timestamp')}|{e.get('member_id')}|{e.get('reason')}|{e.get('urgency')}".encode()).hexdigest()[:12]


def queue_items() -> list[dict]:
    reviewed = {a["key"]: a for a in _read_jsonl(ACTIONS)}
    items, seen = [], {}
    for e in _read_jsonl(QUEUE):
        k = entry_key(e)
        seen[k] = seen.get(k, 0) + 1
        if seen[k] > 1:                       # identical entries in the same second get distinct keys
            k = f"{k}-{seen[k]}"
        items.append({**e, "key": k, "review": reviewed.get(k)})
    return items


def mark_reviewed(key: str, reviewer: str, note: str) -> None:
    config.LOG_DIR.mkdir(exist_ok=True)
    with open(ACTIONS, "a", encoding="utf-8") as f:
        f.write(json.dumps({"key": key, "reviewer": reviewer.strip() or "staff", "note": note.strip(),
                            "reviewed_at": datetime.now().isoformat(timespec="seconds")}) + "\n")


def audit_records() -> list[dict]:
    return _read_jsonl(AUDIT)


def table_df(name: str):
    import pandas as pd
    return pd.DataFrame(load_table(name))


def run_test_suite(offline: bool) -> tuple[int, str]:
    cmd = [sys.executable, str(config.ROOT / "tests" / "run_tests.py")] + (["--offline"] if offline else [])
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=config.ROOT, timeout=900)
    return p.returncode, (p.stdout + p.stderr)


def maybe_autosync(progress=lambda m: None) -> str | None:
    """Called after every save in the Data Manager.

    * AUTO_UPLOAD=1 (default) and Blob configured: upload changed files to Blob Storage at once.
    * AUTO_SYNC=1 as well: then rebuild the search indexes (index mode) or run the knowledge-source indexers (knowledge_base mode).
    A failed upload never loses the save: it stays on disk and is marked "pending" until the next successful upload.
    """
    from src.azure_integration import blob, search
    if not blob.is_configured():
        return "Saved locally. Blob Storage is not configured yet, so nothing was uploaded."
    if not config.AUTO_UPLOAD:
        blob.mark_pending()
        return "Saved locally. Automatic upload is off (AUTO_UPLOAD=0); use Upload to Blob on the Azure Sync page."
    try:
        r = blob.push(progress)
        msg = f"Uploaded to Blob Storage: {r['uploaded']} file(s) changed, {r['removed']} removed."
        if config.AUTO_SYNC:
            search.sync_for_current_mode(progress)
            msg += " Search side refreshed."
        return msg
    except Exception as exc:  # noqa: BLE001
        blob.record_sync("upload", False, f"{type(exc).__name__}: {exc}")
        return f"Saved locally, but the upload to Blob Storage failed ({type(exc).__name__}: {str(exc)[:160]}). It is marked pending."


def pipeline_status() -> list[tuple[str, str, str]]:
    """(label, text, colour) chips for the status strip on every page."""
    from src.agents import foundry_runtime
    from src.azure_integration import blob
    st = blob.read_sync_state()
    chips = []
    if not blob.is_configured():
        chips.append(("Blob Storage", "not configured", "#7B93A0"))
    elif st.get("pending") or not st.get("upload", {}).get("ok", False):
        chips.append(("Blob Storage", "changes not uploaded yet" if st.get("upload") else "nothing uploaded yet", "#E65100"))
    else:
        chips.append(("Blob Storage", "up to date · " + st["upload"]["at"].replace("T", " "), "#2E7D32"))
    mode = "knowledge base" if config.EDUCATION_RETRIEVAL == "knowledge_base" else "search index"
    idx = st.get("indexing")
    chips.append(("Retrieval", mode + (" · refreshed " + idx["at"][11:16] if idx and idx.get("ok") else ""), "#0E7C86" if idx and idx.get("ok") else "#B26A00"))
    if config.foundry_agents_enabled():
        rows = foundry_runtime.status_rows()
        ok = sum(1 for r in rows if r["registered"] and r["up_to_date"])
        chips.append(("Foundry agents", f"{ok}/6 registered", "#2E7D32" if ok == 6 else "#E65100"))
    else:
        chips.append(("Agents", "offline / Python runtime" if config.OFFLINE else "Python runtime (framework)", "#7B93A0"))
    return chips
