#!/usr/bin/env python3
"""The alarm half of ROADMAP.md item 199.

The forty-seventh research pass found /today/ headlined "Tuesday,
September 22" while read on a Friday - build-digest.yml's only cron was
weekly (item 168, correct for the weekend digest but wrong for a page
that is definitionally daily), and the site had been borrowing its
apparent daily freshness from the build loop's own merge commits.
Once the loop paused, nothing rebuilt and nothing noticed.

This script is that notice: it fails loudly (non-zero exit -> GitHub's
own "workflow failed" email, the same mechanism build-digest.yml and
check_send_history.py already rely on) if data/weekend_signal.json's own
`generated_at` - written by build_digest.py's write_weekend_signal() on
every real build - is missing or older than MAX_BUILD_GAP_HOURS. A real
problem stated as itself, not inferred from git history or a workflow
run list.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WEEKEND_SIGNAL_PATH = Path(__file__).resolve().parent.parent / "data" / "weekend_signal.json"

# item 199's own suggestion: "if the committed build stamp is more than
# ~36 hours old, say so in a failing check." The daily cron this item
# also adds targets a same-day rebuild, so 36 hours gives a full day's
# margin before this fires on a normal schedule slip.
MAX_BUILD_GAP_HOURS = 36

logger = logging.getLogger("check_build_freshness")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not WEEKEND_SIGNAL_PATH.exists():
        logger.error("%s does not exist - the site has apparently never built.", WEEKEND_SIGNAL_PATH)
        return 1

    try:
        signal = json.loads(WEEKEND_SIGNAL_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("Could not parse %s: %s", WEEKEND_SIGNAL_PATH, exc)
        return 1

    generated_at = signal.get("generated_at")
    if not generated_at:
        logger.error("%s has no generated_at field.", WEEKEND_SIGNAL_PATH)
        return 1

    built_at = datetime.fromisoformat(generated_at)
    age = datetime.now(timezone.utc) - built_at
    if age > timedelta(hours=MAX_BUILD_GAP_HOURS):
        logger.error(
            "Last build was %s ago (older than %d hours): %s. "
            "The site may have stopped rebuilding - check build-digest.yml's "
            "recent workflow runs.",
            age, MAX_BUILD_GAP_HOURS, generated_at,
        )
        return 1

    logger.info("OK: last build %s ago (%s).", age, generated_at)
    return 0


if __name__ == "__main__":
    sys.exit(main())
