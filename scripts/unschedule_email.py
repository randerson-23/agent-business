#!/usr/bin/env python3
"""Take a scheduled Buttondown email back to draft (ROADMAP.md item 571).

`python scripts/unschedule_email.py <email_id>` (run by unschedule-email.yml,
which holds BUTTONDOWN_API_KEY): reads the email, refuses unless it is
`scheduled` (or already `draft`), PATCHes it to `status: draft` with
`publish_date` cleared, reads it again and fails unless it now reads `draft`.
On success the matching entry in data/send_history.json gets
`"cancelled": "<UTC time>"`, so the four-day repeat guard ignores it.

It never sends, deletes or edits content. A `sent` or `about_to_send` email
is refused with a clear message: nothing can take that back.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from send_newsletter import API_KEY_ENV, BUTTONDOWN_API_URL, BUTTONDOWN_AUTH_SCHEME, load_send_history, save_send_history  # noqa: E402

logger = logging.getLogger("unschedule_email")


class UnscheduleError(Exception):
    pass


def unschedule(email_id: str, api_key: str, get=None, patch=None) -> dict:
    get, patch = get or requests.get, patch or requests.patch
    headers = {"Authorization": f"{BUTTONDOWN_AUTH_SCHEME} {api_key}", "Content-Type": "application/json"}
    url = f"{BUTTONDOWN_API_URL}/{email_id}"
    resp = get(url, headers=headers, timeout=30)
    if not resp.ok:
        raise UnscheduleError(f"Could not read email {email_id}: {resp.status_code} {resp.text[:300]}")
    status = (resp.json() or {}).get("status")
    if status == "draft":
        return resp.json()
    if status != "scheduled":
        raise UnscheduleError(f"Email {email_id} is {status!r}, not scheduled: it can't be taken back.")
    resp = patch(url, headers=headers, json={"status": "draft", "publish_date": None}, timeout=30)
    if not resp.ok:
        raise UnscheduleError(f"Buttondown refused the change: {resp.status_code} {resp.text[:300]}")
    check = get(url, headers=headers, timeout=30)
    after = (check.json() or {}).get("status") if check.ok else None
    if after != "draft":
        raise UnscheduleError(f"Email {email_id} still reads {after!r} after the change; check Buttondown by hand.")
    return check.json()


def mark_cancelled(history: list[dict], email_id: str, when: datetime) -> bool:
    for entry in history:
        if str(entry.get("buttondown_id")) == str(email_id):
            entry["cancelled"] = when.isoformat()
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or not args[0].strip():
        logger.error("Usage: unschedule_email.py <buttondown email id>")
        return 2
    email_id = args[0].strip()
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        logger.error("%s is not set.", API_KEY_ENV)
        return 1
    try:
        unschedule(email_id, api_key)
    except (UnscheduleError, requests.RequestException) as exc:
        logger.error("%s", exc)
        return 1
    history = load_send_history()
    if mark_cancelled(history, email_id, datetime.now(timezone.utc)):
        save_send_history(history)
    logger.info("Email %s is back to draft; it will not send.", email_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
