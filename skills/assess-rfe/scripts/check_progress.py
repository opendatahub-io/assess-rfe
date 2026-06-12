#!/usr/bin/env python3
"""Check progress of an assessment run.

Reports completed result count vs total expected issues.

Usage:
    python3 scripts/check_progress.py /path/to/run_dir
"""

import os
import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: check_progress.py RUN_DIR", file=sys.stderr)
        sys.exit(1)

    run_dir = sys.argv[1]

    if not os.path.isdir(run_dir):
        print(f"Error: {run_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Count completed results
    completed = len([f for f in os.listdir(run_dir) if f.endswith(".result.md")])

    # Determine total from cache directory
    # Run dir is like assessments/RHAIRFE/20260322-131952
    # Project key is the parent directory name
    project = os.path.basename(os.path.dirname(run_dir))
    cache_dir = os.path.join("/tmp/rfe-assess", project)
    total = 0
    if os.path.isdir(cache_dir):
        total = len([f for f in os.listdir(cache_dir) if f.endswith(".md")])

    print(f"COMPLETED={completed}")
    print(f"TOTAL={total}")
    print(f"REMAINING={total - completed}")


if __name__ == "__main__":
    main()
