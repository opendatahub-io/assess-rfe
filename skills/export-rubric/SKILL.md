---
name: export-rubric
description: Export the assess-rfe scoring rubric to artifacts/rfe-rubric.md in the current working directory.
allowed-tools: Read, Write, Bash
---

## Usage
```
/export-rubric
```

## Instructions

### Skill Directory

All scripts are bundled in the `scripts/` subdirectory next to this SKILL.md. Use `${CLAUDE_SKILL_DIR}` (the directory containing this file) as the base for all script and file references.

### Steps

1. Run `python3 ${CLAUDE_SKILL_DIR}/scripts/export_rubric.py` from the current working directory.
2. Confirm the file was written and print its path.

### Required Permissions

Add to your user or project `.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "Bash(python3 <SKILL_PATH>/scripts/export_rubric.py:*)"
    ]
  }
}
```

`<SKILL_PATH>` is a placeholder for the absolute path to the `skills/export-rubric/` directory in this plugin.
