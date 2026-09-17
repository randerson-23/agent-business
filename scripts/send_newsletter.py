#!/usr/bin/env python3
"""Push the built weekly digest to Buttondown (ROADMAP.md Phase 11 #24/#31).

Reads the already-built `docs/<region-id>/email-send.html` - item 91's
annotation-free artifact, which exists precisely so an automated paste
can't ship the "PREVIEW ONLY" row the way a human copy-paste once did -
and creates an email in Buttondown from it. `send.region: "combined"`
reads `docs/combined-email-send.html` instead - the all-regions issue
(item 105), the fix for a real defect: Buttondown's free-plan list has
no per-region segmentation, so mailing one region's digest meant every
subscriber from every OTHER region's signup form got the wrong town's
weekend.

Two things this deliberately does NOT do:

- **It does not build.** It reads what `build_digest.py` already wrote.
  Building and sending in one process would make a partial build
  sendable; keeping them separate means the workflow can build, inspect
  the exit code, and only then send.
- **It does not decide whether to send.** `config/newsletter.yaml`'s
  `send.mode` does: `draft` creates the email in Buttondown and stops,
  `send` mails it immediately, `schedule` creates it with a future
  `publish_date` and lets Buttondown hold and deliver it (item 110 -
  see next paragraph for why). It shipped on `draft` (an email cannot be
  unsent, and this pipeline had just shipped a wrong subject line - item
  90), the owner set it to `send` the same day on the grounds that he
  was the only subscriber, and it moved to `schedule` once item 110
  found that reasoning didn't touch the actual problem the researched
  Thursday-morning slot exists to solve.

Why `schedule` exists (ROADMAP.md item 110): GitHub documents scheduled
Actions runs as best-effort, and this repo's own history proved it -
`build-digest.yml`'s weekly cron fired 5h27m to 6h54m late, three times
out of three measured. A workflow that runs "sometime Thursday
afternoon" cannot deliver "Thursday morning." `schedule` mode stops
asking GitHub Actions to be punctual and asks it only to run *sometime*
in a multi-hour window before the real target time, handing the actual
delivery moment to Buttondown, which is designed to hold a scheduled
send precisely. See send-newsletter.yml's cron comment for the other
half of this: it now fires the night before.

API shape note: the endpoint and field names below could not be verified
from the build sandbox (outbound HTTP is blocked by the egress proxy), so
they are stated once, here, rather than scattered - and any API error is
surfaced verbatim rather than swallowed, so a wrong guess is loud and
obvious on the first run rather than silent. That applies doubly to
`publish_date`/`STATUS_SCHEDULED` below: unlike `about_to_send` and its
confirmation header, which were confirmed against a real API response,
the scheduling shape is this session's best-documented guess and has
never been tried against the live API - the first `schedule`-mode run
is the actual test.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
NEWSLETTER_CONFIG = REPO_ROOT / "config" / "newsletter.yaml"

# Buttondown API v1. See the module docstring: unverified from here.
BUTTONDOWN_API_URL = "https://api.buttondown.com/v1/emails"
BUTTONDOWN_AUTH_SCHEME = "Token"
# Buttondown's status for "created but not sent" vs "send this now" vs
# "send it, but later, at a time Buttondown itself holds" (item 110).
STATUS_DRAFT = "draft"
STATUS_SEND = "about_to_send"
STATUS_SCHEDULED = "scheduled"
# Buttondown refuses an `about_to_send` email unless this header is
# present, deliberately: it is the interlock that stops a first API
# experiment from mailing a real list. Their error says it is "only
# required once per API key", but it is sent on every live send anyway -
# tracking which keys have been blessed would be state this script has no
# business keeping, and the header is harmless once accepted. It is NOT
# sent for drafts, which do not need it and should not imply a send. Also
# not sent for `scheduled`: it isn't an immediate send, and this is exactly
# the unverified-from-here guess the module docstring warns about - a real
# 400 on the first scheduled run would say if that's wrong.
LIVE_SEND_HEADER = "X-Buttondown-Live-Dangerously"

# ROADMAP.md item 110: the researched send slot is Thursday 07:00 Central,
# not "whenever GitHub's cron happens to fire" - this is the local weekday/
# hour `schedule` mode targets. America/Chicago (not a fixed UTC offset) so
# `next_thursday_morning()` gets CDT/CST right automatically across the
# November/March transitions.
SEND_TIMEZONE = ZoneInfo("America/Chicago")
SEND_WEEKDAY = 3  # Monday=0 .. Thursday=3, per datetime.weekday()
SEND_HOUR = 7

# ROADMAP.md item 111: a scheduled Actions run can be silently dropped
# under load, producing no job and no failure email - the one failure mode
# "a failing job emails the owner" cannot catch. A `docs/feed.xml` whose
# <lastBuildDate> is this old is the cheapest signal available that the
# regular rebuild didn't happen, without standing up separate monitoring.
MAX_BUILD_AGE = timedelta(days=4)

API_KEY_ENV = "BUTTONDOWN_API_KEY"

# ROADMAP.md Phase 11 #105: `send.region: "combined"` in
# config/newsletter.yaml selects the all-regions issue
# (docs/combined-email-send.html) instead of one region's own digest -
# the fix for a real defect, not a hypothetical one: the signup form is
# on every region page, but the send only ever mailed Mount Prospect's,
# so anyone who subscribed from another region's page got the wrong
# town's weekend.
COMBINED_REGION = "combined"

logger = logging.getLogger("send_newsletter")


class SendError(RuntimeError):
    """Anything that should stop the send with a readable explanation."""


def load_send_config(path: Path = NEWSLETTER_CONFIG) -> dict:
    """Read the `send:` block from config/newsletter.yaml.

    Absent block means "not configured yet", which is a clean no-op
    rather than an error - the same posture load_newsletter_config()
    takes toward an unconfigured Buttondown username.
    """
    if not path.exists():
        raise SendError(f"No newsletter config at {path}")
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    send_cfg = cfg.get("send") or {}
    region = (send_cfg.get("region") or "").strip()
    mode = (send_cfg.get("mode") or STATUS_DRAFT).strip().lower()
    if mode not in {"draft", "send", "schedule"}:
        raise SendError(
            f"config send.mode must be 'draft', 'send', or 'schedule', got {mode!r}"
        )
    return {
        "enabled": bool(send_cfg.get("enabled")),
        "region": region,
        "mode": mode,
    }


def extract_subject(html: str) -> str:
    """Pull the generated subject line out of the built email's <title>.

    build_email_subject_line() already computed it; re-deriving it here
    would let the two drift. The comment block at the top of
    email_digest.html.j2 mentions "<title>" in prose, so comments are
    stripped before matching - a naive regex picks up the prose mention
    and returns most of the file.
    """
    without_comments = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    matches = re.findall(r"<title>(.*?)</title>", without_comments, re.S)
    if len(matches) != 1:
        raise SendError(f"Expected exactly one <title>, found {len(matches)}")
    subject = unescape(matches[0]).strip()
    if not subject or "\n" in subject:
        raise SendError(f"Unusable subject line: {subject!r}")
    return subject


def read_built_email(region_id: str, docs_dir: Path = DOCS_DIR) -> tuple[str, str]:
    """Return (subject, html) from the built email-send.html - the
    combined, all-regions issue when `region_id` is the `COMBINED_REGION`
    sentinel, one region's own digest otherwise.
    """
    if region_id == COMBINED_REGION:
        path = docs_dir / "combined-email-send.html"
    else:
        path = docs_dir / region_id / "email-send.html"
    if not path.exists():
        raise SendError(
            f"No built email at {path} - run scripts/build_digest.py first"
        )
    html = path.read_text(encoding="utf-8")
    # The exact annotation text both templates emit, not just "PREVIEW
    # ONLY" - a real event title/detail containing that shorter phrase
    # (e.g. a museum's own "Preview Only Weekend") would otherwise block
    # a legitimate send with a misleading error.
    if "PREVIEW ONLY, NOT PART OF THE EMAIL" in html:
        # Item 91's whole point. If this ever trips, email-send.html has
        # regressed into being a copy of email-preview.html and would
        # send the annotation as body copy.
        raise SendError(f"{path} contains the preview annotation - refusing to send")
    return extract_subject(html), html


def html_byte_size(html: str) -> int:
    """The real payload size Gmail's ~102KB clip limit applies to - UTF-8
    bytes, not `len(html)` (character count). The templates are full of
    multi-byte characters (em dashes, arrows, curly quotes) repeated per
    event/region, so character count under-counts and would silently
    miss a real oversized build as more regions/sponsors get added.
    """
    return len(html.encode("utf-8"))


def next_thursday_morning(now: datetime) -> datetime:
    """The next Thursday 07:00 America/Chicago at or after `now` (ROADMAP.md
    item 110) - the researched send slot, not "whenever this happens to
    run". `now` may be in any timezone; the comparison and the result are
    both done in SEND_TIMEZONE so a UTC `now` a few hours after local
    midnight doesn't get treated as still being the previous local day.
    """
    local_now = now.astimezone(SEND_TIMEZONE)
    days_ahead = (SEND_WEEKDAY - local_now.weekday()) % 7
    candidate = local_now.replace(hour=SEND_HOUR, minute=0, second=0, microsecond=0)
    candidate += timedelta(days=days_ahead)
    if candidate <= local_now:
        candidate += timedelta(days=7)
    return candidate


def read_build_timestamp(docs_dir: Path = DOCS_DIR) -> datetime:
    """The last real build's completion time, from `docs/feed.xml`'s
    <lastBuildDate> (written fresh by build_digest.py's build_feed_xml()
    on every run) - the cheapest signal available (ROADMAP.md item 111)
    that a build actually happened recently, without standing up separate
    monitoring for a static site.
    """
    path = docs_dir / "feed.xml"
    if not path.exists():
        raise SendError(f"No {path} - run scripts/build_digest.py first")
    match = re.search(r"<lastBuildDate>(.*?)</lastBuildDate>", path.read_text(encoding="utf-8"))
    if not match:
        raise SendError(f"{path} has no <lastBuildDate> - can't confirm the build is fresh")
    try:
        return parsedate_to_datetime(match.group(1))
    except (TypeError, ValueError) as exc:
        raise SendError(f"Unparseable <lastBuildDate> in {path}: {match.group(1)!r} ({exc})")


def assert_build_is_fresh(build_time: datetime, now: datetime, max_age: timedelta = MAX_BUILD_AGE) -> None:
    """Refuse to mail a digest older than `max_age` (ROADMAP.md item 111).

    This script always rebuilds fresh immediately before calling it (see
    send-newsletter.yml), so under the current workflow this check should
    never actually trip - it exists as insurance against exactly the
    failure mode that prompted it: a scheduled Actions run silently
    dropped rather than delayed, which produces no job and so no failure
    email either. It cannot detect that directly (nothing runs to check
    it), but it does catch anything that would otherwise let a stale
    build get mailed - a future refactor that separates build and send,
    or a manual run against a checkout whose build step didn't run as
    expected.
    """
    age = now - build_time
    if age > max_age:
        raise SendError(
            f"docs/feed.xml was last built {age} ago (older than {max_age}) - "
            "refusing to mail a possibly-stale digest. Run scripts/build_digest.py "
            "and retry, or investigate why the regular build didn't happen."
        )


def post_to_buttondown(
    subject: str, html: str, api_key: str, mode: str, *, now: datetime | None = None
) -> dict:
    """Create the email in Buttondown. Raises SendError with the API's own
    message on any non-2xx, so a wrong endpoint or a plan that gates API
    access fails loudly on the first run instead of looking like success.
    """
    payload = {"subject": subject, "body": html}
    if mode == "send":
        status = STATUS_SEND
    elif mode == "schedule":
        status = STATUS_SCHEDULED
        payload["publish_date"] = next_thursday_morning(now or datetime.now(timezone.utc)).isoformat()
    else:
        status = STATUS_DRAFT
    payload["status"] = status
    headers = {
        "Authorization": f"{BUTTONDOWN_AUTH_SCHEME} {api_key}",
        "Content-Type": "application/json",
    }
    if status == STATUS_SEND:
        headers[LIVE_SEND_HEADER] = "true"
    response = requests.post(
        BUTTONDOWN_API_URL,
        headers=headers,
        json=payload,
        timeout=30,
    )
    if not response.ok:
        raise SendError(
            f"Buttondown returned {response.status_code}: {response.text[:600]}"
        )
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text[:600]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and validate the built email, print what would be sent, "
        "and make no network call.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        cfg = load_send_config()
    except SendError as exc:
        logger.error("%s", exc)
        return 1

    if not cfg["enabled"]:
        logger.info("send.enabled is false in config/newsletter.yaml - nothing to do.")
        return 0
    if not cfg["region"]:
        logger.error("send.region is not set in config/newsletter.yaml.")
        return 1

    try:
        subject, html = read_built_email(cfg["region"])
    except SendError as exc:
        logger.error("%s", exc)
        return 1

    now = datetime.now(timezone.utc)
    try:
        assert_build_is_fresh(read_build_timestamp(), now)
    except SendError as exc:
        logger.error("%s", exc)
        return 1

    # The banner comes first and names the outcome, not the setting. An
    # earlier version printed "Mode: send" directly above "Dry run - no
    # request made", which read as a successful send in the Actions log
    # and cost a real debugging cycle.
    # `banner_verb` stays shouty for the LIVE banner; `plain_verb` is the
    # lowercase phrasing the dry-run completion message uses - built
    # separately rather than by calling .lower() on banner_verb, which
    # would also mangle the ISO timestamp's "T" separator in schedule mode.
    if cfg["mode"] == "send":
        banner_verb, plain_verb = "SEND to every subscriber", "send"
    elif cfg["mode"] == "schedule":
        scheduled_for = next_thursday_morning(now).isoformat()
        banner_verb, plain_verb = f"SCHEDULE for {scheduled_for}", f"schedule for {scheduled_for}"
    else:
        banner_verb, plain_verb = "create a DRAFT in Buttondown", "create the draft"
    if args.dry_run:
        logger.info("=== DRY RUN - validating only, no email will be created ===")
    else:
        logger.info("=== LIVE: this will %s ===", banner_verb)
    html_bytes = html_byte_size(html)
    logger.info("Region:  %s", cfg["region"])
    logger.info("Subject: %s", subject)
    logger.info("Size:    %d bytes", html_bytes)
    logger.info("Configured mode: %s", cfg["mode"])

    # Gmail clips HTML email over ~102KB. The template is ~6KB, so this is
    # a guard against a future regression, not a live concern.
    if html_bytes > 102_000:
        logger.warning("Email exceeds ~102KB and will be clipped by Gmail.")

    if args.dry_run:
        logger.info(
            "Dry run complete - nothing was created or sent. Re-run with the "
            "'dry run' box UNTICKED to actually %s.",
            plain_verb,
        )
        return 0

    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        logger.error(
            "%s is not set. Add it as a repository secret; without it there is "
            "nothing to authenticate with.",
            API_KEY_ENV,
        )
        return 1

    try:
        result = post_to_buttondown(subject, html, api_key, cfg["mode"], now=now)
    except SendError as exc:
        logger.error("%s", exc)
        return 1
    except requests.RequestException as exc:
        logger.error("Network error talking to Buttondown: %s", exc)
        return 1

    if cfg["mode"] == "send":
        logger.info("Sent. Buttondown id: %s", result.get("id", "?"))
    elif cfg["mode"] == "schedule":
        logger.info(
            "Scheduled for %s. Buttondown id: %s",
            next_thursday_morning(now).isoformat(),
            result.get("id", "?"),
        )
    else:
        logger.info(
            "Draft created (id: %s). Open Buttondown and send it when it looks right.",
            result.get("id", "?"),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
