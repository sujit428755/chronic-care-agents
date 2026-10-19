"""Create (or update) all six agents in your Foundry project, so you can show them in the Foundry portal.

    python scripts/create_agents.py                      # register agents that are missing or changed
    python scripts/create_agents.py --force              # new version of every agent
    python scripts/create_agents.py --only education     # one agent (keys: orchestrator reading careplan education engagement escalation)
    python scripts/create_agents.py --list               # what this project has registered
    python scripts/create_agents.py --test "What is a home reading?"   # ask the Education agent one question

Education retrieval mode comes from .env:  EDUCATION_RETRIEVAL=index  or  knowledge_base
After changing that setting, run:  python scripts/create_agents.py --only education
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from src.agents import education_agent, foundry_runtime, registry  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", nargs="+", choices=registry.ORDER)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--test")
    a = ap.parse_args()

    if a.list:
        for r in foundry_runtime.status_rows():
            print(f"{r['foundry_name']:<26} registered={r['registered']!s:<5} version={r['version']:<4} up_to_date={r['up_to_date']}")
        return
    print(f"Retrieval mode for the Education agent: {config.EDUCATION_RETRIEVAL}")
    try:
        foundry_runtime.register_all(force=a.force, only=a.only, progress=print)
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"Could not register: {type(exc).__name__}: {exc}")
    if a.test:
        raw = asyncio.run(education_agent.ask(a.test, "Diabetes Support", offline=False))
        print("\nRaw agent answer:\n" + raw)
        print("\nValidated against the approved catalog:\n", education_agent.interpret(raw, "Diabetes Support"))


if __name__ == "__main__":
    main()
