#!/usr/bin/env python3
"""Post-compaction recovery for the bulk assessment loop.

Wired to a SessionStart ``compact`` hook (see ``hooks/hooks.json``). After
Claude Code auto-compacts the conversation, the coordinator can lose the
batch-loop state and stop early. This script re-injects that state — read
entirely from disk — so the coordinator can resume the loop without any
conversation history.

It is self-gating: if there is no in-progress bulk run (an ``assessments/<PROJ>/
current`` symlink whose target has no ``scores.csv``), it prints nothing. This
makes it a safe no-op for single-input or unrelated sessions. It always exits 0
— a SessionStart hook must never fail the session.

Usage (normally invoked by the hook, not by hand):
    python3 scripts/dispatch_context.py [--assess-dir assessments] [--cache-dir /tmp/rfe-assess]
"""

import argparse
import os
import sys

# The shared scripts live next to this file, so resolving from __file__ is correct
# whichever skill is driving the run — ${CLAUDE_SKILL_DIR} is not, since it points
# at assess-initiative in an initiative session. This is also the form next_action.py
# uses in its NEXT: lines, so the whole loop speaks one path shape.
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

LOOP_PROTOCOL = """\
Resume the bulk assessment dispatch loop. next_action.py decides what runs next
and when the run is complete — do NOT decide completion yourself, and do NOT
stop, summarize, or end your turn until it prints ACTION=done. Context
compaction is automatic and expected — ignore any "running low on context" or
"given budget" impulse and call next_action.py again.

EVERY script prints a NEXT: line with the exact command to run next. Just do
what the latest NEXT: line says — your memory of these steps may be degraded
after this compaction, so trust the script output over memory.

Loop (each command below is complete as written — run it verbatim):
1. python3 {scripts}/next_action.py {run_dir} --batch-size 30
2. ACTION=launch_wave: launch one background {agent_type} agent per key listed
   after the '---' (wave.txt is already written), then FOLLOW the NEXT: line —
   it tells you to run python3 {scripts}/wait_wave.py {run_dir} --keys-file {run_dir}/wave.txt.
   Re-run wait_wave.py while it exits 3 (its NEXT: line repeats the command);
   when it exits 0, its NEXT: line points back to step 1.
   Do NOT instead "wait for agent completion notifications" — that stalls and
   kills the run.
3. ACTION=done: the run is complete (scores.csv exists). Run
   python3 {scripts}/summarize_run.py {run_dir} and present the summary."""


def _find_active_runs(assess_dir):
    """Yield (project, run_dir) for each in-progress run (current → no scores.csv)."""
    if not os.path.isdir(assess_dir):
        return
    for project in sorted(os.listdir(assess_dir)):
        current = os.path.join(assess_dir, project, "current")
        if not os.path.islink(current):
            continue
        target = os.path.join(assess_dir, project, os.readlink(current))
        if os.path.isdir(target) and not os.path.exists(os.path.join(target, "scores.csv")):
            yield project, os.path.abspath(target)


def _counts(project, run_dir, cache_dir):
    completed = len([f for f in os.listdir(run_dir) if f.endswith(".result.md")])
    project_cache = os.path.join(cache_dir, project)
    total = 0
    if os.path.isdir(project_cache):
        total = len([f for f in os.listdir(project_cache) if f.endswith(".md")])
    queue_file = os.path.join(run_dir, "queue.txt")
    queued = 0
    if os.path.exists(queue_file):
        with open(queue_file, "r", encoding="utf-8") as f:
            queued = sum(1 for line in f if line.strip())
    return completed, total, queued


def main():
    # Imported here, not at module scope: the try/except around main() below is
    # what keeps this hook from ever failing the session, and a module-level
    # import would run outside it.
    from agent_types import agent_type_for_project

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--assess-dir",
        default=os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", "."), "assessments"),
        help="Base assessments directory (default: ./assessments)",
    )
    parser.add_argument(
        "--cache-dir",
        default="/tmp/rfe-assess",
        help="Issue cache directory (default: /tmp/rfe-assess)",
    )
    args = parser.parse_args()

    active = list(_find_active_runs(args.assess_dir))
    if not active:
        return  # No in-progress run — no-op.

    for project, run_dir in active:
        completed, total, queued = _counts(project, run_dir, args.cache_dir)
        print(f"[ASSESS-RFE RECOVERY] In-progress bulk run for {project}")
        print(f"RUN_DIR={run_dir}")
        print(f"COMPLETED={completed}")
        print(f"TOTAL={total}")
        print(f"QUEUE_REMAINING={queued}")
        print()
        print(
            LOOP_PROTOCOL.format(
                run_dir=run_dir,
                agent_type=agent_type_for_project(project),
                scripts=SCRIPTS_DIR,
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never fail the session from a hook
        print(f"dispatch_context: {exc}", file=sys.stderr)
    sys.exit(0)
