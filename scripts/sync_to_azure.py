"""Keep the cloud copy in step with this project.

    python scripts/sync_to_azure.py --status          # compare local files with the Blob container
    python scripts/sync_to_azure.py --push            # upload new/changed CSV tables and documents to Blob Storage
    python scripts/sync_to_azure.py --pull            # download from Blob Storage (tables are validated first)
    python scripts/sync_to_azure.py --index           # make the search side current (rebuild indexes, or run knowledge-source indexers)
    python scripts/sync_to_azure.py --register        # create / update the six agents in Foundry
    python scripts/sync_to_azure.py --push --index    # the usual pipeline: Blob -> Search
    python scripts/sync_to_azure.py --watch           # re-run push+index whenever a file changes (Ctrl+C to stop)
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents import foundry_runtime  # noqa: E402
from src.azure_integration import blob, search  # noqa: E402


def fingerprint() -> tuple:
    return tuple((n, p.stat().st_mtime_ns) for n, p in blob.local_files().items())


def run(args) -> None:
    if args.status:
        for r in blob.compare():
            print(f"{r['state']:<30} {r['file']}")
    if args.pull:
        print(blob.pull(print))
    if args.push:
        print(blob.push(print))
    if args.index:
        print(search.sync_for_current_mode(print))
    if args.register:
        foundry_runtime.register_all(progress=print)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    for f in ("status", "push", "pull", "index", "register", "watch"):
        ap.add_argument(f"--{f}", action="store_true")
    a = ap.parse_args()
    if not any(vars(a).values()):
        ap.print_help()
        sys.exit(0)
    try:
        if a.watch:
            a.push = a.index = True
            last = None
            print("Watching for changes. Press Ctrl+C to stop.")
            while True:
                fp = fingerprint()
                if fp != last:
                    run(a)
                    last = fingerprint()
                time.sleep(5)
        else:
            run(a)
    except (blob.AzureNotConfigured, RuntimeError) as exc:
        sys.exit(str(exc))
    except KeyboardInterrupt:
        pass
