#!/usr/bin/env python3
"""Parse RFE assessment result files and produce a scores CSV.

Reads individual .result.md files from the assessment directory,
extracts scores handling all known format variants, and writes a CSV.
"""

import argparse
import csv
import os
import re
import sys


def extract_scores(text):
    """Extract scores from an assessment result text.

    Handles variants:
    - | WHAT | 1/2 | notes |
    - | **WHAT** (0-2) | 2 | rationale |
    - | WHAT | -/2 | Data file not found |  (missing data → ERROR)
    - With or without a Total row (computes if missing)
    """
    # Detect "data file not found" / "unable to assess" results early.
    # These are written by agents that couldn't find their input data file.
    lower_text = text.lower()
    if "data file not found" in lower_text or "unable to assess" in lower_text:
        if re.search(r"-\s*/\s*2", text):
            return {"WHAT": 0, "WHY": 0, "HOW": 0, "Task": 0, "Size": 0,
                    "Total": 0, "Pass_Fail": "ERROR"}

    what = why = how = task = size = total = pf = None

    for line in text.split("\n"):
        ll = line.strip()
        if not ll.startswith("|"):
            continue

        parts = [p.strip() for p in ll.split("|")]
        if len(parts) < 3:
            continue

        criterion = parts[1].lower()
        score_cell = parts[2]

        # Extract score from cell: N/2 or bare digit
        score_m = re.search(r"(\d)\s*/\s*2", score_cell)
        if not score_m:
            score_m = re.match(r"^\s*(\d)\s*$", score_cell)
        score = int(score_m.group(1)) if score_m else None

        # Clean criterion for matching
        crit = re.sub(r"[*_()\d/\-]", " ", criterion).strip().lower()

        if score is not None:
            if crit.startswith("what") and what is None:
                what = score
            elif crit.startswith("why") and why is None:
                why = score
            elif "how" in crit and "total" not in crit and how is None:
                how = score
            elif "task" in crit and task is None:
                task = score
            elif ("size" in crit or "right" in crit) and size is None:
                size = score

        # Total row
        if "total" in criterion:
            tm = re.search(r"(\d+)\s*/\s*10", ll)
            if tm:
                total = int(tm.group(1))
            if "pass" in ll.lower():
                pf = "PASS"
            elif "fail" in ll.lower():
                pf = "FAIL"

    # Compute total if missing
    if total is None and all(x is not None for x in [what, why, how, task, size]):
        total = what + why + how + task + size

    # Determine pass/fail if missing
    if pf is None and all(x is not None for x in [what, why, how, task, size, total]):
        pf = (
            "PASS"
            if total >= 7 and what > 0 and why > 0 and how > 0 and task > 0 and size > 0
            else "FAIL"
        )

    if all(x is not None for x in [what, why, how, task, size, total]):
        return {"WHAT": what, "WHY": why, "HOW": how, "Task": task, "Size": size,
                "Total": total, "Pass_Fail": pf}
    return None


def extract_title(text):
    """Extract the RFE title from result text."""
    m = re.search(r"(?:\*\*)?TITLE(?:\*\*)?:?\s*(.+)", text)
    if m:
        return m.group(1).strip().strip("*").strip()
    return ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_dir",
                        help="Directory containing .result.md files")
    parser.add_argument("-o", "--output", default=None,
                        help="Output CSV path (default: <result_dir>/../<project>-scores.csv)")
    args = parser.parse_args()

    result_dir = args.result_dir.rstrip("/")

    # Find all result files
    result_files = sorted(
        [f for f in os.listdir(result_dir) if f.endswith(".result.md")],
        key=lambda f: int(re.search(r"(\d+)", f).group(1)) if re.search(r"(\d+)", f) else 0,
    )

    if not result_files:
        print(f"No .result.md files found in {result_dir}", file=sys.stderr)
        sys.exit(1)

    # Determine output path (default: scores.csv in the same directory)
    if args.output:
        output_path = args.output
    else:
        output_path = os.path.join(result_dir, "scores.csv")

    rows = []
    failed_parse = []

    for filename in result_files:
        key = filename.replace(".result.md", "")
        filepath = os.path.join(result_dir, filename)

        with open(filepath, encoding="utf-8") as f:
            text = f.read()

        scores = extract_scores(text)
        if scores is None:
            failed_parse.append(key)
            continue

        title = extract_title(text)
        rows.append({
            "ID": key,
            "Title": title,
            **scores,
        })

    # Write CSV
    fieldnames = ["ID", "Title", "WHAT", "WHY", "HOW", "Task", "Size", "Total", "Pass_Fail"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    passed = sum(1 for r in rows if r["Pass_Fail"] == "PASS")
    failed = sum(1 for r in rows if r["Pass_Fail"] == "FAIL")
    errors = sum(1 for r in rows if r["Pass_Fail"] == "ERROR")
    print(f"Parsed {len(rows)} results -> {output_path}", file=sys.stderr)
    print(f"  Passed: {passed}, Failed: {failed}", file=sys.stderr)
    if errors:
        print(f"  Errors (data not found): {errors}", file=sys.stderr)
    if failed_parse:
        print(f"  Could not parse: {len(failed_parse)} files: {', '.join(failed_parse[:10])}", file=sys.stderr)


if __name__ == "__main__":
    main()
