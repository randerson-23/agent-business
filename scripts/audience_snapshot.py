#!/usr/bin/env python3
"""Weekly audience snapshot from GoatCounter (ROADMAP.md item 266).

Reads GoatCounter's statistics API with a read-only token and writes
`data/audience.json`: visits for the last 7 and 30 days, the top referrers, a
count of visits referred by AI assistants, outbound clicks per publisher
(`out/<hostname>` events from item 267) and sponsor-box clicks. The latest
confirmed subscriber count comes from `data/send_history.json`.

Skips quietly when `GOATCOUNTER_TOKEN` is not set, like every other optional
integration here, and never writes a file from a failed fetch, so a bad week
cannot erase the last good numbers. Aggregates only: GoatCounter records no
personal data and this stores none.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_cap import check_free_plan_cap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
AUDIENCE_PATH = ROOT / "data" / "audience.json"
SEND_HISTORY_PATH = ROOT / "data" / "send_history.json"
GOATCOUNTER_CODE = "withinten"
AI_REFERRERS = ("chatgpt.com", "perplexity.ai", "claude.ai", "gemini.google.com", "copilot.microsoft.com")

logger = logging.getLogger("audience_snapshot")


def _api(code: str, token: str, path: str, params: dict) -> dict:
    resp = requests.get(
        f"https://{code}.goatcounter.com/api/v0/{path}",
        params=params,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def summarize_hits(hits: list[dict]) -> dict:
    """Outbound clicks per publisher and sponsor-box clicks from GoatCounter's
    event rows (`path`, `count`, `event`)."""
    out: dict[str, int] = {}
    sponsor = 0
    for h in hits:
        path = str(h.get("path") or "").lstrip("/")
        count = int(h.get("count") or 0)
        if path.startswith("out/"):
            out[path[4:]] = out.get(path[4:], 0) + count
        elif path.startswith("sponsor-click-"):
            sponsor += count
    return {"outbound": dict(sorted(out.items(), key=lambda kv: -kv[1])[:20]), "sponsor_clicks": sponsor}


def count_ai_referrals(refs: list[dict]) -> int:
    total = 0
    for r in refs:
        name = str(r.get("name") or r.get("ref") or "").lower()
        if any(domain in name for domain in AI_REFERRERS):
            total += int(r.get("count") or 0)
    return total


def latest_subscriber_count(path: Path = SEND_HISTORY_PATH) -> int | None:
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for entry in reversed(history if isinstance(history, list) else []):
        count = (entry.get("metrics") or {}).get("recipients")
        if isinstance(count, int):
            return count
        count = entry.get("pre_send_subscriber_count")
        if isinstance(count, int):
            return count
    return None


def build_snapshot(code: str, token: str, today: date, *, api=_api) -> dict:
    def rng(days: int) -> dict:
        return {"start": (today - timedelta(days=days)).isoformat() + "T00:00:00Z", "end": today.isoformat() + "T23:59:59Z"}

    total7 = api(code, token, "stats/total", rng(7))
    total30 = api(code, token, "stats/total", rng(30))
    refs = (api(code, token, "stats/toprefs", {**rng(30), "limit": 20}).get("stats") or [])
    hits = (api(code, token, "stats/hits", {**rng(30), "limit": 100}).get("hits") or [])
    summary = summarize_hits(hits)
    return {
        "as_of": today.isoformat(),
        "visits_7d": int(total7.get("total") or 0),
        "visits_30d": int(total30.get("total") or 0),
        "top_referrers": [{"name": str(r.get("name") or r.get("ref") or ""), "count": int(r.get("count") or 0)} for r in refs[:10]],
        "ai_referrals_30d": count_ai_referrals(refs),
        "outbound_30d": summary["outbound"],
        "sponsor_clicks_30d": summary["sponsor_clicks"],
        "subscribers": latest_subscriber_count(),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    token = os.environ.get("GOATCOUNTER_TOKEN", "").strip()
    if not token:
        logger.info("GOATCOUNTER_TOKEN is not set; skipping the audience snapshot.")
        return 0
    today = datetime.now(timezone.utc).date()
    try:
        snapshot = build_snapshot(GOATCOUNTER_CODE, token, today)
    except Exception as exc:  # noqa: BLE001 - a failed fetch must not overwrite the last good file
        logger.error("Audience snapshot failed (%s); leaving data/audience.json as it was.", exc)
        return 1
    AUDIENCE_PATH.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    check_free_plan_cap(snapshot["subscribers"])  # ROADMAP.md item 349
    logger.info("Wrote %s: %d visits in 30 days.", AUDIENCE_PATH, snapshot["visits_30d"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
