#!/usr/bin/env python3
"""Summarize an assessment run from scores.csv.

Produces: pass/fail counts, criteria averages, zero-score counts,
score distribution, what-if analysis, and near-miss failures.

Usage:
    python3 scripts/summarize_run.py assessments/RHAIRFE/20260322-143000/
    python3 scripts/summarize_run.py assessments/RHAIRFE/20260322-143000/scores.csv
"""

import argparse
import csv
import os
import sys
from collections import Counter


def load_scores(path):
    """Load scores from CSV file or directory containing scores.csv."""
    if os.path.isdir(path):
        path = os.path.join(path, "scores.csv")
    if not os.path.exists(path):
        print(f"ERROR: {path} not found", file=sys.stderr)
        sys.exit(1)

    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for col in ["WHAT", "WHY", "HOW", "Task", "Size", "Total"]:
                row[col] = int(row[col])
            rows.append(row)
    return rows


def summarize(rows):
    """Print summary analysis."""
    n = len(rows)
    if n == 0:
        print("No results to summarize.")
        return

    errors = [r for r in rows if r["Pass_Fail"] == "ERROR"]
    assessed = [r for r in rows if r["Pass_Fail"] != "ERROR"]
    passed = [r for r in assessed if r["Pass_Fail"] == "PASS"]
    failed = [r for r in assessed if r["Pass_Fail"] == "FAIL"]
    na = len(assessed)
    np, nf, ne = len(passed), len(failed), len(errors)
    rate = np / na * 100 if na > 0 else 0

    criteria = ["WHAT", "WHY", "HOW", "Task", "Size"]

    # Averages (exclude errors)
    avgs = {c: sum(r[c] for r in assessed) / na for c in criteria} if na > 0 else {c: 0 for c in criteria}
    avg_total = sum(r["Total"] for r in assessed) / na if na > 0 else 0

    # Zero counts (exclude errors)
    zeros = {c: sum(1 for r in assessed if r[c] == 0) for c in criteria}

    # Score distribution (exclude errors)
    dist = Counter(r["Total"] for r in assessed)

    # What-if: for each criterion, if zeros became 1s, how many more would pass?
    what_if = {}
    for c in criteria:
        extra_passes = 0
        for r in failed:
            if r[c] == 0:
                new_total = r["Total"] + 1
                other_zeros = sum(1 for c2 in criteria if c2 != c and r[c2] == 0)
                if new_total >= 7 and other_zeros == 0:
                    extra_passes += 1
        what_if[c] = extra_passes

    # Near-misses: failed with total >= 6 and exactly one zero
    near_misses = []
    for r in failed:
        zero_criteria = [c for c in criteria if r[c] == 0]
        if r["Total"] >= 6 and len(zero_criteria) == 1:
            near_misses.append((r["ID"], r["Title"][:60], r["Total"], zero_criteria[0]))
    near_misses.sort(key=lambda x: -x[2])

    # Output
    print(f"## Assessment Summary")
    print()
    print(f"- **Total assessed:** {na}")
    print(f"- **Passed:** {np} ({rate:.1f}%)")
    print(f"- **Failed:** {nf} ({100 - rate:.1f}%)")
    if ne > 0:
        print(f"- **Errors (data not found):** {ne}")
    print()

    print(f"### Score Distribution")
    print()
    print(f"| Score | Count | Bar |")
    print(f"|-------|-------|-----|")
    for s in range(11):
        count = dist.get(s, 0)
        bar = "#" * count
        if count > 0:
            print(f"| {s}/10  | {count:>5} | {bar} |")
    print()

    print(f"### Criteria Averages")
    print()
    print(f"| Criterion | Avg  | Zeros | Zero % |")
    print(f"|-----------|------|-------|--------|")
    for c in criteria:
        zp = zeros[c] / na * 100 if na > 0 else 0
        print(f"| {c:<9} | {avgs[c]:.2f} | {zeros[c]:>5} | {zp:>5.1f}% |")
    print(f"| **Total** | **{avg_total:.2f}** | | |")
    print()

    print(f"### What-If Analysis (if zeros became 1)")
    print()
    print(f"| Criterion | Additional passes |")
    print(f"|-----------|-------------------|")
    for c in criteria:
        if what_if[c] > 0:
            print(f"| {c:<9} | +{what_if[c]} |")
    if not any(what_if.values()):
        print(f"| (none)    | Most failures have multiple zeros |")
    print()

    if near_misses:
        print(f"### Near-Miss Failures (total >= 6, exactly one zero)")
        print()
        print(f"| ID | Title | Total | Zero on |")
        print(f"|----|-------|-------|---------|")
        for key, title, total, zero_c in near_misses[:15]:
            print(f"| {key} | {title} | {total}/10 | {zero_c} |")
        if len(near_misses) > 15:
            print(f"| ... | ({len(near_misses) - 15} more) | | |")
        print()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", help="Run directory or scores.csv path")
    args = parser.parse_args()

    rows = load_scores(args.path)
    summarize(rows)


if __name__ == "__main__":
    main()
