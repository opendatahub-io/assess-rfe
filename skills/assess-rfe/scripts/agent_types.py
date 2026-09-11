#!/usr/bin/env python3
"""Single source of truth for which scorer subagent handles which Jira project.

Two scripts name the scorer in the instructions they emit: next_action.py (every
wave of the bulk loop) and dispatch_context.py (post-compaction recovery). They
must agree — telling an in-flight RHOAIENG run to launch the RFE scorer would
score initiatives against the wrong rubric.
"""

AGENT_TYPES = {
    "RHOAIENG": "initiative-scorer",
}
DEFAULT_AGENT_TYPE = "rfe-scorer"


def agent_type_for_project(project):
    """Return the scorer subagent name for a Jira project key."""
    return AGENT_TYPES.get(project, DEFAULT_AGENT_TYPE)
