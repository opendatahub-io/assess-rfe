#!/usr/bin/env python3
"""Dump titles and descriptions of every issue in a Jira project to a file.

The cache directory is keyed on project alone, so a filtered dump
(``--issue-type Initiative``) writes alongside whatever an earlier unfiltered
dump of the same project left behind. setup_run.py then queues every ``.md`` it
finds, so those leftovers get scored — and since RHOAIENG holds Epics and
Stories as well as Initiatives, they are scored against the initiative rubric
and produce plausible-looking rows. By default this script therefore prunes
cached files its own fetch did not write, keeping the cache equal to the query
that produced it. Pass ``--no-prune`` to keep them.
"""

import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request


def make_request(url, user, token, body=None):
    credentials = base64.b64encode(f"{user}:{token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Accept": "application/json",
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {error_body}", file=sys.stderr)
        raise


def get_all_issues(server, user, token, project_key, batch_size=100, issue_type=None):
    base = server.rstrip("/")
    jql_str = f"project={project_key}"
    if issue_type:
        jql_str += f' AND issuetype="{issue_type}"'
    jql_str += " ORDER BY key ASC"
    jql = urllib.parse.quote(jql_str)
    next_page_token = None
    while True:
        url = (
            f"{base}/rest/api/3/search/jql"
            f"?jql={jql}"
            f"&maxResults={batch_size}"
            f"&fields=summary,description"
        )
        if next_page_token:
            url += f"&nextPageToken={urllib.parse.quote(next_page_token)}"
        data = make_request(url, user, token)
        issues = data.get("issues", [])
        if not issues:
            if data.get("isLast") is True:
                break
            raise RuntimeError(
                "Jira pagination ended before completion: received an empty page "
                "without isLast=true; existing cache was not pruned"
            )
        yield from issues
        if data.get("isLast") is True:
            break
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            raise RuntimeError(
                "Jira pagination ended before completion: nextPageToken is missing "
                "while isLast is not true; existing cache was not pruned"
            )


def adf_to_markdown(node, list_depth=0):
    """Convert Atlassian Document Format (ADF) JSON to markdown."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node

    if isinstance(node, list):
        return "".join(adf_to_markdown(item, list_depth) for item in node)

    if not isinstance(node, dict):
        return ""

    node_type = node.get("type", "")
    content = node.get("content", [])
    attrs = node.get("attrs", {})

    if node_type == "doc":
        return adf_to_markdown(content, list_depth)

    if node_type == "text":
        text = node.get("text", "")
        for mark in node.get("marks", []):
            mark_type = mark.get("type", "")
            if mark_type == "strong":
                text = f"**{text}**"
            elif mark_type == "em":
                text = f"*{text}*"
            elif mark_type == "code":
                text = f"`{text}`"
            elif mark_type == "strike":
                text = f"~~{text}~~"
            elif mark_type == "link":
                href = mark.get("attrs", {}).get("href", "")
                text = f"[{text}]({href})"
        return text

    if node_type == "paragraph":
        inner = adf_to_markdown(content, list_depth)
        return f"{inner}\n\n"

    if node_type == "heading":
        level = attrs.get("level", 1)
        inner = adf_to_markdown(content, list_depth)
        return f"{'#' * level} {inner}\n\n"

    if node_type == "bulletList":
        items = adf_to_markdown(content, list_depth)
        return f"{items}\n" if list_depth == 0 else items

    if node_type == "orderedList":
        result = []
        for idx, item in enumerate(content, 1):
            item_text = adf_to_markdown(item.get("content", []), list_depth + 1).strip()
            indent = "  " * list_depth
            result.append(f"{indent}{idx}. {item_text}\n")
        return "".join(result) + ("\n" if list_depth == 0 else "")

    if node_type == "listItem":
        item_parts = []
        for child in content:
            child_type = child.get("type", "")
            if child_type in ("bulletList", "orderedList"):
                item_parts.append(adf_to_markdown(child, list_depth + 1))
            else:
                item_parts.append(adf_to_markdown(child, list_depth).strip())
        indent = "  " * list_depth
        first = item_parts[0] if item_parts else ""
        rest = "".join(item_parts[1:])
        return f"{indent}- {first}\n{rest}"

    if node_type == "codeBlock":
        lang = attrs.get("language", "")
        inner = adf_to_markdown(content, list_depth)
        return f"```{lang}\n{inner}\n```\n\n"

    if node_type == "blockquote":
        inner = adf_to_markdown(content, list_depth)
        lines = inner.strip().split("\n")
        quoted = "\n".join(f"> {line}" for line in lines)
        return f"{quoted}\n\n"

    if node_type == "rule":
        return "---\n\n"

    if node_type == "table":
        rows = []
        for row_node in content:
            if row_node.get("type") == "tableRow":
                cells = []
                for cell in row_node.get("content", []):
                    cell_text = adf_to_markdown(cell.get("content", []), list_depth).strip()
                    cell_text = cell_text.replace("\n", " ")
                    cells.append(cell_text)
                rows.append(cells)
        if not rows:
            return ""
        col_count = max(len(r) for r in rows)
        lines = []
        for i, row in enumerate(rows):
            row += [""] * (col_count - len(row))
            lines.append("| " + " | ".join(row) + " |")
            if i == 0:
                lines.append("| " + " | ".join(["---"] * col_count) + " |")
        return "\n".join(lines) + "\n\n"

    if node_type == "mediaSingle" or node_type == "media":
        return ""

    if node_type == "hardBreak":
        return "\n"

    if node_type == "inlineCard":
        url = attrs.get("url", "")
        return f"[{url}]({url})" if url else ""

    if node_type == "emoji":
        return attrs.get("text", attrs.get("shortName", ""))

    if node_type == "panel":
        inner = adf_to_markdown(content, list_depth)
        return f"> {inner.strip()}\n\n"

    if node_type == "expand":
        title = attrs.get("title", "")
        inner = adf_to_markdown(content, list_depth)
        header = f"**{title}**\n\n" if title else ""
        return f"{header}{inner}"

    # Fallback: recurse into content
    return adf_to_markdown(content, list_depth)


def prune_stale(output_dir, written, owned):
    """Remove cached .md files this fetch did not write.

    ``owned`` is False for a user-supplied --output-dir; that directory is
    reported on but never deleted from, since this script did not choose it.
    """
    stale = sorted(
        f for f in os.listdir(output_dir) if f.endswith(".md") and f[: -len(".md")] not in written
    )
    if not stale:
        return
    names = ", ".join(stale[:10])
    more = f" (+{len(stale) - 10} more)" if len(stale) > 10 else ""
    if not owned:
        print(
            f"WARNING: {len(stale)} file(s) in {output_dir} are not part of this fetch and "
            f"will still be queued for assessment: {names}{more}",
            file=sys.stderr,
        )
        print("  Remove them, or drop --output-dir to let this script prune.", file=sys.stderr)
        return
    for name in stale:
        os.remove(os.path.join(output_dir, name))
    print(f"Pruned {len(stale)} file(s) left by an earlier dump: {names}{more}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="Jira project key (e.g. PROJ)")
    parser.add_argument(
        "-o",
        "--output-dir",
        default=None,
        help="Output directory (default: /tmp/rfe-assess/<PROJECT>/)",
    )
    default_server = (
        os.environ.get("JIRA_SERVER")
        or os.environ.get("JIRA_URL")
        or os.environ.get("JIRA_BASE_URL")
    )
    default_user = os.environ.get("JIRA_USER") or os.environ.get("JIRA_EMAIL")
    default_token = os.environ.get("JIRA_TOKEN") or os.environ.get("JIRA_API_TOKEN")
    parser.add_argument(
        "-s",
        "--server",
        default=default_server,
        help="Jira server URL (or set JIRA_SERVER env var)",
    )
    parser.add_argument(
        "-u",
        "--user",
        default=default_user,
        help="Jira username/email (or set JIRA_USER env var)",
    )
    parser.add_argument(
        "-t",
        "--token",
        default=default_token,
        help="Jira API token (or set JIRA_TOKEN env var)",
    )
    parser.add_argument(
        "--issue-type",
        default=None,
        help="Filter by issue type (e.g. Initiative)",
    )
    parser.add_argument(
        "--no-prune",
        action="store_true",
        help="Keep cached issue files this fetch did not write (default: remove them)",
    )
    args = parser.parse_args()

    server = args.server
    user = args.user
    token = args.token

    if not all([server, user, token]):
        print("Error: Jira server, user, and token are required.", file=sys.stderr)
        print("Set JIRA_SERVER, JIRA_USER, JIRA_TOKEN env vars or use flags.", file=sys.stderr)
        sys.exit(1)

    output_dir = args.output_dir or os.path.join("/tmp/rfe-assess", args.project)
    os.makedirs(output_dir, exist_ok=True)

    written = set()
    count = 0
    for issue in get_all_issues(server, user, token, args.project, issue_type=args.issue_type):
        key = issue.get("key", "unknown")
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")
        description = adf_to_markdown(fields.get("description")).strip()
        filepath = os.path.join(output_dir, f"{key}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# {key}: {summary}\n\n{description}\n")
        written.add(key)
        count += 1
        if count % 100 == 0:
            print(f"  {count} issues dumped...", file=sys.stderr)

    print(f"Wrote {count} issues to {output_dir}/", file=sys.stderr)

    if args.no_prune:
        pass
    elif not written:
        # A query that returned nothing is far more likely to be a bad filter or
        # an auth blip than a genuinely empty project — never let it empty the
        # cache out from under an in-flight run.
        print(
            "No issues returned; leaving the existing cache alone. "
            "Check the project key, --issue-type, and credentials.",
            file=sys.stderr,
        )
    else:
        prune_stale(output_dir, written, owned=args.output_dir is None)


if __name__ == "__main__":
    main()
