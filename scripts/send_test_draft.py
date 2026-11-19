"""Send the per-reader email to ONE test address as a Buttondown draft (ROADMAP.md item 507).

Item 481's per-reader email (each reader's town first) is built and previewed,
but the live send keeps the shared layout until a real delivery proves that
Buttondown renders its per-subscriber conditionals the way the previews show.
This script is that test, run from CI (test-send.yml), which holds the API key:

1. create the issue as a **draft** (`status: draft`, never scheduled or sent),
   with the conditional body from docs/combined-email-conditional.html;
2. send that draft through the send-draft endpoint to ONE reader: the
   `BUTTONDOWN_TEST_RECIPIENT` secret if set, otherwise (item 532) the list's
   only subscriber, or the one tagged `owner`, by subscriber ID. Nobody else.

It never calls the live-send path: no `scheduled`/`about_to_send` status and no
live-send header. When it can't name one certain reader (several subscribers
and none tagged `owner`) it says so and exits 0. Compare what arrives with
/email-preview/<town>.html for the recipient's town tag, then record the
result in config/newsletter.yaml (`per_reader_email.verified`).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from send_newsletter import BUTTONDOWN_API_URL, BUTTONDOWN_AUTH_SCHEME, BUTTONDOWN_SUBSCRIBERS_URL, DOCS_DIR, extract_subject  # noqa: E402

logger = logging.getLogger("send_test_draft")
RECIPIENT_ENV = "BUTTONDOWN_TEST_RECIPIENT"
CONDITIONAL_PATH = DOCS_DIR / "combined-email-conditional.html"
SUBJECT_SOURCE = DOCS_DIR / "combined-email-send.html"
# The live reference names `send-draft`; Buttondown's 2024 post names `send-drafts`.
SEND_DRAFT_PATHS = ("send-draft", "send-drafts")
TEST_SUBJECT = "Per-reader email test: does this match /email-preview/<town>?"  # item 532


def draft_payload(subject: str, body: str) -> dict:
    return {"subject": TEST_SUBJECT, "body": body, "status": "draft"}


def pick_test_subscriber(api_key: str, get=requests.get) -> tuple[str | None, str]:
    """ROADMAP.md item 532: without a test-recipient secret, the test goes to a
    subscriber by **ID** (the field send-draft takes) only when that reader is
    certain: exactly one active subscriber, or one tagged `owner`. Anything
    else returns (None, reason). Never logs or returns an email address."""
    resp = get(BUTTONDOWN_SUBSCRIBERS_URL, headers={"Authorization": f"{BUTTONDOWN_AUTH_SCHEME} {api_key}"}, params={"type": "regular"}, timeout=30)
    if not resp.ok:
        return None, f"listing subscribers failed ({resp.status_code})"
    results = (resp.json() or {}).get("results") or []
    owners = [r for r in results if "owner" in (r.get("tags") or [])]
    if len(owners) == 1 and owners[0].get("id"):
        return str(owners[0]["id"]), "the subscriber tagged owner"
    if len(results) == 1 and results[0].get("id"):
        return str(results[0]["id"]), "the list's only subscriber"
    return None, f"{len(results)} subscribers and no single one tagged owner; not sending a test to an unknown reader"


def create_draft(api_key: str, subject: str, body: str, post=requests.post) -> str:
    headers = {"Authorization": f"{BUTTONDOWN_AUTH_SCHEME} {api_key}", "Content-Type": "application/json"}
    resp = post(BUTTONDOWN_API_URL, headers=headers, json=draft_payload(subject, body), timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Creating the draft failed: {resp.status_code} {resp.text[:400]}")
    email_id = (resp.json() or {}).get("id")
    if not email_id:
        raise RuntimeError("Buttondown returned no email id for the draft")
    return str(email_id)


def send_draft(api_key: str, email_id: str, recipient: str, post=requests.post) -> str:
    """Send the draft to `recipient` only. Returns the path that worked."""
    headers = {"Authorization": f"{BUTTONDOWN_AUTH_SCHEME} {api_key}", "Content-Type": "application/json"}
    last = None
    for path in SEND_DRAFT_PATHS:
        resp = post(f"{BUTTONDOWN_API_URL}/{email_id}/{path}", headers=headers, json={"recipients": [recipient]}, timeout=30)
        if resp.ok:
            return path
        last = resp
        if resp.status_code != 404:
            break
    raise RuntimeError(f"Sending the draft failed: {last.status_code} {last.text[:400]}")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    recipient = os.environ.get(RECIPIENT_ENV, "").strip()
    api_key = os.environ.get("BUTTONDOWN_API_KEY", "").strip()
    if not api_key:
        print("::notice::BUTTONDOWN_API_KEY is not set - no test draft sent.")
        return 0
    if not recipient:  # item 532: by subscriber ID, no new secret
        recipient, why = pick_test_subscriber(api_key)
        if not recipient:
            print(f"::notice::No test draft sent: {why}.")
            return 0
        logger.info("Test draft goes to %s (by subscriber ID).", why)
    body = CONDITIONAL_PATH.read_text(encoding="utf-8")
    subject = extract_subject(SUBJECT_SOURCE.read_text(encoding="utf-8"))
    email_id = create_draft(api_key, subject, body)
    path = send_draft(api_key, email_id, recipient)
    logger.info("Test draft %s sent via /%s. Compare it with /email-preview/<town>.html; reply \"matches\" (Needs Ryan step 5) to turn the per-reader email on.", email_id, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
