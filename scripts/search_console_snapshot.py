#!/usr/bin/env python3
"""Weekly Search Console snapshot (ROADMAP.md item 290).

Queries Google's Search Console API for the last 28 days, by query and by page
(top 25 each, with clicks, impressions, CTR and average position) and writes
`data/search_console.json`. Authenticates with a read-only service account whose
JSON key is in the `GSC_SERVICE_ACCOUNT_JSON` secret; the owner adds that
service account's email as a Restricted user of the property. Skips quietly when
the secret is missing, and a failed fetch never overwrites the last good file.
The API returns aggregates only, so nothing about an individual is stored.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = ROOT / "data" / "search_console.json"
SITE_CANDIDATES = ("sc-domain:withintenmiles.com", "https://withintenmiles.com/")
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
ROW_LIMIT = 25

logger = logging.getLogger("search_console_snapshot")


def access_token(service_account_info: dict) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(service_account_info, scopes=[SCOPE])
    creds.refresh(Request())
    return creds.token


def _query(token: str, site: str, body: dict) -> list[dict]:
    resp = requests.post(
        f"https://www.googleapis.com/webmasters/v3/sites/{quote(site, safe='')}/searchAnalytics/query",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("rows") or []


def shape_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "key": (r.get("keys") or [""])[0],
            "clicks": int(r.get("clicks") or 0),
            "impressions": int(r.get("impressions") or 0),
            "ctr": round(float(r.get("ctr") or 0), 4),
            "position": round(float(r.get("position") or 0), 1),
        }
        for r in rows
    ]


def build_snapshot(token: str, today: date, *, query=_query, sites=SITE_CANDIDATES) -> dict:
    # Search Console data lags by about two days.
    end = today - timedelta(days=2)
    start = end - timedelta(days=27)
    last_error: Exception | None = None
    for site in sites:
        try:
            base = {"startDate": start.isoformat(), "endDate": end.isoformat(), "rowLimit": ROW_LIMIT}
            queries = query(token, site, {**base, "dimensions": ["query"]})
            pages = query(token, site, {**base, "dimensions": ["page"]})
            return {
                "as_of": today.isoformat(),
                "property": site,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "queries": shape_rows(queries),
                "pages": shape_rows(pages),
            }
        except Exception as exc:  # noqa: BLE001 - try the next property type
            last_error = exc
            logger.info("Property %s did not answer (%s).", site, exc)
    raise RuntimeError(f"no Search Console property answered: {last_error}")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raw = os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        logger.info("GSC_SERVICE_ACCOUNT_JSON is not set; skipping the Search Console snapshot.")
        return 0
    try:
        token = access_token(json.loads(raw))
        snapshot = build_snapshot(token, datetime.now(timezone.utc).date())
    except Exception as exc:  # noqa: BLE001 - a failed fetch must not overwrite the last good file
        logger.error("Search Console snapshot failed (%s); leaving data/search_console.json as it was.", exc)
        return 1
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Wrote %s: %d queries, %d pages.", SNAPSHOT_PATH, len(snapshot["queries"]), len(snapshot["pages"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
