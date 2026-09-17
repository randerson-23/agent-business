#!/usr/bin/env python3
"""The alarm half of ROADMAP.md item 114.

send_newsletter.py now writes a positive record to
data/send_history.json on every successful Buttondown response. That
file answers "did this week's issue go out" for anyone who looks - but
nothing was looking. Today's actual failure mode (item 110's own cron
change silently dropping the occurrence it existed to protect) produced
no failing job and so no email to the owner, because there was no send
job at all in which a guard could run.

This script is that guard, run by its own scheduled workflow
(send-watchdog.yml) on a day and offset minute distinct from both
build-digest.yml's and send-newsletter.yml's crons - deliberately: a
watchdog that shares a schedule with the thing it watches would miss
exactly the failure mode that motivated it (a schedule change eating
an occurrence). It fails loudly (non-zero exit -> GitHub's own
"workflow failed" email, the same mechanism build-digest.yml already
relies on) if the newest DELIVERY_MODES record is missing or older than
MAX_SEND_GAP_DAYS - a real problem stated as itself, not inferred from
a build timestamp the way item 111 first (and wrongly) proposed.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from send_newsletter import DELIVERY_MODES, load_send_history  # noqa: E402

MAX_SEND_GAP_DAYS = 9

logger = logging.getLogger("check_send_history")


def latest_delivery(history: list[dict]) -> dict | None:
    """The most recent record whose mode is a real mail-out (`send` or
    `schedule`), not a `draft` sitting unsent in Buttondown - a draft
    nobody sent shouldn't read as "the newsletter went out". Returns
    None if there is no such record at all.
    """
    deliveries = [r for r in history if r.get("mode") in DELIVERY_MODES]
    if not deliveries:
        return None
    return max(deliveries, key=lambda r: r["timestamp"])


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    history = load_send_history()
    latest = latest_delivery(history)
    if latest is None:
        logger.error(
            "No delivery (mode 'send' or 'schedule') recorded in data/send_history.json "
            "at all - either the newsletter has never gone out through this pipeline, or "
            "every record is a stale draft. Investigate before assuming this is fine."
        )
        return 1

    sent_at = datetime.fromisoformat(latest["timestamp"])
    age = datetime.now(timezone.utc) - sent_at
    if age > timedelta(days=MAX_SEND_GAP_DAYS):
        logger.error(
            "Last delivery was %s ago (older than %d days): %r on %s. "
            "The weekly send may have silently failed to run - check "
            "send-newsletter.yml's recent workflow runs.",
            age, MAX_SEND_GAP_DAYS, latest.get("subject", "?"), latest["timestamp"],
        )
        return 1

    logger.info(
        "OK: last delivery %s ago - %r (%s), Buttondown id %s.",
        age, latest.get("subject", "?"), latest["timestamp"], latest.get("buttondown_id", "?"),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
