"""Hospital look and feel: clean white and teal, a cross logo, patient wristbands and triage colours."""
from __future__ import annotations

import html as _html

import streamlit as st

import config

HOSPITAL = "Synthetic Hospital"
DESK = "Chronic Care Desk"

# triage colours (same idea as emergency-department colour coding)
URGENCY = {
    "urgent_staff_review": ("#C62828", "#FDECEA", "URGENT STAFF REVIEW", 1),
    "clinician_referral": ("#E65100", "#FFF1E3", "CLINICIAN REFERRAL", 2),
    "human_review": ("#B26A00", "#FFF6DD", "HUMAN REVIEW", 3),
    "staff_contact": ("#1F6FB2", "#E8F2FB", "STAFF CONTACT", 4),
    "staff_followup": ("#0E7C86", "#E3F4F5", "STAFF FOLLOW-UP", 5),
    "none": ("#2E7D32", "#E8F5E9", "ROUTINE", 6),
}

CROSS_SVG = (
    '<svg width="34" height="34" viewBox="0 0 34 34" xmlns="http://www.w3.org/2000/svg">'
    '<rect width="34" height="34" rx="9" fill="#ffffff"/>'
    '<path d="M13 6h8v7h7v8h-7v7h-8v-7H6v-8h7z" fill="#D64545"/></svg>'
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', 'Segoe UI', sans-serif; }
.block-container { padding-top: 1.2rem; max-width: 1380px; }
header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }

