"""Register ONLY the Education RAG agent (kept for the reference step-by-step flow). Prefer scripts/create_agents.py.

    python scripts/create_education_agent.py
    python scripts/create_education_agent.py --test "What is a home reading?"
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from src.agents import education_agent, foundry_runtime  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", help="ask the registered agent one question (uses member program 'Diabetes Support')")
    args = parser.parse_args()
    r = foundry_runtime.register("education", force=True)
    print(f"Created agent '{r['name']}' version {r['version']}  (retrieval mode: {config.EDUCATION_RETRIEVAL})")
    if args.test:
        raw = asyncio.run(education_agent.ask(args.test, "Diabetes Support", offline=False))
        print("\nRaw agent answer:\n" + raw)
        print("\nValidated against the approved catalog:\n", education_agent.interpret(raw, "Diabetes Support"))


if __name__ == "__main__":
    main()
