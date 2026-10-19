"""Azure Blob Storage: the cloud copy of the data tables and the approved documents.

Container layout (container name = AZURE_STORAGE_CONTAINER):
    data/<table>.csv                       members, readings, care_plan_tasks, escalation_rules, ...
    knowledge/<folder>/<article_id>.md     approved and draft documents

Sign-in: AZURE_STORAGE_CONNECTION_STRING (key string) or AZURE_STORAGE_ACCOUNT_URL + `az login`.
Only files that changed are uploaded (compared by MD5).
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Callable

import config
from src.schemas import SCHEMAS


class AzureNotConfigured(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(config.AZURE_STORAGE_CONNECTION_STRING or config.AZURE_STORAGE_ACCOUNT_URL)


def container_client():
    if not is_configured():
        raise AzureNotConfigured("Set AZURE_STORAGE_CONNECTION_STRING (or AZURE_STORAGE_ACCOUNT_URL and run `az login`) in .env.")
    from azure.storage.blob import BlobServiceClient
    if config.AZURE_STORAGE_CONNECTION_STRING:
        svc = BlobServiceClient.from_connection_string(config.AZURE_STORAGE_CONNECTION_STRING)
    else:
        from azure.identity import DefaultAzureCredential
        svc = BlobServiceClient(account_url=config.AZURE_STORAGE_ACCOUNT_URL, credential=DefaultAzureCredential())
    cc = svc.get_container_client(config.AZURE_STORAGE_CONTAINER)
    if not cc.exists():
        cc.create_container()
    return cc


def local_files() -> dict[str, Path]:
    """blob name -> local path.

    Layout in the container:
        data/<table>.csv
        knowledge/<folder>/<ID>.md              ONLY Approved documents (this is what the knowledge sources read)
        knowledge-unapproved/<folder>/<ID>.md   Draft and Retired documents (never searched)
    """
    from src.knowledge import load_catalog

    approved = {a["article_id"] for a in load_catalog()}
    files: dict[str, Path] = {}
    for p in sorted(config.DATA_DIR.glob("*.csv")):
        files[f"data/{p.name}"] = p
    for folder in ("education", "faq", "careplan_guidance"):
        for p in sorted((config.KNOWLEDGE_DIR / folder).glob("*.md")):
            prefix = config.BLOB_APPROVED_PREFIX if p.stem in approved else config.BLOB_UNAPPROVED_PREFIX
            files[f"{prefix}/{folder}/{p.name}"] = p
    return files


def _is_ours(name: str) -> bool:
    return name.startswith(("data/", f"{config.BLOB_APPROVED_PREFIX}/", f"{config.BLOB_UNAPPROVED_PREFIX}/")) and "/_versions/" not in name


def _md5(path: Path) -> bytes:
    return hashlib.md5(path.read_bytes()).digest()


def compare(cc=None) -> list[dict]:
    """One row per file: name, local/remote presence and whether they match."""
    cc = cc or container_client()
    remote = {b.name: b for b in cc.list_blobs() if _is_ours(b.name)}
    local = local_files()
    rows = []
    for name in sorted(set(local) | set(remote)):
        l, r = local.get(name), remote.get(name)
        if l and r:
            rmd5 = bytes(r.content_settings.content_md5) if r.content_settings and r.content_settings.content_md5 else None
            state = "in sync" if rmd5 == _md5(l) else "changed locally or in cloud"
        else:
            state = "local only (not uploaded)" if l else "cloud only (not downloaded)"
        rows.append({"file": name, "state": state, "local_kb": round(l.stat().st_size / 1024, 1) if l else None,
                     "cloud_kb": round(r.size / 1024, 1) if r else None})
    return rows


def push(progress: Callable[[str], None] = lambda m: None) -> dict:
    """Upload new or changed local files. Documents that are no longer where they were (retired, moved to Draft, deleted)
    are removed from their old place, so a retired document can never be found by the knowledge base."""
    from azure.storage.blob import ContentSettings
    cc = container_client()
    uploaded = skipped = removed = 0
    remote = {b.name: b for b in cc.list_blobs() if _is_ours(b.name)}
    local = local_files()
    for name, path in local.items():
        digest = _md5(path)
        r = remote.get(name)
        if r and r.content_settings and r.content_settings.content_md5 and bytes(r.content_settings.content_md5) == digest:
            skipped += 1
            continue
        ctype = "text/csv" if path.suffix == ".csv" else "text/markdown"
        cc.upload_blob(name, path.read_bytes(), overwrite=True, content_settings=ContentSettings(content_type=ctype, content_md5=bytearray(digest)))
        progress(f"uploaded {name}")
        uploaded += 1
    for name in remote:
        if name.startswith(("knowledge/", "knowledge-unapproved/")) and name not in local:
            cc.delete_blob(name)
            progress(f"removed {name} (no longer approved or deleted)")
            removed += 1
    result = {"uploaded": uploaded, "unchanged": skipped, "removed": removed}
    record_sync("upload", True, result)
    return result


def pull(progress: Callable[[str], None] = lambda m: None) -> dict:
    """Download cloud files into the project. Tables are validated first; an invalid table is skipped, not written."""
    import csv
    import io
    from src.tools.store import write_table
    cc = container_client()
    pulled, rejected = 0, []
    for b in cc.list_blobs():
        if not _is_ours(b.name):
            continue
        data = cc.download_blob(b.name).readall()
        if b.name.startswith("data/") and b.name.endswith(".csv"):
            table = Path(b.name).stem
            if table not in SCHEMAS:
                continue
            try:
                write_table(table, list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")))))
            except ValueError as exc:
                rejected.append(f"{b.name}: {str(exc).splitlines()[0]}")
                continue
        else:
            rel = b.name.split("/", 1)[1]                                   # <folder>/<ID>.md
            dest = config.KNOWLEDGE_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        progress(f"downloaded {b.name}")
        pulled += 1
    return {"downloaded": pulled, "rejected": rejected}


# ---------------------------------------------------------------- sync state (for the UI status strip; no secrets)
SYNC_FILE = config.LOG_DIR / "sync_state.json"


def read_sync_state() -> dict:
    import json
    try:
        return json.loads(SYNC_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def record_sync(kind: str, ok: bool, detail=None) -> None:
    """kind: upload | indexing. Stores when it last ran, whether it worked, and a short detail."""
    import json
    from datetime import datetime
    state = read_sync_state()
    state[kind] = {"ok": ok, "at": datetime.now().isoformat(timespec="seconds"), "detail": detail if ok else str(detail)[:200]}
    if kind == "upload":
        state["pending"] = not ok
    try:
        config.LOG_DIR.mkdir(exist_ok=True)
        SYNC_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    except OSError:
        pass


def mark_pending() -> None:
    """A local save happened that is not in Blob yet."""
    import json
    state = read_sync_state()
    state["pending"] = True
    try:
        config.LOG_DIR.mkdir(exist_ok=True)
        SYNC_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    except OSError:
        pass
