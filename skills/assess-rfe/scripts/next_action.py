#!/usr/bin/env python3
"""Authoritative driver for the bulk assessment loop.

This is the single source of truth for *what runs next* and *when the run is
done* — computed entirely from disk on every call, so it is correct regardless
of what the coordinator remembers (or forgot after a context compaction). It
replaces the coordinator-owned control flow (next_batch.py + a manual
completion check + a manual parse_results call), which let the model decide it
was "done" and stop early — sometimes before the final parse, leaving no
``scores.csv``.

The coordinator's loop collapses to a dumb crank: call this script, do what it
says, repeat until it prints ``ACTION=done``. The model never decides
completion; this script does.

Pending work is derived from disk truth, not a mutable queue: the target key
set is ``queue.txt`` (written by setup_run.py — the full set this run must
assess, possibly a ``--limit`` subset), and a key is *done* when its
``<key>.result.md`` exists. ``pending = [k in queue.txt without a result file]``.
Because this is recomputed every call, a key whose agent died (no result file)
simply reappears in a later wave instead of being silently dropped — no separate
"popped but unfinished" recovery step is needed.

When no pending keys remain, this script runs parse_results.py itself to produce
``scores.csv`` and only then reports ``ACTION=done``. If the parse fails to
produce ``scores.csv`` it exits non-zero rather than reporting done, so the
coordinator never terminates on an incomplete run.

Exit codes:
    0  action computed and printed (launch_wave or done)
    1  error (bad run dir, nothing to do, or parse failed)

Usage:
    python3 scripts/next_action.py /path/to/run_dir
    python3 scripts/next_action.py /path/to/run_dir --batch-size 30

Output (stdout) — launch_wave:
    ACTION=launch_wave
    WAVE_SIZE=30
    PENDING=85
    COMPLETED=1980
    TOTAL=2065
    ---
    RHAIRFE-2399
    RHAIRFE-2401
    ...

Output (stdout) — done:
    ACTION=done
    COMPLETED=2065
    TOTAL=2065
    SCORES_CSV=/path/to/run_dir/scores.csv
"""

import argparse
import os
import subprocess
import sys

from agent_types import agent_type_for_project


def _read_keys(path):
    """Read keys from a file, one per line. Returns [] if missing."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def _completed_keys(run_dir):
    """Set of keys that already have a .result.md in the run directory."""
    return {f[: -len(".result.md")] for f in os.listdir(run_dir) if f.endswith(".result.md")}


def _project_for_run(run_dir):
    """Jira project key for a run dir (``assessments/<PROJECT>/<timestamp>``)."""
    return os.path.basename(os.path.dirname(os.path.abspath(run_dir)))


def _total_from_cache(run_dir, cache_dir):
    """Count cached issues for this run's project (for reporting only)."""
    project_cache = os.path.join(cache_dir, _project_for_run(run_dir))
    if not os.path.isdir(project_cache):
        return 0
    return len([f for f in os.listdir(project_cache) if f.endswith(".md")])


def _sibling(name):
    """Absolute path to a sibling script in this scripts/ directory."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


def _print_done(run_dir, completed, total, scores_csv):
    """Emit the done directive, including the explicit next command."""
    print("ACTION=done")
    print(f"COMPLETED={completed}")
    print(f"TOTAL={total}")
    print(f"SCORES_CSV={os.path.abspath(scores_csv)}")
    print(
        f"NEXT: run python3 {_sibling('summarize_run.py')} {os.path.abspath(run_dir)} "
        f"and present the summary; the run is complete."
    )


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run_dir", help="Run directory (contains queue.txt and .result.md files)")
    parser.add_argument(
        "--batch-size", type=int, default=30, help="Max keys per wave (default: 30)"
    )
    parser.add_argument(
        "--cache-dir",
        default="/tmp/rfe-assess",
        help="Issue cache directory, for TOTAL reporting (default: /tmp/rfe-assess)",
    )
    args = parser.parse_args()

    run_dir = args.run_dir
    if not os.path.isdir(run_dir):
        print(f"ERROR: {run_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    scores_csv = os.path.join(run_dir, "scores.csv")
    completed = _completed_keys(run_dir)
    total = _total_from_cache(run_dir, args.cache_dir)

    # Already finalized — nothing left to do.
    if os.path.exists(scores_csv):
        _print_done(run_dir, len(completed), total, scores_csv)
        return

    # Pending = target keys (queue.txt) that have no result file yet. Recomputed
    # from disk every call, so a key whose agent died reappears here next wave.
    target = _read_keys(os.path.join(run_dir, "queue.txt"))
    pending = [k for k in target if k not in completed]

    if pending:
        wave = pending[: max(args.batch_size, 1)]
        wave_file = os.path.join(run_dir, "wave.txt")
        with open(wave_file, "w", encoding="utf-8") as f:
            for key in wave:
                f.write(key + "\n")
        print("ACTION=launch_wave")
        print(f"WAVE_SIZE={len(wave)}")
        print(f"PENDING={len(pending)}")
        print(f"COMPLETED={len(completed)}")
        print(f"TOTAL={total}")
        # This NEXT: line is the authoritative instruction after a compaction —
        # the coordinator follows it over anything it remembers — so it must name
        # the scorer that matches the run's project, not always the RFE one.
        agent_type = agent_type_for_project(_project_for_run(run_dir))
        print(
            f"NEXT: launch one assess-rfe:{agent_type} background agent (model opus, "
            f"run_in_background) per key listed after '---', then immediately run: "
            f"python3 {_sibling('wait_wave.py')} {os.path.abspath(run_dir)} "
            f"--keys-file {os.path.abspath(wave_file)}  "
            f"Do NOT wait on agent completion notifications — running wait_wave.py "
            f"IS how you wait; it blocks until the wave is done on disk."
        )
        print("---")
        for key in wave:
            print(key)
        return

    # No pending keys. Finalize iff there is something to parse.
    if not completed:
        print(
            f"ERROR: no pending keys and no .result.md files in {run_dir} — run setup_run.py first",
            file=sys.stderr,
        )
        sys.exit(1)

    parse_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parse_results.py")
    result = subprocess.run([sys.executable, parse_script, run_dir])
    if result.returncode != 0 or not os.path.exists(scores_csv):
        print(
            f"ERROR: parse_results.py did not produce {scores_csv} "
            f"(exit {result.returncode}) — run NOT complete",
            file=sys.stderr,
        )
        sys.exit(1)

    _print_done(run_dir, len(completed), total, scores_csv)


if __name__ == "__main__":
    main()
