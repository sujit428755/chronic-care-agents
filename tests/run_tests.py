"""Run all test scenarios and write the test evidence.

    python tests/run_tests.py --offline        # no Azure calls (checks the safety logic and workflow)
    python tests/run_tests.py                  # ONLINE: uses your Foundry agents (the reference run)
    python tests/run_tests.py --only T1,T4     # run a subset

Outputs:
    docs/test_results.json   machine-readable results
    docs/test_evidence.md    the test evidence document (prompt, output, citations, safety observations, pass/fail)

The evidence file states which mode produced it. Use the ONLINE run as the reference evidence: the evidence must match
the deployed solution.
"""
import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from src.middleware.audit_logging import setup_logging  # noqa: E402
from src.middleware.output_guard import check_text  # noqa: E402
from src.orchestrator import CareOrchestrator  # noqa: E402

CASES_FILE = Path(__file__).with_name("test_cases.json")


def evaluate(case: dict, result) -> tuple[list[str], list[str]]:
    """Returns (failures, safety_observations)."""
    exp = case["expect"]
    mr, pk, au = result.member_response, result.coordinator_packet, result.audit
    member_text = mr.render()
    low = member_text.lower()
    fails: list[str] = []
    obs: list[str] = []

    def need(cond: bool, msg: str) -> None:
        if not cond:
            fails.append(msg)

    if "disposition" in exp:
        need(au.disposition in exp["disposition"], f"disposition {au.disposition!r} not in {exp['disposition']}")
    if "category" in exp:
        need(pk.category == exp["category"], f"category {pk.category!r} != {exp['category']!r}")
    for r in exp.get("rule_ids_include", []):
        need(r in pk.rule_ids, f"rule {r} not triggered (got {pk.rule_ids})")
    for r in exp.get("rule_ids_exclude", []):
        need(r not in pk.rule_ids, f"rule {r} should not be triggered")
    if "urgency" in exp:
        need(pk.urgency == exp["urgency"], f"urgency {pk.urgency!r} != {exp['urgency']!r}")
    src_ids = [s.source_id for s in mr.sources]
    for s in exp.get("sources_include", []):
        need(s in src_ids, f"source {s} missing from member response sources {src_ids}")
    for s in exp.get("sources_exclude", []):
        need(s not in src_ids, f"source {s} must not be cited")
    for t in exp.get("member_text_includes", []):
        need(t.lower() in low, f"member text should include {t!r}")
    if exp.get("member_text_includes_any"):
        need(any(t.lower() in low for t in exp["member_text_includes_any"]), f"member text should include one of {exp['member_text_includes_any']}")
    for t in exp.get("member_text_excludes", []):
        need(t.lower() not in low, f"member text must not include {t!r}")
    missing_blob = " ".join(pk.missing_information)
    for d in exp.get("missing_dates_include", []):
        need(d in missing_blob, f"missing date {d} not reported to staff")
    if exp.get("no_readings_in_packet"):
        need(not pk.relevant_readings, "packet must not contain readings")
    for c in exp.get("corrections_include", []):
        need(any(x["superseded"] == c for x in pk.corrections_applied), f"correction {c} not recorded for staff")
    if exp.get("packet_has_reminder"):
        need(bool(pk.reminder_draft), "packet should carry the reminder draft")

    # ---- checks applied to EVERY test ----
    wording = member_text.replace(config.DISCLAIMER, "")
    violations = check_text(wording)
    need(not violations, f"forbidden language in member view: {violations}")
    obs.append("No diagnosis, judgement of a reading, medication advice or clinician claim in the member view." if not violations else f"VIOLATION: {violations}")
    need(config.DISCLAIMER in member_text, "educational-use disclaimer missing")
    obs.append("Educational-use disclaimer shown.")
    need(bool(re.fullmatch(r"M-\d\*\*", au.member)) or au.member == "", f"audit member ID not masked: {au.member!r}")
    obs.append(f"Audit record masks the member ID ({au.member}); no message text or reading values stored.")
    need(not any(w in json.dumps(au.model_dump()) for w in ("mg/dL", "mmHg")), "audit record contains reading values")
    if pk.rule_ids:
        obs.append(f"Rule(s) {', '.join(pk.rule_ids)} applied by code; staff record urgency = {pk.urgency}; no clinical interpretation.")
    if pk.missing_information:
        obs.append("Missing information is reported instead of being filled in.")
    return fails, obs


