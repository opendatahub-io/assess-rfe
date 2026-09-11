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

RFE_KEYS = ["WHAT", "WHY", "HOW", "Task", "Size"]
INITIATIVE_KEYS = ["WHAT", "WHY", "Scope", "HOW", "Size"]

RFE_MATCHERS = [
    lambda c: c.startswith("what"),
    lambda c: c.startswith("why"),
    lambda c: "how" in c and "total" not in c,
    lambda c: "task" in c,
    lambda c: "size" in c or "right" in c,
]

INITIATIVE_MATCHERS = [
    lambda c: c.startswith("what"),
    lambda c: c.startswith("why"),
    lambda c: c == "scope" or c.startswith("scope"),
    lambda c: "how" in c and "total" not in c,
    lambda c: "size" in c or "right" in c,
]


def extract_scores(text):
    """Extract scores from an assessment result text.

    Handles both RFE criteria (WHAT, WHY, HOW, Task, Size) and initiative
    criteria (WHAT, WHY, Scope, HOW, Size).

    Handles format variants:
    - | WHAT | 1/2 | notes |
    - | **WHAT** (0-2) | 2 | rationale |
    - | WHAT | -/2 | Data file not found |  (missing data → ERROR)
    - With or without a Total row (computes if missing)
    """
    lower_text = text.lower()
    if "data file not found" in lower_text or "unable to assess" in lower_text:
        if re.search(r"-\s*/\s*2", text):
            return _error_result(text)

    scores = [None] * 5
    total = pf = None

    is_initiative = _detect_initiative(text)
    matchers = INITIATIVE_MATCHERS if is_initiative else RFE_MATCHERS
    keys = INITIATIVE_KEYS if is_initiative else RFE_KEYS

    for line in text.split("\n"):
        ll = line.strip()
        if not ll.startswith("|"):
            continue

        parts = [p.strip() for p in ll.split("|")]
        if len(parts) < 3:
            continue

        criterion = parts[1].lower()
        score_cell = parts[2]

        score_m = re.search(r"(\d)\s*/\s*2", score_cell)
        if not score_m:
            score_m = re.match(r"^\s*(\d)\s*$", score_cell)
        score = int(score_m.group(1)) if score_m else None

        crit = _normalize_criterion(criterion)

        if score is not None:
            for i, matcher in enumerate(matchers):
                if scores[i] is None and matcher(crit):
                    scores[i] = score
                    break

        if "total" in criterion:
            tm = re.search(r"(\d+)\s*/\s*10", ll)
            if tm:
                total = int(tm.group(1))
            if "pass" in ll.lower():
                pf = "PASS"
            elif "fail" in ll.lower():
                pf = "FAIL"

    if total is None and all(s is not None for s in scores):
        total = sum(scores)

    if pf is None and all(s is not None for s in scores) and total is not None:
        pf = "PASS" if total >= 7 and all(s > 0 for s in scores) else "FAIL"

    if all(s is not None for s in scores) and total is not None:
        result = {"Total": total, "Pass_Fail": pf}
        for i, key in enumerate(keys):
            result[key] = scores[i]
        return result
    return None


def _normalize_criterion(cell):
    """Strip markdown decoration and range hints from a criterion label.

    ``**Scope** (0-2)`` -> ``scope``, ``**Not a task**`` -> ``not a task``.
    """
    return re.sub(r"[*_()\d/\-&]", " ", cell.lower()).strip()


def _criterion_cells(text):
    """Yield the normalized criterion (first) column of each markdown table row."""
    for line in text.split("\n"):
        ll = line.strip()
        if not ll.startswith("|"):
            continue
        parts = [p.strip() for p in ll.split("|")]
        if len(parts) < 3:
            continue
        yield _normalize_criterion(parts[1])


def _detect_initiative(text):
    """Detect whether a result uses initiative criteria.

    Both RFE and initiative rubrics use WHAT/WHY/HOW/Right-sized.
    The distinguishing criterion is Scope (initiative) vs Not a task (RFE).

    Both labels are normalized the same way the score loop normalizes them, so
    the decorated forms the docstring above advertises (``| **Scope** (0-2) |``)
    are recognized. Matching on the criterion column only — rather than any
    ``|...|`` cell — keeps a rationale that happens to start with "scope" from
    flipping an RFE result onto the initiative key set.
    """
    has_scope_row = has_task_row = False
    for criterion in _criterion_cells(text):
        if criterion.startswith("scope"):
            has_scope_row = True
        if "not a task" in criterion:
            has_task_row = True
    return has_scope_row and not has_task_row


def _error_result(text):
    """Return an ERROR result dict with the correct keys for the rubric type."""
    keys = INITIATIVE_KEYS if _detect_initiative(text) else RFE_KEYS
    result = {"Total": 0, "Pass_Fail": "ERROR"}
    for key in keys:
        result[key] = 0
    return result


def extract_title(text):
    """Extract the RFE title from result text."""
    m = re.search(r"(?:\*\*)?TITLE(?:\*\*)?:?\s*(.+)", text)
    if m:
        return m.group(1).strip().strip("*").strip()
    return ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_dir", help="Directory containing .result.md files")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output CSV path (default: <result_dir>/../<project>-scores.csv)",
    )
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
        rows.append(
            {
                "ID": key,
                "Title": title,
                **scores,
            }
        )

    # Column set = union across all rows, ordered by first appearance. Taking it
    # from rows[0] alone made a single odd row (rubric type is re-sniffed per
    # file, so a malformed one can land on the other key set) raise mid-write,
    # after the header and earlier rows had already been flushed — leaving a
    # truncated but plausible-looking scores.csv that next_action.py accepts as
    # a finished run. Widen the header instead, and say so.
    fixed = ("ID", "Title", "Total", "Pass_Fail")
    score_keys = []
    for row in rows:
        for k in row:
            if k not in fixed and k not in score_keys:
                score_keys.append(k)
    if not score_keys:
        score_keys = RFE_KEYS

    mixed = [r["ID"] for r in rows if any(k not in r for k in score_keys)]
    if mixed:
        names = ", ".join(mixed[:10])
        print(
            f"WARNING: this run mixes RFE and initiative criteria — {len(mixed)} of "
            f"{len(rows)} result(s) leave some score columns blank: {names}",
            file=sys.stderr,
        )

    fieldnames = ["ID", "Title"] + score_keys + ["Total", "Pass_Fail"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, restval="", extrasaction="ignore")
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
        names = ", ".join(failed_parse[:10])
        print(
            f"  Could not parse: {len(failed_parse)} files: {names}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
