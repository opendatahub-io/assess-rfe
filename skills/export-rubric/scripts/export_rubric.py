#!/usr/bin/env python3
"""Export the scoring rubric from agent_prompt.md to a standalone markdown file."""

import pathlib
import sys

def main():
    script_dir = pathlib.Path(__file__).resolve().parent
    src = (script_dir / "agent_prompt.md").read_text()

    start = src.index("## Scoring Rubric")
    end = src.index("## Output Format")
    rubric = src[start:end].rstrip()

    out = pathlib.Path("artifacts/rfe-rubric.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "# RFE Assessment Rubric\n"
        "\n"
        "> Exported from the assess-rfe plugin. This is a read-only reference copy.\n"
        "> Source of truth: `skills/assess-rfe/scripts/agent_prompt.md` in the assess-rfe plugin.\n"
        "\n"
        + rubric
        + "\n"
    )
    print(f"Wrote {out.resolve()}")

if __name__ == "__main__":
    main()
