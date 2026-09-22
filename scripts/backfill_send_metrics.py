#!/usr/bin/env python3
"""Backfill open/click metrics onto past sends (ROADMAP.md Phase 11 #187).

`data/send_history.json` records *that* a send happened - timestamp,
subject, region, mode, and the Buttondown id - never how it performed.
Researched what a local sponsor actually asks for before buying: not
list size, but engagement, and specifically the open rate; a publisher
who can't produce one reads as having bad numbers. `SPONSOR_KIT.md`
already makes the engagement-over-count argument well; the gap is that
the data behind it was never captured.

The Buttondown id already stored on each entry is exactly the handle
needed to ask Buttondown for that email's own stats after the fact:
`GET /v1/emails/{id}/analytics` (confirmed via Buttondown's own API
docs, not guessed - this sandbox's own network is proxy-blocked for
api.buttondown.com same as everywhere else, so the endpoint shape is
verified from documentation rather than a live call, same posture
send_newsletter.py's own module docstring already takes for its POST
endpoint).

Deliberately a separate script and workflow, not bolted onto
send_newsletter.py or send-newsletter.yml: a metrics fetch failing must
never affect a send, and the cleanest way to guarantee that is for the
two to have no shared failure path at all. This script never sends
anything and is safe to fail without touching next Thursday's issue.

Runs on a schedule (backfill-send-metrics.yml) rather than once: opens
and clicks keep accruing for days after a send, so reading them at
send time would just record a permanent zero. Each entry is backfilled
exactly once, `METRICS_BACKFILL_MIN_AGE` after it was sent, and future
runs skip anything that already has a `metrics` key.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
SEND_HISTORY_PATH = REPO_ROOT / "data" / "send_history.json"

# Buttondown API v1 - see module docstring for why this is verified from
# documentation rather than a live call.
BUTTONDOWN_EMAILS_URL = "https://api.buttondown.com/v1/emails"
BUTTONDOWN_AUTH_SCHEME = "Token"
API_KEY_ENV = "BUTTONDOWN_API_KEY"

# ROADMAP.md item 187: opens and clicks keep accruing for days after a
# send - reading them immediately would record a permanent zero for
# every entry, since this script only ever backfills a given entry
# once. A few days' wait, not "as soon as possible".
METRICS_BACKFILL_MIN_AGE = timedelta(days=3)

logger = logging.getLogger("backfill_send_metrics")


def load_send_history(path: Path = SEND_HISTORY_PATH) -> list[dict]:
    """Same load-or-fresh-start posture as send_newsletter.py's own
    load_send_history() - a missing or corrupt file reads as empty,
    not a crash.
    """
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read %s, starting fresh: %s", path, exc)
    return []


def save_send_history(history: list[dict], path: Path = SEND_HISTORY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")


def needs_backfill(entry: dict, now: datetime, min_age: timedelta = METRICS_BACKFILL_MIN_AGE) -> bool:
    """An entry is ready once it has a real Buttondown id, has no
    `metrics` recorded yet, and is old enough for opens/clicks to have
    had a chance to accrue (ROADMAP.md item 187).
    """
    if not entry.get("buttondown_id"):
        return False
    if "metrics" in entry:
        return False
    try:
        sent_at = datetime.fromisoformat(entry["timestamp"])
    except (KeyError, ValueError, TypeError):
        return False
    return now - sent_at >= min_age


def fetch_email_analytics(buttondown_id: str, api_key: str) -> dict:
    resp = requests.get(
        f"{BUTTONDOWN_EMAILS_URL}/{buttondown_id}/analytics",
        headers={"Authorization": f"{BUTTONDOWN_AUTH_SCHEME} {api_key}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def derive_metrics(analytics: dict) -> dict:
    """The handful of numbers a sponsor conversation or SPONSOR_KIT.md
    actually needs (ROADMAP.md item 187), not the full raw analytics
    payload. `recipients`/`opens`/`clicks` missing or null (e.g.
    tracking disabled in Buttondown's settings, which the API docs say
    still returns a successful response with no data) reads as 0
    rather than raising - a real, verified caveat, not this script's
    invention.
    """
    recipients = analytics.get("recipients") or 0
    opens = analytics.get("opens") or 0
    clicks = analytics.get("clicks") or 0
    metrics = {"recipients": recipients, "opens": opens, "clicks": clicks}
    if recipients:
        metrics["open_rate"] = round(opens / recipients, 4)
        metrics["click_rate"] = round(clicks / recipients, 4)
    return metrics


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        logger.error(
            "%s is not set. Add it as a repository secret; without it there is "
            "nothing to authenticate with.",
            API_KEY_ENV,
        )
        return 1

    now = datetime.now(timezone.utc)
    # Looked up by name here rather than relying on load_send_history's
    # own default parameter, which is bound once at import time - a
    # test that monkeypatches the module-level SEND_HISTORY_PATH needs
    # this call to see the new value, not the one captured when this
    # module first loaded.
    history = load_send_history(SEND_HISTORY_PATH)

    if not any(needs_backfill(entry, now) for entry in history):
        logger.info("Nothing to backfill - no send is both un-metered and old enough yet.")
        return 0

    updated = 0
    for entry in history:
        if not needs_backfill(entry, now):
            continue
        buttondown_id = entry["buttondown_id"]
        try:
            analytics = fetch_email_analytics(buttondown_id, api_key)
        except requests.RequestException as exc:
            # ROADMAP.md item 187: non-fatal by design - one send's
            # metrics failing to fetch must never block backfilling the
            # others, and must never look like the newsletter itself
            # broke (it didn't; this script never sends anything).
            logger.warning("Could not fetch analytics for %s: %s", buttondown_id, exc)
            continue
        entry["metrics"] = derive_metrics(analytics)
        updated += 1
        logger.info(
            "Backfilled metrics for %s (%s): %s",
            buttondown_id, entry.get("subject", "?"), entry["metrics"],
        )

    if updated:
        save_send_history(history, SEND_HISTORY_PATH)
        logger.info("Updated %d send(s).", updated)
    else:
        logger.info("No sends were successfully backfilled this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
