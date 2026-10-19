"""Approved-knowledge helpers.

* `load_catalog()` reads data/articles_catalog.csv - the list of approved articles and versions.
* `load_documents()` reads the markdown files in knowledge/ (the same files that are uploaded to Azure AI Search).
* `search_local()` is a small keyword retriever used by OFFLINE mode and by the Care Plan guidance tool.
  The Education RAG agent in Foundry uses Azure AI Search instead (see src/agents/education_agent.py).
"""
from __future__ import annotations

import re
from typing import Optional

import config
from src.tools.store import load_table

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "were", "be", "do", "does",
    "did", "i", "me", "my", "we", "you", "your", "it", "its", "this", "that", "these", "those", "what", "why",
    "how", "when", "can", "could", "should", "would", "will", "with", "about", "from", "as", "at", "by", "them",
    "they", "there", "have", "has", "had", "so", "if", "not", "no", "any", "please", "tell", "explain", "know",
    "want", "need", "get", "us", "am",
}


def load_catalog(include_unapproved: bool = False) -> list[dict]:
    """The approved-article list (data/articles_catalog.csv). Draft and Retired entries are invisible to the agents."""
    rows = load_table("articles_catalog")
    return rows if include_unapproved else [r for r in rows if (r.get("status") or "Approved") == "Approved"]


def get_article_meta(article_id: str) -> Optional[dict]:
    for a in load_catalog():
        if a["article_id"].upper() == article_id.upper():
            return a
    return None


def is_applicable(meta: dict, member_program: str) -> bool:
    """An article may be used for a member only if it is for all programs or for the member's program."""
    return meta["program"] in ("All programs", member_program)


def parse_front_matter(text: str) -> tuple[dict, str]:
    meta: dict = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            body = parts[2].strip()
    return meta, body


def load_documents(folders: tuple[str, ...] = ("education", "faq", "careplan_guidance")) -> list[dict]:
    docs = []
    approved = {a["article_id"]: a for a in load_catalog()}
    for folder in folders:
        for path in sorted((config.KNOWLEDGE_DIR / folder).glob("*.md")):
            meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
            if meta.get("article_id") not in approved:      # Draft / Retired / unlisted files are never used
                continue
            cat = approved[meta["article_id"]]
            meta = {**meta, "program": cat["program"], "version": cat["version"], "title": cat["title"]}
            docs.append({**meta, "content": body, "folder": folder, "path": str(path)})
    return docs


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z]+", text.lower())
    out = set()
    for w in words:
        if w in STOPWORDS or len(w) < 3:
            continue
        if w.endswith("s") and len(w) > 3:
            w = w[:-1]
        out.add(w)
    return out


def search_local(query: str, folders: tuple[str, ...], program: Optional[str] = None, min_score: int = 2) -> list[dict]:
    """Rank approved documents by keyword overlap. Returns [] when nothing is relevant (a knowledge gap)."""
    q = _tokens(query)
    results = []
    for doc in load_documents(folders):
        if program and doc.get("program") not in ("All programs", program):
            continue
        title_hits = len(q & _tokens(doc.get("title", "")))
        body_hits = len(q & _tokens(doc["content"]))
        score = body_hits + 2 * title_hits
        if score >= min_score:
            results.append({**doc, "score": score})
    return sorted(results, key=lambda d: d["score"], reverse=True)
