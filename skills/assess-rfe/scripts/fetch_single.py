#!/usr/bin/env python3
"""Fetch a single Jira issue by key via REST API and write it to the single-assessment directory.

This is the REST API fallback for single-input mode when the MCP Atlassian
integration is unavailable. It reuses the same ADF-to-markdown conversion
as dump_jira.py.

Usage:
    python3 scripts/fetch_single.py RHAIRFE-1234

Requires JIRA_SERVER, JIRA_USER, JIRA_TOKEN environment variables.
Writes to /tmp/rfe-assess/single/{KEY}.md in the same format as dump_jira.py.
"""

import os
import sys
# Import shared helpers from dump_jira
sys.path.insert(0, os.path.dirname(__file__))
from dump_jira import make_request, adf_to_markdown


def main():
    if len(sys.argv) < 2:
        print("Usage: fetch_single.py KEY", file=sys.stderr)
        sys.exit(1)

    key = sys.argv[1]

    server = os.environ.get("JIRA_SERVER") or os.environ.get("JIRA_URL") or os.environ.get("JIRA_BASE_URL")
    user = os.environ.get("JIRA_USER") or os.environ.get("JIRA_EMAIL")
    token = os.environ.get("JIRA_TOKEN") or os.environ.get("JIRA_API_TOKEN")

    if not all([server, user, token]):
        print("ENV_OK=false")
        missing = []
        if not server:
            missing.append("JIRA_SERVER")
        if not user:
            missing.append("JIRA_USER")
        if not token:
            missing.append("JIRA_TOKEN")
        print(f"ENV_MISSING={','.join(missing)}")
        sys.exit(1)

    base = server.rstrip("/")
    url = f"{base}/rest/api/3/issue/{key}?fields=summary,description"

    try:
        data = make_request(url, user, token)
    except Exception as e:
        print(f"Error fetching {key}: {e}", file=sys.stderr)
        sys.exit(1)

    fields = data.get("fields", {})
    summary = fields.get("summary", "")
    description = adf_to_markdown(fields.get("description")).strip()

    single_dir = "/tmp/rfe-assess/single"
    os.makedirs(single_dir, exist_ok=True)
    filepath = os.path.join(single_dir, f"{key}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {key}: {summary}\n\n{description}\n")

    print(f"FILE={filepath}")
    print(f"SUMMARY={summary}")


if __name__ == "__main__":
    main()
