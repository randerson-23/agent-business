"""Open one GitHub issue for each workflow whose last two runs failed (ROADMAP.md item 406).

Run daily by .github/workflows/workflow-watchdog.yml with the default
GITHUB_TOKEN (actions: read, issues: write). For every workflow file, if its two
most recent completed runs both failed, one issue "Workflow failing: <name>
(since <date>)" is opened or updated with the last error line; when a later run
succeeds the issue is closed. Fail-soft: a GitHub error is logged, not raised.
"""

from __future__ import annotations

import logging
import os
import sys

import requests

logger = logging.getLogger(__name__)

TITLE_PREFIX = "Workflow failing:"
API = "https://api.github.com"


def failing_since(runs: list[dict]) -> str | None:
    """`runs` newest first. The date (YYYY-MM-DD) of the oldest run in the
    current run of failures when the two most recent completed runs both
    failed, else None. A single failure, or a success on top, is not flagged."""
    done = [r for r in runs if r.get("status") == "completed" and r.get("conclusion") in ("success", "failure", "cancelled", "timed_out")]
    if len(done) < 2 or any(r["conclusion"] not in ("failure", "timed_out") for r in done[:2]):
        return None
    since = done[1]
    for r in done[2:]:
        if r["conclusion"] in ("failure", "timed_out"):
            since = r
        else:
            break
    return str(since.get("created_at") or "")[:10] or None


def issue_title(name: str, since: str) -> str:
    return f"{TITLE_PREFIX} {name} (since {since})"


def decide(workflows: dict[str, list[dict]], open_issues: list[dict]) -> dict:
    """Pure decision: {"open": [(name, since)], "close": [issue numbers]}. A workflow already
    flagged keeps its single open issue (it is updated, not duplicated)."""
    flagged = {name: since for name, runs in workflows.items() if (since := failing_since(runs))}
    close = []
    for issue in open_issues:
        title = str(issue.get("title") or "")
        if not title.startswith(TITLE_PREFIX):
            continue
        name = title[len(TITLE_PREFIX):].strip().rsplit(" (since", 1)[0].strip()
        if name not in flagged and name in workflows:
            close.append(issue["number"])
    return {"open": sorted(flagged.items()), "close": sorted(close)}


def _get(url: str, headers: dict, params: dict | None = None):
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def last_error_line(repo: str, run_id: int, headers: dict) -> str:
    try:
        jobs = _get(f"{API}/repos/{repo}/actions/runs/{run_id}/jobs", headers).get("jobs") or []
        for job in jobs:
            for step in job.get("steps") or []:
                if step.get("conclusion") == "failure":
                    return f"Failed step: {job.get('name')} / {step.get('name')}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read jobs for run %s: %s", run_id, exc)
    return "See the run for the error."


def main() -> int:
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("No GITHUB_TOKEN/GITHUB_REPOSITORY; nothing to do.")
        return 0
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    try:
        workflows = {}
        latest_failed_run = {}
        for wf in _get(f"{API}/repos/{repo}/actions/workflows", headers, {"per_page": 100}).get("workflows") or []:
            if wf.get("state") != "active" or wf["name"].lower().startswith("pages build"):
                continue
            runs = _get(f"{API}/repos/{repo}/actions/workflows/{wf['id']}/runs", headers, {"per_page": 10, "status": "completed"}).get("workflow_runs") or []
            workflows[wf["name"]] = runs
            latest_failed_run[wf["name"]] = runs[0]["id"] if runs else None
        issues = [i for i in _get(f"{API}/repos/{repo}/issues", headers, {"state": "open", "per_page": 100}) if "pull_request" not in i]
        plan = decide(workflows, issues)
        by_name = {str(i.get("title", ""))[len(TITLE_PREFIX):].strip().rsplit(" (since", 1)[0].strip(): i for i in issues if str(i.get("title", "")).startswith(TITLE_PREFIX)}
        for name, since in plan["open"]:
            body = f"The last two runs of **{name}** failed (first failure in this streak: {since}).\n\n{last_error_line(repo, latest_failed_run[name], headers)}\n\nThis issue closes by itself when a run succeeds."
            existing = by_name.get(name)
            if existing:
                requests.patch(f"{API}/repos/{repo}/issues/{existing['number']}", headers=headers, json={"title": issue_title(name, since), "body": body}, timeout=30).raise_for_status()
            else:
                requests.post(f"{API}/repos/{repo}/issues", headers=headers, json={"title": issue_title(name, since), "body": body}, timeout=30).raise_for_status()
        for number in plan["close"]:
            requests.patch(f"{API}/repos/{repo}/issues/{number}", headers=headers, json={"state": "closed", "state_reason": "completed"}, timeout=30).raise_for_status()
        print("Workflow watchdog:", plan)
    except Exception as exc:  # noqa: BLE001 - a watchdog must not fail loudly itself
        print("Workflow watchdog could not finish:", exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
