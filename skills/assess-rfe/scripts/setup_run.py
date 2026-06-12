#!/usr/bin/env python3
"""Set up an assessment run directory with resume support.

Checks for an existing incomplete run (current symlink with no scores.csv),
creates a new timestamped directory if needed, writes pending keys to a queue
file (queue.txt), and outputs run metadata.

Usage:
    python3 scripts/setup_run.py RHAIRFE
    python3 scripts/setup_run.py RHAIRFE --limit 20
"""

import argparse
import os
import sys
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", help="Project key (e.g., RHAIRFE)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit number of pending keys (0 = all)")
    parser.add_argument("--assess-dir", default="assessments",
                        help="Base assessments directory (default: assessments)")
    parser.add_argument("--cache-dir", default="/tmp/rfe-assess",
                        help="Issue cache directory (default: /tmp/rfe-assess)")
    args = parser.parse_args()

    project = args.project
    assess_base = os.path.join(args.assess_dir, project)
    cache_dir = os.path.join(args.cache_dir, project)

    # Check cache exists
    if not os.path.isdir(cache_dir):
        print(f"ERROR: Issue cache not found at {cache_dir}", file=sys.stderr)
        print("Run scripts/dump_jira.py first.", file=sys.stderr)
        sys.exit(1)

    # Get all issue keys from cache
    all_keys = sorted(
        [f.replace(".md", "") for f in os.listdir(cache_dir) if f.endswith(".md")],
        key=lambda k: int(k.split("-")[-1]) if k.split("-")[-1].isdigit() else 0,
    )

    if not all_keys:
        print(f"ERROR: No issue files found in {cache_dir}", file=sys.stderr)
        sys.exit(1)

    # Resume logic
    os.makedirs(assess_base, exist_ok=True)
    current_link = os.path.join(assess_base, "current")
    run_dir = None
    resuming = False

    if os.path.islink(current_link):
        target = os.path.join(assess_base, os.readlink(current_link))
        if os.path.isdir(target) and not os.path.exists(os.path.join(target, "scores.csv")):
            run_dir = target
            resuming = True

    if run_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = os.path.join(assess_base, timestamp)
        os.makedirs(run_dir, exist_ok=True)
        # Update symlink
        tmp_link = current_link + ".tmp"
        os.symlink(os.path.basename(run_dir), tmp_link)
        os.replace(tmp_link, current_link)

    # Find already-assessed keys
    assessed = set()
    if os.path.isdir(run_dir):
        assessed = {
            f.replace(".result.md", "")
            for f in os.listdir(run_dir)
            if f.endswith(".result.md")
        }

    # Pending keys
    pending = [k for k in all_keys if k not in assessed]
    if args.limit > 0:
        pending = pending[:args.limit]

    # Write pending keys to queue file in run directory
    run_dir_abs = os.path.abspath(run_dir)
    queue_file = os.path.join(run_dir_abs, "queue.txt")
    with open(queue_file, "w", encoding="utf-8") as f:
        for key in pending:
            f.write(key + "\n")

    # Output (no longer dumps all keys to stdout)
    print(f"RUN_DIR={run_dir_abs}")
    print(f"TOTAL_ISSUES={len(all_keys)}")
    print(f"ALREADY_ASSESSED={len(assessed)}")
    print(f"PENDING={len(pending)}")
    print(f"QUEUE_FILE={queue_file}")
    print(f"RESUMING={'true' if resuming else 'false'}")

    if resuming:
        print(f"Resuming run: {run_dir_abs} ({len(assessed)} done, {len(pending)} remaining)",
              file=sys.stderr)
    else:
        print(f"New run: {run_dir_abs} ({len(pending)} issues)", file=sys.stderr)


if __name__ == "__main__":
    main()
