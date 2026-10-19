"""Create the three Azure AI Search indexes and upload the APPROVED knowledge (thin wrapper over src/azure_integration/search.py).

    python scripts/setup_search_index.py --dry-run     # build everything locally, no Azure calls
    python scripts/setup_search_index.py               # create indexes + upload (needs .env + `az login`)

Set EMBEDDING_DIMENSIONS if your embedding model is not 1536-dimensional (text-embedding-3-large = 3072).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.azure_integration import search  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="build indexes and documents locally only")
    args = ap.parse_args()
    try:
        search.sync_indexes(dry_run=args.dry_run, progress=print)
    except RuntimeError as exc:
        sys.exit(str(exc))
    print("[dry-run] OK. No Azure calls were made." if args.dry_run else "Done. Next: python scripts/create_education_agent.py")
