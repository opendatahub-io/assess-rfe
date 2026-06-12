#!/usr/bin/env python3
"""Pop the next batch of keys from the assessment queue.

Reads keys from queue.txt, returns the first N, and rewrites the file
with the remaining keys. This ensures each key is only processed once,
even if the caller loses track of which keys have been launched.

Usage:
    python3 scripts/next_batch.py /path/to/run_dir [--batch-size 30]

Output (stdout):
    BATCH_SIZE=30
    REMAINING=1385
    ---
    RHAIRFE-31
    RHAIRFE-32
    ...
"""

import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", help="Run directory containing queue.txt")
    parser.add_argument("--batch-size", type=int, default=30,
                        help="Number of keys to return (default: 30)")
    args = parser.parse_args()

    queue_file = os.path.join(args.run_dir, "queue.txt")

    if not os.path.exists(queue_file):
        print("BATCH_SIZE=0")
        print("REMAINING=0")
        print("---")
        return

    with open(queue_file, "r", encoding="utf-8") as f:
        keys = [line.strip() for line in f if line.strip()]

    batch = keys[:args.batch_size]
    remaining = keys[args.batch_size:]

    # Rewrite queue with remaining keys
    with open(queue_file, "w", encoding="utf-8") as f:
        for key in remaining:
            f.write(key + "\n")

    print(f"BATCH_SIZE={len(batch)}")
    print(f"REMAINING={len(remaining)}")
    print("---")
    for key in batch:
        print(key)


if __name__ == "__main__":
    main()
