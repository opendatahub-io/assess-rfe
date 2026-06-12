#!/usr/bin/env python3
"""Dump titles and descriptions of every issue in a Jira project to a file."""

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
import base64


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


def get_all_issues(server, user, token, project_key, batch_size=100):
    base = server.rstrip("/")
    jql = urllib.parse.quote(f"project={project_key} ORDER BY key ASC")
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
            break
        yield from issues
        if data.get("isLast", True):
            break
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="Jira project key (e.g. PROJ)")
    parser.add_argument("-o", "--output-dir", default=None,
                        help="Output directory (default: /tmp/rfe-assess/<PROJECT>/)")
    parser.add_argument("-s", "--server", default=os.environ.get("JIRA_SERVER") or os.environ.get("JIRA_URL") or os.environ.get("JIRA_BASE_URL"),
                        help="Jira server URL (or set JIRA_SERVER/JIRA_URL/JIRA_BASE_URL env var)")
    parser.add_argument("-u", "--user", default=os.environ.get("JIRA_USER") or os.environ.get("JIRA_EMAIL"),
                        help="Jira username/email (or set JIRA_USER/JIRA_EMAIL env var)")
    parser.add_argument("-t", "--token", default=os.environ.get("JIRA_TOKEN") or os.environ.get("JIRA_API_TOKEN"),
                        help="Jira API token (or set JIRA_TOKEN/JIRA_API_TOKEN env var)")
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

    count = 0
    for issue in get_all_issues(server, user, token, args.project):
        key = issue.get("key", "unknown")
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")
        description = adf_to_markdown(fields.get("description")).strip()
        filepath = os.path.join(output_dir, f"{key}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# {key}: {summary}\n\n{description}\n")
        count += 1
        if count % 100 == 0:
            print(f"  {count} issues dumped...", file=sys.stderr)

    print(f"Wrote {count} issues to {output_dir}/", file=sys.stderr)


if __name__ == "__main__":
    main()
