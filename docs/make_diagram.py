"""Regenerates docs/architecture_diagram.png (one page).   python docs/make_diagram.py"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

BLUE, BLUE_BG = "#1f4e79", "#e8f1fa"
GREEN, GREEN_BG = "#2e7d32", "#e9f5ea"
ORANGE, ORANGE_BG = "#c75b00", "#fff1e0"
GREY, GREY_BG = "#555555", "#f3f3f3"
PURPLE, PURPLE_BG = "#5b3a8c", "#f1ebfa"

fig, ax = plt.subplots(figsize=(16, 10))
ax.set_xlim(0, 100)
ax.set_ylim(-12, 56)
ax.axis("off")


def box(x, y, w, h, title, body="", edge=BLUE, fill=BLUE_BG, title_size=10, body_size=8, dashed=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=0.8", linewidth=1.6,
                                edgecolor=edge, facecolor=fill, linestyle="--" if dashed else "-"))
    ax.text(x + w / 2, y + h - 1.1, title, ha="center", va="top", fontsize=title_size, fontweight="bold", color=edge)
    if body:
        ax.text(x + w / 2, y + h - 3.3, body, ha="center", va="top", fontsize=body_size, color="#222222", linespacing=1.35)


def arrow(x1, y1, x2, y2, color=GREY, style="-|>", ls="-"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=14, linewidth=1.5,
                                 color=color, linestyle=ls))


ax.text(50, 55.2, "Chronic Care Engagement and Follow-up - Multi-Agent Architecture (synthetic data, educational use only)",
        ha="center", va="top", fontsize=14, fontweight="bold", color="#111111")

# --- top row ---
box(1.5, 37, 17, 12, "Member", "Python client\n(client/app.py)\n\nMember View\nStaff View (demo)", edge=GREEN, fill=GREEN_BG)
box(25, 34.5, 45, 16, "Care Orchestrator  (Python code, fixed workflow)",
    "1  Verify member + consent        -> ER-501 stop\n"
    "2  Input guard + medication check -> ER-503 decline\n"
    "3  Classify request (orchestrator agent / keyword fallback)\n"
    "4  Read data window, apply rules  -> ER-502, ER-504\n"
    "5  Call specialist agents, validate their wording\n"
    "6  Build 2 separate outputs + audit record",
    edge=BLUE, fill=BLUE_BG, body_size=8.5)
box(77, 37, 21.5, 12, "Outputs", "Member response (plain language,\nsource IDs, disclaimer)\nCoordinator packet (staff only)\nAudit record (masked IDs)", edge=PURPLE, fill=PURPLE_BG)

arrow(18.7, 43, 24.8, 43, GREEN, "<|-|>")
arrow(70.3, 43, 76.8, 43, PURPLE)

# --- human checkpoints ---
ax.add_patch(FancyBboxPatch((1.5, 26.2), 97, 6.4, boxstyle="round,pad=0.25,rounding_size=0.8", linewidth=1.6,
                            edgecolor=ORANGE, facecolor=ORANGE_BG))
ax.text(3, 31.9, "HUMAN CHECKPOINTS (staff / clinician decide - the system never does)", fontsize=9.5, fontweight="bold", color=ORANGE, va="top")
ax.text(3, 29.9,
        "ER-501 consent not active -> program staff     |     ER-502 configured test value matched -> URGENT staff-review record (no interpretation)\n"
        "ER-503 medication change request -> qualified clinician     |     ER-504 contradictory data -> human review     |     No approved article -> staff follow-up",
        fontsize=8.3, va="top", color="#222222", linespacing=1.5)
arrow(47, 34.3, 47, 32.9, ORANGE)

# --- agents row (all six are Foundry agents) ---
agents = [
    ("Care Orchestrator\nAgent (routing)", "one-word classifier;\nthe workflow itself\nis Python code", GREEN, GREEN_BG),
    ("Reading Summary\nAgent", "describes readings,\nmissing dates", GREEN, GREEN_BG),
    ("Care Plan Agent", "due / upcoming\ntasks as recorded", GREEN, GREEN_BG),
    ("Education RAG Agent", "answers only from\napproved documents + IDs", GREEN, GREEN_BG),
    ("Engagement Agent", "neutral reminder\n+ check-in question", GREEN, GREEN_BG),
    ("Escalation Agent", "words the staff note;\nrules decided by code", GREEN, GREEN_BG),
]
tools = [
    ("no data", "message text only"),
    ("facts in the message", "readings.csv\nACTIVE values only"),
    ("facts in the message", "care_plan_tasks.csv"),
    ("EDUCATION_RETRIEVAL=\nindex | knowledge_base", "edu + FAQ only\n(never care-plan guidance)"),
    ("facts in the message", "due tasks, channel,\nlanguage"),
    ("facts in the message", "matched rules\n(escalation_rules.csv)"),
]
w, gap, x0 = 14.6, 1.5, 1.5
for i, (a, t) in enumerate(zip(agents, tools)):
    x = x0 + i * (w + gap)
    box(x, 14.2, w, 10.2, a[0], a[1], edge=a[2], fill=a[3], title_size=8.0, body_size=7.8)
    box(x, 3.6, w, 8.6, t[0], t[1], edge=GREY, fill=GREY_BG, title_size=7.6, body_size=7.4)
    arrow(x + w / 2, 14.0, x + w / 2, 12.4, GREY)
    arrow(47, 26.0, x + w / 2, 24.7, GREEN)

# --- Foundry container around the six agents ---
ax.add_patch(Rectangle((0.7, 2.9), 98.6, 22.4, fill=False, edgecolor=GREEN, linewidth=1.6, linestyle="--"))
ax.text(2, 2.3, "Microsoft Foundry project: six agents, one deployed chat model.  Python adds: input guard, output guard, retry, safe failure, audit",
        ha="left", va="top", fontsize=7.4, color=GREEN, fontweight="bold")

# --- data and knowledge row ---
box(1.5, -10.2, 20, 8.4, "Data Manager (UI)", "upload CSV / JSON / Excel /\nWord / PDF / text\nvalidate - approve - roll back", edge=BLUE, fill=BLUE_BG, title_size=8.4, body_size=7.4)
box(27, -10.2, 22, 8.4, "Azure Blob Storage", "data/*.csv\nknowledge/ (Approved only)\nknowledge-unapproved/ (Draft, Retired)", edge=BLUE, fill=BLUE_BG, title_size=8.4, body_size=7.4)
box(55, -10.2, 24, 8.4, "Retrieval (switchable)", "index: AI Search (3 indexes)\nknowledge_base: Foundry knowledge base\non Blob (MCP tool)", edge=GREEN, fill=GREEN_BG, title_size=8.4, body_size=7.4)
arrow(21.7, -6, 26.8, -6, BLUE)
arrow(49.2, -6, 54.8, -6, BLUE)
arrow(82, -6, 82, 2.9, GREEN)
ax.plot([79.2, 82], [-6, -6], color=GREEN, linewidth=1.5)
ax.text(99, -9, "Audit: consent check, agents called,\nrule IDs, source versions, disposition", ha="right", va="center", fontsize=7.2, color=PURPLE)

out = Path(__file__).with_name("architecture_diagram.png")
fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
print("wrote", out)