/* top banner */
.topbar { display:flex; align-items:center; gap:16px; background:linear-gradient(110deg,#0A5C66 0%,#0E7C86 50%,#2A8FC7 100%);
  color:#fff; border-radius:18px; padding:18px 26px; margin-bottom:14px; box-shadow:0 10px 28px rgba(14,124,134,.28); }
.topbar h1 { margin:0; font-size:1.55rem; font-weight:800; letter-spacing:-.3px; color:#fff; }
.topbar .sub { opacity:.92; font-size:.92rem; margin-top:2px; }
.topbar .right { margin-left:auto; text-align:right; }
.chip { display:inline-block; padding:3px 11px; margin:3px 0 0 6px; border-radius:999px; background:rgba(255,255,255,.18);
  font-size:.74rem; font-weight:600; border:1px solid rgba(255,255,255,.25); }
.safety-strip { background:#FFF8E6; border:1px solid #F3D98B; border-left:6px solid #E0A800; color:#5B4300; border-radius:12px;
  padding:9px 14px; font-size:.86rem; margin-bottom:14px; }

/* cards */
.card { background:#fff; border:1px solid #DCE9EE; border-radius:16px; padding:16px 18px; box-shadow:0 3px 14px rgba(18,49,61,.06); }
.card h4 { margin:0 0 6px 0; font-size:1rem; color:#0A5C66; }
.section-title { font-size:1.12rem; font-weight:700; color:#0A5C66; margin:18px 0 8px 0; display:flex; align-items:center; gap:8px; }
.section-title:before { content:""; width:5px; height:20px; border-radius:3px; background:#0E7C86; display:inline-block; }
.muted { color:#5E7884; font-size:.85rem; }

/* KPI tiles */
.kpi-row { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:14px; margin:6px 0 16px 0; }
.kpi { background:#fff; border-radius:16px; padding:14px 16px; border:1px solid #DCE9EE; border-top:5px solid var(--c);
  box-shadow:0 3px 14px rgba(18,49,61,.06); }
.kpi .l { font-size:.72rem; text-transform:uppercase; letter-spacing:.8px; color:#5E7884; font-weight:700; }
.kpi .v { font-size:2rem; font-weight:800; color:var(--c); line-height:1.15; }
.kpi .s { font-size:.78rem; color:#7B93A0; }

/* patient wristband */
.wristband { position:relative; background:#fff; border:2px solid #0E7C86; border-radius:14px; padding:14px 16px 12px 22px;
  box-shadow:0 4px 16px rgba(14,124,134,.15); overflow:hidden; }
.wristband:before { content:""; position:absolute; left:0; top:0; bottom:0; width:10px; background:var(--band,#0E7C86); }
.wristband .id { font-size:1.35rem; font-weight:800; color:#12313D; letter-spacing:.5px; }
.wristband .row { display:flex; justify-content:space-between; font-size:.84rem; padding:3px 0; border-bottom:1px dashed #DCE9EE; }
.wristband .row span:first-child { color:#5E7884; }
.barcode { height:26px; margin-top:8px; background:repeating-linear-gradient(90deg,#12313D 0 2px,#fff 2px 4px,#12313D 4px 5px,#fff 5px 9px); opacity:.8; border-radius:2px; }

/* badges */
.badge { display:inline-block; padding:3px 11px; border-radius:999px; font-weight:700; font-size:.74rem; color:#fff; background:var(--c); }
.badge.soft { color:var(--c); background:var(--bg); border:1px solid var(--c); }

/* chat */
.msg-user { background:#E3F4F5; border:1px solid #BFE3E6; color:#12313D; border-radius:16px 16px 4px 16px; padding:10px 14px; margin:8px 0 8px 18%; }
.msg-bot { background:#fff; border:1px solid #DCE9EE; border-left:6px solid #0E7C86; border-radius:16px 16px 16px 4px; padding:12px 16px; margin:8px 18% 4px 0;
  box-shadow:0 2px 10px rgba(18,49,61,.05); line-height:1.55; }
.msg-meta { font-size:.72rem; color:#7B93A0; margin:0 0 2px 4px; }
.src-chip { display:inline-block; background:#E8F2FB; color:#1F6FB2; border:1px solid #B9D7F0; padding:1px 9px; border-radius:999px; font-size:.75rem; font-weight:600; margin:2px 4px 2px 0; }
.notice { background:#FFF1E3; border:1px solid #F5C99B; border-left:6px solid #E65100; border-radius:10px; padding:8px 12px; font-size:.88rem; margin-top:8px; color:#5C2A00; }
.disclaimer { font-size:.76rem; color:#6B8591; margin-top:8px; font-style:italic; }

/* triage cards */
.triage { background:#fff; border:1px solid #DCE9EE; border-left:8px solid var(--c); border-radius:12px; padding:12px 16px; margin:8px 0; box-shadow:0 2px 10px rgba(18,49,61,.05); }
.triage .t { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.triage .mid { font-weight:800; font-size:1.05rem; }
.triage .when { margin-left:auto; color:#7B93A0; font-size:.78rem; }
.triage .why { margin-top:6px; font-size:.9rem; }

/* flow */
.flow { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:6px 0 14px 0; }
.step { background:#fff; border-radius:12px; padding:9px 14px; font-weight:600; font-size:.84rem; border:1px solid #DCE9EE; border-top:4px solid var(--c); box-shadow:0 2px 10px rgba(18,49,61,.06); }
.arrow { color:#9FB6C0; font-weight:800; }

/* tabs, sidebar */
.stTabs [data-baseweb="tab-list"] { gap:6px; background:#fff; padding:6px; border-radius:14px; border:1px solid #DCE9EE; }
.stTabs [data-baseweb="tab"] { border-radius:10px; padding:8px 16px; font-weight:600; }
.stTabs [aria-selected="true"] { background:linear-gradient(110deg,#0E7C86,#2A8FC7); color:#fff !important; }
[data-testid="stSidebar"] { background:#FFFFFF; border-right:1px solid #DCE9EE; }
.side-brand { display:flex; align-items:center; gap:10px; padding:4px 2px 10px 2px; }
.side-brand .n { font-weight:800; color:#0A5C66; line-height:1.15; }
.side-brand .n small { display:block; font-weight:500; color:#5E7884; font-size:.72rem; }
div[data-testid="stMetric"] { background:#fff; border:1px solid #DCE9EE; border-radius:14px; padding:10px 14px; }
.stButton > button, .stDownloadButton > button { border-radius:10px; font-weight:600; }
.stButton > button[kind="primary"] { background:#0E7C86; border-color:#0E7C86; }
</style>
"""


def esc(x) -> str:
    return _html.escape("" if x is None else str(x))


def html(s: str) -> None:
    """Render an HTML snippet. Lines are joined so Markdown never turns indented HTML into a code block."""
    st.markdown(" ".join(line.strip() for line in s.strip().splitlines()), unsafe_allow_html=True)


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def topbar(title: str, subtitle: str) -> None:
    mode = "OFFLINE (templates)" if config.OFFLINE else "ONLINE (Foundry)"
    html(
        f'<div class="topbar"><div>{CROSS_SVG}</div><div><h1>{esc(title)}</h1><div class="sub">{esc(subtitle)}</div></div>'
        f'<div class="right"><span class="chip">{esc(HOSPITAL)}</span><span class="chip">Mode: {mode}</span>'
        f'<span class="chip">Reference date {config.REFERENCE_DATE}</span></div></div>'
        f'<div class="safety-strip"><b>Safety:</b> synthetic data only. This system organises information and hands risky cases to people. '
        f'It never diagnoses, never gives medical advice and never changes medicines.</div>'
    )


def section(text: str) -> None:
    html(f'<div class="section-title">{esc(text)}</div>')


def kpi_row(items: list[tuple[str, object, str, str]]) -> None:
    """items: (label, value, sub text, colour)"""
    cells = "".join(
        f'<div class="kpi" style="--c:{c}"><div class="l">{esc(l)}</div><div class="v">{esc(v)}</div><div class="s">{esc(s)}</div></div>'
        for l, v, s, c in items)
    html(f'<div class="kpi-row">{cells}</div>')


def urgency_badge(urgency: str) -> str:
    c, bg, label, _ = URGENCY.get(urgency, URGENCY["none"])
    return f'<span class="badge" style="--c:{c}">{label}</span>'


def wristband(member: dict | None) -> str:
    if not member:
        return '<div class="wristband"><div class="id">Unknown member</div></div>'
    consent = member.get("consent_status") or "Unknown"
    band = {"Active": "#2E7D32", "Expired": "#E65100", "Revoked": "#C62828", "Pending": "#B26A00"}.get(consent, "#5E7884")
    rows = [("Program", member.get("program")), ("Language", member.get("language")), ("Channel", member.get("preferred_channel")), ("Consent", consent)]
    body = "".join(f'<div class="row"><span>{esc(k)}</span><b>{esc(v)}</b></div>' for k, v in rows)
    return (f'<div class="wristband" style="--band:{band}"><div class="muted">SYNTHETIC PATIENT</div>'
            f'<div class="id">{esc(member.get("member_id"))}</div>{body}<div class="barcode"></div></div>')


def flow(steps: list[tuple[str, str]]) -> None:
    parts = []
    for i, (label, colour) in enumerate(steps):
        parts.append(f'<div class="step" style="--c:{colour}">{esc(label)}</div>')
        if i < len(steps) - 1:
            parts.append('<div class="arrow">&#10140;</div>')
    html(f'<div class="flow">{"".join(parts)}</div>')


def bubble_user(text: str, member_id: str) -> None:
    html(f'<div class="msg-user"><div class="msg-meta">{esc(member_id)}</div>{esc(text).replace(chr(10), "<br>")}</div>')


def bubble_bot(text: str, sources: list[str], notice: str | None, disclaimer: str) -> None:
    chips = "".join(f'<span class="src-chip">{esc(s)}</span>' for s in sources)
    src = f'<div style="margin-top:8px"><span class="muted">Sources: </span>{chips}</div>' if chips else ""
    note = f'<div class="notice">{esc(notice)}</div>' if notice else ""
    html(f'<div class="msg-bot"><div class="msg-meta">Care Assistant</div>{esc(text).replace(chr(10), "<br>")}{src}{note}'
         f'<div class="disclaimer">{esc(disclaimer)}</div></div>')

CSS += "<style>.stButton > button p { white-space: normal; text-align:left; line-height:1.25; }</style>"


def pipeline_strip(chips: list[tuple[str, str, str]]) -> None:
    cells = "".join(f'<span class="badge soft" style="--c:{c};--bg:#fff;margin-right:8px"><b>{esc(l)}</b>: {esc(t)}</span>' for l, t, c in chips)
    html(f'<div style="margin:-4px 0 14px 0">{cells}</div>')
