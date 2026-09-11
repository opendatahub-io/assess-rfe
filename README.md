# assess-rfe

Claude Code plugin for assessing RFEs and Initiatives against quality criteria using structured rubrics.

## Skills

- **assess-rfe** — Score RFEs on five criteria (WHAT, WHY, Open to HOW, Not a task, Right-sized) with single-issue and bulk assessment modes
- **assess-initiative** — Score Initiatives on five criteria (WHAT, WHY, Scope, Open to HOW, Right-sized) with single-issue and bulk assessment modes
- **export-rubric** — Export the scoring rubric to a standalone markdown file

## Installation

```bash
claude plugin marketplace add opendatahub-io/skills-registry
/plugin install assess-rfe@opendatahub-skills
```

## Usage

```
/assess-rfe RHAIRFE-1234        # assess a single RFE
/assess-rfe RHAIRFE-*           # bulk assess all RFEs in the project
/assess-initiative RHOAIENG-12345   # assess a single Initiative
/assess-initiative RHOAIENG-*       # bulk assess all Initiatives in the project
/export-rubric                  # export the rubric to artifacts/rfe-rubric.md
```

## License

Apache-2.0
