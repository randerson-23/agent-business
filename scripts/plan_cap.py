"""Warn before the list reaches Buttondown's free-plan cap (ROADMAP.md item 349).

At 80 or more subscribers, open (or update) one GitHub issue so the owner has
time to move to a paid plan; at 95 or more, also log a warning on every run.
Fail-soft: a missing token or a GitHub error is logged, never raised, so a
newsletter send is never blocked by the warning.
"""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

FREE_PLAN_LIMIT = 100
ISSUE_THRESHOLD = 80
LOG_THRESHOLD = 95
TITLE_PREFIX = "Buttondown free plan:"
BILLING_URL = "https://buttondown.com/settings/billing"


def issue_title(count: int) -> str:
    return f"{TITLE_PREFIX} {count} of {FREE_PLAN_LIMIT} subscribers"


def issue_body(count: int) -> str:
    return (
        f"The list has {count} subscribers; Buttondown's free plan stops at {FREE_PLAN_LIMIT}.\n\n"
        f"Billing and plan: {BILLING_URL}\n\n"
        "If the Meta test (ROADMAP.md item 276) is working, expect to move to the paid plan "
        "(about $9 a month as reported; check the current price) once the list nears 100.\n\n"
        "This issue is updated on each send; close it once the plan is sorted."
    )


def check_free_plan_cap(count: int | None, *, token: str | None = None, repo: str | None = None, request=requests.request) -> str | None:
    """Returns "created", "updated" or None. No-op below ISSUE_THRESHOLD."""
    if count is None or count < ISSUE_THRESHOLD:
        return None
    if count >= LOG_THRESHOLD:
        logger.warning("Buttondown free plan: %d of %d subscribers - upgrade soon (%s).", count, FREE_PLAN_LIMIT, BILLING_URL)
    token = token or os.environ.get("GITHUB_TOKEN")
    repo = repo or os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        logger.info("Plan-cap check: no GITHUB_TOKEN/GITHUB_REPOSITORY, so no issue opened (%d subscribers).", count)
        return None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    base = f"https://api.github.com/repos/{repo}/issues"
    try:
        listing = request("GET", base, headers=headers, params={"state": "open", "per_page": 50}, timeout=20)
        listing.raise_for_status()
        existing = next((i for i in listing.json() if "pull_request" not in i and str(i.get("title", "")).startswith(TITLE_PREFIX)), None)
        if existing:
            resp = request("PATCH", f"{base}/{existing['number']}", headers=headers, json={"title": issue_title(count), "body": issue_body(count)}, timeout=20)
            outcome = "updated"
        else:
            resp = request("POST", base, headers=headers, json={"title": issue_title(count), "body": issue_body(count)}, timeout=20)
            outcome = "created"
        resp.raise_for_status()
        return outcome
    except Exception as exc:  # noqa: BLE001 - a warning must never block a send
        logger.warning("Plan-cap check could not reach GitHub: %s", exc)
        return None
