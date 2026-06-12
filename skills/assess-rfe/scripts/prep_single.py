#!/usr/bin/env python3
"""Prepare the single-assessment directory for a new run.

Removes any existing data and result files for the given key so that
Write tool calls see them as new files (avoiding the read-before-write guard).
Creates the output directory if it doesn't exist.

Usage:
    python3 scripts/prep_single.py RHAIRFE-1234
"""

import os
import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: prep_single.py KEY", file=sys.stderr)
        sys.exit(1)

    key = sys.argv[1]
    single_dir = "/tmp/rfe-assess/single"
    os.makedirs(single_dir, exist_ok=True)

    for suffix in (".md", ".result.md"):
        path = os.path.join(single_dir, f"{key}{suffix}")
        if os.path.exists(path):
            os.remove(path)
            print(f"REMOVED={path}")

    print(f"SINGLE_DIR={single_dir}")


if __name__ == "__main__":
    main()
