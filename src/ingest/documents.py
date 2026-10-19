"""Turn uploaded text (from .txt .md .docx .pdf or pasted) into an approved-knowledge Markdown document.

Every document has a front-matter block and a row in data/articles_catalog.csv. Only status = Approved is indexed
and cited. Editing an existing article bumps its version and keeps the old file in knowledge/_versions/.
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime

import config
from src.ingest import pii
from src.middleware.output_guard import check_text
from src.schemas import ARTICLE_PROGRAMS, ARTICLE_TYPES
from src.tools.store import load_table, write_table

PREFIX = {"education": "EDU", "faq": "FAQ", "careplan_guidance": "CPG"}
FOLDER = {"education": "education", "faq": "faq", "careplan_guidance": "careplan_guidance"}
TYPE_LABEL = {"education": "Education article", "faq": "FAQ", "careplan_guidance": "Care plan guidance"}


def next_article_id(doc_type: str) -> str:
    pre = PREFIX[doc_type]
    nums = [int(re.sub(r"\D", "", r["article_id"])) for r in load_table("articles_catalog") if r["article_id"].startswith(pre)]
    return f"{pre}-{(max(nums) + 1) if nums else 1}" if nums else f"{pre}-{ {'EDU': 401, 'FAQ': 701, 'CPG': 801}[pre] }"


def clean_body(text: str, title: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = re.sub(r"^---.*?---\s*", "", text, count=1, flags=re.S)          # drop any front matter the file already had
    text = re.sub(r"^Article ID:.*\n+", "", text)
    if not re.match(r"#\s", text):
        text = f"# {title}\n\n{text}"
    return text


def review_text(text: str) -> list[str]:
    """Warnings shown before saving. They do not block, because a human approves the document."""
    warns = pii.warnings_for(pii.scan_text(text))
    bad = check_text(text)
    if bad:
        warns.append("The text contains wording the safety guard rejects in assistant answers "
                     f"({', '.join(bad)}). Staff should check it before it is set to Approved.")
    return warns


def save_document(*, title: str, text: str, doc_type: str, program: str, scope: str = "General",
                  status: str = "Draft", approved_by: str = "", article_id: str | None = None, note: str = "") -> dict:
    """Create a new article, or a new version of an existing one (pass its article_id)."""
    if doc_type not in ARTICLE_TYPES or program not in ARTICLE_PROGRAMS:
        raise ValueError("Unknown document type or program.")
    if not title.strip() or not text.strip():
        raise ValueError("Title and text are required.")
    if status == "Approved" and not approved_by.strip():
        raise ValueError("An approved document needs the name or role of the approver.")
    catalog = load_table("articles_catalog")
    existing = next((r for r in catalog if r["article_id"] == article_id), None) if article_id else None
    if article_id and not existing:
        raise ValueError(f"{article_id} is not in the catalog.")
    if existing:
        version = "v" + str(int(existing["version"].lstrip("v")) + 1)
        old = config.ROOT / existing["file"]
        if old.exists():
            vdir = config.KNOWLEDGE_DIR / "_versions" / article_id
            vdir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old, vdir / f"{existing['version']}.md")
        doc_type = existing["type"]
    else:
        article_id, version = next_article_id(doc_type), "v1"

    body = clean_body(text, title.strip())
    rel = f"knowledge/{FOLDER[doc_type]}/{article_id}.md"
    path = config.ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\narticle_id: {article_id}\ntitle: {title.strip()}\nprogram: {program}\nversion: {version}\nscope: {scope.strip() or 'General'}\n---\n"
        f"Article ID: {article_id} | Version: {version} | Scope: {scope.strip() or 'General'} (synthetic content)\n\n{body}\n",
        encoding="utf-8")
    row = {"article_id": article_id, "title": title.strip(), "program": program, "version": version, "scope": scope.strip() or "General",
           "type": doc_type, "file": rel, "status": status, "approved_by": approved_by.strip(),
           "updated_at": datetime.now().strftime("%Y-%m-%d"), "note": note}
    write_table("articles_catalog", [r for r in catalog if r["article_id"] != article_id] + [row])
    return {"article_id": article_id, "version": version, "status": status, "file": rel, "warnings": review_text(body)}


def set_status(article_id: str, status: str, approved_by: str = "") -> None:
    catalog = load_table("articles_catalog")
    for r in catalog:
        if r["article_id"] == article_id:
            if status == "Approved" and not (approved_by or r.get("approved_by")):
                raise ValueError("An approved document needs the name or role of the approver.")
            r["status"] = status
            if approved_by:
                r["approved_by"] = approved_by
            r["updated_at"] = datetime.now().strftime("%Y-%m-%d")
            break
    else:
        raise ValueError(f"{article_id} is not in the catalog.")
    write_table("articles_catalog", catalog)


def read_article(article_id: str) -> tuple[dict, str]:
    from src.knowledge import parse_front_matter
    row = next(r for r in load_table("articles_catalog") if r["article_id"] == article_id)
    meta, body = parse_front_matter((config.ROOT / row["file"]).read_text(encoding="utf-8"))
    body = re.sub(r"^Article ID:.*\n+", "", body)
    return row, body
