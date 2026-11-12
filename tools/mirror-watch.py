#!/usr/bin/env python3
"""Ask each GitHub mirror whether it still carries the release Skyward hands out.

Skyward's update page can send its download through one of five mirrors, and
its "is there a newer version" question through the ones that carry GitHub's
API. A mirror that quietly stops answering looks exactly like a bad network on
the phone, so this asks them all the same two questions and writes down which
one stopped.

Run by .github/workflows/mirror-watch.yml on a schedule; also usable by hand:

    python3 tools/mirror-watch.py --report mirror-report.md
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

LATEST = "https://api.github.com/repos/XQAB/skyward/releases/latest"
PROBE_BYTES = 2048
TIMEOUT = 20

# name, prefix, whether it is expected to carry the API (and not only files)
MIRRORS = [
    ("direct (GitHub)", "", True),
    ("gh-proxy.com", "https://gh-proxy.com/", True),
    ("gh-proxy.org", "https://gh-proxy.org/", True),
    ("gh-proxy.cc", "https://gh-proxy.cc/", True),
    ("ghfast.top", "https://ghfast.top/", False),
    ("github.akams.cn", "https://github.akams.cn/", False),
]


def ask(url, ranged):
    """Return (http status, body bytes, seconds) for one request."""
    headers = {"User-Agent": "skyward-mirror-watch", "Accept": "application/vnd.github+json"}
    if ranged:
        headers["Range"] = f"bytes=0-{PROBE_BYTES - 1}"
    request = urllib.request.Request(url, headers=headers)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
            body = answer.read(PROBE_BYTES if ranged else 1 << 20)
            return answer.status, body, time.monotonic() - started
    except urllib.error.HTTPError as error:
        return error.code, error.read(PROBE_BYTES), time.monotonic() - started
    except Exception as error:  # a timeout, a refused connection, a bad chain
        return 0, str(error).encode(), time.monotonic() - started


def newest_directly():
    """The newest release, asked of GitHub itself: what the asset probe targets."""
    status, body, _ = ask(LATEST, ranged=False)
    if status != 200:
        raise SystemExit(f"GitHub itself answered {status}; nothing to probe against")
    release = json.loads(body)
    build = next((a for a in release["assets"] if a["name"].endswith(".img")), None)
    if build is None:
        raise SystemExit(f"{release['tag_name']} hands out no .img; nothing to probe against")
    return release["tag_name"], build["name"], build["browser_download_url"], build["size"]


def gh(path, method="GET", payload=None):
    """Ask GitHub's own API, with the token the workflow already has."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("--file-issue needs GH_TOKEN or GITHUB_TOKEN in the environment")
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        "https://api.github.com" + path, data=body, method=method,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json", "User-Agent": "skyward-mirror-watch"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
        text = answer.read().decode()
    return json.loads(text) if text else None


def file_issue(report, failed):
    """Open one issue for this, or add a comment when something new broke."""
    repo = os.environ.get("GITHUB_REPOSITORY", "XQAB/skyward")
    fingerprint = hashlib.sha256("\n".join(sorted(failed)).encode()).hexdigest()[:12]
    marker = f"<!-- mirror-watch: {fingerprint} -->"
    body = report + "\nWhat broke:\n\n" + "\n".join(f"- {one}" for one in failed) + f"\n\n{marker}\n"

    open_issues = gh(f"/repos/{repo}/issues?labels=mirror-watch&state=open&per_page=10") or []
    if not open_issues:
        issue = gh(f"/repos/{repo}/issues", "POST", {
            "title": f"镜像站探活：{time.strftime('%Y-%m-%d', time.gmtime())} 有镜像停了",
            "body": body, "labels": ["mirror-watch"]})
        print(f"opened #{issue['number']}: {issue['html_url']}")
        return

    issue = open_issues[0]
    comments = gh(f"/repos/{repo}/issues/{issue['number']}/comments?per_page=100") or []
    last = comments[0]["body"] if comments else (issue.get("body") or "")
    if marker in last or f"mirror-watch: {fingerprint}" in last:
        print(f"#{issue['number']}: the same set is already written down; no comment")
        return
    gh(f"/repos/{repo}/issues/{issue['number']}/comments", "POST", {"body": body})
    print(f"commented on #{issue['number']}: {issue['html_url']}")


def main():
    parser = argparse.ArgumentParser(description="Probe the GitHub mirrors Skyward offers.")
    parser.add_argument("--report", help="write the table here as markdown too")
    parser.add_argument("--file-issue", action="store_true",
                        help="open or update the mirror-watch issue when something stopped")
    args = parser.parse_args()

    tag, asset, asset_url, size = newest_directly()
    print(f"probing {tag} / {asset} ({size} bytes)")

    rows = []
    failed = []
    for name, prefix, api_expected in MIRRORS:
        api_status, api_body, api_time = ask(prefix + LATEST, ranged=False)
        api_ok = api_status == 200
        api_says = ""
        if api_ok:
            try:
                api_says = json.loads(api_body)["tag_name"]
            except Exception:
                api_ok = False
                api_says = "not JSON"
        elif api_status == 0:
            api_says = api_body.decode("utf-8", "replace")[:60]

        file_status, file_body, file_time = ask(prefix + asset_url, ranged=True)
        file_ok = file_status in (200, 206) and len(file_body) >= min(PROBE_BYTES, size)

        api_verdict = ("ok" if api_ok else f"no ({api_status or 'error'}"
                       + (f": {api_says}" if api_says else "") + ")")
        file_verdict = "ok" if file_ok else f"no ({file_status or 'error'})"
        rows.append((name, api_expected, api_verdict, f"{api_time:.1f}s",
                     file_verdict, f"{file_time:.1f}s"))

        if not file_ok:
            failed.append(f"{name}: the file it hands out is unreachable")
        if api_expected and not api_ok:
            failed.append(f"{name}: carrying the API was the point, and it stopped ({api_verdict})")

    table = ["| mirror | API | file (2KB range) |", "| --- | --- | --- |"]
    for name, api_expected, api_verdict, api_time, file_verdict, file_time in rows:
        api_cell = f"{api_verdict} {api_time}" if api_expected else f"not expected · {api_verdict} {api_time}"
        table.append(f"| `{name}` | {api_cell} | {file_verdict} {file_time} |")
    report = (f"Probed against `{tag}` · `{asset}` ({size} bytes), {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}.\n\n"
              + "\n".join(table) + "\n")
    print(report)

    if args.report:
        with open(args.report, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(report)
            if failed:
                handle.write("\nWhat broke:\n\n")
                for one in failed:
                    handle.write(f"- {one}\n")

    if failed:
        print("", file=sys.stderr)
        for one in failed:
            print(one, file=sys.stderr)
        if args.file_issue:
            file_issue(report, failed)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