async def run_case(orchestrator: CareOrchestrator, case: dict) -> dict:
    saved = {k: os.environ.get(k) for k in case.get("env", {})}
    os.environ.update(case.get("env", {}))
    try:
        result = await orchestrator.handle(case["member_id"], case["prompt"])
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    fails, obs = evaluate(case, result)
    return {
        "id": case["id"], "title": case["title"], "member_id": case["member_id"], "prompt": case["prompt"],
        "expected": case["expected_text"], "passed": not fails, "failures": fails, "safety_observations": obs,
        "disposition": result.audit.disposition, "rule_ids": result.coordinator_packet.rule_ids,
        "citations": [s.label() for s in result.member_response.sources],
        "agents_called": result.audit.agents_called, "audit_notes": result.audit.notes,
        "member_view": result.member_response.render(), "staff_view": result.coordinator_packet.render(),
    }


def write_markdown(results: list[dict], mode: str, path: Path) -> None:
    passed = sum(r["passed"] for r in results)
    lines = [
        "# Test Evidence",
        "",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- Mode: **{mode}**",
        f"- Reference date used for the synthetic data: {config.REFERENCE_DATE}",
        f"- Result: **{passed} of {len(results)} tests passed**",
        "",
        "Only synthetic data is used. Member IDs below are synthetic. Evidence for submission must come from an ONLINE run against your deployed Foundry agents.",
        "",
        "## Summary",
        "",
        "| ID | Scenario | Member | Disposition | Rules | Citations | Result |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['id']} | {r['title']} | {r['member_id']} | {r['disposition']} | {', '.join(r['rule_ids']) or '-'} | "
            f"{', '.join(r['citations']) or '-'} | {'PASS' if r['passed'] else 'FAIL'} |"
        )
    for r in results:
        lines += [
            "", f"## {r['id']} - {r['title']}", "",
            f"**Prompt** ({r['member_id']}): {r['prompt']}", "",
            f"**Expected behaviour:** {r['expected']}", "",
            f"**Agents called:** {', '.join(r['agents_called'])}", "",
            "**Member view output:**", "", "```text", r["member_view"], "```", "",
            "**Staff view (coordinator packet):**", "", "```text", r["staff_view"], "```", "",
            f"**Citations:** {', '.join(r['citations']) or 'none'}", "",
            "**Safety observations:**", "",
        ]
        lines += [f"- {o}" for o in r["safety_observations"]]
        if r["audit_notes"]:
            lines += ["", "**Audit notes:** " + "; ".join(r["audit_notes"])]
        lines += [
            "", f"**Result:** {'PASS' if r['passed'] else 'FAIL'}", "",
            "**Corrective action:** " + ("None needed." if r["passed"] else "TO FILL IN - " + "; ".join(r["failures"])),
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--only", help="comma-separated test IDs, e.g. T1,T4")
    args = parser.parse_args()
    if args.offline:
        config.set_offline(True)
    setup_logging()
    from src.agents import foundry_runtime
    _warn = foundry_runtime.ensure_registered(progress=print)
    if _warn:
        print("[Warning] " + _warn)

    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    if args.only:
        wanted = {x.strip().upper() for x in args.only.split(",")}
        cases = [c for c in cases if c["id"] in wanted]

    mode = "OFFLINE dry run (templates, no Azure calls)" if config.OFFLINE else f"ONLINE (agent runtime: {config.AGENT_RUNTIME}; Education retrieval: {config.EDUCATION_RETRIEVAL})"
    orchestrator = CareOrchestrator(offline=config.OFFLINE)
    results = []
    for case in cases:
        try:
            res = await run_case(orchestrator, case)
        except Exception as exc:  # noqa: BLE001
            res = {
                "id": case["id"], "title": case["title"], "member_id": case["member_id"], "prompt": case["prompt"],
                "expected": case["expected_text"], "passed": False, "failures": [f"{type(exc).__name__}: {exc}"],
                "safety_observations": [], "disposition": "error", "rule_ids": [], "citations": [], "agents_called": [],
                "audit_notes": [], "member_view": "", "staff_view": "",
            }
        results.append(res)
        print(f"{res['id']:>4}  {'PASS' if res['passed'] else 'FAIL'}  {res['title']}")
        for f in res["failures"]:
            print(f"        - {f}")

    config.DOCS_DIR.mkdir(exist_ok=True)
    (config.DOCS_DIR / "test_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    write_markdown(results, mode, config.DOCS_DIR / "test_evidence.md")
    passed = sum(r["passed"] for r in results)
    print(f"\n{passed}/{len(results)} passed  |  mode: {mode}\nWrote docs/test_evidence.md and docs/test_results.json")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
