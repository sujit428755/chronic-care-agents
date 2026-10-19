"""Interactive Python client.

Run:   python client/app.py                 (uses Foundry agents; needs .env)
       python client/app.py --offline       (no Azure calls; templates only, handy for a first check)

It shows two separate views for every request:
  MEMBER VIEW - what the member would see
  STAFF VIEW  - the coordinator packet (staff only; shown here so you can demo the separation)
Commands: /member M-102   /view member|staff|both   /help   /quit
"""
import argparse
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from src.middleware.audit_logging import setup_logging  # noqa: E402
from src.orchestrator import CareOrchestrator  # noqa: E402
from src.tools.member_tools import get_member  # noqa: E402

LINE = "=" * 78


def banner(offline: bool) -> None:
    print(LINE)
    print(" Chronic Care Engagement and Follow-up - multi-agent prototype")
    print(f" Mode: {'OFFLINE (templates, no Azure calls)' if offline else 'ONLINE (Foundry agents)'}   |   Reference date: {config.REFERENCE_DATE}")
    print(LINE)
    print(" " + config.DISCLAIMER)
    print(LINE)
    print(" Synthetic members: M-101, M-102, M-103, M-104, M-105.  Type /help for commands.")
    print(LINE)


def show(result, view: str) -> None:
    if view in ("member", "both"):
        print("\n" + LINE + "\n MEMBER VIEW\n" + LINE)
        print(result.member_response.render())
    if view in ("staff", "both"):
        print("\n" + LINE + "\n STAFF VIEW (coordinator packet - staff only)\n" + LINE)
        print(result.coordinator_packet.render())
        a = result.audit
        print(f"\n AUDIT: consent={a.consent_check} | agents={', '.join(a.agents_called)} | rules={', '.join(a.rule_ids) or 'none'}"
              f" | sources={', '.join(a.source_versions) or 'none'} | disposition={a.disposition}")
    print()


async def run(args) -> None:
    orchestrator = CareOrchestrator(offline=config.OFFLINE)
    member_id = args.member.upper()
    view = args.view
    banner(config.OFFLINE)

    while True:
        try:
            text = input(f"[{member_id}] You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return
        if not text:
            continue
        if text.lower() in ("/quit", "/exit", "quit", "exit"):
            print("Goodbye.")
            return
        if text.lower() == "/help":
            print(__doc__)
            continue
        if re.match(r"^/\s+\w", text):          # "/ member M-102" -> "/member M-102"
            text = "/" + text[1:].lstrip()
        if re.fullmatch(r"M-\d{3,6}", text, re.IGNORECASE):
            print("To switch member, type:  /member " + text.upper() + "\n")
            continue
        if text.lower().startswith("/member"):
            parts = text.split()
            if len(parts) == 2 and get_member(parts[1]):
                member_id = parts[1].upper()
                print(f"Switched to {member_id}.")
            else:
                print("Usage: /member M-101   (known synthetic members: M-101 to M-105)")
            continue
        if text.lower().startswith("/view"):
            parts = text.split()
            if len(parts) == 2 and parts[1] in ("member", "staff", "both"):
                view = parts[1]
                print(f"View set to {view}.")
            else:
                print("Usage: /view member|staff|both")
            continue
        try:
            result = await orchestrator.handle(member_id, text)
            show(result, view)
        except RuntimeError as exc:  # e.g. missing .env settings
            print(f"\n[Setup problem] {exc}\n")
        except Exception as exc:  # noqa: BLE001 - never crash the demo
            print(f"\n[Unexpected error] {type(exc).__name__}: {exc}\nNo answer was generated. Please try again or contact program staff.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chronic care multi-agent client")
    parser.add_argument("--offline", action="store_true", help="run without Azure/model calls")
    parser.add_argument("--member", default="M-101", help="starting member ID (default M-101)")
    parser.add_argument("--view", default="both", choices=["member", "staff", "both"])
    args = parser.parse_args()
    if args.offline:
        config.set_offline(True)
    setup_logging()
    from src.agents import foundry_runtime
    warn = foundry_runtime.ensure_registered(progress=print)
    if warn:
        print("\n[Warning] " + warn + "\n")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
