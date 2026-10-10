#!/usr/bin/env python3
"""Build the multi-region weekend/trip digest: fetch sources, tag events,
render a page per region plus a hub page listing all regions.

Usage:
    python3 scripts/build_digest.py

Designed to run unattended from a scheduled GitHub Actions workflow. Every
network call is fail-soft (see fetchers.py) so a single broken source never
blocks publication — the section just falls back to an "no live updates"
message, and the evergreen block always renders. Tagging (see tagging.py)
is best-effort in the same spirit: a missed tag never blocks a build.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import statistics
import sys
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlencode
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

import yaml
from jinja2 import Environment, FileSystemLoader
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from fetchers import FETCHERS, MAX_ITEMS_PER_SOURCE, fetch_weather, submit_indexnow  # noqa: E402
from tagging import infer_tags, is_informational, merge_default_tags, tag_display  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("build_digest")

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
REGIONS_DIR = CONFIG_DIR / "regions"
TEMPLATES_DIR = ROOT / "templates"
FONTS_DIR = ROOT / "assets" / "fonts"
OUTPUT_DIR = ROOT / "docs"
SOURCE_HEALTH_PATH = ROOT / "data" / "source_health.json"
SOURCE_HEALTH_HISTORY_LEN = 10

# ROADMAP.md item 209: item 51's health-regression exit(1) is correct
# for build-digest.yml, whose own "if: always()" commit step still
# publishes the site regardless and only relies on this exit code to
# email the owner. tests.yml runs this same pipeline against live
# external data as a "did the code crash" smoke test on every PR, with
# no such override - a village calendar genuinely going quiet for real
# (confirmed via real GitHub Actions run #189/#190's logs, not this
# sandbox's own blocked network) now fails that check on every push
# regardless of what the PR actually changed, which trains a reviewer
# to read a red "Tests" check as "probably just content, not code."
# Set only by tests.yml's smoke-test step.
SMOKE_TEST_ENV_VAR = "BUILD_DIGEST_SMOKE_TEST"


def should_exit_for_health_regression(
    regressions: list, truncated: list, newly_broken: list, smoke_test: bool
) -> bool:
    """Whether the process should exit non-zero for a content-health
    regression (ROADMAP.md item 209) - true unless `smoke_test` is
    set, since a "did the code crash" check has nothing to do with
    whether a village calendar happens to be non-empty this week.
    """
    return bool(regressions or truncated or newly_broken) and not smoke_test

# ROADMAP.md item 181 (forty-third research pass): a source that fails
# transport on *every* build since it was added never gets a single
# entry in source_health.json above - item 55's "skip a transport
# failure rather than record a misleading 0" is correct for a one-off
# failure, but taken to its extreme it means a permanently-403'd source
# gets no history at all, forever, rather than a forgiving gap. Tracked
# here as a separate file rather than folded into source_health.json's
# own per-key list, so item 55's schema and reasoning (a count history
# that is never polluted with transport-failure noise) stay untouched -
# this is an addition, not a rework.
TRANSPORT_FAILURE_PATH = ROOT / "data" / "source_transport_failures.json"

# ROADMAP.md item 194: the streak above answers "is it down right now" and
# can never see a source that fails every other build (its streak never
# passes 1, and the chronic threshold is 3). This is the trailing window the
# item asked for: for each source, one character per recent build, "1" for a
# transport failure and "0" for a success, oldest first. Kept in its own file
# so item 181's integer streaks, and everything that reads them, are
# untouched.
FAILURE_WINDOW_PATH = ROOT / "data" / "source_failure_window.json"
FAILURE_WINDOW_SIZE = 24
FLAPPING_MIN_BUILDS = 8
FLAPPING_MIN_RATE = 0.2
CONSECUTIVE_TRANSPORT_FAILURE_ALERT_THRESHOLD = 3

# ROADMAP.md item 185 (forty-fourth research pass): the streak above
# tells you a source is chronically failing transport but not *how* -
# "403 on every request" and "DNS does not resolve" currently record
# identically. A separate file, not a reworked source_transport_failures.json:
# that file already has real, committed history under its current flat
# {key: streak_int} shape, and this is an addition, not a schema
# migration of something another consumer already depends on.
TRANSPORT_FAILURE_DETAIL_PATH = ROOT / "data" / "source_transport_failure_details.json"

# ROADMAP.md item 197 (forty-sixth research pass): a page built from 22
# of 25 configured sources looks identical to one built from 25 - the
# "partial freshness degradation" failure mode, where the page stays
# technically fresh but is quietly incomplete. This file records the
# numerator/denominator of the build that just ran, so llms.txt, the
# About page and feed.xml can state a real completeness figure instead
# of the one timestamp this site currently makes do triple duty as
# "data as of," "loaded at" and "built at" all at once. A new file, not
# a migration of source_health.json's per-source counts: this is a
# single build-wide fact, not a per-source history.
SOURCE_COMPLETENESS_PATH = ROOT / "data" / "source_completeness.json"

# ROADMAP.md item 172: a small, committed JSON file (same pattern as
# source_health.json above) recording how many dated weekend events each
# region contributed to the build just finished - the signal
# send_newsletter.py reads to refuse mailing a thin issue, the same way
# it already refuses to mail a stale one via read_build_timestamp()'s
# feed.xml check. Regenerated by CI on every build, same as docs/.
WEEKEND_SIGNAL_PATH = ROOT / "data" / "weekend_signal.json"

# ROADMAP.md item 186 (forty-fourth research pass): every existing
# detector answers "is the source working?" - none answers "is the
# region producing?" Des Plaines proved the gap: four sources, zero
# transport failures, 37 items fetched, and still 0 weekend events for
# two builds running, because nothing it returns lands inside the
# Fri/Sat/Sun window. weekend_signal.json above only ever holds the
# latest build's snapshot (send_newsletter.py reads it that way on
# purpose), so a *trailing* history needs its own file - same pattern
# as source_transport_failures.json: an addition, not a rework of the
# file another consumer already depends on.
WEEKEND_HISTORY_PATH = ROOT / "data" / "weekend_signal_history.json"
WEEKEND_HISTORY_LEN = 10
ZERO_WEEKEND_ALERT_THRESHOLD = 3

DETAIL_MAX_LEN = 160

# The real domain, registered 2026-09-15 (ROADMAP.md Phase 9, item 39/46 -
# open since day one). Used for canonical links, the sitemap, llms.txt and
# every cross-region link. Kept as one constant precisely so this move cost
# one line; the github.io URL it replaced still works, because GitHub Pages
# redirects the old *.github.io path to a configured custom domain.
SITE_BASE_URL = "https://withintenmiles.com/"

# GitHub Pages reads the custom domain from a CNAME file in the published
# directory. docs/ is regenerated by CI on every build, so this has to be
# emitted by the build rather than committed once - otherwise the first
# rebuild after setup would silently drop the domain and the site would
# fall back to github.io.
CUSTOM_DOMAIN = "withintenmiles.com"
# Every region is in the Chicago area; event times are shown and serialised in it.
LOCAL_TZ = ZoneInfo("America/Chicago")

# IndexNow key (ROADMAP.md Phase 11 #72) - not a secret, just a value that
# has to match between this constant and the key file published at the
# site root (docs/<key>.txt), which is how IndexNow verifies the submitter
# actually controls the domain. Fixed rather than regenerated per build,
# same reasoning as CUSTOM_DOMAIN: a value CI re-derives differently every
# run would break its own verification. Any 8-128 char [A-Za-z0-9-] string
# works.
#
# ROADMAP.md item 265: the first key (f3b7799b..., generated with
# `secrets.token_hex(16)`) was bound by Bing while the site was still
# unverified, and every ping returned 403 UserForbiddedToAccessSite even
# with the key file live. Replaced 2026-10-10 by a key the owner generated
# in Bing Webmaster Tools -> IndexNow after verifying the site. The old key
# file keeps being published until RETIRED_INDEXNOW_KEYS_UNTIL, since
# submissions already made under it are checked against it.
INDEXNOW_KEY = "c0dde656278c4dbbad752d8e9475a255"
RETIRED_INDEXNOW_KEYS = ("f3b7799bed06aac4295ec9134d53b014",)
RETIRED_INDEXNOW_KEYS_UNTIL = date(2026, 11, 9)

# The site's real first launch (PR #1, 2026-08-26) - used for the honest
# "running since" line on /sponsor (ROADMAP.md Phase 11 #58). Fixed, not
# derived from git log at build time, so it can't silently drift if
# history is ever rewritten.
LAUNCH_DATE = date(2026, 8, 26)

# The one canonical name for this site, used everywhere a page names its
# own publisher - <title>, og:title, and every WebPage's schema.org name.
# Before this constant existed, region pages independently built a
# shortened "{region} — Weekend Planner" title while every other page
# said "Weekend & Trip Planner" - two different strings for what should
# read as one entity to a search/AI crawler (ROADMAP.md Phase 11 #22
# follow-up, entity-naming audit).
SITE_NAME = "Within Ten"

# The stable @id for the Organization entity every page's WebSite node
# references (ROADMAP.md Phase 11 #99) - defined fully once, on the
# About page, and pointed to by @id everywhere else rather than
# re-declared, the standard schema.org pattern for one entity spanning
# many pages.
ORGANIZATION_ID = SITE_BASE_URL + "about/#organization"


# ROADMAP.md item 255: Google's plain "preferred source" deeplink (no script),
# built from the one domain constant so it can never disagree with CNAME.
PREFERRED_SOURCE_URL = f"https://google.com/preferences/source?q={CUSTOM_DOMAIN}"

# ROADMAP.md item 254: after "Subscribe", the signup shows one button to open
# the reader's own inbox, chosen from the part of the address after "@". Each
# row is (button label, URL, domains). The same table is rendered into the page
# for the script, so Python (tested) and the browser cannot disagree.
WEBMAIL_PROVIDERS = (
    ("Open Gmail", "https://mail.google.com/mail/u/0/#search/from%3Abuttondown", ("gmail.com", "googlemail.com")),
    ("Open Yahoo Mail", "https://mail.yahoo.com/", ("yahoo.com", "ymail.com")),
    ("Open AOL Mail", "https://mail.aol.com/", ("aol.com",)),
    ("Open Outlook", "https://outlook.live.com/mail/0/", ("outlook.com", "hotmail.com", "live.com", "msn.com")),
    ("Open iCloud Mail", "https://www.icloud.com/mail/", ("icloud.com", "me.com", "mac.com")),
)


def webmail_provider(address: str) -> tuple[str, str] | None:
    """(button label, URL) for an email address's webmail, or None when the
    domain is not one we know. Only the part after the last "@" counts and
    case does not, so "Ann@GMAIL.com" matches and "ann@mail.yahoo.com" (not
    an address domain) does not."""
    domain = address.rsplit("@", 1)[-1].strip().lower() if "@" in address else ""
    for label, url, domains in WEBMAIL_PROVIDERS:
        if domain in domains:
            return label, url
    return None


@lru_cache(maxsize=1)
def get_template_env() -> Environment:
    """The one Jinja2 Environment every render_* function in this module
    uses. Every call site used to build its own with identical arguments
    - a code-review pass found 8 of them, none adding a filter/global the
    others lacked - which re-parses every .html.j2 file on every single
    page render for no reason a single build ever needed. `lru_cache`
    makes this a one-time cost per process.
    """
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    env.globals["preferred_source_url"] = PREFERRED_SOURCE_URL
    env.globals["webmail_providers"] = [[label, url, list(domains)] for label, url, domains in WEBMAIL_PROVIDERS]
    return env


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_regions() -> list[dict]:
    # `sorted()` makes the order deterministic (alphabetical by filename:
    # Arlington Heights, Des Plaines, Mount Prospect, Palatine) rather than
    # filesystem-listing order, which matters beyond cosmetics since
    # 2026-09-17: item 108 found the combined email's signup form can't
    # tell which town a subscriber is in (no per-region segmentation on
    # Buttondown's free plan - the same constraint item 105 hit), so
    # "the reader's own region first" isn't implementable. The fallback is
    # a fixed, statable order - this one - named in
    # config/newsletter.yaml's `detail` field so the promise matches what
    # actually ships.
    regions = []
    for path in sorted(REGIONS_DIR.glob("*.yaml")):
        cfg = load_yaml(path)
        if "region" not in cfg:
            logger.warning("Skipping %s: missing top-level `region` key", path)
            continue
        regions.append(cfg)
    return regions


def load_newsletter_config(newsletter_cfg: dict) -> dict:
    """Email capture context (ROADMAP.md Phase 11 #12) - a Buttondown
    embed that only renders a live signup form once a real account's
    username is configured; otherwise the page shows the same headline/
    detail with an honest "coming soon" message instead of a form that
    would post to nothing. See config/newsletter.yaml for why: signing up
    for an email service is a human/paid action this repo can't do on its
    own, same as Stripe for the sponsor page.
    """
    username = (newsletter_cfg.get("buttondown_username") or "").strip()
    return {
        "configured": bool(username),
        "buttondown_username": username,
        "headline": newsletter_cfg.get("headline") or "Get it in your inbox",
        "detail": newsletter_cfg.get("detail") or "",
    }


def load_analytics_config(analytics_cfg: dict) -> dict:
    """Privacy-first analytics context (ROADMAP.md Phase 11 #23) - a
    GoatCounter site code that only gets a tracking script embedded once
    a real account's code is configured; unconfigured means no script at
    all, not a broken one. See config/analytics.yaml for why: signing up
    for a hosted analytics account is a human action this repo can't do
    on its own, same pattern as load_newsletter_config() above.
    """
    code = (analytics_cfg.get("goatcounter_code") or "").strip()
    return {
        "configured": bool(code),
        "goatcounter_code": code,
        # ROADMAP.md item 253: Pinterest's site-claim token, rendered as a
        # <meta> on the home page only when the owner sets it.
        "pinterest_domain_verify": (analytics_cfg.get("pinterest_domain_verify") or "").strip(),
    }


def load_maps_config(maps_cfg: dict) -> dict:
    """Which provider supplies the interactive street map layered over the
    inline-SVG region map.

    Defaults to OpenStreetMap's official export embed, which needs no API
    key and no billing account - so unlike analytics.yaml and
    newsletter.yaml, this feature is *on* out of the box rather than
    waiting on a human to sign up for something.

    Google is supported but only when a real key is present: the Maps
    Embed API returns a grey "for development purposes only" tile wash
    without one, which is worse than OSM working. An unset key therefore
    falls back rather than emitting a URL known to render broken.
    """
    provider = (maps_cfg.get("provider") or "osm").strip().lower()
    key = (maps_cfg.get("google_api_key") or "").strip()
    if provider == "google" and not key:
        provider = "osm"
    return {"provider": provider, "google_api_key": key}


# Formats seen in the wild beyond RFC 822 (pubDate) and RFC 5545 (ICS),
# most likely to show up if a source's `date` field is ever hand-set in
# config or a future fetcher extracts human-readable text ("Sat, Sep 6" /
# "September 6, 2026" / "9/6/2026") instead of a structured value. Tried
# in order; first match wins.
_EXTRA_DATE_FORMATS = (
    "%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d", "%Y-%m-%d",
    "%a, %b %d, %Y", "%a, %b %d %Y",
    "%B %d, %Y", "%b %d, %Y",
    "%m/%d/%Y", "%m/%d/%y",
)


def _try_parse_date(raw: str | None) -> datetime | None:
    """Best-effort parse of whatever date string a source hands us, tried
    against RFC 822 (RSS pubDate) first, then a fixed list of other
    formats seen in the wild. Returns None rather than guessing when
    nothing matches - callers decide what "no date" means for their
    output (a display fallback vs. omitting structured data).
    """
    if not raw:
        return None
    try:
        # An RSS pubDate's offset is not trusted: Communico library feeds
        # (MPPL, DPPL) stamp each event's local start time with "+0000" -
        # a 4:00pm program arrives as "16:00:00 +0000". Read as UTC, every
        # one moved five hours early. The wall-clock time is what the
        # feed means, so keep it and drop the offset.
        return parsedate_to_datetime(raw).replace(tzinfo=None)
    except (TypeError, ValueError):
        pass
    for fmt in _EXTRA_DATE_FORMATS:
        try:
            parsed = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        # ROADMAP.md item 238: an ICS "...Z" time is UTC, not local - left
        # naive, 19:00Z was shown and exported as 7 PM in Chicago.
        return parsed.replace(tzinfo=timezone.utc) if fmt.endswith("Z") else parsed
    return None


def format_event_date(raw: str | None) -> str | None:
    """Best-effort: turn a raw date string into "Aug 28" style display
    text. Falls back to the raw string (or None) if it can't be parsed -
    a card with an odd raw date string is still useful; one that silently
    drops the date isn't.
    """
    if not raw:
        return None
    parsed = _try_parse_date(raw)
    return parsed.strftime("%b %-d") if parsed else raw


def parse_event_date_iso(raw: str | None) -> str | None:
    """Best-effort: turn a raw date string into an ISO 8601 string for
    schema.org/Event structured data (which wants a real machine-readable
    date, unlike the "Aug 28" display text above). Returns None rather
    than a guess when the raw value can't be parsed - omitting startDate
    from structured data is valid; a wrong one isn't.
    """
    parsed = _try_parse_date(raw)
    if parsed is None:
        return None
    # ROADMAP.md item 238: a time that carries a zone is converted to the
    # site's local time, so every consumer (cards, filters, .ics exports)
    # sees the local date and hour. Naive values are already local.
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(LOCAL_TZ)
    return parsed.isoformat()


def schema_start_date(date_iso: str) -> str:
    """startDate for schema.org Event (ROADMAP.md item 238). Google asks for
    ISO 8601 with a timezone offset, or a date alone when the time is
    unknown. A midnight time is how the pipeline represents "no time
    given" (date-only sources, placeholder times), so it becomes a bare
    date - never "T00:00:00", which an agent could read as midnight."""
    dt = datetime.fromisoformat(date_iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    local = dt.astimezone(LOCAL_TZ)
    if local.time() == time(0, 0):
        return local.date().isoformat()
    return local.isoformat()


def schema_location(event: dict, region: dict | None = None) -> dict:
    """schema.org Place for an Event (ROADMAP.md item 238 - Google requires
    `location`). The source config's `venue_name` when the source's events
    happen at one known building (a library), else the town itself. Only the town
    and state go in the address: no invented street address, and no ZIP,
    since a town spans several."""
    town = event.get("town") or (region or {}).get("name")
    state = event.get("state") or (region or {}).get("state")
    address = {"@type": "PostalAddress", "addressCountry": "US"}
    if town:
        address["addressLocality"] = town
    if state:
        address["addressRegion"] = state
    name = event.get("venue") or (f"{town}, {state}" if town and state else town) or SITE_NAME
    return {"@type": "Place", "name": name, "address": address}


def truncate(text: str, max_len: int = DETAIL_MAX_LEN) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rsplit(" ", 1)[0] + "…"


def _ics_escape(text: str) -> str:
    """Inverse of fetchers._unescape_ics_text - escape TEXT values per
    RFC 5545 before writing them into an .ics file we generate.

    Normalizes CRLF and a bare CR to LF *before* escaping, then escapes
    that LF the same as any other - RFC 5545 content lines are CRLF-
    terminated externally and a raw CR should never survive into a
    VALUE. Left unhandled, a title/detail containing a literal `\\r`
    (plausible from an RSS/HTML source, which - unlike fetch_ics's own
    parsing - never runs it through a line-splitting pass) would embed
    an un-escaped line break into the generated SUMMARY/DESCRIPTION
    line: many real-world calendar parsers treat a bare CR as a line
    terminator just as leniently as CRLF, letting fetched content inject
    what reads as extra ICS properties into the same VEVENT. Confirmed
    with a real crafted title before fixing it, not assumed - see the
    regression test.
    """
    return (
        (text or "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )


def _ics_sanitize_url(url: str) -> str:
    """Strip embedded CR/LF from a URL before writing it into a URI-typed
    ICS property (`URL:`) - a real gap _ics_escape() (above) doesn't
    cover, found by checking whether the same bare-CR injection (items
    127/134) had a third, unfixed instance: RFC 5545's TEXT-escaping
    rules only apply to TEXT-valued properties like SUMMARY/DESCRIPTION,
    but `event['url']` (a fetched RSS <link>/HTML href/ICS URL:, never
    line-split the way fetch_ics's own parsing is) flows into `URL:`
    unescaped either way, and a raw CR/LF there corrupts the .ics
    content-line structure exactly like an unescaped one in SUMMARY does
    - a lenient calendar parser reads it as extra injected properties in
    the same VEVENT. Removed outright rather than folded to visible text
    the way _ics_escape() folds a title's CR/LF to `\\n`: RFC 3986 URIs
    never legitimately contain a raw control character, so there is no
    real content to preserve, unlike a title/detail's own line break.
    """
    return re.sub(r"[\r\n]+", "", url or "")


def build_ics_data_uri(event: dict) -> str | None:
    """A downloadable "add to calendar" link for an event with a
    machine-readable start date, as a data: URI - no extra output file
    needed, works with a plain <a download> link. Assumes a 1-hour
    duration since sources rarely give an explicit end time; that's an
    approximation stated nowhere as fact, just a usable default.
    """
    if not event.get("date_iso"):
        return None
    start_dt = datetime.fromisoformat(event["date_iso"])
    end_dt = start_dt + timedelta(hours=1)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{SITE_NAME}//EN",
        "BEGIN:VEVENT",
        f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{_ics_escape(event.get('title', ''))}",
    ]
    if event.get("detail"):
        lines.append(f"DESCRIPTION:{_ics_escape(event['detail'])}")
    if event.get("url"):
        lines.append(f"URL:{_ics_sanitize_url(event['url'])}")
    lines += ["END:VEVENT", "END:VCALENDAR", ""]
    return "data:text/calendar;charset=utf-8," + quote("\r\n".join(lines))


def build_region_calendar_ics(region: dict, blocks: list[dict], now: datetime) -> str:
    """A subscribable .ics feed for the whole region (ROADMAP.md Phase 11
    #100) - the strongest retention mechanism identified: subscribe once
    and every future event appears in the family's own calendar, with no
    email ever needing to be opened again. Same RFC 5545 serialization
    as the per-event data: URI above (_ics_escape), just written once
    per build to docs/<region-id>/calendar.ics instead of inlined per
    card, over every dated event across every source and the curated
    annual events - not weekend-filtered, since a subscription is
    supposed to be the whole calendar.

    Applies item 90's attendable split: a non-attendable event (a
    school half-day) is real and belongs in the feed, but as a
    transparent, all-day entry rather than a timed one a calendar app
    would show as "busy" for.

    UID is stable across rebuilds (region + event date + a sanitized
    slug of the title), so a re-fetch updates the same calendar entry
    instead of duplicating it - the whole point of a subscription over
    a one-time download. SEQUENCE is always 0: correctly bumping it on
    a real content change needs a persisted per-event revision counter
    this pipeline doesn't keep anywhere (source_health.json tracks
    fetch success/failure, not event content) - building that just for
    this would be new state-tracking infrastructure, not a byproduct of
    the feature. A subscribed calendar client re-fetches and diffs by
    UID + content on every refresh regardless, which covers the common
    case here; this is a documented simplification, not a silent gap.
    """
    events = [e for b in blocks for e in b["events"] if e.get("date_iso") and e.get("title")]
    calname = f"{SITE_NAME} — {region['name']}"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{SITE_NAME}//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_ics_escape(calname)}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    for event in events:
        start_dt = datetime.fromisoformat(event["date_iso"])
        slug = re.sub(r"[^a-z0-9]+", "-", event["title"].lower()).strip("-")
        uid = f"{region['id']}-{start_dt.date().isoformat()}-{slug}@withintenmiles.com"
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}", f"LAST-MODIFIED:{stamp}", "SEQUENCE:0"]
        if event.get("attendable", True):
            end_dt = start_dt + timedelta(hours=1)
            lines += [
                f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}",
                f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}",
            ]
        else:
            end_date = start_dt.date() + timedelta(days=1)
            lines += [
                f"DTSTART;VALUE=DATE:{start_dt.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{end_date.strftime('%Y%m%d')}",
                "TRANSP:TRANSPARENT",
            ]
        lines.append(f"SUMMARY:{_ics_escape(event['title'])}")
        if event.get("detail"):
            lines.append(f"DESCRIPTION:{_ics_escape(event['detail'])}")
        if event.get("url"):
            lines.append(f"URL:{_ics_sanitize_url(event['url'])}")
        lines.append("END:VEVENT")
    lines += ["END:VCALENDAR", ""]
    return "\r\n".join(lines)


def build_google_calendar_url(event: dict, location: str) -> str | None:
    """A "add to Google Calendar" link - same 1-hour-duration assumption
    as build_ics_data_uri, for the same reason.
    """
    if not event.get("date_iso"):
        return None
    start_dt = datetime.fromisoformat(event["date_iso"])
    end_dt = start_dt + timedelta(hours=1)
    params = {
        "action": "TEMPLATE",
        "text": event.get("title", ""),
        "dates": f"{start_dt.strftime('%Y%m%dT%H%M%S')}/{end_dt.strftime('%Y%m%dT%H%M%S')}",
        "details": event.get("detail", ""),
        "location": location,
    }
    return "https://www.google.com/calendar/render?" + urlencode(params)


def load_source_health() -> dict:
    """Per-source event-count history (ROADMAP.md Phase 11 #51).

    A small, committed JSON file (alongside docs/, which CI already
    commits) tracking each source's last few fetch counts. The reason it
    exists: every source here is fail-soft by design (a broken scrape
    yields an empty section, never a crash), which is exactly right for
    uptime and exactly wrong for noticing a source has silently died - a
    green build with clean logs looks identical whether a source is
    genuinely returning nothing this week or its selector broke months
    ago. Comparing each run's count against that source's own trailing
    history (detect_source_regressions) is what actually catches that,
    cheaply, with no new service or subscription.
    """
    if SOURCE_HEALTH_PATH.exists():
        try:
            return json.loads(SOURCE_HEALTH_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read %s, starting fresh: %s", SOURCE_HEALTH_PATH, exc)
    return {}


def update_source_health(health: dict, source_key: str, count: int) -> None:
    history = health.setdefault(source_key, [])
    history.append(count)
    del history[:-SOURCE_HEALTH_HISTORY_LEN]


def detect_source_regressions(health: dict) -> list[str]:
    """Source keys whose latest count is 0 despite a positive trailing
    median - the actual "this used to work and just died" signal, as
    opposed to a source that has always legitimately returned 0 (e.g. an
    unconfirmed guess still waiting on a real URL), which this correctly
    leaves alone since its own median is already 0.
    """
    regressions = []
    for key, history in sorted(health.items()):
        if len(history) < 2:
            continue
        *prior, current = history
        if current == 0 and statistics.median(prior) > 0:
            regressions.append(key)
    return regressions


def detect_truncated_sources(health: dict, cap: int = MAX_ITEMS_PER_SOURCE) -> list[str]:
    """Source keys whose last three counts all land exactly on
    MAX_ITEMS_PER_SOURCE - ROADMAP.md item 180 (forty-second research
    pass): a source pinned at exactly the cap three builds running is
    almost certainly being cut off, not coincidentally exhausted at
    exactly the runaway-guard ceiling every time. This is exactly the
    diagnostic that would have surfaced item 178 (the cap sitting at 6
    for every live source, for every recorded build) directly instead
    of needing three passes of inference to find the same fact.
    """
    truncated = []
    for key, history in sorted(health.items()):
        if len(history) >= 3 and history[-3:] == [cap] * 3:
            truncated.append(key)
    return truncated


def detect_newly_broken_sources(health: dict) -> list[str]:
    """Source keys where a third consecutive zero just landed -
    ROADMAP.md item 180 (forty-second research pass): the existing
    regression check above only catches the *transition* from a
    positive trailing median to a single zero, and naturally goes quiet
    again once a chronically-dead source's own history fully ages past
    that transition (its trailing median becomes 0 too, indistinguishable
    from a source that has always legitimately returned nothing). That's
    exactly right for one-off noise and exactly wrong for a source that
    dies and stays dead - it should say so once, not go silently
    unreadable again after ten builds.

    Fires exactly once, on the build where the third consecutive zero
    lands (`history[-4]` was still nonzero), not on every later build a
    source stays dead - a source already fully aged into all-zero
    history (the four known Mount Prospect village sources, items
    161/179) won't re-trigger this every build going forward, since
    that transition already happened outside this file's own tracked
    window. New sources with fewer than four recorded builds are left
    alone; there's nothing to transition from yet.
    """
    newly_broken = []
    for key, history in sorted(health.items()):
        if len(history) >= 4 and history[-3:] == [0, 0, 0] and history[-4] != 0:
            newly_broken.append(key)
    return newly_broken


def save_source_health(health: dict) -> None:
    SOURCE_HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_HEALTH_PATH.write_text(
        json.dumps(health, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def load_transport_failures() -> dict:
    """Per-source consecutive-transport-failure streak (ROADMAP.md item
    181, forty-third research pass) - a source that 403s/times out on
    every build since it was added never earns a single entry in
    source_health.json (item 55's fetch loop deliberately skips
    recording a transport failure there, to keep that file's count
    history free of misleading zeros). That's correct for count
    history and it means a chronically-403'd source gets no signal at
    all, forever, rather than a forgiving gap - tracked here instead,
    separately, so item 55's own file and reasoning stay untouched.
    """
    if TRANSPORT_FAILURE_PATH.exists():
        try:
            return json.loads(TRANSPORT_FAILURE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read %s, starting fresh: %s", TRANSPORT_FAILURE_PATH, exc)
    return {}


def update_transport_failures(failures: dict, source_key: str, transport_failed: bool) -> None:
    """Increment a source's consecutive-failure streak on a transport
    failure, reset to 0 on any successful fetch (any real [] or a
    nonzero count both count as success here - only a `None` transport
    failure, item 55's own signal, increments).
    """
    failures[source_key] = failures.get(source_key, 0) + 1 if transport_failed else 0


def load_failure_window() -> dict:
    """Load FAILURE_WINDOW_PATH; a missing or damaged file starts fresh."""
    if FAILURE_WINDOW_PATH.exists():
        try:
            data = json.loads(FAILURE_WINDOW_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if isinstance(v, str)}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read %s, starting fresh: %s", FAILURE_WINDOW_PATH, exc)
    return {}


def update_failure_window(window: dict, source_key: str, transport_failed: bool) -> None:
    """Append this build's outcome for a source, keeping the newest
    FAILURE_WINDOW_SIZE characters."""
    window[source_key] = (window.get(source_key, "") + ("1" if transport_failed else "0"))[-FAILURE_WINDOW_SIZE:]


def save_failure_window(window: dict) -> None:
    FAILURE_WINDOW_PATH.parent.mkdir(parents=True, exist_ok=True)
    FAILURE_WINDOW_PATH.write_text(json.dumps(window, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def detect_flapping_sources(
    window: dict, min_builds: int = FLAPPING_MIN_BUILDS, min_rate: float = FLAPPING_MIN_RATE
) -> list[tuple[str, int, int]]:
    """(source key, failures, builds) for every source that fails a
    meaningful share of recent builds without being down right now:
    at least `min_builds` of history, a failure rate of `min_rate` or more,
    and not already failing its last three builds (that is the chronic
    detector's job). A source that fails every other build has a streak of
    1 forever and is invisible to every streak-based check; this finds it."""
    flapping = []
    for key, history in sorted(window.items()):
        if len(history) < min_builds or "1" not in history:
            continue
        if history.endswith("111"):
            continue
        failures = history.count("1")
        if failures / len(history) >= min_rate:
            flapping.append((key, failures, len(history)))
    return flapping


def detect_lockstep_failures(window: dict, min_builds: int = FLAPPING_MIN_BUILDS) -> list[list[str]]:
    """Groups of two or more sources whose failures fall on exactly the
    same builds, over the same stretch. Unrelated hosts failing and
    recovering together is one cause (the runner's egress, a shared CDN,
    per-IP rate limiting), not several coincidences. A history that is all
    successes or all failures says nothing about timing and is left out."""
    by_pattern: dict[str, list[str]] = {}
    for key, history in sorted(window.items()):
        if len(history) >= min_builds and "1" in history and "0" in history:
            by_pattern.setdefault(history, []).append(key)
    return [keys for keys in by_pattern.values() if len(keys) >= 2]


def save_transport_failures(failures: dict) -> None:
    TRANSPORT_FAILURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRANSPORT_FAILURE_PATH.write_text(
        json.dumps(failures, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def load_transport_failure_details() -> dict:
    """Load TRANSPORT_FAILURE_DETAIL_PATH (ROADMAP.md item 185) - same
    load-or-fresh-start pattern as load_transport_failures().
    """
    if TRANSPORT_FAILURE_DETAIL_PATH.exists():
        try:
            return json.loads(TRANSPORT_FAILURE_DETAIL_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read %s, starting fresh: %s", TRANSPORT_FAILURE_DETAIL_PATH, exc)
    return {}


def update_transport_failure_details(details: dict, source_key: str, failure_info: dict | None) -> None:
    """Record the most recent transport failure's exception class/status
    code for `source_key` (ROADMAP.md item 185), or clear the entry once
    the source succeeds again - a stale "last failed with a 403" entry
    sitting next to a source that's currently healthy would mislead the
    same way item 185's own stale-health-count finding did.
    """
    if failure_info:
        details[source_key] = failure_info
    else:
        details.pop(source_key, None)


def save_transport_failure_details(details: dict) -> None:
    TRANSPORT_FAILURE_DETAIL_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRANSPORT_FAILURE_DETAIL_PATH.write_text(
        json.dumps(details, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


# ROADMAP.md item 262: the last good copy of each source. A source that
# alternates between answering and failing (Arlington Heights Park District
# was missing from 12 of 30 builds) used to take its town's events off the
# page for as long as the failure lasted. After every successful fetch the
# source's upcoming items are saved here; if the next fetch fails at the
# transport level, a copy under LAST_GOOD_MAX_AGE is used instead, so a
# reader sees nothing different. It never replaces finding the cause
# (item 194), and a source that has never succeeded has no copy to use.
LAST_GOOD_DIR = ROOT / "data" / "source_last_good"
LAST_GOOD_MAX_AGE = timedelta(hours=72)
LAST_GOOD_MAX_ITEMS = 60
# Rewrite an unchanged copy at most this often, so a quiet source does not
# produce a commit on every build but its age still stays well under 72 hours.
LAST_GOOD_REFRESH = timedelta(hours=6)


def last_good_path(directory: Path, region_id: str, source_name: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", source_name.lower()).strip("-") or "source"
    return directory / f"{region_id}__{slug}.json"


def select_last_good_items(raw_items: list[dict], today: date) -> list[dict]:
    """Which of a source's fetched items are worth keeping: those dated today
    or later, soonest first, then undated ones (news), capped so one large
    library calendar cannot make a large file."""
    dated, undated = [], []
    for item in raw_items:
        iso = parse_event_date_iso(item.get("date"))
        if iso is None:
            undated.append(item)
            continue
        try:
            day = datetime.fromisoformat(iso).date()
        except ValueError:
            undated.append(item)
            continue
        if day >= today:
            dated.append((iso, item))
    dated.sort(key=lambda pair: pair[0])
    return ([item for _iso, item in dated] + undated)[:LAST_GOOD_MAX_ITEMS]


def save_last_good(directory: Path, region_id: str, source_name: str, raw_items: list[dict], now: datetime, today: date) -> bool:
    """Record a successful fetch. Returns True when a file was written. An
    empty result is not recorded: it never overwrites a useful copy. An
    unchanged copy is only rewritten once it is LAST_GOOD_REFRESH old."""
    items = select_last_good_items(raw_items, today)
    if not items:
        return False
    path = last_good_path(directory, region_id, source_name)
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
        age = now - datetime.fromisoformat(existing["fetched_at"])
        if existing.get("items") == items and age < LAST_GOOD_REFRESH:
            return False
    except (OSError, ValueError, KeyError, TypeError):
        pass
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"source": source_name, "fetched_at": now.isoformat(timespec="seconds"), "items": items}, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return True


def load_last_good(directory: Path, region_id: str, source_name: str, now: datetime) -> tuple[list[dict], timedelta] | None:
    """(items, age) for a copy younger than LAST_GOOD_MAX_AGE, else None.
    Anything unreadable counts as no copy: this must never break a build."""
    path = last_good_path(directory, region_id, source_name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        fetched = datetime.fromisoformat(data["fetched_at"])
        items = data["items"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(items, list):
        return None
    age = now - fetched
    if age < timedelta(0) or age >= LAST_GOOD_MAX_AGE:
        return None
    return items, age


def last_good_sentence(completeness: dict | None) -> str:
    """"1 source is shown from its last update, 14 hours ago." - appended to
    the completeness line wherever it is stated, or "" when none applies."""
    used = (completeness or {}).get("last_good") or []
    if not used:
        return ""
    hours = max(1, round(max(u["age_hours"] for u in used)))
    noun = "source is" if len(used) == 1 else "sources are"
    unit = "hour" if hours == 1 else "hours"
    return f" {len(used)} {noun} shown from {'its' if len(used) == 1 else 'their'} last update, up to {hours} {unit} ago."


def write_source_completeness(reporting: int, expected: int, now: datetime) -> None:
    """Persist "N of M sources reported" for the build that just ran
    (ROADMAP.md item 197) - a single build-wide snapshot, not a history,
    since llms.txt/about/feed.xml only ever need the latest figure.
    """
    SOURCE_COMPLETENESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_COMPLETENESS_PATH.write_text(
        json.dumps(
            {"reporting": reporting, "expected": expected, "built_at": now.isoformat()},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def detect_chronic_transport_failures(
    failures: dict, threshold: int = CONSECUTIVE_TRANSPORT_FAILURE_ALERT_THRESHOLD
) -> list[str]:
    """Source keys whose transport-failure streak has reached the alert
    threshold - ROADMAP.md item 181. Not reset once flagged (a source
    still 403ing on build N+1 should keep saying so, same reasoning as
    detect_truncated_sources' own non-transition-gating), so this stays
    loud for as long as the failure continues rather than firing once.
    """
    return sorted(key for key, streak in failures.items() if streak >= threshold)


def expected_source_keys(regions: list[dict]) -> set[str]:
    """Every `region_id:source_name` key `config/regions/*.yaml` actually
    declares (enabled sources only - a disabled one is deliberately not
    fetched, so its absence from source_health.json is correct, not a
    gap). The set detect_missing_sources compares real health-file keys
    against.
    """
    keys = set()
    for region_cfg in regions:
        region_id = region_cfg["region"]["id"]
        for source in region_cfg.get("sources", []):
            if source.get("enabled", True):
                keys.add(f"{region_id}:{source['name']}")
    return keys


def detect_missing_sources(regions: list[dict], health: dict) -> list[str]:
    """Source keys `config/regions/*.yaml` declares that have never once
    appeared in `data/source_health.json` - ROADMAP.md item 181 (forty-
    third research pass). detect_source_regressions/detect_truncated_
    sources/detect_newly_broken_sources all iterate `health.items()`, so
    a source that fails transport on every build since it was added -
    which never gets a key at all, per item 55's own design - is
    structurally invisible to every one of them. This is the check that
    catches the absence itself, the one thing "iterate the keys" can't.
    """
    return sorted(expected_source_keys(regions) - health.keys())


def write_weekend_signal(region_counts: dict[str, int], now: datetime) -> None:
    """Write WEEKEND_SIGNAL_PATH (ROADMAP.md item 172) - a snapshot of how
    many dated weekend events this build found per region, plus the total
    across every region, which is exactly the count the combined issue
    (config send.region: "combined") actually mails. send_newsletter.py
    reads this to decide whether an issue is too thin to deliver; a
    region-specific send checks its own entry instead of the total.
    """
    WEEKEND_SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEEKEND_SIGNAL_PATH.write_text(
        json.dumps(
            {
                "generated_at": now.isoformat(),
                "region_counts": region_counts,
                "total": sum(region_counts.values()),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def load_weekend_history() -> dict:
    """Load WEEKEND_HISTORY_PATH (ROADMAP.md item 186) - same
    load-or-fresh pattern as load_source_health()/load_transport_failures().
    """
    if WEEKEND_HISTORY_PATH.exists():
        try:
            return json.loads(WEEKEND_HISTORY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read %s, starting fresh: %s", WEEKEND_HISTORY_PATH, exc)
    return {}


def update_weekend_history(history: dict, region_id: str, count: int) -> None:
    history[region_id] = (history.get(region_id) or [])[-(WEEKEND_HISTORY_LEN - 1):] + [count]


def save_weekend_history(history: dict) -> None:
    WEEKEND_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEEKEND_HISTORY_PATH.write_text(
        json.dumps(history, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def detect_zero_weekend_regions(history: dict, threshold: int = ZERO_WEEKEND_ALERT_THRESHOLD) -> list[str]:
    """Flag any region whose trailing `threshold` builds all landed zero
    weekend events (ROADMAP.md item 186) - a region can be fully healthy
    by every existing check (reachable, un-truncated, no transport
    failures) and still contribute nothing to the one number the
    combined issue's subject line is built from, because nothing it
    returns has a date inside the Fri/Sat/Sun window. Not transition-
    gated, on purpose, matching detect_truncated_sources rather than
    detect_newly_broken_sources: a region that's *still* contributing
    zero should stay loud for as long as that's true, not just on the
    build where it first crossed the threshold.
    """
    return sorted(
        region_id
        for region_id, counts in history.items()
        if len(counts) >= threshold and all(c == 0 for c in counts[-threshold:])
    )


def fetch_region_sections(
    region_cfg: dict,
    health: dict | None = None,
    transport_failures: dict | None = None,
    transport_failure_details: dict | None = None,
    completeness: dict | None = None,
    *,
    last_good_dir: Path | None = None,
    now: datetime | None = None,
    failure_window: dict | None = None,
) -> list[dict]:
    region_id = region_cfg["region"]["id"]
    region_name = region_cfg["region"]["name"]
    blocks = []
    for source in region_cfg.get("sources", []):
        if not source.get("enabled", True):
            continue
        if completeness is not None:
            completeness["expected"] += 1
        fetcher = FETCHERS.get(source["type"])
        if fetcher is None:
            logger.warning("Unknown source type %r for %s", source["type"], source["name"])
            raw_items = []
        else:
            logger.info("Fetching %s (%s)", source["name"], source["type"])
            failure_info: dict = {}
            raw_items = fetcher(
                source["url"],
                keywords=source.get("keywords"),
                detail_link_pattern=source.get("detail_link_pattern"),
                failure_info=failure_info,
            )
            # A fetcher returns None on a transport/parse failure (network
            # error, non-2xx status) versus a real [] (reached the page,
            # found nothing) - see fetchers.py's docstrings (ROADMAP.md
            # Phase 11 #55). Only the latter is meaningful health signal:
            # a 403 or a timeout means the scraper never got a chance to
            # work, so it's skipped from history entirely rather than
            # recorded as a 0 that looks identical to a genuinely dead
            # scraper.
            transport_failed = raw_items is None
            raw_items = raw_items or []
            if last_good_dir is not None and now is not None:
                if not transport_failed:
                    try:
                        save_last_good(last_good_dir, region_id, source["name"], raw_items, now, region_local_date(region_cfg["region"], now))
                    except OSError as exc:
                        logger.warning("Could not save last-good copy for %s: %s", source["name"], exc)
                else:
                    saved = load_last_good(last_good_dir, region_id, source["name"], now)
                    if saved is not None:
                        raw_items, age = saved
                        logger.warning(
                            "%s failed; using its last good copy from %.1f hours ago (%d item(s))",
                            source["name"], age.total_seconds() / 3600, len(raw_items),
                        )
                        if completeness is not None:
                            completeness.setdefault("last_good", []).append(
                                {"source": f"{region_id}:{source['name']}", "age_hours": age.total_seconds() / 3600}
                            )
            logger.info(
                "  -> %d item(s)%s",
                len(raw_items),
                " (transport error - not counted for health)" if transport_failed else "",
            )
            source_key = f"{region_id}:{source['name']}"
            if not transport_failed and completeness is not None:
                completeness["reporting"] += 1
            if health is not None and not transport_failed:
                update_source_health(health, source_key, len(raw_items))
            # ROADMAP.md item 181: tracked regardless of transport_failed,
            # unlike source_health.json above - a streak needs to see
            # every success too, to reset back to 0.
            if transport_failures is not None:
                update_transport_failures(transport_failures, source_key, transport_failed)
            if failure_window is not None:
                update_failure_window(failure_window, source_key, transport_failed)
            # ROADMAP.md item 185: the *kind* of transport failure, not
            # just that one happened - failure_info is only ever
            # populated when transport_failed is true (fetchers.py only
            # fills it in the except branch), so no extra guard needed.
            if transport_failure_details is not None:
                update_transport_failure_details(transport_failure_details, source_key, failure_info)

        events = []
        for item in raw_items:
            tags = infer_tags(item.get("title", ""), item.get("detail", ""), source["section"])
            tags = merge_default_tags(source.get("default_tags"), tags)
            # ROADMAP.md Phase 11 #90: a source-level `informational: true`
            # (for a feed like D57's that's mostly closures/half-days, not
            # events) forces every item non-attendable regardless of
            # wording; otherwise it's inferred per-item from the title/detail.
            attendable = not source.get("informational") and not is_informational(
                item.get("title", ""), item.get("detail", "")
            )
            event = {
                "title": item.get("title", ""),
                "detail": truncate(item.get("detail", "")),
                "url": item.get("url", ""),
                "date": format_event_date(item.get("date")),
                "date_iso": parse_event_date_iso(item.get("date")),
                "tags": tags,
                "tag_badges": [{"id": t, **tag_display(t)} for t in tags],
                "attendable": attendable,
                # ROADMAP.md item 238: where it happens, for Event markup.
                # From config only - never the feed's own LOCATION, which
                # item 115 keeps out of the parser because it can carry
                # text not meant for republication (rooms, staff entrances).
                "venue": source.get("venue_name"),
                "source": source["name"],
                "town": region_name,
                "state": region_cfg["region"].get("state"),
            }
            event["ics_href"] = build_ics_data_uri(event)
            event["google_calendar_url"] = build_google_calendar_url(event, region_name)
            events.append(event)
        blocks.append({"section": source["section"], "events": events})
    return blocks


def prepare_evergreen(region_cfg: dict) -> list[dict]:
    prepared = []
    for item in region_cfg.get("evergreen", []):
        tags = item.get("tags")
        if tags is None:
            tags = infer_tags(item.get("title", ""), item.get("detail", ""))
        prepared.append(
            {**item, "tags": tags, "tag_badges": [{"id": t, **tag_display(t)} for t in tags]}
        )
    return prepared


def prepare_guides(region_cfg: dict) -> list[dict]:
    """Seasonal/evergreen guides (ROADMAP.md Phase 11 #5) - a `guides:` list
    in region YAML, same shape as `evergreen` but grouped into named,
    linkable pages (e.g. "Fall Family Guide") instead of one flat section.
    Doesn't expire every Monday the way a dated event listing does, which
    is the point: it's the placement local sponsors most want to be inside.
    """
    prepared = []
    for guide in region_cfg.get("guides", []):
        items = []
        for item in guide.get("items", []):
            tags = item.get("tags")
            if tags is None:
                tags = infer_tags(item.get("title", ""), item.get("detail", ""))
            items.append(
                {**item, "tags": tags, "tag_badges": [{"id": t, **tag_display(t)} for t in tags]}
            )
        prepared.append(
            {
                "slug": guide["slug"],
                "title": guide["title"],
                "summary": guide.get("summary", ""),
                "items": items,
            }
        )
    return prepared


def build_things_to_do_items(evergreen: list[dict], guides: list[dict]) -> list[dict]:
    """The evergreen "Things to Do in {town}" page (ROADMAP.md item 158).

    The research found the head term splits into two queries this site
    only answered one of - "what's on this Saturday" (the dated digest)
    and "what is there to do here at all" (the half Tripadvisor/Yelp
    rank for, with standing attractions rather than dated events). An
    evergreen page is the right answer for the second, and the research
    is explicit that it's also the *compounding* one: a "things to do"
    page accumulates backlinks and rank over years the way a dated
    listing never gets the chance to.

    Seeded entirely from material already curated for evergreen/guides
    (item 158's own instruction: no new prose) - deduplicated by url
    (falling back to title for the rare item with none) so a source
    that appears in several guides, the park district's mppd.org say,
    shows once here, not four or five times.
    """
    seen: set[str] = set()
    items: list[dict] = []
    for item in evergreen + [i for guide in guides for i in guide["items"]]:
        key = item.get("url") or item.get("title", "")
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
    return items


def is_trick_or_treat_season(now: datetime) -> bool:
    """Whether a footer link to /trick-or-treat/ (item 101) earns its
    place right now. True September through the first few days of
    November - villages post real hours in late September/early October
    (prepare_trick_or_treat()'s own note) and a few families still want
    it in the days right after Halloween. False the rest of the year,
    when the page is real but would just be a permanent link to an
    empty "not posted yet" state - DESIGN_PRINCIPLES.md's standing
    question (does this earn its place, or is it one more thing) says a
    footer link that's irrelevant ten months a year does not.

    A real, if minor, bug this closes: the page has been live and in
    the sitemap since item 101 shipped, but no region or hub page ever
    linked to it - reachable only by a search engine crawling the
    sitemap or an AI agent reading llms.txt, not by an actual visitor.
    """
    return now.month in (9, 10) or (now.month == 11 and now.day <= 5)


def prepare_trick_or_treat(region_cfg: dict) -> dict | None:
    """A region's `trick_or_treat:` block (ROADMAP.md Phase 11 #101), if
    configured - feeds the cross-region /trick-or-treat/ page. `hours`
    is None until the village actually posts it (typically late Sept/
    early Oct); the page shows the honest "not yet posted" state until
    then rather than a guessed time, same discipline as every other
    civic source in this file.
    """
    tot = region_cfg.get("trick_or_treat")
    if not tot or not isinstance(tot, dict) or not tot.get("url"):
        return None
    hours = (tot.get("hours") or "").strip() or None
    # ROADMAP.md item 241: a town that never sets hours (Des Plaines) is a
    # different answer from one that hasn't posted them yet.
    no_official_hours = bool(tot.get("no_official_hours")) and not hours
    # ROADMAP.md item 218: a one-line caveat for hours that are a standing
    # rule rather than this year's announcement, or for what a town with
    # no official hours recommends instead.
    note = (tot.get("note") or "").strip() or None if (hours or no_official_hours) else None
    return {"url": tot["url"], "hours": hours, "no_official_hours": no_official_hours, "note": note}


# ROADMAP.md item 243: the dated Halloween events a parent searching for
# trick-or-treat hours also wants. Matched on the title only - a detail
# line mentions "costume" or "pumpkin" far more loosely than a title does.
HALLOWEEN_TITLE = re.compile(
    r"\b(halloween|trick[- ]?or[- ]?treat\w*|trunk[- ]?or[- ]?treat\w*|costumes?|haunted|pumpkins?|spooky)\b",
    re.IGNORECASE,
)
HALLOWEEN_EVENTS_PER_TOWN = 12


def select_halloween_events(blocks: list[dict], local_today: date) -> list[dict]:
    """A town's dated Halloween events from today through November 1
    (ROADMAP.md item 243), soonest first, capped so one busy library
    calendar can't bury the other towns on /trick-or-treat/."""
    start = max(local_today, date(local_today.year, 10, 1))
    end = date(local_today.year, 11, 1)
    picked = []
    for block in blocks:
        for event in block.get("events", []):
            if not (event.get("title") and event.get("url") and event.get("date_iso")):
                continue
            try:
                day = datetime.fromisoformat(event["date_iso"]).date()
            except ValueError:
                continue
            if start <= day <= end and HALLOWEEN_TITLE.search(event["title"]):
                picked.append(event)
    picked.sort(key=lambda e: e["date_iso"])
    return picked[:HALLOWEEN_EVENTS_PER_TOWN]


def build_halloween_signup_headline(now: datetime) -> str:
    """The signup heading on /trick-or-treat/ (ROADMAP.md item 251): names the
    weekday Halloween falls on this year, computed so it is right every year."""
    weekday = date(now.year, 10, 31).strftime("%A")
    return f"Halloween falls on a {weekday} this year. Get the weekend's events by email on Thursday."


def build_halloween_json_ld(entries: list[dict]) -> str | None:
    """Event markup for the Halloween events listed on /trick-or-treat/
    (ROADMAP.md item 243). Each event's `url` is its card on the town's
    own page, as in events.json."""
    graph = [
        _event_list_item(e, entry["region_url"], 0)["item"]
        for entry in entries
        for e in entry.get("events") or []
    ]
    if not graph:
        return None
    payload = {"@context": "https://schema.org", "@graph": graph}
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


_COUNT_WORDS = {2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"}


def render_trick_or_treat_page(
    entries: list[dict], now: datetime, analytics: dict | None = None, newsletter: dict | None = None
) -> str:
    """The cross-region trick-or-treat hours page (ROADMAP.md Phase 11
    #101) - the single highest-volume hyperlocal query of Q4, and one no
    competitor aggregates (Eventbrite/AllEvents list ticketed events;
    this is a municipal announcement). Villages post in late Sept/early
    Oct, so this ships now, honestly empty of real hours, for indexing
    lead time - the two-week query spike before the 31st is the reason
    this can't wait until hours actually exist.
    """
    env = get_template_env()
    template = env.get_template("trick_or_treat.html.j2")
    # ROADMAP.md item 218: the title said "Four Towns" over five entries -
    # same hardcoded-count bug item 170 fixed elsewhere.
    count = len(entries)
    return template.render(
        entries=entries,
        towns_label=f"{_COUNT_WORDS.get(count, str(count))} Towns" if count != 1 else "One Town",
        town_names=_join_names([e["region_name"] for e in entries]),
        any_events=any(e.get("events") for e in entries),
        event_json_ld=build_halloween_json_ld(entries),
        newsletter=newsletter or {"configured": False},
        signup_headline=build_halloween_signup_headline(now),
        hub_url=SITE_BASE_URL,
        canonical_url=SITE_BASE_URL + "trick-or-treat/",
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        analytics=analytics,
        og_image_url=SITE_BASE_URL + "og/default.png",
    )


def _build_annual_event_dict(
    item: dict, region_name: str, *, date_display: str | None, date_iso: str | None,
    recurrence_note: str | None = None,
) -> dict:
    """Shared dict-construction for both a single dated annual_events entry
    and one expanded occurrence of a recurring one - same event-dict shape
    a fetched item gets (see prepare_annual_events' own docstring for why),
    just with the date fields supplied by the caller instead of parsed from
    a single `date:` string.
    """
    tags = item.get("tags")
    if tags is None:
        tags = infer_tags(item.get("title", ""), item.get("detail", ""), "Annual Events")
    event = {
        "title": item.get("title", ""),
        # ROADMAP.md Phase 11 #71: an optional small kicker for entries
        # that are one day of the same multi-day event (e.g. Friday and
        # Saturday of one festival), so the grouping shows above the
        # title instead of being concatenated into it. Absent for a
        # standalone annual event.
        "series": item.get("series"),
        "detail": truncate(item.get("detail", "")),
        "url": item.get("url", ""),
        "date": date_display,
        "date_iso": date_iso,
        "tags": tags,
        "tag_badges": [{"id": t, **tag_display(t)} for t in tags],
        # ROADMAP.md item 141: a light "every Sunday through Oct 11"
        # kicker for a recurring occurrence, so it reads as a standing
        # reference rather than news repeated week after week - None for
        # a one-off annual event, same as `series` above.
        "recurrence_note": recurrence_note,
    }
    event["ics_href"] = build_ics_data_uri(event)
    event["google_calendar_url"] = build_google_calendar_url(event, region_name)
    return event


_WEEKDAY_NAMES = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# ROADMAP.md item 141: bounds how far forward a recurring event expands -
# a five-month farmers-market season shouldn't inflate calendar.ics with
# occurrences nobody will see for months, and a fixed window means the
# list shrinks back down as the season plays out rather than growing
# without limit build after build.
MAX_RECURRENCE_DAYS = 120


def expand_recurring_annual_event(item: dict, region_name: str, today: date) -> list[dict]:
    """One `annual_events:` entry with a `recurrence:` block (starts, ends,
    weekday, optional time) expanded into concrete dated occurrence dicts -
    the fix ROADMAP.md item 141 asked for: a farmers market running
    Sundays 14 Jun - 11 Oct is invisible to every date-scoped view, the
    combined email, and calendar.ics today, despite being the most
    reliably knowable event a region has, because `annual_events` only
    ever understood a single `date:`.

    Every occurrence is marked `attendable: True` (it's a real event, not
    a closure notice - item 90's distinction doesn't apply here) and
    `recurring: True`, which build_email_subject_line() and
    select_editors_pick() both check and exclude from their headline
    picks - the design caveat item 141 raised explicitly: the same market
    named in twenty consecutive subject lines is exactly how a digest
    starts reading as automated filler, the failure mode item 124's
    competitors already have. A recurring item still appears normally in
    the weekend view, the email body, and calendar.ics - only the
    headline-selection logic treats it differently, via `recurrence_note`
    (see _build_annual_event_dict).

    Bounded to MAX_RECURRENCE_DAYS forward from `today` (or `ends`,
    whichever is sooner) and never includes an occurrence that's already
    passed - same "don't show what's already happened" rule every other
    dated source on this site follows.

    Takes `today` as the region's own local date (region_local_date()'s
    result), not a bare UTC `now` - confirmed as a real, not theoretical,
    bug before fixing: a build running Sunday night Central time is
    already Monday in UTC, and a UTC-dated "today" pushed the very next
    occurrence a full week past the Sunday that was, locally, still in
    progress. weekend_dates()/filter_events_by_dates() already take the
    same local-date precaution for exactly this "near midnight" class of
    error (see region_local_date()'s own docstring) - this just applies
    it here too instead of reintroducing the bug region_local_date exists
    to prevent.
    """
    rec = item.get("recurrence")
    if not rec:
        return []
    title = item.get("title", "<untitled>")
    weekday_name = str(rec.get("weekday", "")).strip().lower()
    weekday = _WEEKDAY_NAMES.get(weekday_name)
    if weekday is None:
        logger.warning("Unknown recurrence weekday %r for %r - skipping recurrence", rec.get("weekday"), title)
        return []
    try:
        starts = datetime.strptime(rec["starts"], "%Y-%m-%d").date()
        ends = datetime.strptime(rec["ends"], "%Y-%m-%d").date()
    except (KeyError, ValueError) as exc:
        logger.warning("Invalid recurrence starts/ends for %r: %s - skipping recurrence", title, exc)
        return []
    occurrence_time = time(0, 0)
    if rec.get("time"):
        try:
            occurrence_time = datetime.strptime(rec["time"], "%H:%M").time()
        except ValueError:
            logger.warning("Invalid recurrence time %r for %r - defaulting to midnight", rec.get("time"), title)

    window_end = min(ends, today + timedelta(days=MAX_RECURRENCE_DAYS))
    first = starts + timedelta(days=(weekday - starts.weekday()) % 7)
    if first < today:
        first = today + timedelta(days=(weekday - today.weekday()) % 7)

    recurrence_note = f"Every {weekday_name.capitalize()} through {ends.strftime('%b %-d')}"
    events = []
    d = first
    while d <= window_end:
        event = _build_annual_event_dict(
            item, region_name,
            date_display=d.strftime("%b %-d"),
            date_iso=datetime.combine(d, occurrence_time).isoformat(),
            recurrence_note=recurrence_note,
        )
        event["attendable"] = True
        event["recurring"] = True
        events.append(event)
        d += timedelta(days=7)
    return events


def prepare_annual_events(region_cfg: dict, now: datetime) -> dict | None:
    """Curated annual events with real dates (ROADMAP.md Phase 11 #67) -
    the missing third content type. `sources:` is fetched and best-effort;
    `evergreen:` is curated but undated; neither covers a known, dated,
    recurring event a human confirmed - a Village festival or Oktoberfest.
    That gap is exactly how a scraper returning 200-with-nothing can
    silently erase a marquee event (item 66's finding: Mount Prospect's
    own Fall Fest & Oktoberfest was invisible on the site three days
    before it happened, since `mpdowntown.com/events/` extracts zero
    items and the dedicated info page was never a configured source).

    Reuses the exact event-dict shape a fetched item gets (tags via
    infer_tags, date_iso via parse_event_date_iso, calendar links via
    build_ics_data_uri/build_google_calendar_url) so every downstream
    consumer - weekend/today/free views, JSON-LD, Editor's Pick - handles
    an `annual_events:` entry with no special-casing; it's just another
    block. Returns None (not an empty block) when a region has none
    configured, so the section never renders as an empty apology.

    An entry with a `recurrence:` block (ROADMAP.md item 141) expands
    into many dated occurrences via expand_recurring_annual_event(),
    using the region's own local date (not the build server's UTC one -
    see that function's docstring for why this matters) as "today".
    Everything else here is unchanged for a plain single-`date:` entry.
    """
    raw_items = region_cfg.get("annual_events", [])
    if not raw_items:
        return None
    region = region_cfg["region"]
    region_name = region["name"]
    today = region_local_date(region, now)
    events = []
    for item in raw_items:
        if item.get("recurrence"):
            events += expand_recurring_annual_event(item, region_name, today)
            continue
        events.append(
            _build_annual_event_dict(
                item, region_name,
                date_display=format_event_date(item.get("date")),
                date_iso=parse_event_date_iso(item.get("date")),
            )
        )
    return {"section": "Annual Events", "events": events}


def resolve_sponsor(sponsors_cfg: dict, region_id: str) -> dict:
    """The active sponsor (or house ad fallback) for a region, tagged with
    `is_active_sponsor` - the region page's sponsor box only uses
    recommendation framing ("Local Recommendation", the optional `why`
    line) for a real paying sponsor, never for the house ad. Nothing has
    actually been recommended yet when the slot is empty, and pretending
    otherwise would undercut the whole point of item 18's rewrite: a
    recommendation reads as trustworthy specifically because it's genuine.
    """
    default_house_ad = sponsors_cfg.get(
        "default_house_ad", {"title": "Sponsor this spot", "detail": "", "url": ""}
    )
    region_sponsor_cfg = sponsors_cfg.get("regions", {}).get(region_id, {})
    active_id = region_sponsor_cfg.get("active")
    if active_id and active_id != "none":
        for entry in region_sponsor_cfg.get("history", []):
            if entry.get("id") == active_id:
                return {**entry, "is_active_sponsor": True}
    house_ad = region_sponsor_cfg.get("house_ad") or default_house_ad
    return {**house_ad, "is_active_sponsor": False}


def build_business_directory(sponsors_cfg: dict, region_id: str) -> list[dict]:
    """Permanent per-region business directory (ROADMAP.md Phase 11 #6) -
    built from `history` entries in config/sponsors.yaml that opted in with
    `directory: true`. This is what makes the Community Partner tier worth
    more than a footer logo that scrolls past: a business keeps its
    listing here even after its sponsored week/month ends, as long as it
    was ever a paying sponsor. No entries exist yet (no sponsor has signed
    up) - that's a fact about the business today, not something to fake
    with invented local businesses, so an empty list here is the honest
    and expected state until the first real sponsor.
    """
    region_sponsor_cfg = sponsors_cfg.get("regions", {}).get(region_id, {})
    directory = []
    for entry in region_sponsor_cfg.get("history", []):
        if not entry.get("directory"):
            continue
        detail = entry.get("detail", "")
        if entry.get("category"):
            detail = f"{entry['category']} — {detail}" if detail else entry["category"]
        directory.append(
            {
                "title": entry.get("title", ""),
                "detail": detail,
                "url": entry.get("url", ""),
                "date": None,
                "tags": [],
                "tag_badges": [],
                "ics_href": None,
            }
        )
    return directory


def _parse_promo_day(value) -> date | None:
    """A promotion's YYYY-MM-DD field. YAML turns an unquoted date into a
    date object, so accept that as well as a string."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def build_promotion_event(sponsors_cfg: dict, region_cfg: dict, today: date) -> dict | None:
    """The one paid Event Promo featured for a region today (ROADMAP.md
    item 245), as an ordinary event dict plus `sponsored_by`, or None.

    A promotion is featured while `starts` <= today <= `ends` (default:
    from the start, until the event's own day). Anything malformed is
    skipped with a warning, never shown wrong: a missing field, an
    unreadable date, an `ends` before `starts`, an event on a day before
    `starts` (it would be featured only after it happened), or a window
    that has closed. When several are live for one region, the earliest
    event is featured and the rest are skipped with a warning - one
    paid event at the top keeps the list useful.
    """
    region = region_cfg["region"]
    live = []
    for index, promo in enumerate(sponsors_cfg.get("promotions") or []):
        if promo.get("region") != region["id"]:
            continue
        label = f"promotions[{index}] ({promo.get('title') or 'untitled'})"
        missing = [f for f in ("title", "url", "date", "sponsor") if not str(promo.get(f) or "").strip()]
        if missing:
            logger.warning("Skipping %s: missing %s", label, ", ".join(missing))
            continue
        event_day = _parse_promo_day(promo["date"])
        starts = _parse_promo_day(promo["starts"]) if promo.get("starts") else None
        ends = _parse_promo_day(promo["ends"]) if promo.get("ends") else event_day
        if event_day is None or (promo.get("starts") and starts is None) or (promo.get("ends") and ends is None):
            logger.warning("Skipping %s: a date is not YYYY-MM-DD", label)
            continue
        if starts and ends and ends < starts:
            logger.warning("Skipping %s: ends %s is before starts %s", label, ends, starts)
            continue
        if starts and event_day < starts:
            logger.warning("Skipping %s: the event (%s) is before the promotion starts (%s)", label, event_day, starts)
            continue
        if (starts and today < starts) or today > ends or event_day < today:
            continue
        live.append((event_day, index, label, promo))
    if not live:
        return None
    live.sort(key=lambda row: (row[0], row[1]))
    for _day, _index, label, _promo in live[1:]:
        logger.warning("Skipping %s: %s already has a featured promotion today", label, region["name"])
    promo = live[0][3]
    tags = promo.get("tags")
    event = _build_annual_event_dict(
        {
            "title": str(promo["title"]).strip(),
            "detail": str(promo.get("blurb") or "").strip(),
            "url": str(promo["url"]).strip(),
            "tags": tags,
        },
        region["name"],
        date_display=format_event_date(live[0][0].isoformat()),
        date_iso=live[0][0].isoformat() + "T00:00:00",
    )
    event["sponsored_by"] = str(promo["sponsor"]).strip()
    event["attendable"] = True
    return event


def apply_promotion(blocks: list[dict], promotion: dict | None) -> list[dict]:
    """A "Featured" block holding `promotion` placed FIRST, after removing
    the same event if a source also carries it (same link, or a
    near-identical title on the same day), so the labelled copy is the one
    shown rather than a bare duplicate beside it."""
    if not promotion:
        return blocks
    day = promotion["date_iso"][:10]

    def same_event(event: dict) -> bool:
        if event.get("url") and event["url"] == promotion["url"]:
            return True
        return (event.get("date_iso") or "")[:10] == day and _is_near_duplicate_title(event.get("title", ""), promotion["title"])

    kept = [{**b, "events": [e for e in b["events"] if not same_event(e)]} for b in blocks]
    return [{"section": "Featured", "events": [promotion]}] + kept


# Keep in sync with SPONSOR_KIT.md's "Placements & pricing" table - that
# file is the canonical human-facing writeup, this is the same numbers
# rendered as a live page.
#
# Repriced around annual memberships, not weekly ad slots (ROADMAP.md
# Phase 11 #29): a membership renews once a year instead of needing to
# be re-sold roughly fifty times, which is what actually keeps sponsor
# work inside BUSINESS_PLAN.md's 30-60-minutes-a-month budget as this
# scales past one sponsor. Every membership benefit below already exists
# in the product - directory listing (item 6), guide placement (items 5
# and 15), the site's own SEO work (Phase 9, item 22) - only the pricing
# packaging changed, no new code.
#
# All four tiers compete for the same one `active` slot per region (see
# resolve_sponsor()), so "Neighborhood Authority" exclusivity isn't a new
# mechanic - a single active-sponsor slot already guarantees no one else
# shares it while a business holds it, at any tier.
#
# Annual Partner priced below 7 months of the old top monthly rate
# ($175 x 12 = $2,100/yr) as a real incentive to commit annually, not a
# token discount. Neighborhood Authority is priced at the low end of the
# $500-1,500/month real-estate "farming" budget range this tier targets
# (ROADMAP.md Phase 11 #30) - deliberately introductory for an unproven,
# brand-new premium product, with room to raise it once it has sold.
#
# Ordered by commitment, low to high (ROADMAP.md Phase 11 #59) - the
# previous order ($1,200/yr, $5,000/yr, $50/wk, $20) climbed no ladder a
# reader could follow. Annual Partner is flagged `recommended` per the
# copy above the grid calling it "the flagship option."
SPONSOR_TIERS = [
    {
        "name": "Event Promo",
        "payment_key": "event_promo",
        "price": "$20 one-time",
        "gated_by": "Newsletter reach",
        "detail": (
            "Your event goes first on your town's page, and first in the weekend list and weekly email "
            "when it falls on a weekend, labelled \"Presented by [you]\" and marked as sponsored in the event "
            "data AI assistants read. Runs until the event day. We guarantee the placement, not any "
            "assistant's mention."
        ),
    },
    {
        "name": "Weekly Spot",
        "payment_key": "weekly_spot",
        "price": "$50/week or $175/month",
        "gated_by": "Newsletter reach",
        "detail": "Not ready for a year? The same top-of-page recommendation, available week-to-week or month-to-month.",
    },
    {
        "name": "Annual Partner",
        "price": "$1,200/year",
        "gated_by": "Site traffic & search presence",
        "detail": "A permanent business directory listing, a spotlight placement inside one relevant seasonal guide, a live SEO backlink, and priority consideration for Editor's Pick — the flagship membership.",
        "recommended": True,
    },
    {
        "name": "Neighborhood Authority",
        "price": "$5,000/year, one business per region",
        "gated_by": "Site traffic & search presence",
        "detail": "Everything in Annual Partner, held exclusively for your region year-round — built for real estate and other locally-budgeted categories seeking neighborhood-level presence, not just leads.",
    },
]


# ROADMAP.md item 247: the "Example" card on /sponsor/. Template-only: it is
# passed to render_sponsor_page and nowhere else, so it can never reach a
# region page, events.json or llms-full.txt. No real business or date.
SAMPLE_PROMOTION_EVENT = {
    "title": "Fall Open House & Pumpkin Painting",
    "detail": "Free for families. Your one-line blurb goes here.",
    "date_label": "Your event's date",
    "sponsored_by": "Your Business Name",
}


def build_payment_line(tiers: list[dict]) -> str:
    """The /sponsor/ page's payment sentence (ROADMAP.md item 247). Venmo,
    Zelle or check until a Stripe Payment Link is configured; once one is,
    say which tiers take a card so the sentence matches the Buy-now
    buttons actually on the page."""
    card_tiers = [t["name"] for t in tiers if t.get("buy_url")]
    if not card_tiers:
        return "Payment: Venmo/Zelle/check."
    joined = " and ".join(card_tiers)
    return f"Card (Stripe) on {joined}; Venmo, Zelle or check for anything else."


SPONSOR_INQUIRY_FIELDS = (
    "Business name: \n"
    "Region(s) of interest: \n"
    "Preferred tier: \n"
    "Preferred week (if any): \n"
    "Why should we recommend you (one sentence): "
)

CORRECTION_PROMPT = "What's wrong or missing, and which region/event: "


def build_contact_mailto_url(contact_email: str | None, subject: str, body: str) -> str:
    """Prefers a real `mailto:` to `contact_email` (config/sponsors.yaml)
    once a real contact address is configured - deliberately never
    defaults to guessing one. Falls back to a prefilled GitHub issue when
    unconfigured, so a CTA built on this never links to a dead address
    either way. Shared by every on-site "reach a real person" CTA
    (originally just the sponsor inquiry, item 57; item 132 added a
    second, the corrections link) rather than duplicating the same
    mailto/GitHub-fallback logic per caller.
    """
    # quote_via=quote: mailto: URIs (RFC 6068) need %20 for spaces, not
    # urlencode's default '+' (an application/x-www-form-urlencoded
    # convention a mail client's subject/body won't understand). Using it
    # for the GitHub fallback too is harmless - GitHub accepts %20 fine.
    if contact_email:
        params = urlencode({"subject": subject, "body": body}, quote_via=quote)
        return f"mailto:{contact_email}?{params}"
    params = urlencode({"title": subject, "body": body}, quote_via=quote)
    return f"https://github.com/randerson-23/agent-business/issues/new?{params}"


def build_sponsor_cta_url(contact_email: str | None) -> str:
    """The sponsor page's only conversion point (ROADMAP.md Phase 11 #57).

    This used to be a hardcoded link to a GitHub "New issue" form - to buy
    a $1,200-5,000/year placement, a realtor or an ice-cream shop owner
    had to create a GitHub account and file an issue in a developer bug
    tracker. Real evidence this was actually broken, not just unpolished:
    it's the *only* conversion point in the entire business.
    """
    return build_contact_mailto_url(contact_email, "Sponsor inquiry", SPONSOR_INQUIRY_FIELDS)


def build_corrections_cta_url(contact_email: str | None) -> str:
    """A real point of contact for "something here is wrong or missing"
    (ROADMAP.md Phase 11 #132) - the corrections path the site's whole
    accuracy claim (item 131) needs to actually offer, not just assert.
    Same mailto/GitHub-issue-fallback pattern as the sponsor CTA, since
    it's the same underlying need: a real address, never guessed.
    """
    return build_contact_mailto_url(contact_email, "Correction", CORRECTION_PROMPT)


def build_sponsor_availability(sponsors_cfg: dict, region_summaries: list[dict]) -> list[dict]:
    """Current sponsor status per region, for the live /sponsor page.

    v1 shows *this week's* status only ("Sponsored by X" / "Open"), not a
    multi-week calendar - config/sponsors.yaml has one active slot per
    region today, not a dated schedule of future weeks. A real rolling
    calendar is a bigger data-model change, left for when there's an
    actual sponsor to schedule around.
    """
    availability = []
    for r in region_summaries:
        sponsor = resolve_sponsor(sponsors_cfg, r["id"])
        region_cfg = sponsors_cfg.get("regions", {}).get(r["id"], {})
        is_booked = bool(region_cfg.get("active") and region_cfg["active"] != "none")
        availability.append(
            {
                "region_name": r["name"],
                "region_url": SITE_BASE_URL + r["id"] + "/",
                "booked": is_booked,
                "sponsor_title": sponsor.get("title") if is_booked else None,
            }
        )
    return availability


def render_about_page(
    now: datetime,
    analytics: dict | None = None,
    contact_email: str | None = None,
    source_completeness: dict | None = None,
) -> str:
    """A real About page (ROADMAP.md Phase 11 #99) - the entity-clarity
    work item 22's GEO strategy was missing: who publishes this, why it
    exists, and how it's built, stated plainly for a reader or a
    crawler rather than left to infer. Also the canonical page where
    the Organization JSON-LD entity is fully defined (see
    build_organization_json_ld) - every other page's WebSite node
    references it by @id instead of re-declaring it.
    """
    env = get_template_env()
    template = env.get_template("about.html.j2")
    return template.render(
        hub_url=SITE_BASE_URL,
        canonical_url=SITE_BASE_URL + "about/",
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        analytics=analytics,
        og_image_url=SITE_BASE_URL + "og/default.png",
        organization_json_ld=build_organization_json_ld(),
        corrections_cta_url=build_corrections_cta_url(contact_email),
        source_completeness=source_completeness,
        last_good_note=last_good_sentence(source_completeness).strip(),
    )


def render_sponsor_page(
    availability: list[dict],
    now: datetime,
    analytics: dict | None = None,
    contact_email: str | None = None,
    stats: dict | None = None,
    payment_links: dict | None = None,
) -> str:
    env = get_template_env()
    template = env.get_template("sponsor.html.j2")
    tiers = [{**t, "buy_url": (payment_links or {}).get(t.get("payment_key") or "") or None} for t in SPONSOR_TIERS]
    return template.render(
        tiers=tiers,
        payment_line=build_payment_line(tiers),
        sample_event=SAMPLE_PROMOTION_EVENT,
        availability=availability,
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        canonical_url=SITE_BASE_URL + "sponsor/",
        hub_url=SITE_BASE_URL,
        analytics=analytics,
        cta_url=build_sponsor_cta_url(contact_email),
        stats=stats,
        og_image_url=SITE_BASE_URL + "og/default.png",
    )


def select_editors_pick(region_cfg: dict, blocks: list[dict], evergreen: list[dict]) -> dict | None:
    """One pinned "Editor's Pick" per region (ROADMAP.md Phase 11 #16) -
    makes the page read as edited rather than purely generated, and it's
    the highest-value adjacency on the page to sell a sponsor next to.

    `region.editors_pick_url` in config/regions/<id>.yaml can force a
    specific item (matched by its `url`) - falls through to the heuristic
    below if unset, or if the configured URL doesn't match anything in
    this build (a source can disappear or an evergreen entry's URL can
    change; a stale override should never crash the build, just get
    ignored with a warning).

    Heuristic: soonest dated item wins first (a "this weekend" pick beats
    an evergreen resource every time it's available); free and
    kid-friendly break ties, since those are this audience's two biggest
    filters. Returns None only when the region has nothing at all to
    pick from.

    Excludes a `recurring` occurrence (ROADMAP.md item 141) from the
    heuristic specifically - the soonest-dated tiebreak would otherwise
    pick the same standing weekly market every single build for its
    entire season, the same "reads as automated filler" risk item 141
    raised for the subject line, applied to the page's other headline
    slot. `editors_pick_url` can still target one explicitly if an owner
    ever wants to feature it - only the automatic pick avoids it.
    """
    # An Editor's Pick is an editorial choice; a paid Featured event (item
    # 245) is already labelled as one and never doubles as the other.
    candidates = [e for b in blocks for e in b["events"] if not e.get("sponsored_by")] + evergreen
    candidates = [c for c in candidates if c.get("title") and c.get("url")]
    if not candidates:
        return None

    override_url = (region_cfg["region"].get("editors_pick_url") or "").strip()
    if override_url:
        for item in candidates:
            if item["url"] == override_url:
                return item
        logger.warning(
            "editors_pick_url %r not found among %s's items this build - falling back to heuristic",
            override_url, region_cfg["region"]["id"],
        )

    def sort_key(item: dict) -> tuple:
        has_date = item.get("date_iso") is not None
        date_key = item["date_iso"] if has_date else "9999"
        tags = item.get("tags", [])
        tag_bonus = -(("free" in tags) + ("kid_friendly" in tags))
        return (not has_date, date_key, tag_bonus)

    heuristic_candidates = [c for c in candidates if not c.get("recurring")] or candidates
    return sorted(heuristic_candidates, key=sort_key)[0]


def all_tags_present(*blocks_and_evergreen: list[dict]) -> list[dict]:
    """Collect every distinct tag actually in use, for the filter bar -
    no point rendering a filter chip for a tag nothing on the page has.
    """
    seen: set[str] = set()
    for group in blocks_and_evergreen:
        for item in group:
            seen.update(item.get("tags", []))
    return [{"id": t, **tag_display(t)} for t in sorted(seen)]


def build_answer_block(region: dict) -> str:
    """A short, plain-language paragraph literally answering "what is
    this page" (ROADMAP.md Phase 11 #22 - GEO). AI answer engines cite
    pages that state their own purpose in ~40-60 words near the top,
    separately from meta descriptions (which they don't reliably read).
    Deliberately generic/accurate rather than citing specific event
    counts or dates - those go stale the moment an AI's cached copy is a
    day old, and a wrong specific is worse than a true generality.

    Doesn't repeat the automation/frequency claim `tagline` already
    makes (item 126 rewrote every region's tagline to lead with "Pulled
    automatically from ... several times a week") - this text is always
    rendered directly after that tagline in the same on-page paragraph,
    so saying it twice read as repetitive rather than reinforcing. Adds
    only what the tagline doesn't: that each listing links back to the
    official source itself.
    """
    return (
        f"{region['name']} ({region['zip']}), {region['state']}: {region['tagline']} "
        f"Every listing links directly to the official village, library, "
        f"and park district source for full details."
    )


def build_region_map_embed_url(region: dict, maps: dict) -> str | None:
    """URL for the interactive street map iframe layered over the inline
    SVG (revisits ROADMAP.md Phase 11 #53 - the owner reported on 2026-09-15 that
    no real map was displaying on any page, which was accurate: #53 had
    removed the embed entirely, leaving only the SVG and an outbound
    link).

    That removal was well-reasoned - an iframe's `load` event fires even
    when navigation is blocked, so the "reveal only on successful load"
    fallback it replaced never caught the failure it existed to hide.
    This restores a real map while keeping that lesson: **no load
    detection is attempted at all**. The SVG sits permanently underneath
    at `.map-fallback`, so the honest floor is always painted; the iframe
    simply covers it when it renders. Nothing has to guess whether a
    cross-origin frame succeeded.

    OpenStreetMap's export embed is the default because it needs no API
    key and no billing account. Google's Maps Embed API is used instead
    only when a real key is configured - see config/maps.yaml.

    Returns None when a region has no lat/lon rather than guessing a
    location, same as build_region_map_link_url().
    """
    lat, lon = region.get("lat"), region.get("lon")
    if lat is None or lon is None:
        return None
    if maps.get("provider") == "google" and maps.get("google_api_key"):
        return (
            "https://www.google.com/maps/embed/v1/view"
            f"?key={quote(maps['google_api_key'], safe='')}"
            f"&center={lat},{lon}&zoom=13"
        )
    # A small bounding box around the village centre - roughly a 4-5 mile
    # window at this latitude, wide enough to show the neighbouring towns
    # this site actually covers rather than a single street corner.
    pad_lat, pad_lon = 0.045, 0.060
    bbox = f"{lon - pad_lon:.4f},{lat - pad_lat:.4f},{lon + pad_lon:.4f},{lat + pad_lat:.4f}"
    return (
        "https://www.openstreetmap.org/export/embed.html"
        f"?bbox={quote(bbox, safe=',')}&layer=mapnik&marker={lat},{lon}"
    )


def build_region_map_link_url(region: dict) -> str | None:
    """A plain, clickable Google Maps link centered on the region's
    coordinates - real streets, pan/zoom, no API key or Google Cloud
    billing account required.

    This used to be an `<iframe>` embed (`maps.google.com/maps?
    q=...&output=embed`) with a client-side "reveal on successful load"
    fallback (ROADMAP.md Phase 11 #53's original ask). Built and tested
    that against the real generated site with Playwright before shipping
    it, per this project's own discipline of verifying rather than
    assuming - and it doesn't work: an iframe's `load` event fires once
    the browser finishes navigating the frame *at all*, including to an
    error/blocked page, which is indistinguishable from a real map from
    the parent document (cross-origin, so its content can't be
    inspected). Confirmed directly: in this sandbox, where the request is
    proxy-blocked, the iframe still reported `loaded`, revealing the
    exact broken box the fallback was built to prevent - the fix didn't
    fix anything.
    A plain outbound link has no such failure mode: it either opens a
    real map when clicked or it doesn't, with no false-positive
    "looks fine" state in between. The reliable inline-SVG region map
    (item 17, `build_region_map`) is the primary visual now; this is a
    small link next to it, not the page's largest element.
    Returns None when a region has no lat/lon rather than guessing one.
    """
    lat, lon = region.get("lat"), region.get("lon")
    if lat is None or lon is None:
        return None
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"


def build_guide_faq(region: dict, region_base_url: str) -> list[dict]:
    """Real, honest FAQ content for a guide page (ROADMAP.md Phase 11 #22
    follow-up) - about how the site itself works, not fabricated facts
    about specific venues, hours, or prices. FAQPage schema requires the
    answer text to also be visible on the page (Google's own guidance),
    so this list is rendered as real HTML in region.html.j2 and the exact
    same text is what build_faq_json_ld() embeds - never two versions of
    the same answer that could drift apart.
    """
    weekend_url = region_base_url + "this-weekend/"
    submit_url = "https://github.com/randerson-23/agent-business/issues/new?template=event-submission.yml"
    sponsor_url = SITE_BASE_URL + "sponsor/"
    return [
        {
            "question": "How current is this guide?",
            "answer": (
                "It's regenerated automatically from the village, library, "
                "and park district's own listings, typically several times "
                "a week - not a one-time write-up that goes stale."
            ),
        },
        {
            "question": "Is this every event or business, or just what's listed here?",
            "answer": (
                "Only what the linked public sources publish. For full "
                "details, hours, or anything not listed here, check the "
                "official page each item links to."
            ),
        },
        {
            "question": f"How do I see what's happening in {region['name']} this specific weekend?",
            "answer": (
                f'See the <a href="{weekend_url}">weekend view</a>, which '
                f"only shows items with a known date in the coming "
                f"Friday-Sunday."
            ),
        },
        {
            "question": "Can I add an event, or suggest a business for the directory?",
            "answer": (
                f'Yes - <a href="{submit_url}">submit an event</a> and a '
                f"person reviews it before it goes live, or a business "
                f'owner can <a href="{sponsor_url}">inquire about a listing</a>.'
            ),
        },
    ]


def build_faq_json_ld(faq_items: list[dict]) -> str:
    """schema.org/FAQPage structured data for build_guide_faq()'s items.
    Answer text here must exactly match what's rendered visibly on the
    page - Google's FAQPage guidance treats hidden-only FAQ markup as
    unreliable, so this is never the only place the Q&A exists.
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["question"],
                "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
            }
            for item in faq_items
        ],
    }
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def build_freshness_json_ld(region: dict, canonical_url: str, now: datetime) -> str:
    """A minimal WebPage node carrying `dateModified` (ROADMAP.md Phase
    11 #28) - a freshness signal both AI citation and human trust key on;
    content updated within 30 days earns roughly 3.2x more AI citations
    per the research behind item 22, and this site rebuilds weekly at
    minimum. Deliberately independent of build_event_json_ld's Event
    graph below (which is None when nothing has a resolved date) - a
    page's freshness is worth signaling even with zero dated events.

    `isPartOf` links every region page's WebPage node back to one
    consistent WebSite entity (SITE_NAME) - entity-naming audit,
    ROADMAP.md Phase 11 #22 follow-up. Without it, a search/AI crawler
    has to infer "these are all the same site" purely from repeated
    title-string matches; this states it directly.

    The WebSite's `publisher` is a reference (`@id` only) to the
    Organization entity fully defined on the About page
    (build_organization_json_ld, item 99) - who publishes this, not
    just what the site is called, is the entity-authority signal the
    item 98 correction found actually decides AI citation.
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": f"{region['name']} — {SITE_NAME}",
        "url": canonical_url,
        "dateModified": now.isoformat(),
        "isPartOf": {
            "@type": "WebSite",
            "name": SITE_NAME,
            "url": SITE_BASE_URL,
            "publisher": {"@id": ORGANIZATION_ID},
        },
    }
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def build_organization_json_ld() -> str:
    """The Organization entity every other page's WebSite node points at
    by `@id` (ROADMAP.md Phase 11 #99) - fully defined only here, on the
    About page, matching the standard schema.org pattern for one entity
    referenced across many pages rather than re-declared on each.

    Deliberately no `logo` or `sameAs`: neither exists yet (no logo
    asset in this repo, no real social/directory profile), and
    inventing either would break the same never-fabricate-a-fact
    discipline every other structured-data function in this file holds
    itself to.

    `founder` added 2026-09-22 (ROADMAP.md item 130) - the same real
    name now on the About page's own prose, not a separate invention.
    This is exactly the "who publishes this" entity-authority signal
    item 99's own docstring above says AI citation actually runs on;
    an anonymous Organization node was a weaker version of the same
    anonymity problem item 130 named for the visible page text.
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "@id": ORGANIZATION_ID,
        "name": SITE_NAME,
        "url": SITE_BASE_URL,
        "founder": {"@type": "Person", "name": "Ryan Anderson"},
    }
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def event_anchor_id(event: dict) -> str:
    """A stable, citable fragment id for one event card (ROADMAP.md item
    228): "ev-<title-slug>-<yyyy-mm-dd>", the same for the same event and
    date on every rebuild. An agent quoting an event can then cite this
    site's card rather than the source's page. Undated items get the slug
    alone."""
    slug = re.sub(r"[^a-z0-9]+", "-", (event.get("title") or "").lower()).strip("-")[:60].rstrip("-") or "event"
    day = (event.get("date_iso") or "")[:10]
    return f"ev-{slug}-{day}" if day else f"ev-{slug}"


def event_date_label(date_iso: str | None) -> str | None:
    """"Sat, Oct 4" for a card's visible date (ROADMAP.md item 234): the
    weekday lets a reader, or an agent quoting the card, catch a wrong
    date at a glance (item 219's lesson). The label is the date alone; the
    start time is a separate `time_label` (item 268). That used to be left
    out because ICS times parsed as naive UTC and could read five hours
    off; items 238 and the RSS fix that followed it made times local and
    checked, so the card now shows them."""
    if not date_iso:
        return None
    try:
        day = date.fromisoformat(date_iso[:10])
    except ValueError:
        return None
    return day.strftime("%a, %b %-d")


def prepare_event_cards(blocks: list[dict]) -> None:
    """Set `anchor_id` and `date_label` on every event card about to be
    rendered on one page. Ids are deduplicated within the page (a repeat
    gets "-2", "-3"), since an HTML id must be unique there; recomputed on
    every render, so the same event object can appear on several pages."""
    seen: dict[str, int] = {}
    for block in blocks:
        for event in block.get("events", []):
            base = event_anchor_id(event)
            seen[base] = seen.get(base, 0) + 1
            event["anchor_id"] = base if seen[base] == 1 else f"{base}-{seen[base]}"
            event["date_label"] = event_date_label(event.get("date_iso"))
            # ROADMAP.md item 268: the start time beside the date, and the
            # card text without the date-and-time header that library feeds
            # put at the start of a description (it would repeat both).
            event["time_label"] = event_time_label(event.get("date_iso"))
            event["card_detail"] = strip_description_header(event.get("detail"))



def build_event_json_ld(blocks: list[dict], page_url: str | None = None, region: dict | None = None) -> str | None:
    """schema.org/Event structured data for fetched events that have a
    real date (not the evergreen resource listings, and not an
    undated item - an "Event" with no date isn't a meaningful event,
    and some of these blocks are filtered views like /free that merge
    evergreen entries in alongside real events; date_iso is what tells
    them apart here). Returns None when there's nothing to embed rather
    than emitting an empty, pointless script block.

    `location` comes from schema_location() (ROADMAP.md item 238): the
    source's configured venue, else the town, never an invented address.
    """
    events = [e for b in blocks for e in b["events"] if e.get("title") and e.get("url") and e.get("date_iso")]
    if not events:
        return None
    graph = []
    for e in events:
        entry = {
            "@type": "Event",
            "name": e["title"],
            "url": e["url"],
            "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        }
        # ROADMAP.md item 228: point `url` at this page's own card so a
        # citation lands here, and keep the source's page in `sameAs` -
        # it still gets the credit and the click-out stays one tap away.
        if page_url and e.get("anchor_id"):
            entry["url"] = f"{page_url}#{e['anchor_id']}"
            entry["sameAs"] = e["url"]
        if e.get("detail"):
            entry["description"] = e["detail"]
        if e.get("date_iso"):
            entry["startDate"] = schema_start_date(e["date_iso"])
        entry["location"] = schema_location(e, region)
        if "free" in (e.get("tags") or []):
            entry["isAccessibleForFree"] = True
        if e.get("sponsored_by"):
            entry["sponsor"] = {"@type": "Organization", "name": e["sponsored_by"]}
        graph.append(entry)
    payload = {"@context": "https://schema.org", "@graph": graph}
    # Escape "</" so an event title/description containing it can't break
    # out of the <script> tag it's embedded in.
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def render_region_page(
    region_cfg: dict,
    blocks: list[dict],
    sponsor: dict,
    evergreen: list[dict],
    now: datetime,
    *,
    heading: str | None = None,
    subheading: str | None = None,
    empty_message: str | None = None,
    empty_cta_url: str | None = None,
    empty_cta_label: str | None = None,
    nav_current: str = "all",
    canonical_suffix: str = "",
    guides_url: str | None = None,
    directory_url: str | None = None,
    things_to_do_url: str | None = None,
    weather: list[dict] | None = None,
    newsletter: dict | None = None,
    editors_pick: dict | None = None,
    analytics: dict | None = None,
    answer_block: str | None = None,
    include_faq: bool = False,
    map_link_url: str | None = None,
    map_embed_url: str | None = None,
    nearby_regions: list[dict] | None = None,
    region_map: dict | None = None,
    build_scope_end_iso: str | None = None,
    stale_empty_message: str | None = None,
    empty_follow_url: str | None = None,
    empty_follow_label: str | None = None,
) -> str:
    env = get_template_env()
    template = env.get_template("region.html.j2")
    all_events_flat = [e for b in blocks for e in b["events"]] + evergreen
    region = region_cfg["region"]
    region_base_url = SITE_BASE_URL + region["id"] + "/"
    canonical_url = region_base_url + canonical_suffix
    faq = build_guide_faq(region, region_base_url) if include_faq else None
    # Distinct <title>/description per view (not just per region) so
    # search engines don't see four near-duplicate pages - the whole
    # point of shipping linkable date/price-scoped views in the first
    # place. Computed here rather than with string concatenation in the
    # template, which gets unreadable fast once quotes have to nest.
    page_title = f"{heading} — {SITE_NAME}" if heading else f"{region['name']} ({region['zip']}) — {SITE_NAME}"
    page_description = subheading or f"What's happening in {region['name']}, {region['state']} ({region['zip']}): {region['tagline']}"
    # ROADMAP.md item 163: dateModified below is machine-only; this is the
    # human-readable half of the same freshness claim, in the region's own
    # local date rather than a UTC timestamp - "last checked" (what's
    # actually true - this build did run) rather than "last updated"
    # (which would imply content changed, unverified here).
    last_checked_label = region_local_date(region, now).strftime("%A, %B %-d")
    prepare_event_cards(blocks)
    return template.render(
        region=region,
        issue_date=now.strftime("%B %d, %Y"),
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        sponsor=sponsor,
        blocks=blocks,
        evergreen=evergreen,
        available_tags=all_tags_present(all_events_flat),
        canonical_url=canonical_url,
        event_json_ld=build_event_json_ld(blocks, page_url=canonical_url, region=region),
        events_json_url=region_base_url + "events.json",
        freshness_json_ld=build_freshness_json_ld(region, canonical_url, now),
        answer_block=answer_block,
        last_checked_label=last_checked_label,
        map_link_url=map_link_url,
        map_embed_url=map_embed_url,
        nearby_regions=nearby_regions,
        region_map=region_map,
        faq=faq,
        faq_json_ld=build_faq_json_ld(faq) if faq else None,
        heading=heading,
        subheading=subheading,
        empty_message=empty_message,
        empty_cta_url=empty_cta_url,
        empty_cta_label=empty_cta_label,
        nav_current=nav_current,
        region_base_url=region_base_url,
        calendar_ics_url=region_base_url + "calendar.ics",
        page_title=page_title,
        page_description=page_description,
        hub_url=SITE_BASE_URL,
        guides_url=guides_url,
        directory_url=directory_url,
        things_to_do_url=things_to_do_url,
        weather=weather,
        newsletter=newsletter,
        editors_pick=editors_pick,
        analytics=analytics,
        og_image_url=SITE_BASE_URL + "og/" + region["id"] + ".png",
        trick_or_treat_in_season=is_trick_or_treat_season(now),
        build_scope_end_iso=build_scope_end_iso,
        stale_empty_message=stale_empty_message,
        empty_follow_url=empty_follow_url,
        empty_follow_label=empty_follow_label,
    )


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles - region-to-region distance is fixed
    (unlike the client-side "distance from you" feature), so it's safe to
    compute once at build time and bake the result into the page.
    """
    r = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def build_region_map(region_summaries: list[dict]) -> dict | None:
    """Region-level inline-SVG map for the hub (ROADMAP.md Phase 11 #17) -
    a simple equirectangular projection of each region's lat/lon (already
    in config for the "distance from you" feature) onto a small canvas.
    Not a real map - good enough to show relative position/spacing
    between covered towns without a tile provider, API key, JS library,
    or rate limit. Needs at least 2 regions with real coordinates to mean
    anything; returns None otherwise so the hub omits the block instead
    of drawing a single dot.
    """
    points = [r for r in region_summaries if r.get("lat") is not None and r.get("lon") is not None]
    if len(points) < 2:
        return None

    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)
    # Guard divide-by-zero if every region happens to share a lat or lon.
    lat_span = max(lat_max - lat_min, 0.01)
    lon_span = max(lon_max - lon_min, 0.01)

    width, height, pad = 320, 220, 55
    pins = []
    for p in points:
        x = pad + (p["lon"] - lon_min) / lon_span * (width - 2 * pad)
        # Invert: higher latitude (further north) draws higher on screen.
        y = pad + (lat_max - p["lat"]) / lat_span * (height - 2 * pad)
        pins.append({"name": p["name"], "path": p["path"], "x": round(x, 1), "y": round(y, 1)})

    lines = []
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            miles = _haversine_miles(points[i]["lat"], points[i]["lon"], points[j]["lat"], points[j]["lon"])
            lines.append(
                {
                    "x1": pins[i]["x"], "y1": pins[i]["y"],
                    "x2": pins[j]["x"], "y2": pins[j]["y"],
                    "mid_x": round((pins[i]["x"] + pins[j]["x"]) / 2, 1),
                    "mid_y": round((pins[i]["y"] + pins[j]["y"]) / 2, 1),
                    "miles": round(miles, 1),
                }
            )

    return {"width": width, "height": height, "pins": pins, "lines": lines}


def build_nearby_regions(current: dict, all_regions: list[dict], limit: int = 3) -> list[dict]:
    """Distances from one region to every other region, nearest first
    (ROADMAP.md Phase 11 #52). Multi-location IA best practice is hub ->
    all locations, each location -> hub, *and* cross-links between nearby
    locations - this site already had the first two; a region page's only
    navigation was "back to the hub", so a reader in one town had to
    return to the hub and guess which one was close. Computed once here
    at build time (region-to-region distance is fixed, unlike the
    client-side "distance from you" feature) using the same haversine
    already used for the hub map, then baked into the page as plain
    links - real, crawlable internal links, not client-side JS, which is
    also what actually distributes link equity across region pages
    instead of pooling it all at the hub.
    Returns [] (template omits the block) with fewer than 2 regions
    total, or if a region is missing real coordinates - same "don't draw
    something meaningless" discipline as build_region_map.
    """
    if current.get("lat") is None or current.get("lon") is None:
        return []
    others = [
        r
        for r in all_regions
        if r["id"] != current["id"] and r.get("lat") is not None and r.get("lon") is not None
    ]
    if not others:
        return []
    with_distance = [
        (r, _haversine_miles(current["lat"], current["lon"], r["lat"], r["lon"])) for r in others
    ]
    with_distance.sort(key=lambda pair: pair[1])
    return [
        {"name": r["name"], "path": f"{r['id']}/", "miles": round(miles, 1)}
        for r, miles in with_distance[:limit]
    ]


def render_hub_page(
    regions: list[dict],
    region_summaries: list[dict],
    now: datetime,
    newsletter: dict | None = None,
    analytics: dict | None = None,
    stats: dict | None = None,
    contact_email: str | None = None,
) -> str:
    env = get_template_env()
    template = env.get_template("hub.html.j2")
    return template.render(
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        region_summaries=region_summaries,
        canonical_url=SITE_BASE_URL,
        newsletter=newsletter,
        analytics=analytics,
        stats=stats,
        og_image_url=SITE_BASE_URL + "og/default.png",
        trick_or_treat_in_season=is_trick_or_treat_season(now),
        corrections_cta_url=build_corrections_cta_url(contact_email),
    )


def render_merged_hub_page(
    region_sections: list[dict],
    now: datetime,
    analytics: dict | None = None,
    *,
    slug: str = "this-weekend",
    heading: str = "This Weekend Near You",
    subheading: str,
    meta_description: str,
    empty_message: str,
    build_scope_end_iso: str | None = None,
    stale_empty_message: str | None = None,
    empty_follow_url: str | None = None,
    empty_follow_label: str | None = None,
    newsletter: dict | None = None,
    signup_headline: str | None = None,
) -> str:
    """A hub-level page merging one date/price-scoped view across every
    region, grouped by region so it's still clear where each one is.
    Originally built for /this-weekend only (ROADMAP.md Phase 11 #26);
    ROADMAP.md item 149 generalized it to also drive /free and /today,
    the same code path with a different predicate feeding
    `region_sections` - see the three call sites in main().
    """
    env = get_template_env()
    template = env.get_template("merged_hub.html.j2")
    prepare_event_cards([{"events": s["events"]} for s in region_sections])
    return template.render(
        region_sections=region_sections,
        heading=heading,
        subheading=subheading,
        page_title=heading,
        meta_description=meta_description,
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        canonical_url=SITE_BASE_URL + slug + "/",
        hub_url=SITE_BASE_URL,
        analytics=analytics,
        og_image_url=SITE_BASE_URL + "og/default.png",
        empty_message=empty_message,
        build_scope_end_iso=build_scope_end_iso,
        stale_empty_message=stale_empty_message,
        empty_follow_url=empty_follow_url,
        empty_follow_label=empty_follow_label,
        slug=slug,
        newsletter=newsletter or {"configured": False},
        signup_headline=signup_headline,
    )


# Open Graph raster size crawlers actually respect (ROADMAP.md Phase 11
# #75) - an SVG won't do here, unlike the favicon/map elsewhere on the
# site, so this is the one place the build needs real image rendering.
OG_IMAGE_SIZE = (1200, 630)

# Mirrors :root's light-mode palette in templates/hub.html.j2 - kept as
# plain RGB tuples here rather than re-parsed from CSS, since this is the
# only other place in the build that needs them.
OG_BG = (246, 239, 225)  # --bg
OG_INK = (43, 35, 24)  # --ink
OG_MUTED = (118, 106, 88)  # --muted
OG_ACCENT = (82, 107, 63)  # --accent
OG_ACCENT_2 = (193, 122, 61)  # --accent-2


def _wrap_og_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


@lru_cache(maxsize=None)
def _og_font(filename: str, size: int) -> ImageFont.FreeTypeFont:
    """Cached so build_og_images()'s one-call-per-region loop doesn't
    re-read and re-parse the same ~1.5MB of font files from disk on every
    region - the font objects themselves are read-only once loaded, so
    reuse across calls is safe.
    """
    return ImageFont.truetype(str(FONTS_DIR / filename), size)


def render_og_image(title: str, subtitle: str) -> Image.Image:
    """A build-time 1200x630 Open Graph image, one per region plus one
    default, rendered from the same palette as the site's own CSS so a
    link post into a local Facebook group doesn't show up as the grey box
    a missing og:image renders as. Uses the DejaVu Sans bundled under
    assets/fonts/ (see LICENSE-DejaVu.txt there) rather than a system font,
    so the result doesn't depend on what happens to be installed on
    whichever runner builds the site.
    """
    width, height = OG_IMAGE_SIZE
    img = Image.new("RGB", (width, height), OG_BG)
    draw = ImageDraw.Draw(img)

    wordmark_font = _og_font("DejaVuSans-Bold.ttf", 30)
    title_font = _og_font("DejaVuSans-Bold.ttf", 64)
    subtitle_font = _og_font("DejaVuSans.ttf", 32)

    margin = 80
    draw.ellipse([margin, 66, margin + 26, 92], fill=OG_ACCENT)
    draw.text((margin + 40, 60), "WITHIN TEN", font=wordmark_font, fill=OG_ACCENT)
    draw.rectangle([margin, 122, margin + 90, 126], fill=OG_ACCENT_2)

    y = 220
    for line in _wrap_og_text(draw, title, title_font, width - 2 * margin)[:2]:
        draw.text((margin, y), line, font=title_font, fill=OG_INK)
        y += 78

    y += 16
    for line in _wrap_og_text(draw, subtitle, subtitle_font, width - 2 * margin)[:2]:
        draw.text((margin, y), line, font=subtitle_font, fill=OG_MUTED)
        y += 44

    draw.rectangle([0, height - 14, width, height], fill=OG_ACCENT)
    return img


def build_og_images(region_summaries: list[dict]) -> dict[str, Image.Image]:
    images = {"default": render_og_image(SITE_NAME, "Everything worth doing, ten miles out")}
    for r in region_summaries:
        # "several times a week" (not "updated weekly") - matches the
        # cadence every other on-page/GEO surface states (tagline, the
        # answer block, llms.txt), since this image is what a link
        # preview actually shows when a region page is shared - the same
        # inconsistency item 128 just fixed in prose, one rendering
        # surface over.
        images[r["id"]] = render_og_image(r["name"], f"What's happening in {r['name']} — updated several times a week")
    return images


# ROADMAP.md item 205: the same dark-bg/red-"W" mark every template's own
# inline-SVG favicon already draws (viewBox 100, rect fill #201e1d, text
# fill #ec3013, font-weight 800) - rendered as real PNGs here because a
# Web App Manifest's `icons` list needs raster files at fixed sizes, not
# a data URI. Deliberately not reusing OG_BG/OG_ACCENT above: those mirror
# an older palette than the current Modernist one (item 174) the favicon
# and every template's CSS actually use now.
APP_ICON_BG = (0x20, 0x1E, 0x1D)
APP_ICON_ACCENT = (0xEC, 0x30, 0x13)
APP_ICON_SIZES = (192, 512)


def render_app_icon(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), APP_ICON_BG)
    draw = ImageDraw.Draw(img)
    font = _og_font("DejaVuSans-Bold.ttf", round(size * 0.58))
    bbox = draw.textbbox((0, 0), "W", font=font)
    x = (size - (bbox[2] - bbox[0])) / 2 - bbox[0]
    y = (size - (bbox[3] - bbox[1])) / 2 - bbox[1]
    draw.text((x, y), "W", font=font, fill=APP_ICON_ACCENT)
    return img


def build_app_icons() -> dict[int, Image.Image]:
    return {size: render_app_icon(size) for size in APP_ICON_SIZES}


def build_web_manifest() -> str:
    """docs/manifest.webmanifest (ROADMAP.md item 205) - lets a returning
    reader add the site to their phone's Home Screen as a standalone app.
    Deliberately no service worker: a cache-first one would reintroduce
    the exact stale-/today/ problem items 199/200 just fixed, in a form
    harder to notice, because the reader's device would keep serving an
    old build after the server had a new one.
    """
    manifest = {
        "name": SITE_NAME,
        "short_name": SITE_NAME,
        "start_url": SITE_BASE_URL,
        "display": "standalone",
        "background_color": "#f3f2f2",
        "theme_color": "#ec3013",
        "icons": [
            {"src": f"icons/icon-{size}.png", "sizes": f"{size}x{size}", "type": "image/png"}
            for size in APP_ICON_SIZES
        ],
    }
    return json.dumps(manifest, indent=2) + "\n"


def collect_sitemap_urls(region_summaries: list[dict]) -> list[str]:
    urls = [
        SITE_BASE_URL,
        SITE_BASE_URL + "this-weekend/",
        SITE_BASE_URL + "today/",
        SITE_BASE_URL + "free/",
        SITE_BASE_URL + "sponsor/",
        SITE_BASE_URL + "about/",
        SITE_BASE_URL + "trick-or-treat/",
    ]
    for r in region_summaries:
        base = SITE_BASE_URL + r["path"]
        urls += [
            base,
            base + "this-weekend/",
            base + "today/",
            base + "free/",
            base + "directory/",
            base + "things-to-do/",
        ]
        if r.get("guide_slugs"):
            urls.append(base + "guides/")
            urls += [base + f"guides/{slug}/" for slug in r["guide_slugs"]]
    return urls


def build_sitemap_xml(region_summaries: list[dict], now: datetime) -> str:
    lastmod = now.strftime("%Y-%m-%d")
    urls = collect_sitemap_urls(region_summaries)
    entries = "\n".join(
        f"  <url>\n    <loc>{u}</loc>\n    <lastmod>{lastmod}</lastmod>\n  </url>" for u in urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n"
        "</urlset>\n"
    )


FEED_MAX_ITEMS = 50


def build_pins_xml(
    groups: list[tuple[str, str, str, list[dict]]],
    friday: date,
    weekend_date_range: str,
    now: datetime,
    image_sizes: dict[str, int],
    trick_or_treat_in_season: bool = False,
) -> str:
    """A small RSS 2.0 feed at /pins.xml for Pinterest's auto-publish
    (ROADMAP.md item 253), separate from /feed.xml on purpose: Pinterest
    rejects a feed whose item links are not on the claimed domain, and
    /feed.xml links every event to its publisher. Here every link is a page
    on this site and every item has an image.

    `groups` is [(region_id, region_name, region_page_url, weekend_events)].
    One item per town that actually has events this weekend (a Pin for an
    empty weekend would send people to nothing), guid'd by the Friday so each
    week is a new Pin. Plus one /trick-or-treat/ item while that page's
    season runs. `image_sizes` maps an OG image name ("default" or a region
    id) to its byte size, for the <enclosure>.
    """
    def enclosure(name: str) -> str:
        return (
            f'    <enclosure url="{xml_escape(SITE_BASE_URL + "og/" + name + ".png")}" '
            f'type="image/png" length="{image_sizes.get(name, 0)}"/>\n'
        )

    pub_date = format_datetime(now.astimezone(timezone.utc))
    items = []
    for region_id, region_name, page_url, events in groups:
        dated = [e for e in events if e.get("title") and e.get("date_iso")]
        if not dated or region_id not in image_sizes:
            continue
        titles = [e["title"] for e in sorted(dated, key=lambda e: e["date_iso"])]
        shown = titles[:3]
        more = f" and {len(titles) - 3} more" if len(titles) > 3 else ""
        description = f"{weekend_date_range} in {region_name}: " + "; ".join(shown) + more + "."
        items.append(
            "  <item>\n"
            f"    <title>{xml_escape(f'This weekend in {region_name} ({weekend_date_range})')}</title>\n"
            f"    <link>{xml_escape(page_url + 'this-weekend/')}</link>\n"
            f'    <guid isPermaLink="false">{xml_escape(page_url + "this-weekend/#" + friday.isoformat())}</guid>\n'
            f"    <description>{xml_escape(description)}</description>\n"
            f"    <pubDate>{pub_date}</pubDate>\n"
            + enclosure(region_id)
            + "  </item>\n"
        )
    if trick_or_treat_in_season:
        items.append(
            "  <item>\n"
            "    <title>Trick-or-treat hours in every town</title>\n"
            f"    <link>{xml_escape(SITE_BASE_URL + 'trick-or-treat/')}</link>\n"
            f'    <guid isPermaLink="false">{xml_escape(SITE_BASE_URL + "trick-or-treat/#" + str(now.year))}</guid>\n'
            "    <description>Each village's official trick-or-treat hours, plus the Halloween events nearby.</description>\n"
            f"    <pubDate>{pub_date}</pubDate>\n"
            + enclosure("default")
            + "  </item>\n"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n<channel>\n'
        f"  <title>{xml_escape(SITE_NAME)} - weekend Pins</title>\n"
        f"  <link>{xml_escape(SITE_BASE_URL)}</link>\n"
        "  <description>One weekend guide per town, for Pinterest.</description>\n"
        f"  <lastBuildDate>{pub_date}</lastBuildDate>\n"
        + "".join(items)
        + "</channel>\n</rss>\n"
    )


def build_feed_xml(feed_items: list[dict], now: datetime, source_completeness: dict | None = None) -> str:
    """A real RSS 2.0 feed at /feed.xml (ROADMAP.md Phase 11 #79) - the
    site syndicating its *own* aggregated events, not republishing onto
    a third-party platform (that's item 48, correctly skipped for a
    different reason). Zero-dependency distribution: a feed reader,
    local-news aggregator, or AI crawler that polls this learns about
    new events without re-scraping the whole site, feeding the same
    freshness/GEO strategy item 22 already bets on.

    Honesty note: this pipeline has no "date first seen" for an event -
    every build re-fetches from scratch - so this isn't a conventional
    "recently published" feed. It's an upcoming-events calendar feed,
    ordered soonest-first, with each item's <pubDate> set to the event's
    own date rather than an invented publish timestamp.

    feed_items: dicts with title/url/detail/date_iso/region_name, already
    filtered to only real events with a resolved date (same filter every
    other structured-data feature in this file uses).

    A real bug, found and fixed the same day it was noticed (ROADMAP.md
    item 145): a `<guid>` must be unique per item - RSS readers and
    aggregators use it for deduplication, many treating a repeat as "the
    same item again" rather than a new one. Multiple events sharing one
    `url` (a recurring event's every occurrence links the same organiser
    page - item 141 - and even a pre-existing case: a multi-day festival
    like Oktoberfest/Fall Festival, item 71's `series`, already linked
    both days to the same info page) used to emit the identical
    `<guid isPermaLink="true">` for every one of them - confirmed against
    a real build's `docs/feed.xml`, which had 6 items for one farmers
    market, all six with byte-identical guids. A feed reader that dedupes
    by guid would surface at most one of six real, distinct occurrences,
    and `isPermaLink="true"` was doubly wrong regardless - one URL cannot
    truthfully be six different dates' "permanent link" at once. Only a
    `url` that's actually unique among this build's items keeps the
    simple `isPermaLink="true"` guid; a shared one gets the date folded
    in and `isPermaLink="false"`, the RFC-documented way to say "this
    guid is a stable identifier, not a dereferenceable page of its own."
    """
    dated = sorted(feed_items, key=lambda e: e["date_iso"])[:FEED_MAX_ITEMS]
    url_counts = Counter(e["url"] for e in dated)
    description = (
        f"Upcoming events across every {SITE_NAME} region, soonest first - "
        "aggregated automatically from village, library, park district and school-district calendars."
    )
    if source_completeness:
        description += (
            f" This build reached {source_completeness.get('reporting', 0)} of "
            f"{source_completeness.get('expected', 0)} configured sources."
            + last_good_sentence(source_completeness)
        )
    items = []
    for e in dated:
        pub_dt = datetime.fromisoformat(e["date_iso"])
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        title = xml_escape(f"{e['region_name']}: {e['title']}")
        if url_counts[e["url"]] > 1:
            guid_value, is_permalink = f"{e['url']}#{e['date_iso']}", "false"
        else:
            guid_value, is_permalink = e["url"], "true"
        items.append(
            "  <item>\n"
            f"    <title>{title}</title>\n"
            f"    <link>{xml_escape(e['url'])}</link>\n"
            f"    <guid isPermaLink=\"{is_permalink}\">{xml_escape(guid_value)}</guid>\n"
            f"    <description>{xml_escape(e.get('detail') or '')}</description>\n"
            f"    <pubDate>{format_datetime(pub_dt)}</pubDate>\n"
            "  </item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n'
        "<channel>\n"
        f"  <title>{SITE_NAME} — Upcoming Local Events</title>\n"
        f"  <link>{SITE_BASE_URL}</link>\n"
        f"  <description>{xml_escape(description)}</description>\n"
        f"  <lastBuildDate>{format_datetime(now)}</lastBuildDate>\n"
        + "\n".join(items)
        + ("\n" if items else "")
        + "</channel>\n"
        "</rss>\n"
    )


# ROADMAP.md item 230: how far ahead the machine-readable event index looks.
EVENTS_JSON_DAYS = 14


def _event_list_item(event: dict, page_url: str, position: int) -> dict:
    """One schema.org ListItem wrapping an Event. `url` is the event's card
    on this site (item 228's anchor), with the source in `sameAs`, and
    `location` from schema_location() (item 238)."""
    entry = {
        "@type": "Event",
        "name": event["title"],
        "startDate": schema_start_date(event["date_iso"]),
        "url": f"{page_url}#{event.get('anchor_id') or event_anchor_id(event)}",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "location": schema_location(event),
    }
    if event.get("url"):
        entry["sameAs"] = event["url"]
    if event.get("detail"):
        entry["description"] = event["detail"]
    if "free" in (event.get("tags") or []):
        entry["isAccessibleForFree"] = True
    if event.get("sponsored_by"):
        entry["sponsor"] = {"@type": "Organization", "name": event["sponsored_by"]}
    return {"@type": "ListItem", "position": position, "item": entry}


def build_events_json(groups: list[tuple[str, str, list[dict]]], name: str, now: datetime) -> str:
    """A schema.org ItemList of upcoming Events (ROADMAP.md item 230) - the
    clean machine-readable index agents and NLWeb-style tools read most
    easily. `groups` is [(region_name, region_page_url, events)]; events
    are ordered by start date across groups."""
    rows = [(e, page_url) for _name, page_url, events in groups for e in events if e.get("title") and e.get("date_iso")]
    rows.sort(key=lambda r: r[0]["date_iso"])
    payload = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": name,
        "dateModified": now.isoformat(timespec="seconds"),
        "numberOfItems": len(rows),
        "itemListElement": [_event_list_item(e, page_url, i) for i, (e, page_url) in enumerate(rows, start=1)],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def build_llms_full_txt(groups: list[tuple[str, str, list[dict]]], weekend_date_range: str) -> str:
    """llms-full.txt (ROADMAP.md item 230): this weekend's events as plain
    text, grouped by town, so an agent fetching the llms.txt family gets
    the content itself and not only links. Each line links to the
    event's card on this site."""
    lines = [f"# {SITE_NAME} — this weekend ({weekend_date_range})", ""]
    for region_name, page_url, events in groups:
        lines.append(f"## {region_name}")
        dated = [e for e in events if e.get("title") and e.get("date_iso")]
        if not dated:
            lines.append("- Nothing dated yet this weekend.")
        for e in sorted(dated, key=lambda e: e["date_iso"]):
            label = event_date_label(e["date_iso"]) or ""
            featured = f" (Featured, presented by {e['sponsored_by']})" if e.get("sponsored_by") else ""
            lines.append(f"- {label}: {e['title']}{featured} — {page_url}#{event_anchor_id(e)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_llms_txt(region_summaries: list[dict], source_completeness: dict | None = None) -> str:
    """llms.txt (llmstxt.org convention, ROADMAP.md Phase 11 #22 - GEO):
    a plain-language map of the site for an AI agent/crawler to read
    directly, generated at build time from the same region_summaries the
    sitemap uses - so it can never drift out of sync with what's actually
    live the way a hand-written one would.
    """
    lines = [
        f"# {SITE_NAME}",
        "",
        "> A hyperlocal weekend/trip planner for Chicago-area ZIP codes. "
        "Aggregates village news, public library events, and park "
        "district programs per town, rebuilt automatically (usually "
        "multiple times a week), so it stays current without a human "
        "keeping it that way.",
        "",
    ]
    if source_completeness:
        lines += [
            f"As of this build, {source_completeness.get('reporting', 0)} of "
            f"{source_completeness.get('expected', 0)} configured sources reported "
            "successfully; the rest is a source that didn't answer this time, not "
            "missing coverage." + last_good_sentence(source_completeness),
            "",
        ]
    lines.append("## Regions")
    for r in region_summaries:
        base = SITE_BASE_URL + r["path"]
        lines.append(f"- [{r['name']} ({r['zip']})]({base}): {r['tagline']}")
    lines += ["", "## This weekend", f"- [Across every region]({SITE_BASE_URL}this-weekend/)"]
    for r in region_summaries:
        base = SITE_BASE_URL + r["path"]
        lines.append(f"- [{r['name']} — this weekend]({base}this-weekend/)")
    # ROADMAP.md item 149: same GEO discoverability as the "This weekend"
    # section above, for the two hub-level views it added.
    lines += ["", "## Today", f"- [Across every region]({SITE_BASE_URL}today/)"]
    for r in region_summaries:
        base = SITE_BASE_URL + r["path"]
        lines.append(f"- [{r['name']} — today]({base}today/)")
    lines += ["", "## Free things to do", f"- [Across every region]({SITE_BASE_URL}free/)"]
    for r in region_summaries:
        base = SITE_BASE_URL + r["path"]
        lines.append(f"- [{r['name']} — free]({base}free/)")
    # ROADMAP.md item 158: the evergreen counterpart to the dated sections
    # above - "what is there to do here at all", not tied to a weekend.
    lines += ["", "## Things to do (evergreen)"]
    for r in region_summaries:
        base = SITE_BASE_URL + r["path"]
        lines.append(f"- [{r['name']} — things to do]({base}things-to-do/)")
    guide_lines = [
        f"- [{g['title']} — {r['name']}]({SITE_BASE_URL}{r['path']}guides/{g['slug']}/)"
        for r in region_summaries
        for g in r.get("guides", [])
    ]
    if guide_lines:
        lines += ["", "## Guides"] + guide_lines
    calendar_lines = [
        f"- [{r['name']} — subscribable calendar (.ics)]({SITE_BASE_URL}{r['path']}calendar.ics)"
        for r in region_summaries
    ]
    lines += ["", "## Calendars"] + calendar_lines
    lines += ["", "## Sponsorship", f"- [Sponsor a region]({SITE_BASE_URL}sponsor/)"]
    lines += ["", "## About", f"- [Who publishes this, and why]({SITE_BASE_URL}about/)"]
    lines += ["", "## Seasonal", f"- [Trick-or-treat hours, all {len(region_summaries)} towns]({SITE_BASE_URL}trick-or-treat/)"]
    lines += ["", "## Feed", f"- [RSS: upcoming events across every region]({SITE_BASE_URL}feed.xml)"]
    # ROADMAP.md item 230: the machine-readable index, and the plain-text
    # content itself, for agents that read this file family.
    lines += [
        "",
        f"## Machine-readable events (schema.org JSON-LD, next {EVENTS_JSON_DAYS} days)",
        f"- [Every region]({SITE_BASE_URL}events.json)",
    ]
    lines += [f"- [{r['name']}]({SITE_BASE_URL}{r['path']}events.json)" for r in region_summaries]
    lines += ["", "## Full text", f"- [This weekend's events, as plain text]({SITE_BASE_URL}llms-full.txt)"]
    return "\n".join(lines) + "\n"


# AI crawlers worth naming explicitly (ROADMAP.md Phase 11 #22 - GEO).
# `Allow: /` under `User-agent: *` already covers these; naming them is a
# deliberate signal, not a behavior change - fewer than 10% of sources
# cited by AI answer engines rank in Google's organic top 10 for the same
# query, so leaving crawler access unstated costs a channel the existing
# SEO work (Phase 9) doesn't buy on its own.
_AI_CRAWLERS = (
    "GPTBot", "ChatGPT-User", "OAI-SearchBot",  # OpenAI
    "ClaudeBot", "Claude-Web", "anthropic-ai",  # Anthropic
    "PerplexityBot", "Perplexity-User",  # Perplexity
    "Google-Extended",  # Google Gemini / AI Overviews training+grounding
    "CCBot",  # Common Crawl, widely used to train/ground other models
    # ROADMAP.md item 230: published Meta and Apple agent/crawler names.
    "Meta-ExternalAgent", "Meta-ExternalFetcher",  # Meta (incl. Muse fetches)
    "Applebot-Extended",  # Apple Intelligence
)


def build_robots_txt() -> str:
    lines = ["User-agent: *", "Allow: /", ""]
    for bot in _AI_CRAWLERS:
        lines += [f"User-agent: {bot}", "Allow: /", ""]
    lines.append(f"Sitemap: {SITE_BASE_URL}sitemap.xml")
    return "\n".join(lines) + "\n"


def structured_date_coverage(blocks: list[dict]) -> tuple[int, int]:
    """(events with a machine-readable date, total events) - an event
    without date_iso is invisible to schema.org/Event rich results and
    can't be added to a calendar, so this is worth watching for silent
    regressions as sources change, not just a one-time check.
    """
    events = [e for b in blocks for e in b["events"]]
    dated = sum(1 for e in events if e.get("date_iso"))
    return dated, len(events)


def region_local_date(region: dict, now_utc: datetime) -> date:
    """"Today" in a region's own timezone, not the build server's -
    matters for what counts as "today"/"this weekend" near midnight.
    Falls back to the UTC date if the configured timezone is missing or
    invalid rather than failing the whole build over it.
    """
    tz_name = region.get("timezone")
    if tz_name:
        try:
            return now_utc.astimezone(ZoneInfo(tz_name)).date()
        except Exception:
            logger.warning("Invalid timezone %r for region %s, using UTC", tz_name, region.get("id"))
    return now_utc.date()


def format_date_range(start: date, end: date) -> str:
    """"Aug 29–30" when both dates share a month, "Aug 29–Sep 1" when
    they don't - avoids the redundant "Aug 29–Aug 30" a naive per-date
    format would produce.
    """
    if start == end:
        return start.strftime("%b %-d")
    if start.month == end.month:
        return f"{start.strftime('%b %-d')}–{end.day}"
    return f"{start.strftime('%b %-d')}–{end.strftime('%b %-d')}"


def build_weekly_summary_txt(
    region: dict, weekend_events: list[dict], evergreen: list[dict], region_url: str, weekend_date_range: str
) -> str:
    """A short, plain-text block the owner can paste into an existing
    local Facebook group in about thirty seconds (ROADMAP.md Phase 11
    #33) - distribution without taking on a managed community's
    moderation duty, which the near-zero-owner-time constraint rules out.
    Built from the same real, already-fetched data every other view
    uses - never invents an event to fill space. Honest empty state when
    nothing's dated this weekend, same philosophy as every other view.

    Split into a post body and a separate first-comment block (ROADMAP.md
    Phase 11 #76) rather than one block with the link inline - Facebook
    has down-weighted posts containing an external link since 2017, and
    a reply to your own post is worth roughly 27x a like, so the link
    belongs in the first comment, not the post, and the post should end
    on a real question rather than a parenthetical to invite exactly
    that reply.

    Leads with a `SUBJECT:` line (ROADMAP.md Phase 11 #91) matching this
    file's own `POST`/`FIRST COMMENT` convention - a label for whoever's
    reading, not text to paste into Facebook, same distinction that
    landed the subject line in the wrong place in the email template.
    """
    subject_line = f"SUBJECT: {build_email_subject_line(region, weekend_events)}\n\n"
    post_lines = [f"What's happening in {region['name']} this weekend ({weekend_date_range}):", ""]
    if weekend_events:
        for event in weekend_events[:6]:
            prefix = f"{event['date']} — " if event.get("date") else ""
            featured = f" (Featured, presented by {event['sponsored_by']})" if event.get("sponsored_by") else ""
            post_lines.append(f"- {prefix}{event['title']}{featured}")
    else:
        highlights = [e for e in evergreen if "free" in e.get("tags", [])][:3]
        if highlights:
            post_lines.append("Nothing new dated for this weekend yet, but a few things worth knowing about:")
            for item in highlights:
                post_lines.append(f"- {item['title']}")
        else:
            post_lines.append("Nothing dated for this weekend yet - the full guide has what's coming up.")
    post_lines.append("")
    post_lines.append("Anything I've missed this weekend?")

    return (
        subject_line
        + "POST (paste this as your post - no link, so Facebook doesn't downrank it):\n\n"
        + "\n".join(post_lines)
        + "\n\n"
        "FIRST COMMENT (reply to your own post with this right after - the link goes here instead):\n\n"
        f"See everything: {region_url}\n"
        "(Pulled automatically from the village, library, and park district — several times a week.)\n"
    )


_SUBJECT_LINE_STOPWORDS = {"and", "the", "a", "an", "of"}


def _significant_tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w for w in words if w not in _SUBJECT_LINE_STOPWORDS}


def _is_near_duplicate_title(a: str, b: str) -> bool:
    """Two titles that would read as "the same thing" named twice in one
    subject line - e.g. "Oktoberfest" and "Fall Festival & Oktoberfest"
    (ROADMAP.md Phase 11 #86, a real pair this shipped with). Neither
    title is wrong and neither should be dropped from the digest itself
    - this only decides which two get *named* in the subject line.
    One title's significant words being a subset of the other's (after
    lowercasing and dropping stopwords/"&") is close enough to collide.
    """
    tokens_a, tokens_b = _significant_tokens(a), _significant_tokens(b)
    if not tokens_a or not tokens_b:
        return False
    return tokens_a <= tokens_b or tokens_b <= tokens_a


def build_email_subject_line(region: dict, weekend_events: list[dict]) -> str:
    """ROADMAP.md Phase 11 #80: settle the subject-line format before
    there's a list whose open rates become a trend somebody judges,
    since the habit calcifies the moment sending starts. Format: name
    the town, lead with the specific, state the count - "This weekend
    in Mount Prospect: Oktoberfest, a free fall fest, and 6 more."
    is the pass's own example, but real event titles are used here
    rather than inventing descriptive phrasing not grounded in the
    actual data - clarity over cleverness stays true either way, and a
    real title is never wrong the way a guessed paraphrase could be.

    A selection rule, not a filter (item 86): the second title named is
    the first one that doesn't read as a near-duplicate of the first,
    so two real, distinct events never collapse into what looks like
    one event named twice. If every remaining title collides, name just
    the first and let the count carry the rest.

    Only picks from `attendable` events (item 90, found from a real send
    that headlined "Half-Day Student Attendance" as a weekend plan): a
    school closure or office closure is real and worth knowing, but
    nobody drives somewhere for one, so it must never win the subject
    line. Falls back to the honest "what's coming up" empty state if a
    weekend has no attendable events at all, same as having none at all.

    Also never picks a `recurring` event (ROADMAP.md item 141) - the same
    farmers market named in twenty consecutive subject lines is exactly
    how a digest starts reading as automated filler, the design caveat
    item 141 raised explicitly. A recurring event still counts toward
    the "and N more" tally, same as a non-attendable one doesn't count
    at all - two different kinds of "real, but not the headline."
    """
    name = region["name"]
    # A paid Featured event never decides the subject line (item 245).
    attendable = [e for e in weekend_events if e.get("attendable", True) and not e.get("sponsored_by")]
    if not attendable:
        return f"This weekend in {name}: what's coming up"

    headline_candidates = [e for e in attendable if not e.get("recurring")]
    if not headline_candidates:
        return f"This weekend in {name}: what's coming up"

    total = len(attendable)
    first = headline_candidates[0]["title"]
    if total == 1:
        return f"This weekend in {name}: {first}"

    second = next(
        (e["title"] for e in headline_candidates[1:] if not _is_near_duplicate_title(first, e["title"])),
        None,
    )
    if second is None:
        remaining = total - 1
        return f"This weekend in {name}: {first}, and {remaining} more"

    more = total - 2
    if more == 0:
        return f"This weekend in {name}: {first} and {second}"
    return f"This weekend in {name}: {first}, {second}, and {more} more"


# ROADMAP.md item 207: preview text shows 35-140 characters depending
# on the mail client, with 40-90 the reported safe zone across major
# clients. 90 keeps every client's truncation point inside real content
# rather than mid-word in a client with a shorter window.
PREHEADER_MAX_LEN = 90


def _pick_preheader_titles(attendable_events: list[dict], limit: int = 2) -> list[str]:
    """First `limit` distinct, non-recurring titles for the preheader -
    the same near-duplicate/recurring exclusion build_email_subject_line()
    already uses for the subject line, reused here since it is the same
    "what is actually distinctive about this issue" question, just
    feeding the preheader instead.
    """
    candidates = [e for e in attendable_events if not e.get("recurring")]
    picked: list[str] = []
    for e in candidates:
        title = e["title"]
        if any(_is_near_duplicate_title(title, p) for p in picked):
            continue
        picked.append(title)
        if len(picked) >= limit:
            break
    return picked


def build_email_preheader(count: int, titles: list[str]) -> str:
    """Hidden inbox preview text (ROADMAP.md item 207). Without one,
    every client falls back to whatever visible text comes first in
    <body>, which on this template is the wordmark and issue date -
    largely repeating the subject line rather than complementing it.
    Deliberately never names a region: the subject line already does,
    and item 207's own finding was a preview that mostly restated the
    subject rather than adding something new.
    """
    if count == 0:
        return "Nothing new dated yet this week — see what's evergreen and coming up"
    if not titles:
        body = f"{count} thing{'s' if count != 1 else ''} this weekend"
    elif len(titles) == 1:
        body = f"{count} thing{'s' if count != 1 else ''} this weekend — incl. {titles[0]}"
    else:
        body = f"{count} things this weekend — incl. {titles[0]} and {titles[1]}"
    return truncate(body, PREHEADER_MAX_LEN)


def render_email_digest(
    region: dict,
    weekend_events: list[dict],
    evergreen: list[dict],
    region_url: str,
    weekend_date_range: str,
    sponsor: dict | None,
    newsletter: dict | None = None,
    *,
    preview: bool = False,
    now: datetime | None = None,
) -> str:
    """The actual email HTML (ROADMAP.md Phase 11 #36) - a gate on items
    24/31, not a standalone feature, since nothing sends yet without
    SPF/DKIM/DMARC (item 47). Built from scratch in templates/
    email_digest.html.j2 rather than reusing region.html.j2, which uses
    flexbox/grid, web fonts and CSS the mail clients this has to render
    in (especially Outlook's Word engine) don't support. Reuses the same
    already-fetched weekend_events/evergreen data as
    build_weekly_summary_txt - never invents content to fill space.

    `preview=True` adds the "PREVIEW ONLY" annotation row naming the
    subject line to paste; `preview=False` (the default, used for the
    file that actually gets sent) omits it. ROADMAP.md Phase 11 #91: a
    real send shipped that row as the first line of body copy, because
    the intended workflow - select all, copy, paste into Buttondown -
    pastes the whole file including the warning about itself. A warning
    inside the thing it warns about gets pasted along with it every
    time, so the two files are now byte-identical except for this row.
    """
    env = get_template_env()
    template = env.get_template("email_digest.html.j2")
    evergreen_highlights = [e for e in evergreen if "free" in e.get("tags", [])][:3]
    # ROADMAP.md Phase 11 #90: a school half-day or office closure is real
    # and belongs on the site, but must never be presented as a weekend
    # event to attend - split it into its own "Also this week" line
    # instead of interleaving it with attendable events as an equal.
    attendable_events = [e for e in weekend_events if e.get("attendable", True)]
    informational_events = [e for e in weekend_events if not e.get("attendable", True)]
    return template.render(
        region=region,
        weekend_events=prepare_email_events(attendable_events, limit=6),
        informational_events=informational_events,
        evergreen_highlights=evergreen_highlights,
        region_url=region_url,
        weekend_date_range=weekend_date_range,
        sponsor=sponsor,
        subject_line=build_email_subject_line(region, weekend_events),
        preheader=build_email_preheader(len(attendable_events), _pick_preheader_titles(attendable_events)),
        newsletter=newsletter or {"configured": False},
        preview=preview,
        seasonal_link=seasonal_email_link(now or datetime.now(timezone.utc)),
    )


def _join_names(names: list[str], conjunction: str = "and") -> str:
    """"X", "X and Y", or "X, Y, and Z" - natural-language joining for the
    combined email's subject line and headline. `conjunction` defaults
    to "and" (those two call sites); item 177's collapsed-empty-regions
    line passes "or" instead, since it's naming alternatives ("nothing
    dated yet in A, B, or C") rather than a set that's all true at once.
    """
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} {conjunction} {names[1]}"
    return ", ".join(names[:-1]) + f", {conjunction} {names[-1]}"


# ROADMAP.md item 217: most clients show roughly 40-60 subject
# characters before truncating, and the subject now carries event
# titles that vary in length week to week.
SUBJECT_MAX_LEN = 60


def _round_robin_attendable(sections: list[dict]) -> list[dict]:
    """Every attendable event, interleaved across regions (first from
    each region, then second from each, ...), so the titles a subject
    line picks aren't all from whichever town sorts first."""
    # A paid Featured event never decides the subject line (item 245).
    per_region = [[e for e in s["weekend_events"] if e.get("attendable", True) and not e.get("sponsored_by")] for s in sections]
    interleaved = []
    for i in range(max((len(r) for r in per_region), default=0)):
        interleaved.extend(r[i] for r in per_region if i < len(r))
    return interleaved


# ROADMAP.md item 222: words that mark a one-off community occasion -
# the kind of thing a subject line should lead with - versus a routine
# programme, which shouldn't, even when it happens to sort first.
_OCCASION_WORDS = re.compile(
    r"\b(?:fest|festival|oktoberfest|fair|parade|market|concert|tree lighting|"
    r"trick[- ]or[- ]treat|carnival|celebration|halloween|harvest|holiday|"
    r"fireworks|craft show|art show|block party|5k|fun run)\b",
    re.I,
)
_ROUTINE_WORDS = re.compile(
    r"\b(?:class|classes|lesson|lessons|workshop|meeting|board|council|session|"
    r"practice|club|drawing|tutoring|lab|open gym|registration|closed|closure)\b",
    re.I,
)
_TRAILING_YEAR = re.compile(r"\s*[-–—:,]?\s*\(?\b(?:19|20)\d\d\b\)?\s*$")
_TRAILING_SESSION = re.compile(
    r"\s*\((?:(?:week|session|part|day|class)\s*\d+(?:\s*of\s*\d+)?|(?:mon|tues|wednes|thurs|fri|satur|sun)day)\)\s*$", re.I
)


def _clean_subject_title(title: str) -> str:
    """A title as it should read in a subject line (item 222): no trailing
    year or edition token ("Life Drawing at the Library 2026") and no
    session suffix ("(Week 5 of 5)"). Card titles stay as published -
    this only shapes the subject."""
    cleaned = _TRAILING_SESSION.sub("", title).strip()
    # "Class of 2026" names a cohort, not an edition - keep that year.
    if not re.search(r"\bof\s+(?:19|20)\d\d\s*$", cleaned, re.I):
        cleaned = _TRAILING_YEAR.sub("", cleaned).strip()
    cleaned = _TRAILING_SESSION.sub("", cleaned).strip()
    return cleaned or title


def _occasion_score(event: dict) -> int:
    """How strongly an event should lead a subject line (item 222). A
    festival beats a library class even when the class sorts first."""
    title = event.get("title", "")
    tags = set(event.get("tags") or [])
    score = 0
    if _OCCASION_WORDS.search(title):
        score += 3
    if _ROUTINE_WORDS.search(title):
        score -= 2
    if "free" in tags:
        score += 1
    if "kid_friendly" in tags:
        score += 1
    return score


def _fit_subject(titles: list[str], total: int, lone_leads: list[str] | None = None) -> str:
    """'{A}, {B} and N more this weekend' within SUBJECT_MAX_LEN.

    Prefers whole real titles over clipped ones: the first pair that
    fits, else the first single title that fits, and only then a clipped
    first title - and before clipping, a compact "{title} + N more" (item
    225), so a lead title is cut only when it can't fit even alone. "and"
    rather than "&" because real titles contain "&"
    themselves ("Harmony Fest & Taste of Arlington Heights (Friday)" is
    one event), and a clipped one followed by another "&" read as
    nonsense in a real build.
    """
    def compose(named: list[str]) -> str:
        more = total - len(named)
        if len(named) == 1:
            return f"This weekend: {named[0]}" if more == 0 else f"{named[0]} and {more} more this weekend"
        lead = f"{named[0]}, {named[1]}" if more else f"{named[0]} and {named[1]}"
        return f"{lead} and {more} more this weekend" if more else f"{lead} this weekend"

    def compact(title: str) -> str:
        # Item 225: "{title} + N more" drops "this weekend" (13 characters)
        # so a long lead title can stay whole instead of being cut mid-name.
        more = total - 1
        return f"This weekend: {title}" if more == 0 else f"{title} + {more} more"

    leads = lone_leads if lone_leads is not None else titles
    candidates = [compose(titles[:2])] if len(titles) >= 2 else []
    # Item 222: only a top-ranked title may lead alone, so a shorter but
    # less notable title can't win just by fitting. Item 225: each lead
    # gets its compact form before the next lead is tried, so the lead
    # stays the lead rather than yielding to a shorter tie.
    for title in leads:
        candidates += [compose([title]), compact(title)]
    for subject in candidates:
        if len(subject) <= SUBJECT_MAX_LEN:
            return subject
    # Last resort, only for a title too long even on its own: shorten at a
    # word boundary (truncate never cuts inside a word).
    room = SUBJECT_MAX_LEN - (len(compact(titles[0])) - len(titles[0]))
    return compact(truncate(titles[0], room))


def build_combined_email_subject_line(sections: list[dict]) -> str:
    """ROADMAP.md Phase 11 #105: one subject line for every region, since
    Buttondown's free-plan list has no per-region segmentation and every
    subscriber receives the same issue.

    ROADMAP.md item 217: leads with what is happening, not which towns.
    The town-list version read "This weekend across Arlington Heights,
    Mount Prospect, and Wheeling" on three sends in a row - identical
    each week, no reason to open, and it left out every town with
    nothing dated. Same selection rules as the single-region subject
    (item 83): attendable only (item 90), never a recurring event (item
    141), no near-duplicate second title (item 86). The towns move to
    the preheader (build_combined_email_preheader), so subject and
    preview never repeat each other.
    """
    attendable = _round_robin_attendable(sections)
    if not attendable:
        return f"This week across {_join_names([s['region_name'] for s in sections])}: what's coming up"
    # Item 222: lead with the most notable occasion, not whichever event
    # round-robin order puts first. sorted() is stable, so ties keep the
    # round-robin spread across towns.
    ranked = sorted(attendable, key=_occasion_score, reverse=True)
    cleaned = [dict(e, title=_clean_subject_title(e["title"])) for e in ranked]
    titles = _pick_preheader_titles(cleaned, limit=5)
    if not titles:
        with_events = [s["region_name"] for s in sections if any(e.get("attendable", True) for e in s["weekend_events"])]
        return truncate(f"This weekend across {_join_names(with_events)}", SUBJECT_MAX_LEN)
    scores = {e["title"]: _occasion_score(e) for e in cleaned}
    best = max((scores.get(title, 0) for title in titles), default=0)
    lone_leads = [title for title in titles if scores.get(title, 0) == best]
    return _fit_subject(titles, len(attendable), lone_leads)


def build_combined_email_preheader(sections: list[dict]) -> str:
    """ROADMAP.md item 217 swaps roles with item 207: once the subject
    carries the event titles, the preview names every covered town -
    including the ones with nothing dated this weekend, which the old
    subject silently dropped - and never repeats a title."""
    if not any(e.get("attendable", True) for s in sections for e in s["weekend_events"]):
        return build_email_preheader(0, [])
    return truncate(f"Across {_join_names([s['region_name'] for s in sections])}", PREHEADER_MAX_LEN)


# ROADMAP.md item 257: an email entry a reader can act on without clicking.
# Communico library feeds (MPPL, DPPL) start their description with the
# event's own date and time ("Sunday, October 04 2026 12:15pm - 1:15pm"),
# which the email already shows in its own line, so it is dropped here.
_DESCRIPTION_DATE_PREFIX = re.compile(
    r"^\s*(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,?\s+[A-Za-z]+\s+\d{1,2},?\s+\d{4}"
    r"(?:\s+\d{1,2}(?::\d{2})?\s*[ap]m(?:\s*[-–]\s*\d{1,2}(?::\d{2})?\s*[ap]m)?)?\s*",
    re.I,
)
EMAIL_BLURB_MAX_LEN = 90


def event_time_label(date_iso: str | None) -> str | None:
    """"10:00 AM" for a timed event, None for an all-day or untimed one. A
    midnight time is how the pipeline represents "no time given" (the same
    rule as schema_start_date), so it is never shown as 12:00 AM."""
    if not date_iso or "T" not in date_iso:
        return None
    try:
        dt = datetime.fromisoformat(date_iso)
    except ValueError:
        return None
    if dt.time() == time(0, 0):
        return None
    return dt.strftime("%-I:%M %p")


def strip_description_header(detail: str | None) -> str:
    """A description with its leading Communico date/time header removed and
    whitespace collapsed - what a card shows beneath the date and time it
    already displays."""
    text = _DESCRIPTION_DATE_PREFIX.sub("", detail or "")
    return re.sub(r"\s+", " ", text).strip(" -–:")


def email_blurb(detail: str | None, title: str = "", max_len: int = EMAIL_BLURB_MAX_LEN) -> str | None:
    """One line of description for an email entry: whitespace collapsed, a
    leading Communico date/time header removed, trimmed to `max_len` at a
    word boundary. None when nothing useful is left, or the text only
    repeats the title - never a placeholder."""
    text = strip_description_header(detail)
    if not text or text.lower().rstrip(".…") == (title or "").strip().lower():
        return None
    if len(text) <= max_len:
        return text
    cut = text[: max_len - 1].rsplit(" ", 1)[0].rstrip(" ,;:-–")
    return (cut or text[: max_len - 1]) + "…"


def email_event_where(event: dict) -> str | None:
    """Where the event is, as plainly as we know: the configured venue (a
    library's events happen at the library), else the publishing source's
    short name ("Village of Palatine" from "Village of Palatine — News")."""
    where = event.get("venue") or (event.get("source") or "").split(" — ")[0].strip()
    return where or None


# ROADMAP.md item 268: which events lead a family-facing weekend list. Words
# and tags live in config/relevance.yaml so a wrong call is a one-line fix.
RELEVANCE_PATH = CONFIG_DIR / "relevance.yaml"


@lru_cache(maxsize=1)
def load_relevance_config() -> dict:
    try:
        data = load_yaml(RELEVANCE_PATH)
    except OSError:
        data = {}
    boost = [str(t) for t in data.get("boost_tags") or []]
    words = [str(w).lower() for w in data.get("adult_title_keywords") or []]
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in words) + r")(?!\w)", re.I) if words else None
    return {"boost_tags": boost, "adult_pattern": pattern}


def family_relevance(event: dict) -> int:
    """A small score for ordering: +1 for each boost tag the event carries
    (kid-friendly, free, outdoor), -2 for each adult-programme word in the
    title. Reorders only; nothing is ever hidden by it."""
    cfg = load_relevance_config()
    tags = set(event.get("tags") or [])
    score = sum(1 for t in cfg["boost_tags"] if t in tags)
    if cfg["adult_pattern"] is not None:
        score -= 2 * len(cfg["adult_pattern"].findall(event.get("title") or ""))
    return score


def weekend_display_key(event: dict) -> tuple:
    """Featured first, then date and start time, then the more family-relevant
    of two events at the same moment. One key for the weekend hub, the
    region weekend pages and both emails, so they cannot disagree."""
    return (not event.get("sponsored_by"), event.get("date_iso") or "9999", -family_relevance(event))


def order_weekend_events(events: list[dict]) -> list[dict]:
    return sorted(events, key=weekend_display_key)


def prepare_email_events(events: list[dict], limit: int | None = None) -> list[dict]:
    """Copies of `events` ready for an email (ROADMAP.md item 257): a paid
    Featured event first (item 245), then by date and start time, each with
    `email_when` ("Sat Oct 10 · 10:00 AM", or the date alone when untimed),
    `email_where` and `email_blurb`. Sorted before the per-town cap is
    applied, so the entries shown are the soonest ones."""
    prepared = []
    for e in events:
        when = None
        if e.get("date_iso"):
            try:
                when = datetime.fromisoformat(e["date_iso"]).strftime("%a %b %-d")
            except ValueError:
                when = None
        when = when or e.get("date")
        clock = event_time_label(e.get("date_iso"))
        if when and clock:
            when = f"{when} · {clock}"
        prepared.append(
            dict(e, email_when=when, email_where=email_event_where(e), email_blurb=email_blurb(e.get("detail"), e.get("title", "")))
        )
    if limit is not None and len(prepared) > limit:
        # Which entries make the cap: Featured, then the most family-relevant,
        # then the soonest. They are then shown in date order like the rest.
        chosen = sorted(prepared, key=lambda e: (not e.get("sponsored_by"), -family_relevance(e), e.get("date_iso") or "9999"))[:limit]
        chosen_ids = {id(e) for e in chosen}
        prepared = [e for e in prepared if id(e) in chosen_ids]
    return sorted(prepared, key=weekend_display_key)


# ROADMAP.md item 263: seasonal pages the weekly email links while their send
# window is open - the email is the most engaged reader the site has, and these
# pages exist for exactly one stretch of the year. Each entry is
# (page path, first (month, day), last (month, day), line shown). Items 258 and
# 259 add their pages here when they ship. One line only, never a block.
SEASONAL_EMAIL_LINKS = (
    ("trick-or-treat/", (10, 12), (10, 31), "🎃 Trick-or-treat hours for every town we cover →"),
)


def seasonal_email_link(now: datetime) -> dict | None:
    """The one seasonal line to show in this week's emails, or None.
    When two windows overlap, the one that closes first wins: it has the
    fewest sends left. The URL carries utm_source=email&utm_campaign=seasonal
    so the email's pull can be told apart in analytics."""
    today = (now.month, now.day)
    open_now = [row for row in SEASONAL_EMAIL_LINKS if row[1] <= today <= row[2]]
    if not open_now:
        return None
    path, _start, _end, label = min(open_now, key=lambda row: row[2])
    return {"url": f"{SITE_BASE_URL}{path}?utm_source=email&utm_campaign=seasonal", "label": label}


def _pick_evergreen_highlights(evergreen: list[dict], limit: int) -> list[dict]:
    """Fallback picks for a region with nothing dated this weekend
    (ROADMAP.md item 177). Every region's `evergreen:` list is
    [library, park district, village, HS athletics] in that config
    order, and only the library entry carries an explicit "free" tag -
    so the old `[e for e in evergreen if "free" in tags][:3]` filter
    always returned exactly one item (the library) no matter how high
    its own slice limit was, which is why four of five combined-email
    region blocks read as the same single library link. Preferring the
    "free"-tagged item first (still the safest single pick) and then
    filling remaining slots from the rest of the region's own curated
    list draws from more than one real source instead.
    """
    free = [e for e in evergreen if "free" in e.get("tags", [])]
    rest = [e for e in evergreen if e not in free]
    return (free + rest)[:limit]


def render_combined_email_digest(sections: list[dict], weekend_date_range: str, now: datetime, newsletter: dict | None = None, *, preview: bool = False) -> str:
    """The combined, all-regions email (ROADMAP.md Phase 11 #105) - the
    signup form is on every region page, but the automated send (item
    24/31) only ever mailed Mount Prospect's digest, since Buttondown's
    free plan is one undifferentiated list. A subscriber from any other
    region got the wrong town's weekend, a real defect the moment the
    list has anyone on it besides the owner.

    `sections` is the same per-region shape `main()` already builds for
    `hub_weekend_sections` (region_name/region_url/weekend_events), with
    each entry additionally carrying that region's own `evergreen` and
    `sponsor` - the data is already computed once per region in the main
    loop, so this only needs the same numbers routed to a second
    template rather than fetched or computed twice.

    Same `preview` split as render_email_digest (item 91): `False` (the
    default, used for the file that actually gets sent) omits the
    "PREVIEW ONLY" annotation row.

    ROADMAP.md item 177: a region with no attendable event, no
    informational note, and no active-sponsor placement to protect its
    own card for is a candidate to collapse into one shared block
    instead of repeating a full "Nothing new dated..." card once per
    region - the forty-first research pass found four of five region
    blocks reading as that identical sentence in one real thin-week
    build. Collapsing only kicks in once two or more regions qualify at
    once (`collapse` below); a single quiet region reads fine as its
    own ordinary card and loses nothing by staying one.
    """
    env = get_template_env()
    template = env.get_template("combined_email_digest.html.j2")
    all_blocks = []
    empty_candidates = []
    house_ad = None
    for s in sections:
        weekend_events = s["weekend_events"]
        attendable_events = [e for e in weekend_events if e.get("attendable", True)]
        informational_events = [e for e in weekend_events if not e.get("attendable", True)]
        sponsor = s.get("sponsor")
        is_sponsored = bool(sponsor and sponsor.get("is_active_sponsor"))
        block = {
            "region_name": s["region_name"],
            "region_url": s["region_url"],
            "attendable_events": prepare_email_events(attendable_events, limit=4),
            "informational_events": informational_events,
            "evergreen_highlights": _pick_evergreen_highlights(s.get("evergreen", []), limit=2),
            "sponsor": sponsor,
        }
        all_blocks.append(block)
        if not attendable_events and not informational_events and not is_sponsored:
            empty_candidates.append(block)
        # ROADMAP.md item 169: house ads are inventory notices and
        # appear at most once per artifact, not once per region - a
        # real paying sponsor still gets its own per-region block above
        # (that placement is what the tier sells). The first unsold
        # slot found stands in for all of them, since today every
        # region's house ad is the same shared default anyway; picking
        # deterministically (first in section order) rather than
        # arbitrarily keeps this reproducible if that ever changes.
        if house_ad is None and sponsor and not sponsor.get("is_active_sponsor"):
            house_ad = sponsor

    collapse = len(empty_candidates) >= 2
    region_blocks = [b for b in all_blocks if not (collapse and b in empty_candidates)]
    empty_regions_summary = None
    if collapse:
        empty_regions_summary = {
            "names": _join_names([b["region_name"] for b in empty_candidates], conjunction="or"),
            "entries": [
                {
                    "region_name": b["region_name"],
                    "region_url": b["region_url"],
                    "highlight": b["evergreen_highlights"][:1],
                }
                for b in empty_candidates
            ],
        }
    return template.render(
        region_blocks=region_blocks,
        empty_regions_summary=empty_regions_summary,
        house_ad=house_ad,
        weekend_date_range=weekend_date_range,
        subject_line=build_combined_email_subject_line(sections),
        preheader=build_combined_email_preheader(sections),
        newsletter=newsletter or {"configured": False},
        preview=preview,
        seasonal_link=seasonal_email_link(now),
    )


def weekend_dates(local_date: date) -> tuple[date, date, date]:
    """The Friday/Saturday/Sunday of the calendar week (Mon-Sun) containing
    local_date - correct whether local_date is itself a weekday (the
    upcoming weekend) or already Fri/Sat/Sun (this weekend, in progress).
    Friday's included because most people's weekend starts Friday evening
    after work, not Saturday morning.
    """
    monday = local_date - timedelta(days=local_date.weekday())
    return monday + timedelta(days=4), monday + timedelta(days=5), monday + timedelta(days=6)


def build_weekend_weather(region: dict, friday: date, saturday: date, sunday: date) -> list[dict]:
    """Friday/Saturday/Sunday forecast for a region's /this-weekend/ page
    (ROADMAP.md Phase 11 #11) - the indoor/outdoor tag only becomes
    genuinely useful next to the actual forecast. Matched by date, not by
    list position (see fetch_weather's docstring), and returns [] rather
    than a guess when a region has no lat/lon or the fetch fails - same
    fail-soft rule as every other data source in this build.
    """
    lat, lon = region.get("lat"), region.get("lon")
    if lat is None or lon is None:
        return []
    forecast = fetch_weather(lat, lon, region.get("timezone", "America/Chicago"))
    by_date = {d["date"]: d for d in forecast}
    days = []
    for target in (friday, saturday, sunday):
        day = by_date.get(target.isoformat())
        if day:
            days.append({"day_name": target.strftime("%A"), **day})
    return days


def filter_events_by_dates(blocks: list[dict], target_dates: set[date]) -> list[dict]:
    """Flatten every fetched event across sections down to the ones whose
    date falls on one of target_dates. Events without a resolved
    date_iso are silently excluded here (not an error - they just can't
    be placed on a specific day) rather than guessed into a bucket.
    """
    matched = []
    for block in blocks:
        for event in block["events"]:
            iso = event.get("date_iso")
            if not iso:
                continue
            try:
                event_date = datetime.fromisoformat(iso).date()
            except ValueError:
                continue
            if event_date in target_dates:
                matched.append(event)
    return matched


def filter_past_events(blocks: list[dict], today: date) -> list[dict]:
    """Drop dated items whose date has already passed, evaluated against
    `today` (region_local_date()'s result, not a bare UTC now - the same
    local-date precaution region_local_date's own docstring explains).
    ROADMAP.md item 171: every dated view on the site treats freshness as
    its one structural advantage over generated local-content sites, but
    nothing anywhere ever dropped a stale item, so a scraped or curated
    event kept showing for weeks after it happened - confirmed on the
    live build (Palatine's dated inventory was entirely last weekend's
    Oktoberfest; Arlington Heights served a sign-up dated three weeks
    gone).

    Undated items (no date_iso) pass straight through untouched -
    evergreen/guide entries never reach this function at all (they're
    separate lists built by prepare_evergreen/prepare_guides and have no
    date fields to begin with), but a fetched item without a resolved
    date is common and isn't "past", it's just undated.

    Applied once, here, to every block before it's used for anything -
    not a second filter to keep in sync with filter_events_by_dates
    below, which only narrows an already-filtered list down to specific
    days.

    A multi-day event modeled as one dict per day (the `series` kicker -
    see _build_annual_event_dict's docstring) needs no special-casing:
    each day has its own date_iso, so only the days that have actually
    happened drop, and the festival's later days remain until their own
    turn comes - "survives until its end date" falls out of filtering
    per-occurrence rather than needing a separate start/end range. A
    weekly-recurring entry (expand_recurring_annual_event) already never
    generates a past occurrence in the first place, so this is a no-op
    for those, not a second place that logic could drift out of sync.
    """
    filtered = []
    for block in blocks:
        events = []
        for event in block["events"]:
            iso = event.get("date_iso")
            if iso:
                try:
                    event_date = datetime.fromisoformat(iso).date()
                except ValueError:
                    event_date = None
                if event_date is not None and event_date < today:
                    continue
            events.append(event)
        filtered.append({**block, "events": events})
    return filtered


def dedupe_events(blocks: list[dict]) -> list[dict]:
    """Collapse near-duplicate dated items across every source in a
    region's build (ROADMAP.md item 173) - e.g. a village feed and a
    downtown-merchants feed both announcing the same Oktoberfest, which
    the fortieth research pass found live: "Palatine Oktoberfest
    (Friday)" and "Tween LitCrate Sign Up" each appeared twice on the
    same page with the same date.

    Reuses `_is_near_duplicate_title` (item 86's subject-line matching)
    rather than a fresh comparison, on the grounds the research pass
    named explicitly: it already answers "do these read as the same
    thing" and a second answer would just be a second place for that
    logic to drift out of sync. Two events count as duplicates only when
    they also fall on the same calendar day - same-titled recurring
    events on different days (e.g. "Every Sunday...") are a completely
    normal, non-duplicate case this must not collapse. Undated items
    (no date_iso) are never compared here at all - "same day" has no
    meaning for them, and evergreen/guide entries never reach this
    function in the first place (they're separate lists).

    When a duplicate group is found, keeps the entry with a detail line
    and a working URL over one with neither (a bare village RSS stub
    duplicating a fuller downtown-merchants listing, say), so collapsing
    duplicates makes the surviving card better rather than picking
    whichever happened to be fetched first. Ties keep the earliest
    occurrence, for a deterministic, order-stable result across builds.
    """
    flat = [
        (block_idx, event_idx, event)
        for block_idx, block in enumerate(blocks)
        for event_idx, event in enumerate(block["events"])
    ]

    def event_day(event: dict) -> date | None:
        iso = event.get("date_iso")
        if not iso:
            return None
        try:
            return datetime.fromisoformat(iso).date()
        except ValueError:
            return None

    groups: list[list[int]] = []
    for i, (_, _, event) in enumerate(flat):
        day = event_day(event)
        if day is None:
            continue
        for group in groups:
            leader = flat[group[0]][2]
            if event_day(leader) == day and _is_near_duplicate_title(leader["title"], event["title"]):
                group.append(i)
                break
        else:
            groups.append([i])

    drop: set[tuple[int, int]] = set()
    for group in groups:
        if len(group) < 2:
            continue
        best = max(group, key=lambda i: (bool(flat[i][2].get("detail")), bool(flat[i][2].get("url"))))
        for i in group:
            if i != best:
                block_idx, event_idx, _ = flat[i]
                drop.add((block_idx, event_idx))

    filtered = []
    for block_idx, block in enumerate(blocks):
        events = [e for event_idx, e in enumerate(block["events"]) if (block_idx, event_idx) not in drop]
        filtered.append({**block, "events": events})
    return filtered


def filter_free_items(blocks: list[dict], evergreen: list[dict]) -> list[dict]:
    """Every fetched event and evergreen entry tagged 'free', regardless
    of whether it has a resolved date - unlike the weekend/today views,
    "is this free" doesn't depend on knowing when it happens.
    """
    matched = [e for b in blocks for e in b["events"] if "free" in e.get("tags", [])]
    matched += [e for e in evergreen if "free" in e.get("tags", [])]
    return matched


# ROADMAP.md item 224: IndexNow is the build's one automated "tell search
# engines" step, and every real build logged a 403 that nothing kept. A
# short trailing history makes "has Bing accepted a single ping?" a lookup.
INDEXNOW_LOG_PATH = ROOT / "data" / "indexnow_log.json"
INDEXNOW_LOG_KEEP = 20


# ROADMAP.md item 265 (folding in item 235's second half): IndexNow's guidance
# is to submit URLs that changed, not the whole sitemap on every build. One
# fingerprint per sitemap page, committed by CI, is the "what changed" record.
# Only written after a submission IndexNow accepted, so a rejected build keeps
# its changes pending instead of losing them.
INDEXNOW_HASHES_PATH = ROOT / "data" / "indexnow_hashes.json"

# Parts of a built page that change on every build whatever the content: the
# footer's "Generated <time>" line and the WebPage JSON-LD's dateModified.
_FINGERPRINT_NOISE = (
    re.compile(r"Generated \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC"),
    re.compile(r'"dateModified": "[^"]*"'),
)


def page_fingerprint(html: str) -> str:
    for pattern in _FINGERPRINT_NOISE:
        html = pattern.sub("", html)
    return hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]


def sitemap_url_to_file(url: str, output_dir: Path) -> Path:
    path = url[len(SITE_BASE_URL):] if url.startswith(SITE_BASE_URL) else url.lstrip("/")
    return output_dir / path / "index.html"


def changed_indexnow_urls(urls: list[str], previous: dict, output_dir: Path) -> tuple[list[str], dict]:
    """(urls whose page differs from the last accepted submission, the
    fingerprint of every url now). A page that cannot be read counts as
    changed and is left out of the new map, so it is retried."""
    current, changed = {}, []
    for url in urls:
        try:
            fingerprint = page_fingerprint(sitemap_url_to_file(url, output_dir).read_text(encoding="utf-8"))
        except OSError:
            changed.append(url)
            continue
        current[url] = fingerprint
        if previous.get(url) != fingerprint:
            changed.append(url)
    return changed, current


def load_indexnow_hashes(path: Path = INDEXNOW_HASHES_PATH) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if isinstance(v, str)} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def record_indexnow_outcome(path: Path, now: datetime, url_count: int, ok: bool, outcome: dict) -> list[dict]:
    """Append this build's IndexNow result to `path`, keeping the last
    INDEXNOW_LOG_KEEP entries. A missing or unreadable file starts fresh."""
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(history, list):
            history = []
    except (OSError, ValueError):
        history = []
    history.append({
        "timestamp": now.isoformat(timespec="seconds"),
        "url_count": url_count,
        "ok": ok,
        "status": outcome.get("status"),
        "error": outcome.get("error"),
        # Item 265: Bing's own reason for a rejection, whether the live key
        # file answered correctly, and why a build sent nothing.
        "body": outcome.get("body"),
        "key_file_ok": outcome.get("key_file_ok"),
        "skipped": outcome.get("skipped"),
    })
    history = history[-INDEXNOW_LOG_KEEP:]
    path.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
    return history


def main() -> None:
    sponsors_cfg = load_yaml(CONFIG_DIR / "sponsors.yaml")
    contact_email = (sponsors_cfg.get("contact_email") or "").strip() or None
    newsletter = load_newsletter_config(load_yaml(CONFIG_DIR / "newsletter.yaml"))
    analytics = load_analytics_config(load_yaml(CONFIG_DIR / "analytics.yaml"))
    maps = load_maps_config(load_yaml(CONFIG_DIR / "maps.yaml"))
    regions = load_regions()
    now = datetime.now(timezone.utc)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / ".nojekyll").touch()

    source_health = load_source_health()
    transport_failures = load_transport_failures()
    failure_window = load_failure_window()
    transport_failure_details = load_transport_failure_details()
    weekend_history = load_weekend_history()
    # ROADMAP.md item 197: numerator/denominator for this build's
    # "N of M sources reported" fact, accumulated across every region's
    # fetch_region_sections() call below.
    source_completeness = {"expected": 0, "reporting": 0}
    # Static config (id/name/lat/lon), independent of fetch results, so
    # it's safe to build once before the fetch loop below - every
    # region's own nearby-regions strip (ROADMAP.md Phase 11 #52) needs
    # every *other* region's coordinates, including ones not yet reached
    # in the loop.
    all_regions_meta = [
        {
            "id": r["region"]["id"],
            "name": r["region"]["name"],
            "lat": r["region"].get("lat"),
            "lon": r["region"].get("lon"),
            "path": r["region"]["id"] + "/",
        }
        for r in regions
    ]
    region_summaries = []
    hub_weekend_sections = []
    hub_weekend_date_range = None
    hub_weekend_end_iso = None
    hub_today_label = None
    hub_today_iso = None
    # ROADMAP.md item 149: same merge-across-regions pattern as
    # hub_weekend_sections above, extended to /free and /today at the hub
    # level - populated inside the per-region `views` loop below, from the
    # exact same filtered item lists each region's own /free and /today
    # pages already render, so there's no separate filtering logic to
    # drift out of sync with the per-region views.
    hub_free_sections = []
    hub_today_sections = []
    feed_items = []
    events_json_groups: list[tuple[str, str, list[dict]]] = []
    llms_full_groups: list[tuple[str, str, list[dict]]] = []
    pins_groups: list[tuple[str, str, str, list[dict]]] = []
    trick_or_treat_entries = []
    combined_email_sections = []
    total_dated, total_events = 0, 0
    # ROADMAP.md item 172: how many dated events each region contributes
    # to this weekend's combined issue, so send_newsletter.py can refuse
    # to mail a thin one - populated in the loop below, written once via
    # write_weekend_signal() after every region's weekend_events is known.
    weekend_event_counts: dict[str, int] = {}
    for region_cfg in regions:
        region = region_cfg["region"]
        region_id = region["id"]
        logger.info("=== Building region: %s (%s) ===", region["name"], region_id)

        trick_or_treat = prepare_trick_or_treat(region_cfg)
        if trick_or_treat:
            trick_or_treat_entries.append(
                {
                    "region_id": region_id,
                    "region_name": region["name"],
                    "region_url": SITE_BASE_URL + region_id + "/",
                    **trick_or_treat,
                }
            )

        local_today = region_local_date(region, now)
        blocks = fetch_region_sections(
            region_cfg,
            health=source_health,
            transport_failures=transport_failures,
            transport_failure_details=transport_failure_details,
            completeness=source_completeness,
            last_good_dir=LAST_GOOD_DIR,
            now=now,
            failure_window=failure_window,
        )
        annual_block = prepare_annual_events(region_cfg, now)
        if annual_block:
            # First, not appended: curated + dated is the highest-
            # confidence content on the page (a human put it there
            # deliberately), and it's often the most time-sensitive too.
            blocks.insert(0, annual_block)
        # ROADMAP.md item 171: drop dated items whose date has already
        # passed, before blocks feeds anything downstream - the main
        # region page, the RSS feed, calendar.ics, Editor's Pick, and
        # every date-scoped view all read from this same list, so
        # filtering here once is what keeps them all honest instead of
        # re-filtering (or forgetting to) in each one separately.
        blocks = filter_past_events(blocks, local_today)
        # ROADMAP.md item 173: same single-insertion-point reasoning as
        # item 171's filter above - collapsing duplicates here, before
        # anything downstream reads blocks, means the main region page,
        # the RSS feed, calendar.ics, and every date-scoped view all see
        # the same deduped list instead of needing their own pass.
        blocks = dedupe_events(blocks)
        # ROADMAP.md item 245: a paid Event Promo goes in after the filters
        # above, so it can never be deduped away or dropped, and goes first.
        blocks = apply_promotion(blocks, build_promotion_event(sponsors_cfg, region_cfg, local_today))
        feed_items += [
            {**e, "region_name": region["name"]}
            for b in blocks
            for e in b["events"]
            if e.get("title") and e.get("url") and e.get("date_iso")
        ]
        evergreen = prepare_evergreen(region_cfg)
        guides = prepare_guides(region_cfg)
        directory = build_business_directory(sponsors_cfg, region_id)
        sponsor = resolve_sponsor(sponsors_cfg, region_id)
        guides_url = SITE_BASE_URL + region_id + "/guides/" if guides else None
        # Always present (not gated on directory being non-empty, unlike
        # guides_url) - the empty state itself is a CTA to become the
        # first listed business, so the page is worth linking to before
        # there's any real content in it.
        directory_url = SITE_BASE_URL + region_id + "/directory/"
        # ROADMAP.md item 158: always present, same reasoning as
        # directory_url above - the page always has content (evergreen
        # entries alone guarantee that), so it's never worth hiding
        # behind a conditional the way guides_url is.
        things_to_do_url = SITE_BASE_URL + region_id + "/things-to-do/"
        editors_pick = select_editors_pick(region_cfg, blocks, evergreen)

        html = render_region_page(
            region_cfg,
            blocks,
            sponsor,
            evergreen,
            now,
            guides_url=guides_url,
            directory_url=directory_url,
            things_to_do_url=things_to_do_url,
            newsletter=newsletter,
            analytics=analytics,
            editors_pick=editors_pick,
            answer_block=build_answer_block(region),
            map_link_url=build_region_map_link_url(region),
            map_embed_url=build_region_map_embed_url(region, maps),
            nearby_regions=build_nearby_regions(region, all_regions_meta),
            region_map=build_region_map(all_regions_meta),
        )

        region_dir = OUTPUT_DIR / region_id
        region_dir.mkdir(parents=True, exist_ok=True)
        (region_dir / "index.html").write_text(html, encoding="utf-8")
        logger.info("Wrote %s", region_dir / "index.html")

        calendar_ics = build_region_calendar_ics(region, blocks, now)
        (region_dir / "calendar.ics").write_text(calendar_ics, encoding="utf-8")
        logger.info("Wrote %s", region_dir / "calendar.ics")

        # ROADMAP.md item 230: anchors as the region index page assigns them,
        # so each event's url in the index lands on its card there.
        prepare_event_cards(blocks)
        region_page_url = SITE_BASE_URL + region_id + "/"
        upcoming = filter_events_by_dates(blocks, {local_today + timedelta(days=i) for i in range(EVENTS_JSON_DAYS)})
        # Copies, so later page renders re-assigning anchor_id on the shared
        # event objects can't change the site-wide index built after the loop.
        upcoming = [dict(e, town=e.get("town") or region["name"], state=e.get("state") or region.get("state")) for e in upcoming]
        # ROADMAP.md item 243: copied now, while anchor_id matches this
        # town's index page, like `upcoming` above.
        if trick_or_treat:
            trick_or_treat_entries[-1]["events"] = [
                dict(e, town=e.get("town") or region["name"], state=e.get("state") or region.get("state"))
                for e in select_halloween_events(blocks, local_today)
            ]
        events_json_groups.append((region["name"], region_page_url, upcoming))
        (region_dir / "events.json").write_text(
            build_events_json([(region["name"], region_page_url, upcoming)], f"Upcoming events in {region['name']} — {SITE_NAME}", now),
            encoding="utf-8",
        )
        logger.info("Wrote %s (%d events)", region_dir / "events.json", len(upcoming))

        friday, saturday, sunday = weekend_dates(local_today)
        # ROADMAP.md item 268: on Saturday the page is for Saturday and Sunday;
        # Friday's events have passed and leave it.
        window_days = [d for d in (friday, saturday, sunday) if d >= local_today]
        weekend_events = order_weekend_events(filter_events_by_dates(blocks, set(window_days)))
        weekend_event_counts[region_id] = len(weekend_events)
        update_weekend_history(weekend_history, region_id, len(weekend_events))
        # ROADMAP.md item 186: the three-stage funnel a zero-contribution
        # region's own numbers hide - fetched (post-filter/dedupe) -> has
        # a parseable date at all -> actually lands inside this weekend's
        # window. Des Plaines looked healthy by every existing per-source
        # check while collapsing at the third stage; this is the log line
        # that would have shown it directly instead of needing this pass's
        # own manual accounting.
        _fetched_count = sum(len(b["events"]) for b in blocks)
        _dated_count = sum(1 for b in blocks for e in b["events"] if e.get("date_iso"))
        logger.info(
            "  Weekend funnel for %s: %d fetched -> %d dated -> %d in this weekend's window",
            region_id, _fetched_count, _dated_count, len(weekend_events),
        )
        weekend_weather = [w for w in build_weekend_weather(region, friday, saturday, sunday) if w.get("date", "") >= local_today.isoformat()]
        weekend_date_range = format_date_range(window_days[0], sunday)
        if hub_weekend_date_range is None:
            hub_weekend_date_range = weekend_date_range  # regions share a timezone today
            hub_weekend_end_iso = sunday.isoformat()
        if hub_today_label is None:
            hub_today_label = local_today.strftime("%A, %B %-d")  # regions share a timezone today
            hub_today_iso = local_today.isoformat()

        weekly_summary_txt = build_weekly_summary_txt(
            region, weekend_events, evergreen, SITE_BASE_URL + region_id + "/", weekend_date_range
        )
        (region_dir / "weekly-summary.txt").write_text(weekly_summary_txt, encoding="utf-8")
        logger.info("Wrote %s", region_dir / "weekly-summary.txt")

        email_digest_args = (
            region, weekend_events, evergreen, SITE_BASE_URL + region_id + "/", weekend_date_range, sponsor,
            newsletter,
        )
        # ROADMAP.md Phase 11 #91: two files, byte-identical except for
        # the annotation row - email-send.html is the one to paste into
        # Buttondown, email-preview.html is the one to read in a browser.
        (region_dir / "email-send.html").write_text(render_email_digest(*email_digest_args, now=now), encoding="utf-8")
        logger.info("Wrote %s", region_dir / "email-send.html")
        (region_dir / "email-preview.html").write_text(
            render_email_digest(*email_digest_args, preview=True, now=now), encoding="utf-8"
        )
        logger.info("Wrote %s", region_dir / "email-preview.html")
        if weekend_events:
            hub_weekend_sections.append(
                {
                    "region_name": region["name"],
                    "region_url": SITE_BASE_URL + region_id + "/",
                    "events": weekend_events,
                }
            )
        # Unconditional, unlike hub_weekend_sections above: the combined
        # email (item 105) always shows every region, even one with
        # nothing dated this weekend, so every subscriber finds their
        # town in the same issue rather than four subscriber-specific
        # ones Buttondown's free plan can't send anyway.
        llms_full_groups.append((region["name"], SITE_BASE_URL + region_id + "/this-weekend/", weekend_events))
        pins_groups.append((region_id, region["name"], SITE_BASE_URL + region_id + "/", weekend_events))
        combined_email_sections.append(
            {
                "region_name": region["name"],
                "region_url": SITE_BASE_URL + region_id + "/",
                "weekend_events": weekend_events,
                "evergreen": evergreen,
                "sponsor": sponsor,
            }
        )
        views = [
            (
                "this-weekend",
                weekend_events,
                f"This weekend in {region['name']}",
                f"{weekend_date_range} — everything with a known date in this range.",
                "weekend",
                "Nothing dated for this weekend yet — check back, or see all events.",
            ),
            (
                "today",
                filter_events_by_dates(blocks, {local_today}),
                f"Today in {region['name']}",
                f"{local_today.strftime('%A, %B %-d')} — everything happening today.",
                "today",
                "Nothing dated for today yet — check back, or see all events.",
            ),
            (
                "free",
                filter_free_items(blocks, evergreen),
                f"Free things to do in {region['name']}",
                "Everything tagged free, any date.",
                "free",
                "Nothing tagged free yet — check back, or see all events.",
            ),
        ]
        for slug, items, heading, subheading, nav_current, empty_message in views:
            # ROADMAP.md item 200: a static build can't know the viewer's
            # real clock, so /today/ and /this-weekend/ carry enough for
            # the page's own client-side script to notice when the
            # viewer's local date has moved past what the build covered,
            # and swap in an honest message instead of presenting a
            # stale day under today's/this weekend's heading. Only these
            # two views are date-scoped in a way a headline can go wrong
            # about; /free/ has no such claim.
            if slug == "this-weekend":
                build_scope_end_iso = sunday.isoformat()
                stale_empty_message = "This weekend's events have passed —"
                empty_follow_url = f"{SITE_BASE_URL}{region_id}/today/"
                empty_follow_label = "here's today"
            elif slug == "today":
                build_scope_end_iso = local_today.isoformat()
                stale_empty_message = "Nothing listed for today yet —"
                empty_follow_url = f"{SITE_BASE_URL}{region_id}/this-weekend/"
                empty_follow_label = "here's this weekend"
            else:
                build_scope_end_iso = stale_empty_message = empty_follow_url = empty_follow_label = None
            view_html = render_region_page(
                region_cfg,
                [{"section": heading, "events": items}],
                sponsor,
                [],
                now,
                heading=heading,
                subheading=subheading,
                empty_message=empty_message,
                nav_current=nav_current,
                canonical_suffix=f"{slug}/",
                guides_url=guides_url,
                directory_url=directory_url,
                things_to_do_url=things_to_do_url,
                weather=weekend_weather if slug == "this-weekend" else None,
                newsletter=newsletter,
                analytics=analytics,
                build_scope_end_iso=build_scope_end_iso,
                stale_empty_message=stale_empty_message,
                empty_follow_url=empty_follow_url,
                empty_follow_label=empty_follow_label,
            )
            view_dir = region_dir / slug
            view_dir.mkdir(parents=True, exist_ok=True)
            (view_dir / "index.html").write_text(view_html, encoding="utf-8")
            logger.info("Wrote %s (%d item%s)", view_dir / "index.html", len(items), "" if len(items) == 1 else "s")

            # ROADMAP.md item 149: same non-empty gate as hub_weekend_sections
            # (a region with nothing tagged free today shouldn't render an
            # empty section on the hub page).
            if slug == "today" and items:
                hub_today_sections.append(
                    {"region_name": region["name"], "region_url": SITE_BASE_URL + region_id + "/", "events": items}
                )
            elif slug == "free" and items:
                hub_free_sections.append(
                    {"region_name": region["name"], "region_url": SITE_BASE_URL + region_id + "/", "events": items}
                )

        if guides:
            for guide in guides:
                guide_html = render_region_page(
                    region_cfg,
                    [{"section": "What's inside", "events": guide["items"]}],
                    sponsor,
                    [],
                    now,
                    heading=guide["title"],
                    subheading=guide["summary"],
                    empty_message="Nothing in this guide yet.",
                    nav_current="guides",
                    canonical_suffix=f"guides/{guide['slug']}/",
                    guides_url=guides_url,
                    directory_url=directory_url,
                    things_to_do_url=things_to_do_url,
                    newsletter=newsletter,
                    analytics=analytics,
                    include_faq=True,
                )
                guide_dir = region_dir / "guides" / guide["slug"]
                guide_dir.mkdir(parents=True, exist_ok=True)
                (guide_dir / "index.html").write_text(guide_html, encoding="utf-8")
                logger.info("Wrote %s", guide_dir / "index.html")

            guide_index_items = [
                {
                    "title": g["title"],
                    "detail": g["summary"],
                    "url": guides_url + g["slug"] + "/",
                    "date": None,
                    "tags": [],
                    "tag_badges": [],
                    "ics_href": None,
                }
                for g in guides
            ]
            guides_index_html = render_region_page(
                region_cfg,
                [{"section": "Guides", "events": guide_index_items}],
                sponsor,
                [],
                now,
                heading=f"Guides for {region['name']}",
                subheading="Curated, evergreen guides that don't expire every Monday.",
                empty_message="No guides yet.",
                nav_current="guides",
                canonical_suffix="guides/",
                guides_url=guides_url,
                directory_url=directory_url,
                things_to_do_url=things_to_do_url,
                newsletter=newsletter,
                analytics=analytics,
            )
            guides_index_dir = region_dir / "guides"
            guides_index_dir.mkdir(parents=True, exist_ok=True)
            (guides_index_dir / "index.html").write_text(guides_index_html, encoding="utf-8")
            logger.info("Wrote %s (%d guide%s)", guides_index_dir / "index.html", len(guides), "" if len(guides) == 1 else "s")

        directory_html = render_region_page(
            region_cfg,
            [{"section": "Local Business Directory", "events": directory}],
            sponsor,
            [],
            now,
            heading=f"Local Business Directory — {region['name']}",
            subheading="Permanent listings for Community Partner sponsors — a lasting spot, not a footer logo that scrolls past.",
            empty_message="No businesses listed yet. Community Partner sponsors get a permanent spot here.",
            empty_cta_url=SITE_BASE_URL + "sponsor/",
            empty_cta_label="Be the first →",
            nav_current="directory",
            canonical_suffix="directory/",
            guides_url=guides_url,
            directory_url=directory_url,
            things_to_do_url=things_to_do_url,
            newsletter=newsletter,
            analytics=analytics,
        )
        directory_dir = region_dir / "directory"
        directory_dir.mkdir(parents=True, exist_ok=True)
        (directory_dir / "index.html").write_text(directory_html, encoding="utf-8")
        logger.info("Wrote %s (%d listing%s)", directory_dir / "index.html", len(directory), "" if len(directory) == 1 else "s")

        # ROADMAP.md item 158: the evergreen answer to "what is there to do
        # here at all" - seeded from material already curated for
        # evergreen/guides rather than new prose, deduplicated across the two.
        things_to_do_items = build_things_to_do_items(evergreen, guides)
        things_to_do_html = render_region_page(
            region_cfg,
            [{"section": "Things to Do", "events": things_to_do_items}],
            sponsor,
            [],
            now,
            heading=f"Things to Do in {region['name']}",
            subheading="Standing attractions and activities, any time of year — not tied to a date.",
            empty_message="Nothing listed yet.",
            nav_current="things-to-do",
            canonical_suffix="things-to-do/",
            guides_url=guides_url,
            directory_url=directory_url,
            things_to_do_url=things_to_do_url,
            newsletter=newsletter,
            analytics=analytics,
            include_faq=True,
        )
        things_to_do_dir = region_dir / "things-to-do"
        things_to_do_dir.mkdir(parents=True, exist_ok=True)
        (things_to_do_dir / "index.html").write_text(things_to_do_html, encoding="utf-8")
        logger.info(
            "Wrote %s (%d item%s)",
            things_to_do_dir / "index.html",
            len(things_to_do_items),
            "" if len(things_to_do_items) == 1 else "s",
        )

        event_count = sum(len(b["events"]) for b in blocks)
        dated, total = structured_date_coverage(blocks)
        total_dated += dated
        total_events += total
        if total:
            logger.info("  Structured-date coverage: %d/%d events have a machine-readable start date", dated, total)
        region_summaries.append(
            {
                **region,
                "event_count": event_count,
                "path": f"{region_id}/",
                "guide_slugs": [g["slug"] for g in guides],
                "guides": [{"slug": g["slug"], "title": g["title"]} for g in guides],
            }
        )

    hub_stats = {
        "region_count": len(region_summaries),
        "event_count": total_events,
        "weekend_count": sum(len(s["events"]) for s in hub_weekend_sections),
        "weekend_date_range": hub_weekend_date_range or "",
        "free_count": sum(len(s["events"]) for s in hub_free_sections),
        "today_count": sum(len(s["events"]) for s in hub_today_sections),
    }
    hub_html = render_hub_page(regions, region_summaries, now, newsletter, analytics, stats=hub_stats, contact_email=contact_email)
    (OUTPUT_DIR / "index.html").write_text(hub_html, encoding="utf-8")
    logger.info("Wrote %s", OUTPUT_DIR / "index.html")

    weekend_hub_html = render_merged_hub_page(
        hub_weekend_sections,
        now,
        analytics,
        newsletter=newsletter,
        signup_headline="Get this list every Thursday.",
        slug="this-weekend",
        heading="This Weekend Near You",
        subheading=f"{hub_weekend_date_range or ''} — everything with a known date, across every region.",
        meta_description=f"Everything with a known date this weekend ({hub_weekend_date_range or ''}), across every region — one page for planning a trip nearby.",
        empty_message="Nothing dated for this weekend yet across any region — check back, or browse a region's full page.",
        build_scope_end_iso=hub_weekend_end_iso,
        stale_empty_message="This weekend's events have passed —",
        empty_follow_url=f"{SITE_BASE_URL}today/",
        empty_follow_label="here's today",
    )
    weekend_hub_dir = OUTPUT_DIR / "this-weekend"
    weekend_hub_dir.mkdir(parents=True, exist_ok=True)
    (weekend_hub_dir / "index.html").write_text(weekend_hub_html, encoding="utf-8")
    logger.info("Wrote %s (%d region section%s)", weekend_hub_dir / "index.html", len(hub_weekend_sections), "" if len(hub_weekend_sections) == 1 else "s")

    # ROADMAP.md item 149: same hub-level merge, /free and /today - the
    # per-region /free and /today views already exist (the `views` loop
    # above); this just collects them across regions the same way
    # hub_weekend_sections does for /this-weekend.
    today_hub_html = render_merged_hub_page(
        hub_today_sections,
        now,
        analytics,
        newsletter=newsletter,
        signup_headline="Get the weekend's events by email on Thursday.",
        slug="today",
        heading="Happening Today Near You",
        subheading=f"{hub_today_label or ''} — everything happening today, across every region.",
        meta_description=f"Everything happening today ({hub_today_label or ''}), across every region.",
        empty_message="Nothing dated for today yet across any region — check back, or browse a region's full page.",
        build_scope_end_iso=hub_today_iso,
        stale_empty_message="Nothing listed for today yet —",
        empty_follow_url=f"{SITE_BASE_URL}this-weekend/",
        empty_follow_label="here's this weekend",
    )
    today_hub_dir = OUTPUT_DIR / "today"
    today_hub_dir.mkdir(parents=True, exist_ok=True)
    (today_hub_dir / "index.html").write_text(today_hub_html, encoding="utf-8")
    logger.info("Wrote %s (%d region section%s)", today_hub_dir / "index.html", len(hub_today_sections), "" if len(hub_today_sections) == 1 else "s")

    free_hub_html = render_merged_hub_page(
        hub_free_sections,
        now,
        analytics,
        newsletter=newsletter,
        signup_headline="Free things to do, every Thursday.",
        slug="free",
        heading="Free Things To Do Near You",
        subheading="Everything tagged free, any date, across every region.",
        meta_description="Everything tagged free, any date, across every region — one page for planning a no-cost outing nearby.",
        empty_message="Nothing tagged free yet across any region — check back, or browse a region's full page.",
    )
    free_hub_dir = OUTPUT_DIR / "free"
    free_hub_dir.mkdir(parents=True, exist_ok=True)
    (free_hub_dir / "index.html").write_text(free_hub_html, encoding="utf-8")
    logger.info("Wrote %s (%d region section%s)", free_hub_dir / "index.html", len(hub_free_sections), "" if len(hub_free_sections) == 1 else "s")

    # ROADMAP.md Phase 11 #105: the actual file scripts/send_newsletter.py
    # reads and mails - every region in one issue, since Buttondown's
    # free-plan list has no per-region segmentation to send four separate
    # ones to. Same email-send/email-preview split as the single-region
    # digest (item 91).
    combined_email_args = (combined_email_sections, hub_weekend_date_range or "", now, newsletter)
    (OUTPUT_DIR / "combined-email-send.html").write_text(
        render_combined_email_digest(*combined_email_args), encoding="utf-8"
    )
    logger.info("Wrote %s", OUTPUT_DIR / "combined-email-send.html")
    (OUTPUT_DIR / "combined-email-preview.html").write_text(
        render_combined_email_digest(*combined_email_args, preview=True), encoding="utf-8"
    )
    logger.info("Wrote %s", OUTPUT_DIR / "combined-email-preview.html")

    sponsor_availability = build_sponsor_availability(sponsors_cfg, region_summaries)
    sponsor_stats = {
        "region_count": len(region_summaries),
        "event_count": total_events,
        "since": LAUNCH_DATE.strftime("%b %-d, %Y"),
    }
    sponsor_html = render_sponsor_page(
        sponsor_availability,
        now,
        analytics,
        contact_email=contact_email,
        stats=sponsor_stats,
        payment_links=sponsors_cfg.get("payment_links"),
    )
    sponsor_dir = OUTPUT_DIR / "sponsor"
    sponsor_dir.mkdir(parents=True, exist_ok=True)
    (sponsor_dir / "index.html").write_text(sponsor_html, encoding="utf-8")
    logger.info("Wrote %s", sponsor_dir / "index.html")

    about_html = render_about_page(now, analytics, contact_email=contact_email, source_completeness=source_completeness)
    about_dir = OUTPUT_DIR / "about"
    about_dir.mkdir(parents=True, exist_ok=True)
    (about_dir / "index.html").write_text(about_html, encoding="utf-8")
    logger.info("Wrote %s", about_dir / "index.html")

    trick_or_treat_html = render_trick_or_treat_page(trick_or_treat_entries, now, analytics, newsletter)
    trick_or_treat_dir = OUTPUT_DIR / "trick-or-treat"
    trick_or_treat_dir.mkdir(parents=True, exist_ok=True)
    (trick_or_treat_dir / "index.html").write_text(trick_or_treat_html, encoding="utf-8")
    logger.info("Wrote %s", trick_or_treat_dir / "index.html")

    sitemap_urls = collect_sitemap_urls(region_summaries)
    (OUTPUT_DIR / "sitemap.xml").write_text(build_sitemap_xml(region_summaries, now), encoding="utf-8")
    (OUTPUT_DIR / "robots.txt").write_text(build_robots_txt(), encoding="utf-8")
    (OUTPUT_DIR / "llms.txt").write_text(build_llms_txt(region_summaries, source_completeness), encoding="utf-8")
    (OUTPUT_DIR / "events.json").write_text(
        build_events_json(events_json_groups, f"Upcoming events across every region — {SITE_NAME}", now), encoding="utf-8"
    )
    (OUTPUT_DIR / "llms-full.txt").write_text(build_llms_full_txt(llms_full_groups, weekend_date_range), encoding="utf-8")
    (OUTPUT_DIR / "CNAME").write_text(CUSTOM_DOMAIN + "\n", encoding="utf-8")
    (OUTPUT_DIR / f"{INDEXNOW_KEY}.txt").write_text(INDEXNOW_KEY, encoding="utf-8")
    if now.astimezone(LOCAL_TZ).date() <= RETIRED_INDEXNOW_KEYS_UNTIL:
        for old_key in RETIRED_INDEXNOW_KEYS:
            (OUTPUT_DIR / f"{old_key}.txt").write_text(old_key, encoding="utf-8")
    (OUTPUT_DIR / "feed.xml").write_text(build_feed_xml(feed_items, now, source_completeness), encoding="utf-8")
    logger.info("Wrote sitemap.xml, robots.txt, llms.txt, CNAME, feed.xml, and IndexNow key file")
    og_dir = OUTPUT_DIR / "og"
    og_dir.mkdir(parents=True, exist_ok=True)
    og_images = build_og_images(region_summaries)
    for name, image in og_images.items():
        image.save(og_dir / f"{name}.png", "PNG")
    logger.info("Wrote %d Open Graph image(s) to %s", len(og_images), og_dir)
    pins_today = region_local_date(regions[0]["region"], now)
    pins_friday, _pins_sat, pins_sunday = weekend_dates(pins_today)
    (OUTPUT_DIR / "pins.xml").write_text(
        build_pins_xml(
            pins_groups,
            pins_friday,
            format_date_range(max(pins_friday, pins_today), pins_sunday),
            now,
            {name: (og_dir / f"{name}.png").stat().st_size for name in og_images},
            is_trick_or_treat_season(now),
        ),
        encoding="utf-8",
    )
    logger.info("Wrote pins.xml")
    icons_dir = OUTPUT_DIR / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    for size, image in build_app_icons().items():
        image.save(icons_dir / f"icon-{size}.png", "PNG")
    (OUTPUT_DIR / "manifest.webmanifest").write_text(build_web_manifest(), encoding="utf-8")
    logger.info("Wrote manifest.webmanifest and %d app icon(s) to %s", len(APP_ICON_SIZES), icons_dir)
    indexnow_outcome: dict = {}
    indexnow_urls, indexnow_current = changed_indexnow_urls(sitemap_urls, load_indexnow_hashes(), OUTPUT_DIR)
    if indexnow_urls:
        indexnow_ok = submit_indexnow(
            host=CUSTOM_DOMAIN,
            key=INDEXNOW_KEY,
            key_location=f"{SITE_BASE_URL}{INDEXNOW_KEY}.txt",
            urls=indexnow_urls,
            outcome=indexnow_outcome,
        )
        if indexnow_ok:
            INDEXNOW_HASHES_PATH.write_text(json.dumps(indexnow_current, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    else:
        indexnow_ok = True
        indexnow_outcome = {"status": None, "error": None, "skipped": "no page changed since the last accepted submission"}
        logger.info("IndexNow: no page changed since the last accepted submission; nothing sent.")
    record_indexnow_outcome(INDEXNOW_LOG_PATH, now, len(indexnow_urls), indexnow_ok, indexnow_outcome)
    if total_events:
        logger.info(
            "TOTAL structured-date coverage: %d/%d events (%.0f%%) have a machine-readable start date",
            total_dated, total_events, 100 * total_dated / total_events,
        )

    write_weekend_signal(weekend_event_counts, now)

    save_source_health(source_health)
    save_transport_failures(transport_failures)
    save_failure_window(failure_window)
    save_transport_failure_details(transport_failure_details)
    save_weekend_history(weekend_history)
    write_source_completeness(source_completeness["reporting"], source_completeness["expected"], now)
    logger.info(
        "Source completeness: %d of %d configured sources reported.",
        source_completeness["reporting"], source_completeness["expected"],
    )
    # ROADMAP.md item 181 (forty-third research pass): logged, not
    # build-failing like the checks below - real, current
    # data/source_health.json already has exactly the 5 sources this
    # check is designed to catch (confirmed by the research pass that
    # asked for it), and send-newsletter.yml's "Build digest" step has
    # no `continue-on-error`/`if: always()` on the step after it. A
    # build-failing version of this check right now would deterministically
    # block the very next scheduled send (2026-09-23) on a condition
    # this loop cannot fix without real network access to diagnose the
    # five real URLs. The diagnostic value is in the log line existing
    # at all, not in stopping the build over a gap that needs a
    # separate pass with real network to close.
    for key in detect_missing_sources(regions, source_health):
        logger.warning(
            "Source never recorded: %s is configured but has never once appeared in source_health.json - a permanent transport failure, invisible to every regression check.",
            key,
        )
    for key in detect_chronic_transport_failures(transport_failures):
        # ROADMAP.md item 185 (forty-fourth research pass): a nonzero
        # transport streak means this source's source_health.json count
        # is, by definition, not a current reading - it's the last value
        # recorded before transport failures started, frozen there by
        # item 55's own "skip rather than record a misleading 0" rule.
        # Item 179 was written from exactly one of these stale numbers
        # without knowing it was stale. Naming the frozen count alongside
        # the streak here is what makes that visible at the point anyone
        # would read it, instead of requiring a cross-reference against
        # this file to discover it.
        stale_history = source_health.get(key)
        stale_note = f" (source_health.json still shows a stale {stale_history[-1]} from before the failures began)" if stale_history else ""
        # ROADMAP.md item 185's own "what to build" list, second bullet:
        # the *kind* of failure, not just that one is happening - "403 on
        # every request" and "DNS does not resolve" used to record
        # identically. Absent (empty dict) reads as "unknown" rather than
        # a crash - e.g. an existing data/source_transport_failures.json
        # entry from before this detail file existed.
        detail = transport_failure_details.get(key) or {}
        detail_note = (
            f" Last failure: {detail['exception_class']}"
            + (f" (HTTP {detail['status_code']})" if detail.get("status_code") else "")
            + "."
            if detail.get("exception_class")
            else ""
        )
        logger.warning(
            "Source chronic transport failure: %s has failed transport on %d+ consecutive builds.%s%s",
            key, transport_failures[key], stale_note, detail_note,
        )

    # ROADMAP.md item 194: sources that fail often without being down right
    # now, which the streak check above cannot represent, and groups of
    # sources that fail on exactly the same builds. Non-blocking, like the
    # streak warning: the log line existing is the signal.
    for key, failures, builds in detect_flapping_sources(failure_window):
        logger.warning(
            "Source flapping: %s failed transport on %d of its last %d builds without being down now (last good copy: item 262 covers the reader; the cause is still open).",
            key, failures, builds,
        )
    for group in detect_lockstep_failures(failure_window):
        logger.warning(
            "Lockstep transport failures: %s failed on exactly the same builds - one shared cause (the runner's egress, a shared CDN, per-IP rate limiting), not %d separate ones.",
            ", ".join(group), len(group),
        )

    # ROADMAP.md item 186 (forty-fourth research pass): non-blocking for
    # the same reason item 181/185's own checks above are - Des Plaines
    # and Palatine are *already* at their threshold right now, and a
    # build-failing version would deterministically fail every build
    # (including send-newsletter.yml's own, which has no
    # continue-on-error/if: always() on this step) until item 182's
    # remaining feed-discovery work lands for those two regions, which
    # needs real network access this loop doesn't have.
    for region_id in detect_zero_weekend_regions(weekend_history):
        logger.warning(
            "Region zero weekend contribution: %s has recorded 0 weekend events for %d+ consecutive builds despite being otherwise healthy.",
            region_id, ZERO_WEEKEND_ALERT_THRESHOLD,
        )

    regressions = detect_source_regressions(source_health)
    truncated = detect_truncated_sources(source_health)
    newly_broken = detect_newly_broken_sources(source_health)
    if regressions or truncated or newly_broken:
        # Deliberately fails the build *after* every other file above is
        # already written to disk (ROADMAP.md Phase 11 #51) - the
        # workflow's commit step still runs with `if: always()` so the
        # site keeps publishing and source_health.json keeps accumulating
        # real history either way. What actually changes is the job's own
        # conclusion: a real GitHub Actions failure, which GitHub emails
        # the owner about at no cost and with no new service to run. That
        # alert is the point - a source that normally returns real events
        # and just returned zero is a silent scraper death, not a normal
        # fail-soft empty section (which this never flags: a source whose
        # own trailing median is already 0 is left alone).
        for key in regressions:
            logger.error(
                "Source health regression: %s just returned 0 items despite a positive trailing history - likely a silently broken scraper, not a normal empty week.",
                key,
            )
        # ROADMAP.md item 180 (forty-second research pass): the two gaps
        # item 51's original check didn't know about. Truncation isn't
        # transition-gated - it fires on every build a source stays
        # pinned at the cap, since that's an ongoing condition worth
        # continued attention until fixed, not a one-time event like a
        # source dying.
        for key in truncated:
            logger.error(
                "Source truncation: %s has returned exactly the %d-item cap on its last 3 builds - likely being cut off, not coincidentally exhausted at the same number every time.",
                key, MAX_ITEMS_PER_SOURCE,
            )
        # Transition-gated (fires once, on the build the third consecutive
        # zero lands) - a source already fully aged into all-zero history
        # (the four known Mount Prospect village sources, items 161/179)
        # won't re-trigger this every build going forward.
        for key in newly_broken:
            logger.error(
                "Source newly broken: %s has returned 0 items on 3 consecutive builds - broken, not a normal quiet week.",
                key,
            )
        smoke_test = os.environ.get(SMOKE_TEST_ENV_VAR) == "1"
        if should_exit_for_health_regression(regressions, truncated, newly_broken, smoke_test):
            sys.exit(1)
        elif smoke_test:
            logger.warning(
                "%s=1 - not failing the process despite the health regression(s) above "
                "(this run's job is 'did the code crash', not live content health).",
                SMOKE_TEST_ENV_VAR,
            )


if __name__ == "__main__":
    main()
