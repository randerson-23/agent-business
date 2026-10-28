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
import shutil
import statistics
import sys
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlencode
from html import escape, unescape
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

import yaml
from jinja2 import Environment, FileSystemLoader
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from fetchers import FETCHERS, MAX_ITEMS_PER_SOURCE, fetch_night_forecast, fetch_weather, safe_http_url, submit_bing_urls, submit_indexnow  # noqa: E402
import warm_prospects  # noqa: E402
from tagging import infer_tags, is_informational, merge_default_tags, parse_registration_opens, tag_display  # noqa: E402

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
    # ROADMAP.md item 305: trim_blocks/lstrip_blocks stop every {% %} line
    # leaving a blank, indented line behind in the output.
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True, trim_blocks=True, lstrip_blocks=True)
    env.filters["short"] = lambda text, n=70: (str(text)[: n - 1].rstrip() + "…") if len(str(text)) > n else str(text)
    env.filters["display_title"] = display_title
    env.globals["email_surfaces"] = EMAIL_SURFACES
    env.globals["email_inks"] = EMAIL_INKS
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
        # ROADMAP.md item 246: the no-account "Add your event" form, once the
        # owner has created it.
        "event_form_url": str(newsletter_cfg.get("event_form_url") or "").strip() or None,
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


def json_for_script(payload: object, **kwargs) -> str:
    """JSON for a <script type="application/ld+json"> block. Every `<` becomes
    \\u003c, so no feed-supplied text can close the script tag or open an HTML
    comment inside it (`</script>`, `<!--`), whatever the Jinja `|safe` does."""
    return json.dumps(payload, ensure_ascii=False, **kwargs).replace("<", "\\u003c")


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
    if event.get("street_address"):
        address["streetAddress"] = event["street_address"]
        if event.get("postal_code"):
            address["postalCode"] = event["postal_code"]
    name = event.get("venue") or (f"{town}, {state}" if town and state else town) or SITE_NAME
    return {"@type": "Place", "name": name, "address": address}


def truncate(text: str, max_len: int = DETAIL_MAX_LEN) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rsplit(" ", 1)[0] + "…"


EVENT_PAGE_DETAIL_MAX_LEN = 600


def sentence_cut(text: str, max_len: int = EVENT_PAGE_DETAIL_MAX_LEN) -> str:
    """`text` whole if it fits, else cut at the last sentence end within
    `max_len` (ROADMAP.md item 373: a page's description never ends in the
    card's ellipsis). With no sentence end that early, cut at a word and add
    one - an honest ellipsis beats a clause cut off silently."""
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    window = text[:max_len]
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s|$)", window)]
    if ends and ends[-1] >= max_len // 3:
        return window[: ends[-1]].strip()
    return truncate(text, max_len)


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
    if event.get("street_address"):  # item 335: only a matched venue, never a guessed place
        lines.append(f"LOCATION:{_ics_escape(event_location_text(event))}")
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


def load_venues(region_cfg: dict) -> dict[str, dict]:
    """A region's `venues:` table (ROADMAP.md items 335 and 372), keyed by
    lower-cased name. Each row has `name`, `street_address`, optional
    `postal_code`, and `source_url` (the agency's own page the address came
    from). Rows without a name or street address are ignored. Never inferred
    from a town and never geocoded."""
    table = {}
    for row in region_cfg.get("venues") or []:
        name, street = str(row.get("name") or "").strip(), str(row.get("street_address") or "").strip()
        if name and street:
            table[name.lower()] = {"name": name, "street_address": street, "postal_code": str(row.get("postal_code") or "").strip() or None}
    return table


def match_venue(venues: dict[str, dict], venue_name: str | None, detail: str | None) -> dict | None:
    """The venue-table row for an event: the source's configured venue name
    if it is in the table, else a table name found as "at <Name>" in the
    first sentence of the description (exact name, case-insensitive, never
    fuzzy)."""
    if venue_name and venue_name.lower() in venues:
        return venues[venue_name.lower()]
    first = re.split(r"(?<=[.!?])\s", (detail or "").strip(), maxsplit=1)[0]
    for key, row in venues.items():
        if re.search(r"\bat\s+" + re.escape(row["name"]) + r"\b", first, re.IGNORECASE):
            return row
    return None


def event_location_text(event: dict) -> str:
    """"Pioneer Park, 1100 N Ridge Ave, Arlington Heights" for calendar files
    and links: venue, street address (when the table has one) and town."""
    return ", ".join(p for p in (event.get("venue"), event.get("street_address"), event.get("town")) if p)


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
    venues = load_venues(region_cfg)
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
                exclude_patterns=source.get("exclude_patterns"),
                max_per_week=source.get("max_per_week"),
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
            tags = infer_tags(item.get("title", ""), item.get("detail", ""), section=source["section"])
            tags = merge_default_tags(source.get("default_tags"), tags)
            # ROADMAP.md item 354: a venue-type override (theatres and libraries are indoors).
            veto = set(source.get("veto_tags") or [])
            tags = [t for t in tags if t not in veto]
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
                "detail_long": sentence_cut(strip_description_header(item.get("detail", ""))),  # item 373: the /e/ page
                "url": safe_http_url(item.get("url")),  # untrusted feed text: http(s) only
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
            matched = match_venue(venues, event["venue"], item.get("detail"))
            if matched:
                event.update({"venue": matched["name"], "street_address": matched["street_address"], "postal_code": matched["postal_code"]})
            event["ics_href"] = build_ics_data_uri(event)
            event["google_calendar_url"] = build_google_calendar_url(event, event_location_text(event))
            # ROADMAP.md item 327: only from an explicit phrase in the source's own text.
            reg = parse_registration_opens(f"{item.get('title', '')}. {item.get('detail', '')}", _event_day(event))
            event["registration_opens"] = reg.isoformat() if reg else None
            events.append(event)
        # ROADMAP.md item 308: the page a dead event link falls back to.
        source_page = source.get("calendar_page") or (source["url"] if source["type"] == "html_events" else None)
        blocks.append({"section": source["section"], "events": events, "source_page": source_page})
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


def prepare_trick_or_treat(region_cfg: dict, year: int | None = None) -> dict | None:
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
    # ROADMAP.md item 292: a separate, sourced trick-or-treat in the same town
    # (Downtown Mount Prospect's merchants). Built from an ISO `date` so the
    # weekday is computed, and dropped when the date is not in `year`, so a
    # previous year's date can never be shown as this year's.
    also = []
    for extra in tot.get("also") or []:
        day = _parse_promo_day(extra.get("date"))
        if not (extra.get("label") and extra.get("url") and day) or (year is not None and day.year != year):
            continue
        when = day.strftime("%A, %B ") + str(day.day)
        if extra.get("time"):
            when += ", " + str(extra["time"]).strip()
        also.append({"label": extra["label"], "url": extra["url"], "when": when, "place": extra.get("place")})
    return {"url": tot["url"], "hours": hours, "no_official_hours": no_official_hours, "note": note, "also": also}


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
    # ROADMAP.md item 272: one dealer's trunk-or-treat at four lots is four
    # cards on the source calendar; here it is one line linking each location.
    collapsed: list[dict] = []
    seen: dict[tuple, dict] = {}
    for event in picked:
        head, sep, place = event["title"].partition(" at ")
        key = (event["date_iso"][:10], head.strip().lower())
        first = seen.get(key)
        if first is None:
            seen[key] = event = dict(event)
            collapsed.append(event)
        else:
            first.setdefault("also_at", []).append(
                {"label": place.strip() if sep and place.strip() else "another location", "anchor_id": event.get("anchor_id")}
            )
    return collapsed[:HALLOWEEN_EVENTS_PER_TOWN]


TRUNK_OR_TREAT = re.compile(r"trunk[- ]?or[- ]?treat", re.IGNORECASE)


_VILLAGE_POST_TITLE = re.compile(r"trick[- ]?or[- ]?treat", re.IGNORECASE)
_VILLAGE_POST_SECTION = re.compile(r"news|village|city|calendar", re.IGNORECASE)


def find_village_post(blocks: list[dict], year: int) -> dict | None:
    """A town's own announcement about trick-or-treat, dated this year (ROADMAP.md
    item 301): a news or calendar item whose title says trick-or-treat. It is
    shown as a link beside the configured hours and never changes them, since a
    misread time on /trick-or-treat/ is the worst error this site could make.
    Items dated in any other year, or undated, are ignored."""
    best = None
    for block in blocks:
        if not _VILLAGE_POST_SECTION.search(block.get("section") or ""):
            continue
        for e in block.get("events", []):
            if not (e.get("title") and e.get("url") and e.get("date_iso") and _VILLAGE_POST_TITLE.search(e["title"])):
                continue
            if TRUNK_OR_TREAT.search(e["title"]):
                continue
            try:
                posted = datetime.fromisoformat(e["date_iso"])
            except ValueError:
                continue
            if posted.year == year and (best is None or e["date_iso"] > best["date_iso"]):
                best = e
    return {"title": best["title"].strip(), "url": best["url"]} if best else None


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
    return json_for_script(payload)


_COUNT_WORDS = {2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"}


_TOT_TIMES = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?\s*[\u2013\u2014-]\s*(\d{1,2})(?::(\d{2}))?\s*(AM|PM)", re.IGNORECASE
)
_MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"), 1)}


def short_tot_hours(hours: str | None) -> str | None:
    """"3:00\u20137:00 PM, Saturday, October 31" -> "3\u20137 PM": the time range
    only, for the one-glance table (ROADMAP.md item 318)."""
    if not hours:
        return None
    return hours.split(",")[0].strip().replace(":00", "")


def tot_hours_date(hours: str | None) -> str | None:
    """The date part of a configured hours string ("Saturday, October 31")."""
    if not hours or "," not in hours:
        return None
    return hours.split(",", 1)[1].strip() or None


def parse_tot_window(hours: str | None, year: int) -> tuple[datetime, datetime] | None:
    """Start and end of a configured hours string as wall-clock datetimes, or
    None when it cannot be read with certainty (the page then offers no
    calendar link rather than a guessed one)."""
    if not hours:
        return None
    t = _TOT_TIMES.search(hours)
    d = re.search(r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2})\b", hours, re.IGNORECASE)
    if not (t and d):
        return None
    h1, m1, ap1, h2, m2, ap2 = t.groups()
    ap1 = (ap1 or ap2).upper()
    ap2 = ap2.upper()

    def to24(h: str, m: str | None, ap: str) -> tuple[int, int]:
        hour = int(h) % 12 + (12 if ap == "PM" else 0)
        return hour, int(m or 0)

    try:
        day = date(year, _MONTHS[d.group(1).lower()], int(d.group(2)))
        (a, am), (b, bm) = to24(h1, m1, ap1), to24(h2, m2, ap2)
        start, end = datetime(day.year, day.month, day.day, a, am), datetime(day.year, day.month, day.day, b, bm)
    except ValueError:
        return None
    return (start, end) if end > start else None


def build_tot_ics_uri(town: str, hours: str | None, url: str, year: int) -> str | None:
    """An "add to calendar" data link for a town's trick-or-treat hours, only
    when the hours parse to a real time window."""
    window = parse_tot_window(hours, year)
    if not window:
        return None
    start, end = window
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{SITE_NAME}//EN", "BEGIN:VEVENT",
        f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}", f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{_ics_escape(f'Trick-or-treat in {town}')}", f"URL:{_ics_sanitize_url(url)}",
        "END:VEVENT", "END:VCALENDAR", "",
    ]
    return "data:text/calendar;charset=utf-8," + quote("\r\n".join(lines))


TOT_WATCH_PATH = ROOT / "data" / "tot_watch.json"


def load_tot_checked(now: datetime, path: Path = TOT_WATCH_PATH, max_age_hours: int = 72) -> dict[str, str]:
    """When each village page was last compared (ROADMAP.md item 317), as
    "Oct 24", only for checks newer than `max_age_hours` so the page never
    claims a check that is days old."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    checked: dict[str, str] = {}
    for region_id, rec in (data.items() if isinstance(data, dict) else []):
        try:
            when = datetime.fromisoformat(str(rec["checked_at"]))
        except (KeyError, ValueError, TypeError):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if timedelta(0) <= now - when <= timedelta(hours=max_age_hours):
            local = when.astimezone(LOCAL_TZ)
            checked[region_id] = local.strftime("%b ") + str(local.day)
    return checked


def build_halloween_night(forecast: dict | None, now: datetime, indoor_events: list[dict] | None = None) -> dict | None:
    """The "Halloween night" box (ROADMAP.md item 316): the 3-8 PM average
    temperature and rain chance, the sunset, and - at 60% rain or more - up
    to three indoor Halloween events from the page's own list. Only from
    Oct 24 to Oct 31; None (no box at all) outside that or when the forecast
    is missing, so a failed fetch never shows a guess.
    """
    local = now.astimezone(LOCAL_TZ)
    day = date(local.year, 10, 31)
    if not forecast or not (day - timedelta(days=7) <= local.date() <= day):
        return None
    window = [forecast["hours"][h] for h in range(15, 20) if h in forecast["hours"]]
    if not window:
        return None
    temp = round(sum(t for t, _ in window) / len(window))
    rain = round(sum(r for _, r in window) / len(window))
    try:
        sunset = datetime.fromisoformat(forecast["sunset"])
    except ValueError:
        return None
    sunset_label = f"{sunset.hour % 12 or 12}:{sunset.minute:02d} {'AM' if sunset.hour < 12 else 'PM'}"
    indoor = []
    if rain >= 60:
        indoor = [e for e in (indoor_events or []) if "indoor" in (e.get("tags") or []) and e.get("title") and e.get("url")][:3]
    return {
        "weekday": day.strftime("%A"),
        "temp": temp,
        "rain": rain,
        "sunset": sunset_label,
        "indoor": indoor,
        "updated": local.strftime("%b %-d, %-I:%M %p").replace("AM", "AM CT").replace("PM", "PM CT"),
    }


def tot_off_season(local_today: date) -> bool:
    """True from Nov 1 through Sep 14: villages post trick-or-treat hours in
    late September, so until then the page shows no current-year events."""
    return local_today.month >= 11 or local_today < date(local_today.year, 9, 15)


def render_trick_or_treat_page(
    entries: list[dict], now: datetime, analytics: dict | None = None, newsletter: dict | None = None,
    checked: dict[str, str] | None = None, night_forecast: dict | None = None,
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
    # ROADMAP.md item 272: trunk-or-treats get their own section (a separate
    # query); the per-town lists keep the rest.
    trunk_events = sorted(
        (
            {**e, "region_name": entry["region_name"], "region_url": entry["region_url"]}
            for entry in entries
            for e in entry.get("events") or []
            if TRUNK_OR_TREAT.search(e["title"])
        ),
        key=lambda e: e["date_iso"],
    )
    town_entries = [
        {**entry, "events": [e for e in entry.get("events") or [] if not TRUNK_OR_TREAT.search(e["title"])]}
        for entry in entries
    ]
    # ROADMAP.md item 293: each town keeps its email colour, and events get
    # their emoji, so the page matches the homepage banner and the email.
    colored = []
    for i, entry in enumerate(entries):
        colored.append({
            **entry,
            "color": EMAIL_TOWN_COLORS[i % len(EMAIL_TOWN_COLORS)][0],
            "hours_short": short_tot_hours(entry.get("hours")),
            "checked": (checked or {}).get(entry.get("region_id", "")),
            "ics_href": build_tot_ics_uri(entry["region_name"], entry.get("hours"), entry["url"], now.year),
        })
    entries = colored
    # ROADMAP.md item 318: when every town's hours are on the same date, say it
    # once above the table and drop it from the cards; otherwise each card
    # keeps its full string so no date is ever hidden.
    dates = {tot_hours_date(e.get("hours")) for e in entries if e.get("hours")}
    common_date = next(iter(dates)) if len(dates) == 1 and None not in dates else None
    town_colors = {e["region_name"]: e["color"] for e in entries}
    for e in trunk_events:
        e["town_color"] = town_colors.get(e["region_name"], "#605d5d")
    for lst in (trunk_events, *[t["events"] for t in town_entries]):
        for e in lst:
            e["emoji"] = email_event_emoji(e)
    local_today = now.astimezone(LOCAL_TZ).date()
    # ROADMAP.md item 366: from Nov 1 until villages usually post (mid
    # September) the page looks ahead to next Halloween, with this year's
    # hours kept as a labelled reference. The year follows the date.
    off_season = tot_off_season(local_today)
    display_year = local_today.year + 1 if local_today.month >= 11 else local_today.year
    if off_season:
        trunk_events = []
        town_entries = [{**t, "events": []} for t in town_entries]
    halloween_day = date(display_year if off_season else local_today.year, 10, 31)
    days_left = (halloween_day - local_today).days
    countdown = (
        None if days_left < 0 or off_season else "Tonight!" if days_left == 0 else "Tomorrow!" if days_left == 1 else f"{days_left} days to go"
    )
    return template.render(
        entries=entries,
        town_entries=town_entries,
        trunk_events=trunk_events,
        countdown=countdown,
        common_date=common_date,
        night=None if off_season else build_halloween_night(night_forecast, now, [e for t in town_entries for e in t["events"]]),
        off_season=off_season,
        ref_year=display_year - 1,
        halloween_weekday=halloween_day.strftime("%A"),
        year=display_year,
        title_towns=", ".join(sorted(e["region_name"] for e in entries)),
        towns_label=f"{_COUNT_WORDS.get(count, str(count))} Towns" if count != 1 else "One Town",
        town_names=_join_names([e["region_name"] for e in entries]),
        any_events=any(e.get("events") for e in entries) and not off_season,
        event_json_ld=None if off_season else build_halloween_json_ld(entries),
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
        tags = infer_tags(item.get("title", ""), item.get("detail", ""), section="Annual Events")
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

    # ROADMAP.md item 397: an optional `nth: [1, 3]` keeps only the 1st and 3rd
    # such weekday of each month ("1st and 3rd Saturdays").
    nth = sorted({int(n) for n in rec.get("nth") or [] if str(n).isdigit() and 1 <= int(n) <= 5})
    ordinal = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th"}
    if nth:
        recurrence_note = f"{' and '.join(ordinal[n] for n in nth)} {weekday_name.capitalize()}s through {ends.strftime('%b %-d')}"
    else:
        recurrence_note = f"Every {weekday_name.capitalize()} through {ends.strftime('%b %-d')}"
    events = []
    d = first
    while d <= window_end:
        if nth and ((d.day - 1) // 7 + 1) not in nth:
            d += timedelta(days=7)
            continue
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


def prepare_tree_lighting(region_cfg: dict, year: int) -> dict | None:
    """A region's `tree_lighting:` block (ROADMAP.md item 274) for /holidays/.
    `label` is built from the ISO `date`, so its weekday cannot be wrong, and
    a date from any year but the current one counts as not posted - search
    results presenting last year's date as this year's is what this guards."""
    block = region_cfg.get("tree_lighting")
    if not isinstance(block, dict) or not block.get("url"):
        return None
    day = _parse_promo_day(block.get("date"))
    label = None
    if day is not None and day.year == year:
        label = day.strftime("%A, %B ") + str(day.day)
        extra = [str(block[k]).strip() for k in ("time", "place") if block.get(k)]
        label = ", ".join([label] + extra)
    return {"url": block["url"], "label": label, "date_iso": day.isoformat() if label else None}


ISSUES_DIR = ROOT / "data" / "issues"
_ISSUE_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.html$")
_PREHEADER = re.compile(r'<div style="display:none;[^>]*mso-hide:all;">.*?</div>\s*', re.DOTALL)


def load_issues(directory: Path | None = None) -> list[dict]:
    """Archived sent issues (ROADMAP.md item 280), newest first. Each is
    `data/issues/<YYYY-MM-DD>.html`, the HTML exactly as it was sent, written
    by send_newsletter.py. Never regenerated from current data."""
    directory = ISSUES_DIR if directory is None else directory
    issues = []
    for path in sorted(directory.glob("*.html"), reverse=True) if directory.is_dir() else []:
        m = _ISSUE_FILE.match(path.name)
        if not m:
            continue
        html = path.read_text(encoding="utf-8")
        title = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
        issues.append({"date": m.group(1), "subject": unescape(title.group(1)).strip() if title else m.group(1), "html": html})
    return issues


# ROADMAP.md item 368: the "Did you go?" poll is for subscribers; an archive
# page shows the issue without it (the stored file is left exactly as sent).
_ISSUE_POLL_ROW = re.compile(r'<tr>(?:(?!<tr>).)*?/thanks/(?:went|not-yet)/.*?</tr>\s*(?:<tr><td style="padding:0 0 16px 0;"></td></tr>)?', re.S)

_ISSUE_PICK = re.compile(r"font-size:19px[^>]*>([^<]+)</a>")


def issue_picks(html: str, limit: int = 3) -> list[str]:
    """Event titles from an archived issue's "Don't miss" block, for its meta
    description (ROADMAP.md item 357). [] when the block is absent."""
    start = html.find("DON'T MISS")
    if start < 0:
        return []
    return [unescape(m).strip() for m in _ISSUE_PICK.findall(html[start:])][:limit]


def render_issue_page(
    issue: dict, newer: dict | None = None, older: dict | None = None, newsletter: dict | None = None,
    analytics: dict | None = None, town_names: list[str] | None = None,
) -> str:
    """One archived issue as a page on this site (ROADMAP.md items 280, 357):
    the current site wrapper - header, a banner pointing at this weekend's
    events, an H1 naming the weekend, the signup - around the email frozen as
    it was sent (preheader removed, shown in an iframe, links opening the
    top window). Self-canonical and indexable: a real sample of the product."""
    html = _PREHEADER.sub("", issue["html"], count=1)
    html = _ISSUE_POLL_ROW.sub("", html)
    html = html.replace("<head>", '<head><base target="_top">', 1) if "<head>" in html else '<base target="_top">' + html
    issue_day = datetime.strptime(issue["date"], "%Y-%m-%d").date()
    friday, _saturday, sunday = weekend_dates(issue_day)
    weekend = format_date_range(friday, sunday)
    year = sunday.year
    issue_label = issue_day.strftime("%b ") + f"{issue_day.day}, {issue_day.year}"
    names = town_names or []
    names = sorted(names)
    towns = (", ".join(names[:-1]) + " & " + names[-1] if len(names) > 1 else names[0]) if names else "the northwest suburbs"
    picks = issue_picks(issue["html"])
    description = (
        f"The Within Ten issue of {issue_label}: " + _join_names(picks) + f". What was on in {towns}, from each town's own calendar."
        if picks else f"The Within Ten issue of {issue_label}: {issue.get('subject', '')}. What was on in {towns}, from each town's own calendar."
    )
    return get_template_env().get_template("issue.html.j2").render(
        page_title=f"Things to do {weekend}, {year} in {towns} | Within Ten",
        description=description,
        heading=f"Weekend of {weekend}, {year}",
        issue_label=issue_label,
        frozen_html=html,
        canonical_url=f"{SITE_BASE_URL}issues/{issue['date']}/",
        hub_url=SITE_BASE_URL,
        newer=newer,
        older=older,
        newsletter=newsletter or {"configured": False},
        analytics=analytics,
        og_image_url=SITE_BASE_URL + "og/default.png",
    )


def render_issues_index(issues: list[dict], now: datetime, analytics: dict | None = None) -> str:
    items = "\n".join(
        f'<li><a href="{SITE_BASE_URL}issues/{i["date"]}/">{escape(i["subject"])}</a> <span>{datetime.strptime(i["date"], "%Y-%m-%d").strftime("%B %-d, %Y")}</span></li>'
        for i in issues
    )
    gc = (
        f'<script data-goatcounter="https://{analytics["goatcounter_code"]}.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>'
        if analytics and analytics.get("configured")
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Past weekly issues — Within Ten</title>
<meta name="description" content="Every weekly Within Ten email, newest first: what was on in Arlington Heights, Des Plaines, Mount Prospect, Palatine and Wheeling.">
<link rel="canonical" href="{SITE_BASE_URL}issues/">
<style>
body {{ font-family: Arial, Helvetica, sans-serif; max-width: 680px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #201e1d; background: #f3f2f2; }}
h1 {{ font-family: Georgia, serif; }}
li {{ margin: 10px 0; }} li span {{ color: #605d5d; font-size: 14px; display: block; }}
a {{ color: #ae1800; font-weight: 700; }}
@media (prefers-color-scheme: dark) {{ body {{ background: #171615; color: #f3f2f2; }} li span {{ color: #a9a5a5; }} a {{ color: #ff9783; }} }}
</style>
</head>
<body>
<p><a href="{SITE_BASE_URL}">&larr; Within Ten</a></p>
<h1>Past weekly issues</h1>
<p>Every weekly email, exactly as it was sent. <a href="{SITE_BASE_URL}join/">Get the next one by email.</a></p>
<ul>
{items}
</ul>
<p style="font-size:12.5px;color:#605d5d;">Generated {now.strftime("%Y-%m-%d %H:%M UTC")}.</p>
{gc}
</body>
</html>
"""


def build_join_picks(sections: list[dict], limit: int = 3) -> list[dict]:
    """This weekend's "Don't miss" picks for /join/ (ROADMAP.md item 277): the
    same choice the combined email makes, from the same per-region sections."""
    blocks = []
    for i, s in enumerate(sections):
        attendable = [e for e in s["weekend_events"] if e.get("attendable", True)]
        blocks.append(
            {
                "region_name": s["region_name"],
                "attendable_events": prepare_email_events(attendable, limit=4),
                "color": EMAIL_TOWN_COLORS[i % len(EMAIL_TOWN_COLORS)][0],
            }
        )
    tints = dict(EMAIL_TOWN_COLORS)
    return [dict(p, pick_tint=tints.get(p["pick_color"], "#f6f1ea")) for p in pick_email_top_picks(blocks, limit)]


def render_join_page(
    sections: list[dict], now: datetime, analytics: dict | None = None, newsletter: dict | None = None,
    weekend_date_range: str = "",
    recent_issue_url: str | None = None,
) -> str:
    """The /join/ landing page (ROADMAP.md item 277), for traffic sent on
    purpose: one headline, this weekend's picks, and the signup with a town
    picker whose value becomes the subscriber's `town:` tag. noindex."""
    env = get_template_env()
    template = env.get_template("join.html.j2")
    tag_options = [("town:all", "All towns")] + [
        ("town:" + s["region_url"].rstrip("/").rsplit("/", 1)[-1], s["region_name"]) for s in sections
    ]
    return template.render(
        picks=build_join_picks(sections),
        weekend_date_range=weekend_date_range,
        recent_issue_url=recent_issue_url or SITE_BASE_URL + "combined-email-preview.html",
        event_total=sum(1 for s in sections for e in s["weekend_events"] if e.get("attendable", True)),
        town_total=sum(1 for s in sections if any(e.get("attendable", True) for e in s["weekend_events"])),
        tag_options=tag_options,
        town_names=_join_names([s["region_name"] for s in sections]),
        newsletter=newsletter or {"configured": False},
        hub_url=SITE_BASE_URL,
        canonical_url=SITE_BASE_URL + "join/",
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        analytics=analytics,
        og_image_url=SITE_BASE_URL + "og/default.png",
    )


def build_holiday_listing_offer(now: datetime, contact_email: str | None) -> dict | None:
    """The /holidays/ page's offer box (ROADMAP.md item 294): $20 through Nov
    15, $50 after, until the guide ends on Dec 31, linking to an email to the
    owner (no Payment Link exists yet). None when there is no contact address
    or it is January through September."""
    today = now.astimezone(LOCAL_TZ).date()
    if not contact_email or today.month < 10:  # the offer runs October through December
        return None
    early = today <= date(today.year, 11, 15)
    return {
        "price": "$20" if early else "$50",
        "early": early,
        "url": f"mailto:{contact_email}?subject=Holiday%20guide%20listing",
    }


def render_holidays_page(
    entries: list[dict], now: datetime, analytics: dict | None = None, newsletter: dict | None = None,
    contact_email: str | None = None,
) -> str:
    """The cross-town /holidays/ page (ROADMAP.md item 274): tree lightings
    town by town (a confirmed date with its source, or an honest "not posted
    yet"), then each town's holiday events from its own feeds."""
    env = get_template_env()
    template = env.get_template("holidays.html.j2")
    # ROADMAP.md item 294: each town keeps its email colour, events get emoji.
    entries = [{**e, "color": EMAIL_TOWN_COLORS[i % len(EMAIL_TOWN_COLORS)][0]} for i, e in enumerate(entries)]
    entries = [{**e, "events": [{**ev, "emoji": email_event_emoji(ev)} for ev in e.get("events") or []]} for e in entries]
    return template.render(
        entries=entries,
        year=now.year,
        listing_offer=build_holiday_listing_offer(now, contact_email),
        town_names=_join_names([e["region_name"] for e in entries]),
        any_events=any(e.get("events") for e in entries),
        newsletter=newsletter or {"configured": False},
        hub_url=SITE_BASE_URL,
        canonical_url=SITE_BASE_URL + "holidays/",
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        analytics=analytics,
        og_image_url=SITE_BASE_URL + "og/default.png",
    )


# ROADMAP.md item 258: the per-town /holiday/ page, live November 1 - December 31
# (or earlier once a paid listing exists, so an early-bird buyer can see
# what they bought). Paid listings are labelled; the "Holiday events"
# half is free and comes from the town's own feeds.
HOLIDAY_TITLE = re.compile(
    r"\b(tree[- ]lighting|christmas|holiday|santa|menorah|hanukkah|chanukah|kris kringle|"
    r"winter wonderland|reindeer|small business saturday|cookie walk|gingerbread|snow ?flake|"
    r"craft fair|holiday market|makers[\u2019' ]*s? market|bazaar|vendor fair|holiday boutique)\b",
    re.IGNORECASE,
)
HOLIDAY_EVENTS_CAP = 30


def is_holiday_season(now: datetime) -> bool:
    return now.month in (11, 12)


def format_holiday_listing(entry: dict) -> dict:
    """One holiday-page listing card from a `holiday_listings:` entry. The
    /sponsor/ page's "Example" card is built by this same function, so the
    preview cannot drift from the product (ROADMAP.md items 258 and 352)."""
    parts = [p for p in (entry.get("category"), entry.get("address")) if p]
    detail = "Local business listing" + (" · " + " · ".join(str(p) for p in parts) if parts else "")
    if entry.get("line"):
        detail += f" — {str(entry['line']).strip()}"
    return {"title": str(entry.get("name") or "").strip(), "detail": detail, "url": str(entry.get("url") or "").strip(), "date": None, "tags": [], "tag_badges": [], "ics_href": None}


def build_holiday_listings(sponsors_cfg: dict, region_id: str, local_today: date) -> list[dict]:
    """Paid "Local business listing" cards for a region's /holiday/ page, from
    `holiday_listings:` in config/sponsors.yaml (ROADMAP.md item 258). An entry
    needs `name` and `url`; optional `line`, `address`, `category`, and `until`
    (the last day it runs; default December 31). Expired entries drop off."""
    entries = sponsors_cfg.get("regions", {}).get(region_id, {}).get("holiday_listings") or []
    listings = []
    for entry in entries:
        name, url = str(entry.get("name") or "").strip(), str(entry.get("url") or "").strip()
        if not name or not url:
            continue
        until = _parse_promo_day(entry.get("until"))
        # No `until`: runs through December 31, and never shows January
        # through September, so last year's entry cannot reappear.
        if until is None and local_today.month < 10:
            continue
        if until is not None and until < local_today:
            continue
        listings.append(format_holiday_listing(entry))
    return listings


def select_holiday_events(blocks: list[dict], local_today: date) -> list[dict]:
    """A town's dated holiday events from today through December 31, soonest
    first. Title match only, like select_halloween_events."""
    start = max(local_today, date(local_today.year, 11, 1))
    end = date(local_today.year, 12, 31)
    picked = []
    for block in blocks:
        for event in block.get("events", []):
            if not (event.get("title") and event.get("url") and event.get("date_iso")):
                continue
            try:
                day = datetime.fromisoformat(event["date_iso"]).date()
            except ValueError:
                continue
            if start <= day <= end and HOLIDAY_TITLE.search(event["title"]):
                picked.append(dict(event))
    picked.sort(key=lambda e: e["date_iso"])
    return picked[:HOLIDAY_EVENTS_CAP]


# ROADMAP.md item 379: the cross-town /santa/ page. Title match only, like
# the holiday selection; the window is Nov 1 - Dec 24 of the season's year.
SANTA_TITLE = re.compile(r"\b(santa(?:['\u2019]s)?|kris kringle)\b", re.IGNORECASE)
_SOLD_OUT = re.compile(r"\bsold[- ]out\b", re.IGNORECASE)


def santa_season_year(today: date) -> int:
    """The year the page is about: this year until Dec 24, next year after."""
    return today.year if today <= date(today.year, 12, 24) else today.year + 1


def santa_in_season(today: date) -> bool:
    return date(today.year, 11, 1) <= today <= date(today.year, 12, 24)


def select_santa_events(blocks: list[dict], today: date) -> list[dict]:
    """A town's dated Santa events from today through Dec 24 of the season's
    year (never before Nov 1), soonest first."""
    year = santa_season_year(today)
    start, end = max(today, date(year, 11, 1)), date(year, 12, 24)
    picked, seen = [], set()
    for block in blocks:
        for event in block.get("events", []):
            if not (event.get("title") and event.get("url") and event.get("date_iso")) or event.get("attendable") is False:
                continue
            try:
                day = datetime.fromisoformat(event["date_iso"]).date()
            except ValueError:
                continue
            key = (event["title"].strip().lower(), event["date_iso"])
            if start <= day <= end and SANTA_TITLE.search(event["title"]) and key not in seen:
                seen.add(key)
                picked.append(dict(event))
    picked.sort(key=lambda e: e["date_iso"])
    return picked


def is_leaf_pickup_season(now: datetime) -> bool:
    """ROADMAP.md item 323: Oct 15 - Dec 15, the only time the page is linked,
    in the sitemap and indexable."""
    today = now.astimezone(LOCAL_TZ).date()
    return date(today.year, 10, 15) <= today <= date(today.year, 12, 15)


def prepare_leaf_pickup(region_cfg: dict) -> dict | None:
    block = region_cfg.get("leaf_pickup")
    if not isinstance(block, dict) or not block.get("url"):
        return None
    return {"url": safe_http_url(block["url"]), "summary": str(block.get("summary") or "").strip() or None, "note": str(block.get("note") or "").strip() or None}


def render_leaf_pickup_page(entries: list[dict], now: datetime, analytics: dict | None = None, newsletter: dict | None = None) -> str:
    """The /leaf-pickup/ page: one sourced line per town, never a guessed date."""
    in_season = is_leaf_pickup_season(now)
    towns = [dict(e, color=EMAIL_TOWN_COLORS[i % len(EMAIL_TOWN_COLORS)][0]) for i, e in enumerate(entries)]
    names = _join_names([e["name"] for e in entries])
    return get_template_env().get_template("leaf_pickup.html.j2").render(
        page_title=f"Leaf Pickup {now.year}: {names} | Within Ten",
        description=f"Leaf pickup in {names}: what each village says about dates and rules, linked to the village's own page.",
        heading=f"Leaf pickup {now.year}",
        subheading=f"What {names} say about fall leaf collection, each linked to the village's own page.",
        towns=towns, in_season=in_season,
        newsletter=newsletter or {"configured": False},
        hub_url=SITE_BASE_URL, canonical_url=SITE_BASE_URL + "leaf-pickup/",
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"), analytics=analytics, og_image_url=SITE_BASE_URL + "og/default.png",
    )


def santa_look_links(region_cfg: dict) -> list[dict]:
    """ROADMAP.md item 389: where to look for Santa events meanwhile, from
    the town's own `evergreen:` links (its park district and village)."""
    out = []
    for e in region_cfg.get("evergreen") or []:
        title = str(e.get("title") or "")
        if e.get("url") and re.search(r"park district|^village of|^city of", title, re.IGNORECASE):
            out.append({"title": title, "url": e["url"]})
    return out[:2]


def render_santa_page(entries: list[dict], now: datetime, analytics: dict | None = None, newsletter: dict | None = None, event_page_paths: set[str] | None = None) -> str:
    """The /santa/ page. `entries` is [{region_name, region_url, events}]."""
    today = now.astimezone(LOCAL_TZ).date()
    year = santa_season_year(today)
    in_season = santa_in_season(today)
    town_names = _join_names([e["region_name"] for e in entries])
    rows = []
    for i, entry in enumerate(entries):
        color = EMAIL_TOWN_COLORS[i % len(EMAIL_TOWN_COLORS)][0]
        for ev in entry.get("events") or []:
            path = event_page_path(ev)
            page_url = SITE_BASE_URL + path if path in (event_page_paths or set()) else f"{entry['region_url']}#{ev.get('anchor_id') or event_anchor_id(ev)}"
            rows.append({
                "title": display_title(ev["title"]), "town": entry["region_name"], "color": color, "date_iso": ev["date_iso"],
                "time_label": event_time_label(ev["date_iso"]), "page_url": page_url, "reg_badge": ev.get("reg_badge"),
                "sold_out": bool(_SOLD_OUT.search(f"{ev['title']} {ev.get('detail') or ''}")),
            })
    rows.sort(key=lambda r: r["date_iso"])
    days = []
    for r in rows:
        label = event_date_label(r["date_iso"])
        if not days or days[-1]["label"] != label:
            days.append({"label": label, "events": []})
        days[-1]["events"].append(r)
    pattern = "Breakfast with Santa & Santa Visits"
    page_title = f"{pattern} {year}: {town_names} | Within Ten"
    return get_template_env().get_template("santa.html.j2").render(
        page_title=page_title,
        description=f"Every Santa event in {town_names} in {year}: breakfast with Santa, Santa visits, photos and parades, each linked to the town's own listing.",
        heading=f"Santa near you, {year}",
        subheading=f"Breakfast with Santa, Santa visits and photos in {town_names}, each linked to the listing it came from.",
        days=days,
        places=[{"name": e["region_name"], "color": EMAIL_TOWN_COLORS[i % len(EMAIL_TOWN_COLORS)][0], "links": e.get("links") or [], "tree": (e.get("tree") or {}).get("label") if e.get("tree") else None} for i, e in enumerate(entries)],
        empty_message="Park districts usually post Santa events in early November; they appear here as soon as they do." if year == today.year else f"Santa events for {year} are usually posted in early November. Sign up below and we'll email you when they appear.",
        reminder_tag=None if in_season else f"remind:santa-{year}",
        reminder_headline=f"Email me when the {year} Santa events are posted",
        newsletter=newsletter or {"configured": False},
        hub_url=SITE_BASE_URL,
        canonical_url=SITE_BASE_URL + "santa/",
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        analytics=analytics,
        og_image_url=SITE_BASE_URL + "og/default.png",
    )


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
        # ROADMAP.md item 314: three Weekly Spots at 10% off.
        "name": "Starter: 3 weeks",
        "payment_key": "starter",
        "price": "$135 for 3 weeks",
        "gated_by": "Newsletter reach",
        "detail": "Three Weekly Spots in a row, 10% off. Long enough to see which pages and clicks your recommendation brings, short enough to be an easy yes.",
    },
    {
        # ROADMAP.md item 352: a seasonal tier, shown on /sponsor/ from Oct 15 to Dec 15 only.
        "name": "Holiday listing",
        "payment_key": "holiday",
        "price": "$20 until Nov 15, then $50",
        "gated_by": "Newsletter reach",
        "detail": (
            "Your shop on your town's holiday page, with your sale or hours, through Dec 31 - "
            "just in time for Small Business Saturday (Nov 28). Labelled \"Local business listing\"; "
            "the page is for real shops with a real sale or hours."
        ),
        "season": ((10, 15), (12, 15)),
        "anchor": "holiday",
        "mailto_subject": "Holiday listing",
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


# ROADMAP.md item 352: a made-up business, template-only (never reaches a
# region page, events.json or llms-full.txt), formatted by the same function
# the real holiday-page listings use.
SAMPLE_HOLIDAY_LISTING = format_holiday_listing(
    {"name": "Your Shop Name", "url": "https://example.com/", "category": "Gifts", "address": "Your street address", "line": "Your sale or holiday hours go here."}
)


def holiday_tier_visible(tier: dict, today: date) -> bool:
    season = tier.get("season")
    if not season:
        return True
    (m1, d1), (m2, d2) = season
    return date(today.year, m1, d1) <= today <= date(today.year, m2, d2)


FOUNDING_PROMO_SPOTS = 5
FOUNDING_PROMO_ENDS = date(2026, 12, 31)


def founding_offer(used, today: date) -> dict | None:
    """ROADMAP.md item 388: the founding Event Promo offer for /sponsor/, or
    None once all spots are used or after Dec 31. `used` comes from
    `founding_promos_used:` in config/sponsors.yaml."""
    used = used if isinstance(used, int) and not isinstance(used, bool) and used >= 0 else 0
    left = FOUNDING_PROMO_SPOTS - used
    if left <= 0 or today > FOUNDING_PROMO_ENDS:
        return None
    return {"left": left, "total": FOUNDING_PROMO_SPOTS, "ends": f"{FOUNDING_PROMO_ENDS.strftime('%b')} {FOUNDING_PROMO_ENDS.day}"}


def early_bird_line(today: date) -> str | None:
    """"Early-bird price ends Sun Nov 15 (N days left)" through Nov 15 itself."""
    end = date(today.year, 11, 15)
    if today > end:
        return None
    left = (end - today).days
    return f"Early-bird price ends {end.strftime('%a %b')} {end.day} ({'today' if left == 0 else f'{left} day' + ('s' if left != 1 else '') + ' left'})"


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


AUDIENCE_PATH = ROOT / "data" / "audience.json"
AUDIENCE_MIN_VISITS_30D = 500
AUDIENCE_MIN_SUBSCRIBERS = 50


def sponsor_issue_stats(now: datetime, path: Path | None = None) -> dict:
    """ROADMAP.md item 351: what the sponsor page can say about the email
    without inventing anything - how many issues have gone out and since
    when, counted from `data/send_history.json` (entries dated in the past)."""
    try:
        history = json.loads((path or ROOT / "data" / "send_history.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"issues_sent": 0, "issues_since": None}
    days = sorted(h["timestamp"][:10] for h in history if isinstance(h, dict) and str(h.get("timestamp") or "")[:10] <= now.date().isoformat())
    since = datetime.fromisoformat(days[0]).strftime("%b %-d, %Y") if days else None
    return {"issues_sent": len(days), "issues_since": since}


def load_audience_line(path: Path = AUDIENCE_PATH) -> dict | None:
    """The sponsor page's "Audience, last 30 days" numbers (ROADMAP.md item
    266), only from a real snapshot and only above a floor (at least 500
    visits in 30 days, or at least 50 subscribers). Below it nothing is shown:
    never a number that would embarrass the pitch, never rounded up."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    visits = data.get("visits_30d")
    subscribers = data.get("subscribers")
    visits = visits if isinstance(visits, int) else None
    subscribers = subscribers if isinstance(subscribers, int) else None
    if not ((visits or 0) >= AUDIENCE_MIN_VISITS_30D or (subscribers or 0) >= AUDIENCE_MIN_SUBSCRIBERS):
        return None
    ai = data.get("ai_referrals_30d")
    return {
        "visits": visits,
        "subscribers": subscribers,
        "ai_referrals": ai if isinstance(ai, int) and ai > 0 else None,
        "as_of": str(data.get("as_of") or ""),
    }


def render_sponsor_page(
    availability: list[dict],
    now: datetime,
    analytics: dict | None = None,
    contact_email: str | None = None,
    stats: dict | None = None,
    payment_links: dict | None = None,
    audience: dict | None = None,
    founding_promos_used: int = 0,
) -> str:
    env = get_template_env()
    template = env.get_template("sponsor.html.j2")
    today = now.astimezone(LOCAL_TZ).date()
    tiers = [
        {
            **t,
            "buy_url": (payment_links or {}).get(t.get("payment_key") or "") or None,
            "mailto_url": build_contact_mailto_url(contact_email, t["mailto_subject"], SPONSOR_INQUIRY_FIELDS) if t.get("mailto_subject") else None,
            "early_line": early_bird_line(today) if t.get("payment_key") == "holiday" else None,
        }
        for t in SPONSOR_TIERS
        if holiday_tier_visible(t, today)
    ]
    return template.render(
        sample_holiday=SAMPLE_HOLIDAY_LISTING,
        founding=founding_offer(founding_promos_used, today),
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
        audience=audience,
        og_image_url=SITE_BASE_URL + "og/default.png",
    )


def render_sponsor_preview(sections: list[dict], payment_links: dict | None, contact_email: str | None) -> str:
    """ROADMAP.md item 313: the `/sponsor/preview/` page. The template fills in
    the business name, town, line and link from the address in the visitor's
    browser (textContent only); the build supplies each town's colour and its
    first two real attendable events."""
    towns = []
    for i, sec in enumerate(sections):
        evs = [e for e in sec["weekend_events"] if e.get("attendable", True) and e.get("title") and e.get("date_iso") and not e.get("sponsored_by")][:2]
        towns.append({
            "name": sec["region_name"], "color": EMAIL_TOWN_COLORS[i % len(EMAIL_TOWN_COLORS)][0],
            "events": [{"title": display_title(e["title"]), "when": event_date_label(e["date_iso"]) or ""} for e in evs],
        })
    links = payment_links or {}
    mailto = build_contact_mailto_url(contact_email, "Sponsor preview", SPONSOR_INQUIRY_FIELDS) if contact_email else SITE_BASE_URL + "sponsor/"
    return get_template_env().get_template("sponsor_preview.html.j2").render(
        data_json=json_for_script({"towns": towns}),
        canonical_url=SITE_BASE_URL + "sponsor/preview/", hub_url=SITE_BASE_URL,
        featured_price="$20 one-time", spot_price="$50/week or $175/month",
        event_buy_url=links.get("event_promo") or mailto, event_buy_label="Buy now" if links.get("event_promo") else "Email to claim this",
        spot_buy_url=links.get("weekly_spot") or mailto, spot_buy_label="Buy now" if links.get("weekly_spot") else "Email to claim this",
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
    return json_for_script(payload)


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
    return json_for_script(payload)


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
    return json_for_script(payload)


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
        merge_repeated_sessions(block.get("events", []))


SESSION_MERGE_DAYS = 7


def merge_repeated_sessions(events: list[dict]) -> None:
    """ROADMAP.md item 381: events with the same normalised title and venue
    inside one week render as ONE card listing every session. The first
    session keeps the card and gets `sessions` (label, calendar link, anchor
    for each); the rest are flagged `merged_away` so the template skips
    them. Nothing is removed, so JSON-LD, events.json and the calendar feed
    still carry one Event per session. Flags are reset on every call because
    one event object is rendered on several pages."""
    groups: dict[tuple, list[dict]] = {}
    for event in events:
        event.pop("merged_away", None)
        event.pop("sessions", None)
        if not event.get("date_iso") or event.get("attendable") is False or event.get("sponsored_by"):
            continue
        key = (re.sub(r"[^a-z0-9]+", " ", (event.get("title") or "").lower()).strip(), (event.get("venue") or event.get("source") or "").lower())
        groups.setdefault(key, []).append(event)
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda e: e["date_iso"])
        try:
            first_day = date.fromisoformat(group[0]["date_iso"][:10])
            members = [e for e in group if (date.fromisoformat(e["date_iso"][:10]) - first_day).days < SESSION_MERGE_DAYS]
        except ValueError:
            continue
        if len(members) < 2:
            continue
        primary = members[0]
        primary["sessions"] = [
            {
                "label": " ".join(p for p in (datetime.fromisoformat(e["date_iso"]).strftime("%a"), e.get("time_label")) if p),
                "ics_href": e.get("ics_href"),
                "anchor_id": e.get("anchor_id"),
            }
            for e in members
        ]
        for e in members[1:]:
            e["merged_away"] = True



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
    return json_for_script(payload)


TITLE_LIMIT = 65
DESCRIPTION_LIMIT = 160


def top_pick_titles(events: list[dict], limit: int = 3) -> list[str]:
    """Up to `limit` distinct real titles from attendable, unpaid events, the
    most family-relevant first, soonest on ties (ROADMAP.md item 310)."""
    ranked = sorted(
        (e for e in events if e.get("title") and e.get("attendable", True) and not e.get("sponsored_by")),
        key=lambda e: (-family_relevance(e), e.get("date_iso") or "9999"),
    )
    titles: list[str] = []
    for e in ranked:
        title = e["title"].strip()
        if title not in titles:
            titles.append(title)
        if len(titles) == limit:
            break
    return titles


def build_search_meta(name: str, state: str, events: list[dict], *, when: str, date_range: str | None = None) -> dict | None:
    """Title and description that match how people search (ROADMAP.md item
    310): "Things to Do in Mount Prospect, IL This Weekend (Oct 16-18)" and
    "23 things to do Oct 16-18: A, B, C and more, from the village, library and
    park district." The title is at most TITLE_LIMIT characters before the brand
    (the date range goes first when it is too long), the description at most
    DESCRIPTION_LIMIT (picks are dropped from the end), and None when there is
    nothing to count so the caller keeps its plain wording."""
    plain = [e for e in events if e.get("attendable", True) and not e.get("sponsored_by")]
    count = len(plain)
    if count == 0:
        return None
    base = f"Things to Do in {name}, {state}{': ' if when.startswith('Events') else ' '}{when}"
    title = f"{base} ({date_range})" if date_range and len(base) + len(date_range) + 3 <= TITLE_LIMIT else base
    span = date_range or ("this week" if "Week" in when else "this weekend")
    lead = f"{count} thing{'s' if count != 1 else ''} to do {span}"
    tail = ", from the village, library and park district."
    picks = top_pick_titles(plain)
    while True:
        body = ", ".join(picks) + (" and more" if len(plain) > len(picks) else "")
        desc = f"{lead}: {body}{tail}" if picks else f"{lead}{tail}"
        if len(desc) <= DESCRIPTION_LIMIT or not picks:
            break
        picks = picks[:-1]
    if len(desc) > DESCRIPTION_LIMIT:
        desc = desc[: DESCRIPTION_LIMIT - 1].rstrip(" ,;") + "…"
    return {"title": title, "description": desc, "h1": f"Things to do in {name} {when.lower()}"}


def build_hub_weekend_description(town_names: list[str], sections: list[dict], date_range: str) -> str:
    """The hub weekend page's meta description (item 310): the real count, the
    towns and the date range, at most DESCRIPTION_LIMIT characters; plain
    wording when nothing is dated."""
    count = sum(1 for s in sections for e in s["events"] if e.get("attendable", True) and not e.get("sponsored_by"))
    towns = _join_names(sorted(town_names)) if town_names else "the northwest suburbs"
    if count == 0:
        return f"Things to do this weekend in {towns}: everything with a known date, across every town, in one place."[:DESCRIPTION_LIMIT]
    desc = f"{count} things to do this weekend{f' ({date_range})' if date_range else ''} in {towns}, from the village, library and park district calendars."
    return desc if len(desc) <= DESCRIPTION_LIMIT else desc[: DESCRIPTION_LIMIT - 1].rstrip(" ,;") + "…"


def render_region_page(
    region_cfg: dict,
    blocks: list[dict],
    sponsor: dict,
    evergreen: list[dict],
    now: datetime,
    *,
    heading: str | None = None,
    subheading: str | None = None,
    search_meta: dict | None = None,
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
    days_off: list[dict] | None = None,
    days_off_sponsor: dict | None = None,
    closures: list[dict] | None = None,
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
    if search_meta:
        page_title = f"{search_meta['title']} | {SITE_NAME}"
        page_description = search_meta["description"]
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
        feed_url=region_base_url + "feed.xml",
        freshness_json_ld=build_freshness_json_ld(region, canonical_url, now),
        answer_block=answer_block,
        last_checked_label=last_checked_label,
        map_link_url=map_link_url,
        map_embed_url=map_embed_url,
        nearby_regions=nearby_regions,
        region_map=region_map,
        days_off=days_off,
        days_off_sponsor=days_off_sponsor,
        closures=closures,
        election_line=election_day_line(now),
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
        leaf_pickup_in_season=is_leaf_pickup_season(now),
        holiday_in_season=is_holiday_season(now),
        winter_in_season=winter_break_season(now),
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


def weekend_season_banner(halloween: dict | None) -> dict | None:
    """The one-line seasonal link at the top of /this-weekend/ (ROADMAP.md
    item 360): the hub's Halloween banner in miniature, shown exactly when
    that banner is."""
    if not halloween:
        return None
    return {"emoji": "🎃", "text": "Trick-or-treat hours by town", "url": SITE_BASE_URL + "trick-or-treat/"}


def build_halloween_banner(entries: list[dict], now: datetime) -> dict | None:
    """The homepage's Halloween banner (owner request, 2026-10-13: the
    trick-or-treat link sat in the footer, and in October it belongs at the
    very top). Shown from the start of trick-or-treat season through
    Halloween itself, then hidden, since the page's job is done by Nov 1
    even though the footer link stays a few more days. Each town's hours are
    shortened to the time range ("3–7 PM"), with Des Plaines' "no official
    hours" and a not-yet-posted town stated as such, never guessed."""
    if not entries or not is_trick_or_treat_season(now):
        return None
    today = now.astimezone(LOCAL_TZ).date()
    halloween = date(today.year, 10, 31)
    if today > halloween:
        return None
    days = (halloween - today).days
    towns = []
    for e in entries:
        if e.get("hours"):
            short = short_tot_hours(e["hours"])
        elif e.get("no_official_hours"):
            short = "No set hours"
        else:
            short = "Not posted yet"
        note = (e.get("note") or "").lower() if e.get("hours") else ""
        qualifier = "standing" if "standing" in note else "recommended" if "recommended" in note else None
        towns.append({"name": e["region_name"], "hours": short, "post": e.get("village_post"), "qualifier": qualifier})
    if days == 0:
        countdown = "Tonight!"
    elif days == 1:
        countdown = "Tomorrow!"
    else:
        countdown = f"{days} days to go"
    return {"weekday": halloween.strftime("%A"), "countdown": countdown, "towns": towns}


def build_winter_banner(region_summaries: list[dict], now: datetime) -> dict | None:
    """The homepage's small "Kids off school?" strip, Dec 15 - Jan 3 (ROADMAP.md
    item 285's third window), linking each town's winter-break page. It sits
    under the holiday banner while that runs (to Dec 24) and alone after."""
    today = now.astimezone(LOCAL_TZ).date()
    start, end = date(today.year, 12, 15), date(today.year, 1, 3)
    in_window = today >= start or today <= end
    links = [{"name": r["name"], "url": r["path"] + "winter-break/"} for r in region_summaries if r.get("winter_break")]
    return {"links": links} if in_window and links else None


def build_holiday_banner(entries: list[dict], now: datetime) -> dict | None:
    """The homepage's holiday banner (ROADMAP.md item 285): Nov 1 - Dec 24,
    after the Halloween banner's last day, so there is at most one banner at a
    time. Each town shows its confirmed tree-lighting date ("Sat Nov 21") or
    "date TBA", never a guess. `offer` is True through Nov 15, the early-bird
    deadline for holiday-guide business listings."""
    today = now.astimezone(LOCAL_TZ).date()
    if not entries or not (date(today.year, 11, 1) <= today <= date(today.year, 12, 24)):
        return None
    towns = []
    for e in entries:
        day = _parse_promo_day((e.get("tree") or {}).get("date_iso"))
        towns.append({"name": e["region_name"], "date": day.strftime("%a %b ") + str(day.day) if day else "date TBA"})
    return {"towns": towns, "offer": today <= date(today.year, 11, 15)}


def hub_next_up(blocks: list[dict], today: date, limit: int = 2, days: int = 14) -> list[dict]:
    """ROADMAP.md item 342: a town with nothing in the current weekend window
    shows its next dated events (any day in the next `days` days) instead of
    an empty card. Earliest first, attendable, never a paid promotion."""
    end = today + timedelta(days=days)
    found = []
    for block in blocks:
        for e in block["events"]:
            day = _event_day(e)
            if day is None or not (today <= day <= end) or not e.get("attendable", True) or e.get("sponsored_by") or not e.get("title"):
                continue
            found.append(e)
    found.sort(key=lambda e: (e["date_iso"], e["title"]))
    picks = prepare_email_events(found[:limit])
    return [{"emoji": email_event_emoji(e), "title": e["title"], "when": e.get("email_when") or e.get("date") or ""} for e in picks]


def hub_town_picks(weekend_events: list[dict], limit: int = 2) -> list[dict]:
    """ROADMAP.md item 339: a town's next two picks for its homepage card,
    chosen the way the email's "Don't miss" is (most family-relevant
    attendable event, ties to the earlier one), never a paid promotion."""
    pool = [e for e in weekend_events if e.get("attendable", True) and not e.get("sponsored_by")]
    best = sorted(pool, key=lambda e: (-family_relevance(e), e.get("date_iso") or "9999"))[:limit]
    picks = prepare_email_events(best)
    picks.sort(key=lambda e: e.get("date_iso") or "9999")
    return [{"emoji": email_event_emoji(e), "title": e["title"], "when": e.get("email_when") or e.get("date") or ""} for e in picks]


def render_hub_page(
    regions: list[dict],
    region_summaries: list[dict],
    now: datetime,
    newsletter: dict | None = None,
    analytics: dict | None = None,
    stats: dict | None = None,
    contact_email: str | None = None,
    halloween: dict | None = None,
    holiday: dict | None = None,
    winter: dict | None = None,
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
        leaf_pickup_in_season=is_leaf_pickup_season(now),
        corrections_cta_url=build_corrections_cta_url(contact_email),
        halloween=halloween,
        holiday=holiday,
        winter=winter,
        contact_email=contact_email,
    )


def build_celebration_block(region_sections: list[dict]) -> list[dict]:
    """The weekend hub's "Celebrations" block (item 295): events the feeds
    carry that match an open celebration, grouped by celebration name, with
    their town. [] (and no block) when none match."""
    groups: dict[str, list[dict]] = {}
    for section in region_sections:
        for e in section["events"]:
            if e.get("celebration"):
                groups.setdefault(e["celebration"], []).append(
                    {"title": e["title"], "url": e.get("url"), "town": section["region_name"], "date": e.get("date_label") or e.get("date"), "anchor": e.get("anchor_id"), "region_url": section["region_url"]}
                )
    return [{"name": name, "events": events} for name, events in groups.items()]


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
    event_pages: list[dict] | None = None,
    picks: list[dict] | None = None,
    season_banner: dict | None = None,
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
        celebrations=build_celebration_block(region_sections) if slug == "this-weekend" else None,
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
        event_pages=event_pages or [],
        picks=picks or [],
        season_banner=season_banner,
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


WEEKLY_CARD_SIZES: dict[str, tuple[int, int]] = {
    "weekly-square": (1080, 1080),
    "weekly-portrait": (1080, 1350),
    "weekly-pin": (1000, 1500),
}


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def render_weekly_card(size: tuple[int, int], date_range: str, picks: list[dict]) -> Image.Image:
    """The weekly ad and social image (ROADMAP.md items 278 and 216): the
    email's red hero, a yellow date pill and up to three pick cards with the
    email's town colours, drawn with the bundled DejaVu fonts (no emoji, no
    external services). Rendered at 1080x1080, 1080x1350 and 1000x1500."""
    width, height = size
    k = width / 1080
    img = Image.new("RGB", size, _hex_rgb("#ec3013"))
    d = ImageDraw.Draw(img)
    f = lambda name, px: _og_font(name, max(10, round(px * k)))
    m = round(64 * k)
    d.text((m, round(54 * k)), "WITHIN TEN  ·  WEEKEND GUIDE", font=f("DejaVuSans-Bold.ttf", 26), fill=_hex_rgb("#ffe9b3"))
    y = round(104 * k)
    d.text((m, y), "This weekend near you", font=f("DejaVuSans-Bold.ttf", 68), fill=(255, 255, 255))
    y += round(92 * k)
    pill_font = f("DejaVuSans-Bold.ttf", 34)
    pill_w = int(d.textlength(date_range, font=pill_font)) + round(52 * k)
    pill_h = round(58 * k)
    d.rounded_rectangle([m, y + round(6 * k), m + pill_w, y + round(6 * k) + pill_h], radius=pill_h // 2, fill=_hex_rgb("#ffd23f"))
    d.text((m + round(26 * k), y + round(6 * k) + round(9 * k)), date_range, font=pill_font, fill=_hex_rgb("#201e1d"))
    y += pill_h + round(40 * k)

    footer_h = round(96 * k)
    shown = picks[:3]
    if shown:
        gap = round(22 * k)
        card_h = min(round((230 if height / width < 1.2 else 330) * k), (height - footer_h - y - gap * (len(shown) - 1) - round(24 * k)) // len(shown))
        for pick in shown:
            d.rounded_rectangle([m, y, width - m, y + card_h], radius=round(22 * k), fill=(255, 255, 255))
            chip_w, chip_x, chip_y = round(124 * k), m + round(28 * k), y + (card_h - round(138 * k)) // 2
            d.rounded_rectangle([chip_x, chip_y, chip_x + chip_w, chip_y + round(138 * k)], radius=round(16 * k), fill=_hex_rgb(pick["pick_tint"]))
            d.rounded_rectangle([chip_x, chip_y, chip_x + chip_w, chip_y + round(46 * k)], radius=round(16 * k), fill=_hex_rgb(pick["pick_color"]))
            d.rectangle([chip_x, chip_y + round(30 * k), chip_x + chip_w, chip_y + round(46 * k)], fill=_hex_rgb(pick["pick_color"]))
            dow = (pick.get("email_dow") or "WKND")
            d.text((chip_x + chip_w // 2, chip_y + round(23 * k)), dow, font=f("DejaVuSans-Bold.ttf", 24), fill=(255, 255, 255), anchor="mm")
            d.text((chip_x + chip_w // 2, chip_y + round(94 * k)), str(pick.get("email_daynum") or ""), font=f("DejaVuSans-Bold.ttf", 54), fill=_hex_rgb("#201e1d"), anchor="mm")
            tx = chip_x + chip_w + round(32 * k)
            title_font = f("DejaVuSans-Bold.ttf", 38)
            lines = _wrap_og_text(d, pick["title"], title_font, width - m - round(28 * k) - tx)
            if len(lines) > 2:
                lines = lines[:2]
                lines[1] = lines[1].rstrip(".,; ") + "…"
            block_h = len(lines) * round(46 * k) + round(44 * k)
            ty = y + (card_h - block_h) // 2
            for line in lines:
                d.text((tx, ty), line, font=title_font, fill=_hex_rgb("#201e1d"))
                ty += round(46 * k)
            meta = pick["pick_town"] + (f" · {pick['email_clock']}" if pick.get("email_clock") else "")
            d.text((tx, ty + round(4 * k)), meta, font=f("DejaVuSans-Bold.ttf", 28), fill=_hex_rgb(pick["pick_color"]))
            y += card_h + gap
    d.text((width // 2, height - footer_h // 2), "withintenmiles.com", font=f("DejaVuSans-Bold.ttf", 36), fill=(255, 255, 255), anchor="mm")
    return img


TOT_AD_SIZES: dict[str, tuple[int, int]] = {
    "tot-square": (1080, 1080),
    "tot-portrait": (1080, 1350),
    "tot-story": (1080, 1920),
}


def tot_ad_rows(entries: list[dict]) -> tuple[list[dict], str | None]:
    """ROADMAP.md item 344: one row per town for the Halloween ad image -
    the posted or standing hours exactly as the page shows them (short form
    when every town shares one date), "standing" when the region config
    carries a note, and the shared date line. Only what the configs say."""
    dates = {tot_hours_date(e.get("hours")) for e in entries if e.get("hours")}
    common = next(iter(dates)) if len(dates) == 1 and None not in dates else None
    rows = []
    for e in entries:
        if e.get("hours"):
            hours = short_tot_hours(e["hours"]) if common else e["hours"]
        else:
            hours = "No set hours" if e.get("no_official_hours") else "Not posted yet"
        note = (e.get("note") or "").lower() if e.get("hours") else ""
        qualifier = "standing" if "standing" in note else "recommended" if "recommended" in note else None
        rows.append({"town": e["region_name"], "hours": hours, "qualifier": qualifier})
    return rows, common


def render_tot_ad(size: tuple[int, int], rows: list[dict], common_date: str | None) -> Image.Image:
    """The trick-or-treat ad creative: a night gradient, a pumpkin, the five
    towns' hours as a mini table and "Hours from each village's own page".
    Drawn with the bundled DejaVu fonts - no stock photos, no emoji."""
    width, height = size
    k = width / 1080
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    top, bottom = _hex_rgb("#0b0613"), _hex_rgb("#3a1a63")
    for y in range(height):
        t = y / max(1, height - 1)
        d.line([(0, y), (width, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    f = lambda name, px: _og_font(name, max(10, round(px * k)))
    m = round(64 * k)
    # Pumpkin: orange body, stem and a plain face.
    cx, cy, r = width - m - round(110 * k), round(150 * k), round(86 * k)
    d.ellipse([cx - r, cy - round(r * 0.85), cx + r, cy + round(r * 0.85)], fill=_hex_rgb("#ff7a00"))
    d.rectangle([cx - round(8 * k), cy - round(r * 0.85) - round(26 * k), cx + round(8 * k), cy - round(r * 0.85) + round(6 * k)], fill=_hex_rgb("#4a7a1a"))
    for ex in (-1, 1):
        d.polygon([(cx + ex * round(34 * k), cy - round(18 * k)), (cx + ex * round(14 * k), cy - round(18 * k)), (cx + ex * round(24 * k), cy - round(46 * k))], fill=_hex_rgb("#0b0613"))
    d.polygon([(cx - round(40 * k), cy + round(22 * k)), (cx + round(40 * k), cy + round(22 * k)), (cx + round(20 * k), cy + round(52 * k)), (cx - round(20 * k), cy + round(52 * k))], fill=_hex_rgb("#0b0613"))

    d.text((m, round(60 * k)), "TRICK-OR-TREAT", font=f("DejaVuSans-Bold.ttf", 60), fill=(255, 255, 255))
    d.text((m, round(134 * k)), "HOURS", font=f("DejaVuSans-Bold.ttf", 60), fill=_hex_rgb("#ffb347"))
    sub = common_date or "Halloween"
    d.text((m, round(212 * k)), sub, font=f("DejaVuSans.ttf", 34), fill=_hex_rgb("#e8dcff"))

    footer_h = round(150 * k)
    table_top = round(290 * k)
    table_bottom = height - footer_h
    n = max(1, len(rows))
    row_h = min(round(150 * k), (table_bottom - table_top) // n)
    for i, row in enumerate(rows):
        y = table_top + i * row_h
        d.rounded_rectangle([m, y + round(6 * k), width - m, y + row_h - round(6 * k)], radius=round(18 * k), fill=_hex_rgb("#1d1033"), outline=_hex_rgb("#6b4aa8"), width=max(1, round(2 * k)))
        d.text((m + round(28 * k), y + row_h // 2), row["town"], font=f("DejaVuSans-Bold.ttf", 38), fill=(255, 255, 255), anchor="lm")
        label = row["hours"] + (f"  ({row['qualifier']})" if row["qualifier"] else "")
        d.text((width - m - round(28 * k), y + row_h // 2), label, font=f("DejaVuSans-Bold.ttf", 36 if not row["qualifier"] else 30), fill=_hex_rgb("#ffb347"), anchor="rm")
    d.text((m, height - footer_h + round(34 * k)), "Hours from each village's own page", font=f("DejaVuSans.ttf", 30), fill=_hex_rgb("#e8dcff"))
    d.text((m, height - footer_h + round(84 * k)), "withintenmiles.com/trick-or-treat", font=f("DejaVuSans-Bold.ttf", 34), fill=(255, 255, 255))
    return img


def build_tot_ads(entries: list[dict], now: datetime) -> dict[str, Image.Image]:
    """The three Halloween ad creatives, in trick-or-treat season only and
    only when at least two towns have hours to show."""
    if not is_trick_or_treat_season(now) or sum(1 for e in entries if e.get("hours")) < 2:
        return {}
    rows, common = tot_ad_rows(entries)
    return {name: render_tot_ad(size, rows, common) for name, size in TOT_AD_SIZES.items()}


def build_weekly_cards(sections: list[dict], date_range: str) -> dict[str, Image.Image]:
    """One image per size from this weekend's picks; {} when there are not
    enough picks to show (fewer than two towns with something to pick)."""
    picks = build_join_picks(sections)
    if not picks or not date_range:
        return {}
    return {name: render_weekly_card(size, date_range, picks) for name, size in WEEKLY_CARD_SIZES.items()}


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


# ROADMAP.md item 321: short paths a person can type from a flyer. GitHub
# Pages has no server redirects, so each is a tiny static page (meta refresh,
# canonical to the region page, noindex) and none is in the sitemap.
SHORT_PATHS = {
    "mount-prospect-60056": "mp",
    "arlington-heights-60005": "ah",
    "des-plaines-60016": "dp",
    "palatine-60067": "pal",
    "wheeling-60090": "wh",
}


def short_redirect_target(region_id: str) -> str:
    return f"{SITE_BASE_URL}{region_id}/?utm_source=print&utm_campaign=short"


def render_short_redirect(region_id: str) -> str:
    target = short_redirect_target(region_id)
    canonical = f"{SITE_BASE_URL}{region_id}/"
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Within Ten</title>"
        '<meta name="robots" content="noindex">'
        f'<link rel="canonical" href="{canonical}">'
        f'<meta http-equiv="refresh" content="0; url={escape(target)}">'
        f'</head><body><p><a href="{escape(target)}">Continue to this weekend\'s events</a></p></body></html>\n'
    )


LINK_HEALTH_PATH = ROOT / "data" / "link_health.json"
LINK_CANDIDATES_PATH = ROOT / "data" / "link_candidates.json"
LINK_CHECK_DAYS = 14


def load_link_health(path: Path | None = None) -> dict:
    try:
        data = json.loads((path or LINK_HEALTH_PATH).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _event_day(event: dict) -> date | None:
    try:
        return datetime.fromisoformat(event["date_iso"]).date() if event.get("date_iso") else None
    except ValueError:
        return None


def annotate_registration(blocks: list[dict], today: date) -> None:
    """ROADMAP.md item 327: `reg_badge` on an event whose registration-opens
    date is known - "Sign-up opens Wed, Oct 21" until that date, then
    "Sign-up open" until the event."""
    for block in blocks:
        for event in block["events"]:
            opens = event.get("registration_opens")
            day = _event_day(event)
            if not opens or day is None or today > day:
                event.pop("reg_badge", None)
                continue
            opens_date = date.fromisoformat(opens)
            event["reg_badge"] = f"Sign-up opens {opens_date.strftime('%a, %b %-d')}" if opens_date > today else "Sign-up open"


# ROADMAP.md item 334: publishers' ALL-CAPS titles read as shouting in an email
# or on a card. Title-cased for display only; the stored title and the
# JSON-LD name keep the publisher's own text.
_KEEP_UPPER = frozenset({"ESL", "STEM", "STEAM", "LEGO", "AARP", "DIY", "CPR", "PTA", "PTO", "MS", "AI", "USA", "HS", "DJ", "LGBTQ", "ASL", "GED", "IL"})
_SMALL_WORDS = frozenset({"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "with"})
_TITLE_WORD = re.compile(r"[A-Za-z][A-Za-z']*")


def display_title(title: str | None) -> str:
    """Title case for a shouting title: more than 70% of its letters are
    capitals and it is longer than 12 characters. Known acronyms stay."""
    title = title or ""
    letters = [c for c in title if c.isalpha()]
    if len(title) <= 12 or not letters or sum(c.isupper() for c in letters) / len(letters) <= 0.7:
        return title
    first = True

    def fix(m: re.Match) -> str:
        nonlocal first
        word = m.group(0)
        is_first, first = first, False
        if word.upper() in _KEEP_UPPER:
            return word.upper()
        low = word.lower()
        return low if low in _SMALL_WORDS and not is_first else low[0].upper() + low[1:]

    return _TITLE_WORD.sub(fix, title)


def format_session_dates(days: list[date]) -> str:
    """"Wed Nov 4, 11 & 18" for sessions in one month on one weekday; the
    weekday is dropped when they differ, and a month change repeats the
    month ("Nov 25 & Dec 2")."""
    days = sorted(set(days))
    same_weekday = len({d.weekday() for d in days}) == 1
    parts, last_month = [], None
    for d in days:
        parts.append(f"{d.strftime('%b')} {d.day}" if d.month != last_month else str(d.day))
        last_month = d.month
    text = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " & " + parts[-1]
    return (days[0].strftime("%a ") if same_weekday else "") + text


def build_signups_opening(blocks: list[dict], today: date, days: int = 7, per_town: int = 2) -> list[dict]:
    """Events whose registration opens within the next `days` days (today
    included), sessions of the same title at the same venue grouped into one
    line, soonest first, at most `per_town` lines (item 334)."""
    groups: dict[tuple, dict] = {}
    for block in blocks:
        for event in block["events"]:
            opens = event.get("registration_opens")
            day = _event_day(event)
            if not opens or day is None or not event.get("attendable", True) or event.get("sponsored_by"):
                continue
            opens_date = date.fromisoformat(opens)
            if not (today <= opens_date <= today + timedelta(days=days) and day > opens_date):
                continue
            key = ((event["title"] or "").strip().lower(), event.get("venue") or event.get("source") or "", opens_date)
            group = groups.setdefault(key, {"title": display_title(event["title"]), "url": event.get("url"), "opens": opens_date, "opens_label": opens_date.strftime("%a, %b %-d"), "days": []})
            group["days"].append(day)
    found = []
    for group in groups.values():
        group["sessions_label"] = format_session_dates(group["days"])
        group["event_label"] = group["sessions_label"]
        found.append(group)
    found.sort(key=lambda e: (e["opens"], e["title"]))
    return found[:per_town]


def pick_signups_across_towns(sections: list[dict], limit: int = 4) -> list[dict]:
    """Up to `limit` sign-up lines for the email, one from each town before
    any town gets a second."""
    queues = [list(s.get("signups") or []) for s in sections]
    picked, rank = [], 0
    while len(picked) < limit and any(rank < len(q) for q in queues):
        for q in queues:
            if rank < len(q) and len(picked) < limit:
                picked.append(q[rank])
        rank += 1
    return picked


def apply_link_health(blocks: list[dict], health: dict) -> int:
    """ROADMAP.md item 308: an event link that returned 404 or 410 on two
    consecutive weekly checks is replaced by its source's calendar page and
    flagged `link_moved`. Anything else (403, a timeout, one strike) is left
    alone - a bot wall is not a dead page. Returns how many were replaced."""
    replaced = 0
    for block in blocks:
        page = block.get("source_page")
        if not page:
            continue
        for event in block["events"]:
            entry = health.get(event.get("url") or "")
            if entry and entry.get("status") in (404, 410) and entry.get("strikes", 0) >= 2:
                logger.warning("Dead link on two checks, using %s instead of %s", page, event["url"])
                event["url"] = page
                event["link_moved"] = True
                event["ics_href"] = build_ics_data_uri(event)
                event["google_calendar_url"] = build_google_calendar_url(event, event.get("town", ""))
                replaced += 1
    return replaced


def collect_link_candidates(blocks: list[dict], today: date, region_id: str) -> list[dict]:
    """Event links dated within the next LINK_CHECK_DAYS days, for the weekly
    link check to read."""
    end = today + timedelta(days=LINK_CHECK_DAYS)
    found = []
    for block in blocks:
        for event in block["events"]:
            url, iso = event.get("url") or "", event.get("date_iso")
            if not url.startswith("http") or not iso:
                continue
            try:
                when = datetime.fromisoformat(iso).date()
            except ValueError:
                continue
            if today <= when <= end:
                found.append({"url": url, "region": region_id})
    return found


THANKS_PAGES = {
    "went": ("Thanks, that helps us keep this useful.", "Glad you got out. Knowing that readers go to the events we list is how we decide what to keep."),
    "not-yet": ("Thanks, that helps us keep this useful.", "No problem. There is another list every Thursday, and the towns below have this weekend's events right now."),
}


def poll_links(issue_date: date) -> dict:
    """ROADMAP.md item 331: the two "Did you go?" links for an issue, counted
    as page views of /thanks/went/ and /thanks/not-yet/ and as per-link
    clicks in Buttondown."""
    w = issue_date.isoformat()
    return {"went": f"{SITE_BASE_URL}thanks/went/?w={w}", "not_yet": f"{SITE_BASE_URL}thanks/not-yet/?w={w}"}


def render_thanks_page(kind: str, regions: list[dict], analytics: dict | None = None) -> str:
    headline, body = THANKS_PAGES[kind]
    towns = [
        {"name": r["name"], "url": SITE_BASE_URL + r["id"] + "/", "color": EMAIL_TOWN_COLORS[i % len(EMAIL_TOWN_COLORS)][0]}
        for i, r in enumerate(regions)
    ]
    forward = "mailto:?subject=" + quote("What's on this weekend near us") + "&body=" + quote(
        f"A free weekly email with what's on this weekend in our towns: {SITE_BASE_URL}join/?utm_source=forward"
    )
    return get_template_env().get_template("thanks.html.j2").render(
        headline=headline, body=body, towns=towns, forward_href=forward,
        canonical_url=f"{SITE_BASE_URL}thanks/{kind}/", analytics=analytics,
    )


def flyer_url(region_id: str, campaign: str) -> str:
    """The URL a flyer's QR code encodes (ROADMAP.md item 320)."""
    return f"{SITE_BASE_URL}{region_id}/?utm_source=print&utm_campaign={campaign}#newsletter-signup"


def flyer_variants(placements: list[dict] | None) -> list[dict]:
    """One generic flyer plus one per configured print placement, each with
    its own counted campaign (`flyer-<place id>`)."""
    variants = [{"id": "", "campaign": "flyer-general"}]
    for p in placements or []:
        if p.get("id"):
            variants.append({"id": str(p["id"]), "campaign": f"flyer-{p['id']}"})
    return variants


def render_flyer(region_id: str, town: str, examples: list[str], campaign: str, copies: int = 1, color: str = "#0f766e") -> str:
    import segno

    url = flyer_url(region_id, campaign)
    qr = segno.make(url, error="m").svg_inline(scale=8, border=2, dark="#000", light="#fff", omitsize=True)
    template = get_template_env().get_template("flyer.html.j2")
    return template.render(
        town=town, examples=examples[:3], qr=qr, url=url, copies=copies, color=color, short=SHORT_PATHS.get(region_id, region_id)
    )


EVENT_PAGES_PATH = ROOT / "data" / "event_pages.json"
EVENT_PAGE_CAP = 20
EVENT_PAGE_NOINDEX_DAYS = 7
EVENT_PAGE_DELETE_DAYS = 60
_EVENT_PAGE_FIELDS = ("title", "date_iso", "detail", "detail_long", "venue", "street_address", "postal_code", "town", "state", "source", "url", "tags", "region_id", "region_url", "sponsored_by", "ics_href")


def event_page_path(event: dict) -> str:
    """`e/<yyyy-mm-dd>-<slug>/` (ROADMAP.md item 369): dated, so the same
    title on another day is another page."""
    slug = re.sub(r"[^a-z0-9]+", "-", (event.get("title") or "").lower()).strip("-")[:60].rstrip("-") or "event"
    return f"e/{(event.get('date_iso') or '')[:10]}-{slug}/"


def select_event_page_events(sections: list[dict], tot_entries: list[dict] | None = None, limit: int = EVENT_PAGE_CAP, santa_entries: list[dict] | None = None) -> list[dict]:
    """The few events that get their own page (ROADMAP.md item 369), at most
    `limit`: paid Featured/Event Promo events, the week's "Don't miss" picks
    and the weekend's trunk-or-treats, in that order. Never all events (that
    would be hundreds of thin copies of publishers' listings), and never an
    event with no first-party link to point at."""
    region_of = {s["region_name"]: s for s in sections}
    chosen: list[dict] = []
    seen: set[str] = set()

    def add(event: dict, section: dict | None):
        url = event.get("url") or ""
        if len(chosen) >= limit or not url.startswith(("http://", "https://")) or not event.get("date_iso") or not event.get("title"):
            return
        entry = {k: event.get(k) for k in _EVENT_PAGE_FIELDS}
        entry["region_url"] = (section or {}).get("region_url") or event.get("region_url")
        entry["region_id"] = ((entry["region_url"] or "").rstrip("/").rsplit("/", 1)[-1]) or None
        path = event_page_path(event)
        if path not in seen:
            seen.add(path)
            chosen.append({"path": path, **entry})

    for s in sections:
        for e in s["weekend_events"]:
            if e.get("sponsored_by"):
                add(e, s)
    for pick in build_join_picks(sections, limit=3):
        add(pick, region_of.get(pick.get("pick_town")))
    for entry in tot_entries or []:
        for e in entry.get("events") or []:
            if TRUNK_OR_TREAT.search(e.get("title", "")):
                add(dict(e, town=e.get("town") or entry["region_name"]), {"region_url": entry.get("region_url")})
    for entry in santa_entries or []:  # item 379: every Santa event, within the cap
        for e in entry.get("events") or []:
            add(dict(e, town=e.get("town") or entry["region_name"]), {"region_url": entry.get("region_url")})
    return chosen


def update_event_pages(registry: dict, selected: list[dict], today: date) -> tuple[dict, list[dict], list[dict], list[str]]:
    """Merge this build's selection into the stored registry and apply the
    lifetime rules: indexable until the event is `EVENT_PAGE_NOINDEX_DAYS`
    days past (then noindex and out of the sitemap), deleted after
    `EVENT_PAGE_DELETE_DAYS`. Returns (registry, active pages, expired pages,
    deleted paths)."""
    registry = dict(registry)
    for entry in selected:
        registry.setdefault(entry["path"], {**entry, "first_seen": today.isoformat()})
        registry[entry["path"]].update({k: v for k, v in entry.items() if k != "path" and v is not None})
    active, expired, deleted = [], [], []
    for path, entry in sorted(registry.items()):
        try:
            age = (today - date.fromisoformat(entry["date_iso"][:10])).days
        except (KeyError, ValueError):
            age = EVENT_PAGE_DELETE_DAYS + 1
        entry["path"] = path
        if age > EVENT_PAGE_DELETE_DAYS:
            deleted.append(path)
        elif age > EVENT_PAGE_NOINDEX_DAYS:
            expired.append(entry)
        else:
            active.append(entry)
    for path in deleted:
        registry.pop(path, None)
    return registry, active, expired, deleted


def render_event_page(entry: dict, *, expired: bool = False, more: list[dict] | None = None, newsletter: dict | None = None, analytics: dict | None = None) -> str:
    day = datetime.fromisoformat(entry["date_iso"])
    time_label = event_time_label(entry["date_iso"])
    when_label = day.strftime("%a %b ") + str(day.day) + (f", {time_label}" if time_label else "")
    town, state = entry.get("town") or "", entry.get("state") or ""
    venue = entry.get("venue")
    where_label = ", ".join(p for p in (venue, entry.get("street_address"), town) if p)
    page_url = SITE_BASE_URL + entry["path"]
    title = entry["title"]
    short_when = day.strftime("%a %b ") + str(day.day)
    page_title = f"{display_title(title)}, {short_when}, {', '.join(p for p in (venue, town) if p)} | Within Ten"
    detail = entry.get("detail_long") or sentence_cut(strip_description_header(entry.get("detail")))
    source_name = short_district(entry.get("source") or "") or "the organiser"
    tags = [tag_display(t)["label"] for t in (entry.get("tags") or [])]
    ld = {"@context": "https://schema.org", **event_jsonld({**entry, "detail": detail}, page_url)}
    return get_template_env().get_template("event.html.j2").render(
        page_title=page_title,
        description=truncate(f"{display_title(title)} on {short_when} in {town}. {detail}", 200),
        canonical_url=page_url,
        og_image_url=SITE_BASE_URL + "og/default.png",
        json_ld=json_for_script(ld),
        hub_url=SITE_BASE_URL,
        region_url=entry.get("region_url") or SITE_BASE_URL,
        region_id=entry.get("region_id") or "all",
        town=town,
        title=display_title(title),
        emoji=email_event_emoji(entry),
        town_color=entry.get("town_color") or EMAIL_TOWN_COLORS[0][0],
        dow=day.strftime("%a").upper(),
        daynum=str(day.day),
        when_label=when_label,
        where_label=where_label,
        detail=detail,
        tags=tags,
        source_url=entry["url"],
        source_name=source_name,
        ics_href=entry.get("ics_href"),
        more=more or [],
        expired=expired,
        newsletter=newsletter or {"configured": False},
        analytics=analytics,
    )


def load_event_page_registry() -> dict:
    try:
        stored = json.loads(EVENT_PAGES_PATH.read_text(encoding="utf-8"))
        return stored if isinstance(stored, dict) else {}
    except (OSError, ValueError):
        return {}


def prime_event_page_paths(now: datetime) -> None:
    """Load which `/e/` pages are active before any listing is rendered, so
    the region pages' markup can point an event at its own page (item 375)."""
    global ACTIVE_EVENT_PAGE_PATHS
    _, active, _, _ = update_event_pages(load_event_page_registry(), [], now.astimezone(LOCAL_TZ).date())
    ACTIVE_EVENT_PAGE_PATHS = {e["path"] for e in active}


def event_page_more_links(entry: dict, sections: list[dict], limit: int = 3) -> list[dict]:
    """Up to `limit` other attendable events for an `/e/` page's "More this
    weekend": the event's own town first, then the nearest towns (ROADMAP.md
    items 373 and 214) when it has fewer. One link per title."""
    home = next((s for s in sections if s["region_url"] == entry.get("region_url")), None)
    ordered = [home] if home else []
    rest = [s for s in sections if s is not home]
    if home and home.get("region_lat") is not None and home.get("region_lon") is not None:
        rest.sort(key=lambda s: _haversine_miles(home["region_lat"], home["region_lon"], s["region_lat"], s["region_lon"]) if s.get("region_lat") is not None and s.get("region_lon") is not None else 1e9)
    ordered += rest
    more, seen = [], {entry["title"]}
    for section in ordered:
        for e in section["weekend_events"]:
            if len(more) >= limit:
                return more
            if e.get("title") and e["title"] not in seen and e.get("attendable", True):
                seen.add(e["title"])
                more.append({"title": display_title(e["title"]), "town": section["region_name"], "url": f"{section['region_url']}#{e.get('anchor_id') or event_anchor_id(e)}", "same_town": section is home})
    return more


def write_event_pages(sections: list[dict], tot_entries: list[dict], now: datetime, newsletter: dict | None, analytics: dict | None, santa_entries: list[dict] | None = None) -> list[dict]:
    """Select, store and write the `/e/` pages; returns the active (indexable,
    in-sitemap) ones. Expired pages are rewritten noindex; pages past the
    delete age are removed from disk and the registry."""
    today = now.astimezone(LOCAL_TZ).date()
    registry, active, expired, deleted = update_event_pages(load_event_page_registry(), select_event_page_events(sections, tot_entries, santa_entries=santa_entries), today)
    colors = {s["region_url"]: EMAIL_TOWN_COLORS[i % len(EMAIL_TOWN_COLORS)][0] for i, s in enumerate(sections)}
    for group, is_expired in ((active, False), (expired, True)):
        for entry in group:
            more = [] if is_expired else event_page_more_links(entry, sections)
            entry = {**entry, "town_color": colors.get((entry.get("region_url") or ""), EMAIL_TOWN_COLORS[0][0])}
            page_dir = OUTPUT_DIR / entry["path"]
            page_dir.mkdir(parents=True, exist_ok=True)
            (page_dir / "index.html").write_text(
                render_event_page(entry, expired=is_expired, more=more, newsletter=newsletter, analytics=analytics), encoding="utf-8"
            )
    for path in deleted:
        shutil.rmtree(OUTPUT_DIR / path, ignore_errors=True)
    EVENT_PAGES_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVENT_PAGES_PATH.write_text(json.dumps(registry, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    logger.info("Event pages: %d active, %d expired (noindex), %d deleted", len(active), len(expired), len(deleted))
    return active


def collect_sitemap_urls(region_summaries: list[dict], issues: list[dict] | None = None, event_pages: list[dict] | None = None, leaf_pickup_in_season: bool = False) -> list[str]:
    urls = [
        SITE_BASE_URL,
        SITE_BASE_URL + "this-weekend/",
        SITE_BASE_URL + "today/",
        SITE_BASE_URL + "free/",
        SITE_BASE_URL + "sponsor/",
        SITE_BASE_URL + "about/",
        SITE_BASE_URL + "trick-or-treat/",
        SITE_BASE_URL + "holidays/",
        SITE_BASE_URL + "santa/",
    ]
    if leaf_pickup_in_season:
        urls.append(SITE_BASE_URL + "leaf-pickup/")
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
        if r.get("holiday"):
            urls.append(base + "holiday/")
        if r.get("winter_break"):
            urls.append(base + "winter-break/")
        if r.get("guide_slugs"):
            urls.append(base + "guides/")
            urls += [base + f"guides/{slug}/" for slug in r["guide_slugs"]]
    if issues:
        urls.append(SITE_BASE_URL + "issues/")
        urls += [SITE_BASE_URL + f"issues/{i['date']}/" for i in issues]
    urls += [SITE_BASE_URL + e["path"] for e in event_pages or []]  # item 369: active event pages only
    return urls


def build_sitemap_xml(region_summaries: list[dict], now: datetime, issues: list[dict] | None = None, event_pages: list[dict] | None = None) -> str:
    lastmod = now.strftime("%Y-%m-%d")
    urls = collect_sitemap_urls(region_summaries, issues, event_pages, is_leaf_pickup_season(now))
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


WEEKLY_FEED_HISTORY_PATH = ROOT / "data" / "weekly_feed_history.json"
WEEKLY_FEED_KEEP = 8


def load_weekly_feed_history(path: Path = WEEKLY_FEED_HISTORY_PATH) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def record_weekly_feed_item(history: dict, region_id: str, item: dict, keep: int = WEEKLY_FEED_KEEP) -> list[dict]:
    """Add this weekend's item to a town's history (newest first, one per
    guid, last `keep` weekends). The same weekend rebuilt many times replaces
    its own item, so a feed reader never sees it twice."""
    items = [i for i in history.get(region_id, []) if i.get("guid") != item["guid"]]
    items.insert(0, item)
    items = sorted(items, key=lambda i: i["weekend"], reverse=True)[:keep]
    history[region_id] = items
    return items


def build_weekly_item(
    region_id: str, region_name: str, events: list[dict], friday: date, date_range: str, now: datetime, image: dict | None
) -> dict | None:
    """One Nextdoor-ready item per town per weekend (ROADMAP.md item 304): the
    town's top picks as a short article. Sponsored and promoted events are
    left out, as Nextdoor requires, and a town with nothing to pick gets no
    item rather than an empty post."""
    plain = [e for e in events if e.get("attendable", True) and not e.get("sponsored_by")]
    if not plain:
        return None
    prepared = prepare_email_events(plain, limit=6)
    link = f"{SITE_BASE_URL}{region_id}/this-weekend/?utm_source=nextdoor&utm_campaign=weekly"
    parts = [f"<p>What's on in {escape(region_name)} this weekend ({escape(date_range)}), from the village, library and park district calendars.</p>"]
    for e in prepared:
        when = " · ".join(x for x in (e.get("email_when"), e.get("email_where")) if x)
        blurb = f" {escape(e['email_blurb'])}" if e.get("email_blurb") else ""
        title = escape(e["title"])
        parts.append(f'<h3><a href="{escape(e["url"])}">{title}</a></h3><p>{escape(when)}.{blurb}</p>')
    parts.append(f'<p><a href="{escape(link)}">See everything happening this weekend in {escape(region_name)}</a></p>')
    return {
        "guid": f"{SITE_BASE_URL}{region_id}/this-weekend/#weekly-{friday.isoformat()}",
        "weekend": friday.isoformat(),
        "title": f"This weekend in {region_name}: {len(plain)} thing{'s' if len(plain) != 1 else ''} to do ({date_range})",
        "link": link,
        "pub_date": format_datetime(now.astimezone(timezone.utc)),
        "html": "\n".join(parts),
        "image": image,
    }


def build_weekly_feed_xml(region_name: str, region_id: str, items: list[dict], now: datetime) -> str:
    """RSS 2.0 for Nextdoor News Accounts (item 304): full article HTML in
    content:encoded and the featured image as both an enclosure and
    media:content."""
    out = []
    for it in items:
        img = it.get("image")
        media = ""
        if img:
            media = (
                f'    <enclosure url="{xml_escape(img["url"])}" type="image/png" length="{img["length"]}"/>\n'
                f'    <media:content url="{xml_escape(img["url"])}" type="image/png" medium="image"/>\n'
            )
        out.append(
            "  <item>\n"
            f"    <title>{xml_escape(it['title'])}</title>\n"
            f"    <link>{xml_escape(it['link'])}</link>\n"
            f'    <guid isPermaLink="false">{xml_escape(it["guid"])}</guid>\n'
            f"    <pubDate>{it['pub_date']}</pubDate>\n"
            f"    <description>{xml_escape(it['title'])}</description>\n"
            f"    <content:encoded><![CDATA[{it['html'].replace(']]>', ']]]]><![CDATA[>')}]]></content:encoded>\n"
            + media
            + "  </item>\n"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:media="http://search.yahoo.com/mrss/">\n<channel>\n'
        f"  <title>{xml_escape(SITE_NAME)} · {xml_escape(region_name)} weekly</title>\n"
        f"  <link>{xml_escape(SITE_BASE_URL + region_id + '/this-weekend/')}</link>\n"
        f"  <description>One post a week: what's on this weekend in {xml_escape(region_name)}.</description>\n"
        f"  <lastBuildDate>{format_datetime(now.astimezone(timezone.utc))}</lastBuildDate>\n"
        + "".join(out)
        + "</channel>\n</rss>\n"
    )


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


def build_feed_xml(
    feed_items: list[dict],
    now: datetime,
    source_completeness: dict | None = None,
    *,
    title: str | None = None,
    scope: str = "every",
    self_url: str | None = None,
) -> str:
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
    # ROADMAP.md item 269: an item may carry `site_url`, its card on this site
    # (the same URL events.json uses). Then <link> and <guid> point there, so
    # anything built on the feed cites Within Ten, and the publisher moves to
    # the description ("Official listing: ...") and <source url>. Without it
    # (older callers) the item links to the publisher as before.
    where = f"across every {SITE_NAME} region" if scope == "every" else f"in {scope}"
    description = (
        f"Upcoming events {where}, soonest first - "
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
        item_title = xml_escape(f"{e['region_name']}: {e['title']}")
        site_url = e.get("site_url")
        if site_url:
            link, guid_value, is_permalink = site_url, site_url, "true"
            body = (e.get("detail") or "").strip()
            body = (body + " " if body else "") + f"Official listing: {e['url']}"
            source = f'    <source url="{xml_escape(e["url"])}">{xml_escape(e.get("source") or e["region_name"])}</source>\n'
        else:
            link = e["url"]
            if url_counts[e["url"]] > 1:
                guid_value, is_permalink = f"{e['url']}#{e['date_iso']}", "false"
            else:
                guid_value, is_permalink = e["url"], "true"
            body = e.get("detail") or ""
            source = ""
        items.append(
            "  <item>\n"
            f"    <title>{item_title}</title>\n"
            f"    <link>{xml_escape(link)}</link>\n"
            f"    <guid isPermaLink=\"{is_permalink}\">{xml_escape(guid_value)}</guid>\n"
            f"    <description>{xml_escape(body)}</description>\n"
            f"    <pubDate>{format_datetime(pub_dt)}</pubDate>\n"
            + source
            + "  </item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n'
        "<channel>\n"
        f"  <title>{xml_escape(title or f'{SITE_NAME} — Upcoming Local Events')}</title>\n"
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


# Paths of `/e/` pages that exist (ROADMAP.md items 369 and 375), loaded from the
# stored registry at the start of a build, so a listing's markup can point at
# the event's own page when it has one.
ACTIVE_EVENT_PAGE_PATHS: set[str] = set()


def event_jsonld(event: dict, url: str) -> dict:
    """The one schema.org Event builder (ROADMAP.md item 375), used by the
    region pages, events.json, /trick-or-treat/ and the /e/ pages so they
    cannot disagree: `location` through schema_location() (the venue table,
    items 335 and 372), `organizer`, `eventStatus`, `isAccessibleForFree`,
    `sponsor` and no `offers` (no price is known; add `priceCurrency` with
    any future `offers`). Only `url` differs per output."""
    entry = {
        "@type": "Event",
        "name": event["title"],
        "startDate": schema_start_date(event["date_iso"]),
        "url": url,
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "location": schema_location(event),
    }
    if event.get("url"):
        entry["sameAs"] = event["url"]
        origin = re.match(r"https?://[^/]+", event["url"])
        organizer = {"@type": "Organization", "name": short_district(event.get("source") or "") or "the organiser"}
        if origin:
            organizer["url"] = origin.group(0)
        entry["organizer"] = organizer
    if event.get("detail"):
        entry["description"] = event["detail"]
    if "free" in (event.get("tags") or []):
        entry["isAccessibleForFree"] = True
    if event.get("sponsored_by"):
        entry["sponsor"] = {"@type": "Organization", "name": event["sponsored_by"]}
    if event.get("registration_opens"):
        entry["registrationOpens"] = event["registration_opens"]  # extension key (item 327)
    return entry


def _event_list_item(event: dict, page_url: str, position: int) -> dict:
    """One schema.org ListItem wrapping an Event. `url` is the event's own
    `/e/` page when it has one (item 369), else its card on this site (item
    228's anchor), with the source in `sameAs`."""
    own_page = event_page_path(event) if event.get("date_iso") else None
    url = SITE_BASE_URL + own_page if own_page in ACTIVE_EVENT_PAGE_PATHS else f"{page_url}#{event.get('anchor_id') or event_anchor_id(event)}"
    return {"@type": "ListItem", "position": position, "item": event_jsonld(event, url)}


def count_next_seven_days(groups: list[tuple[str, str, list[dict]]], today: date) -> int:
    """ROADMAP.md item 384: attendable, dated events in the next 7 days
    (today included) across every group, one per title and start time. The
    sponsor page's proof number: a rolling window, so it doesn't shrink as
    the weekend passes."""
    end = today + timedelta(days=7)
    seen = set()
    for _name, _url, events in groups:
        for e in events:
            if not e.get("title") or not e.get("date_iso") or e.get("attendable") is False:
                continue
            try:
                day = date.fromisoformat(e["date_iso"][:10])
            except ValueError:
                continue
            if today <= day < end:
                seen.add((e["title"].strip().lower(), e["date_iso"]))
    return len(seen)


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


def build_llms_txt(region_summaries: list[dict], source_completeness: dict | None = None, issues: list[dict] | None = None) -> str:
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
    lines += [f"- [RSS: {r['name']}]({SITE_BASE_URL}{r['path']}feed.xml)" for r in region_summaries]
    lines += ["", "## Weekly posts (one article a week per town)"]
    lines += [f"- [RSS: {r['name']} this weekend]({SITE_BASE_URL}{r['path']}weekly.xml)" for r in region_summaries]
    # ROADMAP.md item 230: the machine-readable index, and the plain-text
    # content itself, for agents that read this file family.
    lines += [
        "",
        f"## Machine-readable events (schema.org JSON-LD, next {EVENTS_JSON_DAYS} days)",
        f"- [Every region]({SITE_BASE_URL}events.json)",
    ]
    lines += [f"- [{r['name']}]({SITE_BASE_URL}{r['path']}events.json)" for r in region_summaries]
    lines += ["", "## Full text", f"- [This weekend's events, as plain text]({SITE_BASE_URL}llms-full.txt)"]
    if issues:
        lines += ["", "## Past weekly issues", f"- [All issues, newest first]({SITE_BASE_URL}issues/)"]
        lines += [f"- [{i['subject']}]({SITE_BASE_URL}issues/{i['date']}/)" for i in issues[:10]]
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
SUBJECT_MAX_LEN = 50  # ROADMAP.md item 363: about 33 characters show on a phone, 30-50 recommended
HALLOWEEN_SUBJECT_MAX_LEN = 60  # item 348's fixed Halloween subject is exempt


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


def _fit_subject(titles: list[str], total: int, lone_leads: list[str] | None = None, towns: int = 0) -> str:
    """'{A}, {B} and N more this weekend' within SUBJECT_MAX_LEN.

    Never cuts a title (items 363 and 225): the first form that fits whole
    wins - two titles with the count, the lead alone with the count, the
    next-ranked titles alone, two titles without the count - and the last
    resort is the plain "N things to do this weekend in M towns". No "…" and
    no "+ N more". "and" rather than "&" because real titles contain "&"
    themselves.
    """
    def compose(named: list[str]) -> str:
        more = total - len(named)
        if len(named) == 1:
            return f"{named[0]} this weekend" if more == 0 else f"{named[0]} and {more} more this weekend"
        lead = f"{named[0]}, {named[1]}" if more else f"{named[0]} and {named[1]}"
        return f"{lead} and {more} more this weekend" if more else f"{lead} this weekend"

    leads = lone_leads if lone_leads is not None else titles
    candidates = [compose(titles[:2])] if len(titles) >= 2 else []
    candidates += [compose([t]) for t in leads]
    candidates += [compose([t]) for t in titles if t not in leads]
    if len(titles) >= 2:
        candidates.append(f"{titles[0]} and {titles[1]}")
    for subject in candidates:
        if len(subject) <= SUBJECT_MAX_LEN:
            return subject
    places = f" in {towns} towns" if towns > 1 else ""
    return f"{total} thing{'s' if total != 1 else ''} to do this weekend{places}"


def build_combined_email_subject_line(sections: list[dict], now: datetime | None = None, top_picks: list[dict] | None = None) -> str:
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
    # ROADMAP.md item 348: the Halloween-weekend issue has one fixed subject.
    if now is not None and email_edition(now) == "halloween":
        count = _COUNT_WORDS.get(len(sections), str(len(sections))).lower()
        return truncate(f"Trick-or-treat hours, all {count} towns, plus Halloween weekend", HALLOWEEN_SUBJECT_MAX_LEN)
    # ROADMAP.md item 393: so does the Thanksgiving-weekend issue (the Wednesday
    # before); the longer wording is 66 characters, so the short form is used.
    if now is not None and email_edition(now) == "holiday":
        return "Thanksgiving weekend: lights, shops & more"
    attendable = _round_robin_attendable(sections)
    if not attendable:
        return f"This week across {_join_names([s['region_name'] for s in sections])}: what's coming up"
    # Item 222: lead with the most notable occasion, not whichever event
    # round-robin order puts first. sorted() is stable, so ties keep the
    # round-robin spread across towns.
    ranked = sorted(attendable, key=_occasion_score, reverse=True)
    # ROADMAP.md item 364: lead with the email's first "Don't miss" pick and
    # name a pick from a different town second; the occasion score only
    # orders what is left.
    ordered = ranked
    lead_first = bool(top_picks)
    if lead_first:
        first = top_picks[0]
        second = next((p for p in top_picks[1:] if p.get("pick_town") != first.get("pick_town")), None) or (top_picks[1] if len(top_picks) > 1 else None)
        chosen = [p for p in (first, second) if p]
        keys = {(p.get("title"), p.get("url")) for p in chosen}
        ordered = chosen + [e for e in ranked if (e.get("title"), e.get("url")) not in keys]
    cleaned = [dict(e, title=display_title(_clean_subject_title(e["title"]))) for e in ordered]
    titles = _pick_preheader_titles(cleaned, limit=5)
    if not titles:
        with_events = [s["region_name"] for s in sections if any(e.get("attendable", True) for e in s["weekend_events"])]
        return f"{len(attendable)} things to do this weekend in {len(with_events)} towns"
    scores = {e["title"]: _occasion_score(e) for e in cleaned}
    best = max((scores.get(title, 0) for title in titles), default=0)
    lone_leads = [titles[0]] if lead_first else [title for title in titles if scores.get(title, 0) == best]
    towns = sum(1 for s in sections if any(e.get("attendable", True) and not e.get("sponsored_by") for e in s["weekend_events"]))
    return _fit_subject(titles, len(attendable), lone_leads, towns)


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


_LEADING_CONTACT_TOKEN = re.compile(r"^(?:[\w.+-]+@[\w-]+(?:\.[\w-]+)+|https?://\S+|www\.\S+)\s+(?=\S)")


def strip_description_header(detail: str | None) -> str:
    """A description with its leading Communico date/time header removed and
    whitespace collapsed - what a card shows beneath the date and time it
    already displays."""
    text = _DESCRIPTION_DATE_PREFIX.sub("", detail or "")
    text = re.sub(r"\s+", " ", text).strip(" -–:")
    # ROADMAP.md item 333: a bare contact email or URL ahead of the first sentence.
    return _LEADING_CONTACT_TOKEN.sub("", text)


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
    def phrases(key: str):
        items = [str(w).lower() for w in data.get(key) or []]
        return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in items) + r")(?!\w)", re.I) if items else None

    return {
        "boost_tags": boost, "adult_pattern": pattern, "partisan_pattern": phrases("exclude_partisan"), "civic_pattern": phrases("keep_civic"),
        "pick_min_score": int(data.get("pick_min_score") or 0), "not_a_pick_pattern": phrases("not_a_pick"),
    }


def filter_partisan_events(blocks: list[dict], config: dict | None = None) -> tuple[list[dict], list[dict]]:
    """ROADMAP.md item 361: drop party and campaign meetings from a region's
    fetched blocks (matched whole-word on title and description), keeping
    civic information - an event that also matches a `keep_civic` phrase
    stays. Returns (blocks, the excluded events); every exclusion is logged
    with its source so a wrong call is visible and fixable in the YAML."""
    config = config if config is not None else load_relevance_config()
    partisan, civic = config.get("partisan_pattern"), config.get("civic_pattern")
    if partisan is None:
        return blocks, []
    kept_blocks, excluded = [], []
    for block in blocks:
        kept = []
        for event in block["events"]:
            text = f"{event.get('title') or ''}. {event.get('detail') or ''}"
            if partisan.search(text) and not (civic and civic.search(text)):
                excluded.append(event)
                logger.info("Excluded partisan listing %r from %s", event.get("title"), event.get("source") or block.get("section"))
            else:
                kept.append(event)
        kept_blocks.append({**block, "events": kept})
    return kept_blocks, excluded


CELEBRATIONS_PATH = CONFIG_DIR / "celebrations.yaml"


@lru_cache(maxsize=1)
def load_celebrations() -> list[dict]:
    try:
        data = load_yaml(CELEBRATIONS_PATH)
    except OSError:
        data = {}
    return [c for c in (data.get("celebrations") or []) if c.get("name") and c.get("keywords")]


def active_celebrations(day: date, celebrations: list[dict] | None = None) -> list[dict]:
    """Celebrations whose window includes `day` (ROADMAP.md item 295)."""
    active = []
    for c in load_celebrations() if celebrations is None else celebrations:
        if c.get("date"):
            center = _parse_promo_day(c["date"])
            if center and center - timedelta(days=int(c.get("days_before", 0))) <= day <= center + timedelta(days=int(c.get("days_after", 0))):
                active.append(c)
        elif c.get("start") and c.get("end"):
            md = (day.month, day.day)
            start = tuple(int(x) for x in str(c["start"]).split("-"))
            end = tuple(int(x) for x in str(c["end"]).split("-"))
            if start <= md <= end:
                active.append(c)
    return active


def annotate_celebrations(blocks: list[dict], day: date, celebrations: list[dict] | None = None) -> None:
    """Set `celebration` on every event that matches an open celebration's
    keywords, in place. Matched on the title and description."""
    active = active_celebrations(day, celebrations)
    if not active:
        return
    for block in blocks:
        for e in block.get("events", []):
            text = f"{e.get('title') or ''} {e.get('detail') or ''}".lower()
            for c in active:
                if any(str(k).lower() in text for k in c["keywords"]):
                    e["celebration"] = c["name"]
                    break


def family_relevance(event: dict) -> int:
    """A small score for ordering: +1 for each boost tag the event carries
    (kid-friendly, free, outdoor), +1 for a celebration the feeds carry (item
    295), -2 for each adult-programme word in the title. Reorders only;
    nothing is ever hidden by it."""
    cfg = load_relevance_config()
    tags = set(event.get("tags") or [])
    score = sum(1 for t in cfg["boost_tags"] if t in tags) + (1 if event.get("celebration") else 0)
    if cfg["adult_pattern"] is not None:
        score -= 2 * len(cfg["adult_pattern"].findall(event.get("title") or ""))
    return score


def is_pick_worthy(event: dict) -> bool:
    """ROADMAP.md item 380: only an event that reaches the minimum family
    score and is not a class, service or pick-up kit may be a "pick". Weak
    events stay on every list; they just never lead one."""
    cfg = load_relevance_config()
    pattern = cfg.get("not_a_pick_pattern")
    if pattern is not None and pattern.search(event.get("title") or ""):
        return False
    return family_relevance(event) >= cfg.get("pick_min_score", 0)


def weekend_display_key(event: dict) -> tuple:
    """Featured first, then date and start time, then the more family-relevant
    of two events at the same moment. One key for the weekend hub, the
    region weekend pages and both emails, so they cannot disagree."""
    return (not event.get("sponsored_by"), event.get("date_iso") or "9999", -family_relevance(event))


def order_weekend_events(events: list[dict]) -> list[dict]:
    return sorted(events, key=weekend_display_key)


# The weekly email's visual layer: an emoji per event, a day/date chip and up
# to two badges. Emoji are chosen from the title first (what the event *is*),
# then from its tags, so a "Spooky Scary Studio" reads as Halloween rather
# than as a generic indoor programme. Plain Unicode, so every client renders
# it with no images to block.
_EMAIL_EMOJI_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("halloween", "spooky", "trick-or-treat", "trick or treat", "costume", "haunted", "monster", "boo "), "🎃"),
    (("pumpkin", "harvest", "hayride", "apple", "fall fest", "autumn", "scarecrow"), "🍂"),
    (("farmers market", "market"), "🧺"),
    (("fishing", "derby"), "🎣"),
    (("concert", "music", "band", "jazz", "orchestra", "choir", "sing"), "🎵"),
    (("movie", "film", "screening", "cinema"), "🎬"),
    (("storytime", "story time", "book", "read", "author", "library"), "📚"),
    (("craft", "paint", "art", "studio", "draw"), "🎨"),
    (("lego", "stem", "science", "robot", "tinker", "coding", "tech"), "🔬"),
    (("game", "trivia", "bingo", "wii"), "🎲"),
    (("baby", "toddler", "tots", "babytime", "walkers"), "👶"),
    (("dog", "pet", "puppy"), "🐕"),
    (("run", "5k", "walk", "bike", "hike", "yoga", "fitness", "swim"), "🏃"),
    (("food", "taste", "pancake", "breakfast", "dinner", "cook", "bake", "wine", "beer"), "🍽️"),
    (("festival", "fest", "fair", "parade", "carnival", "celebration", "re-opening", "grand opening"), "🎉"),
    (("sale", "shop"), "🛍️"),
    (("computer", "digital", "photos", "device", "tablet", "phone"), "💻"),
)
_EMAIL_TAG_EMOJI_ORDER = ("kid_friendly", "outdoor", "food", "art_culture", "toddler", "dog_friendly", "elementary", "teen", "free", "indoor")
_EMAIL_BADGE_ORDER = ("free", "kid_friendly", "outdoor", "dog_friendly")


def email_event_emoji(event: dict) -> str:
    """One emoji that says what the event is, for the weekly email."""
    title = " " + (event.get("title") or "").lower() + " "
    for keywords, emoji in _EMAIL_EMOJI_RULES:
        if any(k in title for k in keywords):
            return emoji
    tags = set(event.get("tags") or [])
    for tag in _EMAIL_TAG_EMOJI_ORDER:
        if tag in tags:
            return tag_display(tag).get("emoji") or "📍"
    return "📍"


def email_visuals(event: dict) -> dict:
    """Display-only fields for the email's event row: `email_emoji`, a date
    chip (`email_dow` "SAT", `email_daynum` "10"), `email_clock` ("10:00 AM"
    or None) and up to two `email_badges` (label + emoji) from the tags that
    matter most when choosing a weekend plan. Nothing here is invented: an
    untimed event has no clock, an untagged one has no badges."""
    dow = daynum = None
    if event.get("date_iso"):
        try:
            d = datetime.fromisoformat(event["date_iso"])
            dow, daynum = d.strftime("%a").upper(), str(d.day)
        except ValueError:
            pass
    tags = set(event.get("tags") or [])
    badges = [{"label": tag_display(t).get("label", t), "emoji": tag_display(t).get("emoji", "")} for t in _EMAIL_BADGE_ORDER if t in tags][:2]
    return {
        "email_emoji": email_event_emoji(event),
        "email_dow": dow,
        "email_daynum": daynum,
        "email_clock": event_time_label(event.get("date_iso")),
        "email_badges": badges,
    }


# Town colours for the email's region headers and date chips: dark enough for
# white text (all at or above 4.5:1 on white), cycled in section order so the
# same town keeps the same colour from week to week.
# ROADMAP.md item 330: one class per surface colour the emails actually use.
# Feeds the dark-mode override include (_email_dark_mode.css.j2); a test
# checks every `wt-*` surface class in the built send file against its
# element's inline background-color, so the two can't drift apart again.
EMAIL_SURFACES: dict[str, str] = {
    "wt-bg": "#f3f2f2",  # single-town email page
    "wt-card": "#eae9e9",  # single-town email card
    "wt-card-sponsor": "#fff2ef",
    "wt-cta-bg": "#ec3013",
    "wt-page": "#f6f1ea",  # combined email page
    "wt-paper": "#fffefc",  # combined email cards (not pure white)
    "wt-season": "#fffaf2",
    "wt-pick": "#fff4d6",
    "wt-sky": "#eaf4ff",
    "wt-sponsor": "#fff2ef",
}
EMAIL_INKS: dict[str, str] = {"wt-ink": "#201e1d", "wt-muted": "#605d5d", "wt-accent": "#ae1800", "wt-brand": "#ae1800"}

EMAIL_TOWN_COLORS: tuple[tuple[str, str], ...] = (
    ("#0f766e", "#effaf8"),  # teal
    ("#6d28d9", "#f6f3fe"),  # violet
    ("#c2410c", "#fff6ef"),  # burnt orange
    ("#1d4ed8", "#f0f5ff"),  # blue
    ("#be185d", "#fdf2f7"),  # raspberry
)


def pick_email_top_picks(blocks: list[dict], limit: int = 3) -> list[dict]:
    """Up to `limit` "Don't miss" events for the top of the combined email,
    at most one per town: the most family-relevant attendable event in each
    town (paid promotions excluded, since they already lead their own town's
    list and must never be presented as an editorial pick), then the
    strongest of those across towns. Ties go to the earlier event. Needs at
    least two towns with something to pick, or the section is skipped."""
    candidates, spare = [], []
    for block in blocks:
        pool = [e for e in block.get("attendable_events") or [] if not e.get("sponsored_by") and is_pick_worthy(e)]
        if not pool:
            continue  # item 380: a town with nothing good contributes no pick
        ranked = sorted(pool, key=lambda e: (-family_relevance(e), e.get("date_iso") or "9999"))
        color = block.get("color", EMAIL_TOWN_COLORS[0][0])
        candidates.append(dict(ranked[0], pick_town=block["region_name"], pick_color=color))
        spare += [dict(e, pick_town=block["region_name"], pick_color=color) for e in ranked[1:]]
    if len(candidates) < 2:
        return []
    key = lambda e: (-family_relevance(e), e.get("date_iso") or "9999")  # noqa: E731
    candidates.sort(key=key)
    if len(candidates) < limit:  # the empty towns' slots go to the strongest events elsewhere
        spare.sort(key=key)
        candidates += spare[: limit - len(candidates)]
    return candidates[:limit]


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
            dict(
                e,
                email_when=when,
                email_where=email_event_where(e),
                email_blurb=email_blurb(e.get("detail"), e.get("title", "")),
                **email_visuals(e),
            )
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
    ("holidays/", (11, 1), (12, 23), "🎄 Tree lightings and holiday events in every town we cover →"),
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


def render_combined_email_digest(sections: list[dict], weekend_date_range: str, now: datetime, newsletter: dict | None = None, *, preview: bool = False, halloween: dict | None = None, holiday: dict | None = None, weather: list[dict] | None = None, halloween_extras: dict | None = None) -> str:
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
            "indoor_ideas": thin_week_ideas(s.get("evergreen", []), len(attendable_events)) if attendable_events else [],
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

    for i, block in enumerate(all_blocks):
        block["color"], block["tint"] = EMAIL_TOWN_COLORS[i % len(EMAIL_TOWN_COLORS)]
    collapse = len(empty_candidates) >= 2
    region_blocks = [b for b in all_blocks if not (collapse and b in empty_candidates)]
    top_picks = pick_email_top_picks(region_blocks)
    event_total = sum(len([e for e in s["weekend_events"] if e.get("attendable", True)]) for s in sections)
    town_total = sum(1 for s in sections if any(e.get("attendable", True) for e in s["weekend_events"]))
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
    edition = email_edition(now)
    edition_block = build_email_edition_block(edition, halloween, holiday, now, halloween_extras)
    weather_line = build_email_weather_line(weather)
    night_out = pick_night_out(region_blocks, top_picks)  # item 355: Don't miss, then Night out, then Rain plan, then Sign-ups
    days_off_line = build_days_off_email_line(sections, now)
    closures_line = build_closures_email_line(sections, now)
    rain_plan = pick_rain_plan(region_blocks, top_picks + ([night_out] if night_out else [])) if weather_line and weather_line["rain"] else []
    # ROADMAP.md item 327: up to four events whose registration opens this week.
    town_colors = {b["region_name"]: b["color"] for b in all_blocks}
    used_urls = {e.get("url") for e in [*top_picks, *([night_out] if night_out else []), *rain_plan] if e.get("url")}
    signups = [dict(e, color=town_colors.get(e["town"], EMAIL_TOWN_COLORS[0][0])) for e in pick_signups_across_towns(sections) if e.get("url") not in used_urls]
    return template.render(
        signups=signups,
        region_blocks=region_blocks,
        top_picks=top_picks,
        poll=poll_links(now.astimezone(LOCAL_TZ).date()),
        event_total=event_total,
        town_total=town_total,
        empty_regions_summary=empty_regions_summary,
        house_ad=house_ad,
        weekend_date_range=weekend_date_range,
        subject_line=build_combined_email_subject_line(sections, now, top_picks),
        preheader=build_combined_email_preheader(sections),
        newsletter=newsletter or {"configured": False},
        preview=preview,
        seasonal_link=None if edition_block else seasonal_email_link(now),
        edition=edition if edition_block else None,
        edition_block=edition_block,
        weather_line=weather_line["text"] if weather_line else None,
        days_off_line=days_off_line,
        closures_line=closures_line,
        night_out=night_out,
        election_line=election_day_line(now, email=True),
        rain_plan=rain_plan,
    )


# ROADMAP.md item 296: a "Days off school" box. The district's own wording is
# kept as the reason; nothing is inferred from a date alone.
DAY_OFF_TITLE = re.compile(
    r"no school|non-?attendance|institute|half[- ]day|early (?:release|dismissal)|conferences?|"
    r"holiday|winter break|spring break|thanksgiving break|school closed|schools closed|staff development",
    re.IGNORECASE,
)
DAYS_OFF_WINDOW = 45
DAYS_OFF_MAX_DAYS = 6


def short_district(source_name: str) -> str:
    """"Mount Prospect School District 57 — Calendar" -> "D57"; "Wheeling CCSD
    21 — Calendar" -> "CCSD 21"; anything else keeps its name before the dash."""
    name = source_name.split(" — ")[0].strip()
    m = re.search(r"\bCCSD\s*(\d+)", name)
    if m:
        return f"CCSD {m.group(1)}"
    m = re.search(r"\bDistrict\s*(\d+)|\bSD\s*(\d+)|\bD(\d+)\b", name)
    if m:
        return "D" + next(g for g in m.groups() if g)
    return name


# ROADMAP.md item 299: what suits a school-age child who is home. Toddler and
# baby programmes and adult programmes never qualify as a "what's on" pick.
_DAYS_OFF_TOO_YOUNG = re.compile(r"\b(baby|babies|toddlers?|tots?|lapsit|infants?|preschool|pre-k|storytime|story time)\b", re.IGNORECASE)
_DAYS_OFF_ADULT = re.compile(r"\b(aarp|driver safety|medicare|tax|taxes|seniors?|retirement|adults?)\b", re.IGNORECASE)


def _days_off_idea_rank(event: dict) -> tuple | None:
    """None when an event does not suit a school-age child; otherwise a sort
    key: elementary/teen first, then kid-friendly, then all-ages."""
    title = event.get("title") or ""
    tags = set(event.get("tags") or [])
    if "toddler" in tags or _DAYS_OFF_TOO_YOUNG.search(title) or _DAYS_OFF_ADULT.search(title) or family_relevance(event) < 0:
        return None
    tier = 0 if tags & {"elementary", "teen"} else 1 if "kid_friendly" in tags else 2
    return (tier, -family_relevance(event), event.get("date_iso") or "")


def _next_school_day(day: date) -> date:
    nxt = day + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


# ROADMAP.md item 259: a per-town winter-break page, live Nov 1 - Jan 4, listing
# feed events from Dec 21 to Jan 3 that look like camps or school-break programmes.
WINTER_BREAK_TITLE = re.compile(
    r"\b(camps?|winter break|no school|school'?s out|schools out|day off|break (?:camp|day|program))\b", re.IGNORECASE
)


def winter_break_season(now: datetime) -> bool:
    today = now.astimezone(LOCAL_TZ).date()
    return today.month in (11, 12) or (today.month == 1 and today.day <= 4)


def winter_break_window(now: datetime) -> tuple[date, date]:
    """Dec 21 through Jan 3 of the season now open (the year before in
    January), so the same dates are used from November through Jan 4."""
    today = now.astimezone(LOCAL_TZ).date()
    year = today.year if today.month >= 11 else today.year - 1
    return date(year, 12, 21), date(year + 1, 1, 3)


def select_winter_break_events(blocks: list[dict], now: datetime, limit: int = 40) -> list[dict]:
    start, end = winter_break_window(now)
    picked = []
    for block in blocks:
        for e in block.get("events", []):
            if not (e.get("title") and e.get("url") and e.get("date_iso")):
                continue
            try:
                day = datetime.fromisoformat(e["date_iso"]).date()
            except ValueError:
                continue
            if start <= day <= end and WINTER_BREAK_TITLE.search(e["title"]):
                picked.append(dict(e))
    picked.sort(key=lambda e: e["date_iso"])
    return picked[:limit]


def winter_break_catalogues(evergreen: list[dict]) -> list[dict]:
    """Evergreen entries a region already carries that mention camps (park
    district camp catalogues), shown even when no dated camp is in the feeds."""
    return [e for e in evergreen if re.search(r"\bcamps?\b", f"{e.get('title', '')} {e.get('detail', '')}", re.IGNORECASE)]


def build_days_off_sponsor(sponsors_cfg: dict, region_id: str, local_today: date, key: str = "days_off_sponsor") -> dict | None:
    """The paid slot under a region's "Days off school" box (ROADMAP.md item
    297): `days_off_sponsor:` in config/sponsors.yaml under the region, with
    `title`, `url`, an optional `detail`, and an optional `until` (the last day
    it runs; without one it never shows). Labelled as paid and rendered below
    the free listings, never in place of them."""
    entry = sponsors_cfg.get("regions", {}).get(region_id, {}).get(key)
    if not isinstance(entry, dict) or not str(entry.get("title") or "").strip() or not str(entry.get("url") or "").strip():
        return None
    until = _parse_promo_day(entry.get("until"))
    if until is None or until < local_today:
        return None
    return {"title": str(entry["title"]).strip(), "url": str(entry["url"]).strip(), "detail": str(entry.get("detail") or "").strip()}


ELECTION_DAY_URL = "https://www.cookcountyclerkil.gov/"


def election_day_line(now: datetime, *, email: bool = False) -> dict | None:
    """One neutral Election Day line (ROADMAP.md item 298): the date and a link
    to the Cook County Clerk's official site, nothing else - no candidates,
    measures or opinions. Pages show it on Nov 2-3; the email also carries it
    for the issue sent the week before (Oct 27 on). First Tuesday after the
    first Monday in November."""
    today = now.astimezone(LOCAL_TZ).date()
    nov1 = date(today.year, 11, 1)
    first_monday = nov1 + timedelta(days=(0 - nov1.weekday()) % 7)
    election = first_monday + timedelta(days=1)
    start = election - timedelta(days=(7 if email else 1))
    if not (start <= today <= election):
        return None
    return {"text": f"🗳️ Election Day is {election.strftime('%a %b')} {election.day}. Find your polling place and early voting", "url": ELECTION_DAY_URL}


def build_days_off(
    blocks: list[dict], local_today: date, window: int = DAYS_OFF_WINDOW, ideas_per_day: int = 3, official: list[dict] | None = None
) -> list[dict]:
    """School days off in the next `window` days from the region's "School ..."
    sections, with each district's own wording as the reason. Consecutive
    school days off for the same districts are one row (item 299), and each
    row gets up to `ideas_per_day` timed daytime (before 5 p.m.) events from
    the other sections across its dates that suit a school-age child, best
    first. [] when no district lists a day off."""
    end = local_today + timedelta(days=window)
    days: dict[date, list[dict]] = {}
    for block in blocks:
        if "school" not in (block.get("section") or "").lower():
            continue
        for e in block.get("events", []):
            if not (e.get("title") and e.get("date_iso") and DAY_OFF_TITLE.search(e["title"])):
                continue
            try:
                day = datetime.fromisoformat(e["date_iso"]).date()
            except ValueError:
                continue
            if not (local_today <= day <= end):
                continue
            reason = {"district": short_district(e.get("source") or ""), "reason": e["title"].strip()}
            if reason not in days.setdefault(day, []):
                days[day].append(reason)
    # ROADMAP.md item 300: a district's official board-approved calendar, entered
    # by hand in the region config where no live feed works. Merged with the
    # feed entries and de-duplicated by date and district.
    for entry in official or []:
        day = _parse_promo_day(entry.get("date"))
        if not (day and entry.get("district") and entry.get("reason") and local_today <= day <= end):
            continue
        reason = {"district": str(entry["district"]).strip(), "reason": str(entry["reason"]).strip()}
        existing = days.setdefault(day, [])
        if not any(r["district"] == reason["district"] for r in existing):
            existing.append(reason)
    rows: list[dict] = []
    for day in sorted(days):
        districts = {r["district"] for r in days[day]}
        last = rows[-1] if rows else None
        if last and last["_districts"] == districts and _next_school_day(last["end"]) == day:
            last["end"] = day
            last["reasons"] += [r for r in days[day] if r["reason"] not in {x["reason"] for x in last["reasons"] if x["district"] == r["district"]}]
        else:
            rows.append({"date": day, "end": day, "reasons": list(days[day]), "_districts": districts})
    rows = rows[:DAYS_OFF_MAX_DAYS]
    for row in rows:
        start, finish = row["date"], row["end"]
        row["label"] = start.strftime("%a %b ") + str(start.day)
        if finish != start:
            row["label"] += " – " + finish.strftime("%a %b ") + str(finish.day)
        row.pop("_districts")
        pool = []
        for block in blocks:
            if "school" in (block.get("section") or "").lower():
                continue
            for e in block.get("events", []):
                if not (e.get("title") and e.get("url") and e.get("date_iso")) or e.get("attendable") is False:
                    continue
                try:
                    begin = datetime.fromisoformat(e["date_iso"])
                except ValueError:
                    continue
                rank = _days_off_idea_rank(e)
                if rank and start <= begin.date() <= finish and (begin.hour, begin.minute) != (0, 0) and begin.hour < 17:
                    pool.append((rank, e))
        pool.sort(key=lambda p: p[0])
        multi = finish != start
        row["ideas"] = [
            {
                "title": e["title"],
                "url": e["url"],
                "clock": (datetime.fromisoformat(e["date_iso"]).strftime("%a ") if multi else "") + (event_time_label(e["date_iso"]) or ""),
            }
            for _rank, e in pool[:ideas_per_day]
        ]
    return rows


# ROADMAP.md item 307: around Thanksgiving, Christmas and New Year, one compact
# "Closed / changed this week" box built only from what the town's own feeds say.
CLOSURE_TITLE = re.compile(
    r"\b(closed|closes? early|early close|closing early|delayed?|delays?|no (?:refuse|trash|garbage|recycling|yard waste) (?:collection|pick-?up)|"
    r"holiday (?:hours|schedule)|reduced hours)\b",
    re.IGNORECASE,
)
CLOSURE_MAX_ITEMS = 4


def closure_window(day: date) -> tuple[date, date] | None:
    """The holiday window `day` is in, as (first, last): Thanksgiving week
    (Nov 23-29), Christmas (Dec 21-27) or New Year (Dec 28 - Jan 3)."""
    for (m1, d1), (m2, d2) in (((11, 23), (11, 29)), ((12, 21), (12, 27)), ((12, 28), (1, 3))):
        start_year = day.year if (day.month, day.day) >= (m1, d1) else day.year - 1
        start = date(start_year, m1, d1)
        end = date(start_year + (1 if m2 < m1 else 0), m2, d2)
        if start <= day <= end:
            return start, end
    return None


def build_closures(blocks: list[dict], local_today: date) -> list[dict]:
    """Items whose titles say closed, closes early, delayed or no collection,
    dated inside the holiday window we are in, from non-school feeds. Only what
    a source says - nothing is inferred from the holiday. [] outside a window or
    when no source posts one."""
    window = closure_window(local_today)
    if not window:
        return []
    start, end = window
    found, seen = [], set()
    for block in blocks:
        if "school" in (block.get("section") or "").lower():
            continue
        for e in block.get("events", []):
            if not (e.get("title") and e.get("url") and e.get("date_iso") and CLOSURE_TITLE.search(e["title"])):
                continue
            try:
                day = datetime.fromisoformat(e["date_iso"]).date()
            except ValueError:
                continue
            if not (max(start, local_today) <= day <= end) or (e["title"], day) in seen:
                continue
            seen.add((e["title"], day))
            found.append({"title": e["title"].strip(), "url": e["url"], "date": day, "label": day.strftime("%a %b ") + str(day.day)})
    found.sort(key=lambda c: c["date"])
    return found[:CLOSURE_MAX_ITEMS]


def build_closures_email_line(sections: list[dict], now: datetime) -> dict | None:
    """One email line when any town's feeds post a holiday closure this week."""
    parts, url = [], None
    for s in sections:
        for c in s.get("closures") or []:
            parts.append(f"{s['region_name']}: {c['title'][:60]}")
            url = url or s["region_url"] + "#closures"
    if not parts:
        return None
    return {"text": "🔒 " + " · ".join(parts[:3]), "url": url}


def build_days_off_email_line(sections: list[dict], now: datetime) -> dict | None:
    """One email line when any town has a day off in the next 7 days (item
    296): "📚 No school next week: D57 Wed Nov 11 · CCSD 15 Tue Nov 3"."""
    today = now.astimezone(LOCAL_TZ).date()
    parts, first_url = [], None
    for s in sections:
        for day in s.get("days_off") or []:
            if today <= day["date"] <= today + timedelta(days=7):
                for r in day["reasons"]:
                    part = f"{r['district']} {day['label']}"
                    if part not in parts:
                        parts.append(part)
                        first_url = first_url or s["region_url"] + "#days-off"
    if not parts:
        return None
    return {"text": "📚 No school next week: " + " · ".join(parts[:4]), "url": first_url}


THIN_WEEK_THRESHOLD = 4


def thin_week_ideas(evergreen: list[dict], attendable_count: int, limit: int = 3) -> list[dict]:
    """Up to `limit` evergreen indoor ideas for a thin week (ROADMAP.md item
    312): when a town has fewer than THIN_WEEK_THRESHOLD attendable weekend
    events. Kid-friendly and free ones first. Always labelled "Anytime this
    week" by the caller so they are never mistaken for dated events; none on
    a busy week."""
    if attendable_count >= THIN_WEEK_THRESHOLD:
        return []
    indoor = [e for e in evergreen if "indoor" in (e.get("tags") or []) and e.get("title") and e.get("url")]
    indoor.sort(key=lambda e: -sum(1 for t in ("kid_friendly", "free") if t in (e.get("tags") or [])))
    return indoor[:limit]


def pick_night_out(blocks: list[dict], exclude: list[dict] | None = None) -> dict | None:
    """One "Night out" line for the email's adult readers (ROADMAP.md item
    284): the earliest arts-and-culture event across the towns that starts at
    6 p.m. or later on a Friday or Saturday. Never a paid promotion, and None
    when nothing qualifies."""
    skip = {(e.get("title"), e.get("url")) for e in exclude or []}
    best = None
    for block in blocks:
        for e in block.get("attendable_events") or []:
            if e.get("sponsored_by") or "art_culture" not in (e.get("tags") or []) or not e.get("date_iso") or (e.get("title"), e.get("url")) in skip:
                continue
            try:
                start = datetime.fromisoformat(e["date_iso"])
            except ValueError:
                continue
            if start.hour < 18 or start.weekday() not in (4, 5):
                continue
            if best is None or (e["date_iso"], e["title"]) < (best[0].get("date_iso"), best[0]["title"]):
                best = (e, block, start)
    if not best:
        return None
    e, block, start = best
    venue = e.get("email_where") or e.get("venue")
    return {
        "title": e["title"],
        "url": e["url"],
        "venue": venue,
        "when": f"{start.strftime('%A')} {event_time_label(e['date_iso']) or ''}".strip(),
        "town": block["region_name"],
    }


def build_email_weather_line(weather: list[dict] | None) -> dict | None:
    """The email's one weather line (ROADMAP.md item 291) from a region's
    Friday-Sunday forecast: "☀️ Sat 58° · 🌧️ Sun 70% rain". Saturday and
    Sunday only, and `rain` is True when either has a 60% or greater chance
    of rain. None when there is no forecast, so a failed fetch shows nothing
    rather than a stale line."""
    days = [d for d in (weather or []) if d.get("day_name") in ("Saturday", "Sunday")]
    if not days:
        return None
    parts = []
    for d in days:
        part = f"{d.get('emoji', '')} {d['day_name'][:3]} {round(d['high_f'])}°".strip()
        if (d.get("precip_percent") or 0) >= 30:
            part += f" {round(d['precip_percent'])}% rain"
        parts.append(part)
    rain = any((d.get("precip_percent") or 0) >= 60 for d in days)
    return {"text": " · ".join(parts), "rain": rain}


def pick_rain_plan(blocks: list[dict], exclude: list[dict] | None = None, limit: int = 3) -> list[dict]:
    """Up to `limit` indoor events across the towns for a wet weekend (item
    291): family relevance first, then soonest. Paid promotions and anything
    already shown as a "Don't miss" pick are left out."""
    skip = {(e.get("title"), e.get("url")) for e in exclude or []}
    pool = []
    for block in blocks:
        for e in block.get("attendable_events") or []:
            if e.get("sponsored_by") or "indoor" not in (e.get("tags") or []) or (e.get("title"), e.get("url")) in skip:
                continue
            pool.append(dict(e, pick_town=block["region_name"], pick_color=block.get("color", EMAIL_TOWN_COLORS[0][0])))
    pool.sort(key=lambda e: (-family_relevance(e), e.get("date_iso") or "9999"))
    return pool[:limit]


def _thanksgiving(year: int) -> date:
    """The fourth Thursday of November."""
    first = date(year, 11, 1)
    return first + timedelta(days=(3 - first.weekday()) % 7 + 21)


def email_edition(now: datetime) -> str | None:
    """Which seasonal edition this week's issue is (ROADMAP.md item 289), by
    the Friday of the weekend it covers: "halloween" when that Friday is the
    last one on or before Oct 31 (so a Sunday or Monday Halloween still gets
    the weekend before it), "holiday" when it is the Friday after
    Thanksgiving (Small Business Saturday's weekend). Every other week is None."""
    friday = weekend_dates(now.astimezone(LOCAL_TZ).date())[0]
    if date(friday.year, 10, 25) <= friday <= date(friday.year, 10, 31):
        return "halloween"
    if friday == _thanksgiving(friday.year) + timedelta(days=1):
        return "holiday"
    return None


def build_halloween_issue_extras(entries: list[dict], now: datetime, night: dict | None) -> dict:
    """ROADMAP.md item 348: what the Halloween-weekend issue adds to its lead
    block - the Halloween-night forecast line (item 316) and the weekend's
    trunk-or-treats - from data the build already holds. Nothing guessed:
    the night line only when the forecast fetched, trunk-or-treats only from
    the towns' own Saturday and Sunday events."""
    local = now.astimezone(LOCAL_TZ)
    friday, saturday, sunday = weekend_dates(weekend_reference_date(local))
    night_line = (
        f"Halloween night, {night['weekday']} 3\u20138 PM: {night['temp']}\u00b0F, {night['rain']}% rain. "
        f"Sunset {night['sunset']}: bring a light."
        if night else None
    )
    trunks = []
    for e in entries:
        for ev in e.get("events") or []:
            day = _event_day(ev)
            if day in (saturday, sunday) and TRUNK_OR_TREAT.search(ev.get("title", "")) and ev.get("title"):
                trunks.append({"town": e["region_name"], "title": ev["title"], "url": ev.get("url"), "when": day.strftime("%a %b ") + str(day.day), "date_iso": ev.get("date_iso") or ""})
    trunks.sort(key=lambda t: (t["date_iso"], t["town"], t["title"]))
    return {"night_line": night_line, "trunks": trunks[:6]}


def build_email_edition_block(edition: str | None, halloween: dict | None, holiday: dict | None, now: datetime, halloween_extras: dict | None = None) -> dict | None:
    """The first block of a seasonal edition: Halloween's trick-or-treat hours
    or the holidays' tree-lighting dates plus Small Business Saturday. None
    when there is nothing true to show (no banner data)."""
    if edition == "halloween" and halloween:
        return {
            "title": "Trick-or-treat hours, all five towns",
            "pills": [f"{t['name']} {t['hours']}" + (f" ({t['qualifier']})" if t.get("qualifier") else "") for t in halloween["towns"]],
            "night_line": (halloween_extras or {}).get("night_line"),
            "trunks": (halloween_extras or {}).get("trunks") or [],
            "link": SITE_BASE_URL + "trick-or-treat/?utm_source=email&utm_campaign=edition",
            "link_label": "Hours, trunk-or-treats and Halloween events →",
        }
    if edition == "holiday" and holiday:
        sbs = _thanksgiving(now.year) + timedelta(days=2)
        pills = [f"{t['name']} {t['date']}" for t in holiday["towns"]]
        pills.append(f"Small Business Saturday {sbs.strftime('%b')} {sbs.day}")
        return {
            "title": "Tree lightings and Small Business Saturday",
            "pills": pills,
            "link": SITE_BASE_URL + "holidays/?utm_source=email&utm_campaign=edition",
            "link_label": "Tree lightings and holiday events →",
            "extra_link": SITE_BASE_URL + "santa/?utm_source=email&utm_campaign=edition",
            "extra_label": "Santa near you →",
        }
    return None


WEEKEND_ROLLOVER_HOUR = 15


def rolls_to_next_weekend(local_now: datetime) -> bool:
    """ROADMAP.md item 341: from Sunday 15:00 local the weekend is over for
    practical purposes, so pages look at the coming Friday-Sunday instead."""
    return local_now.weekday() == 6 and local_now.hour >= WEEKEND_ROLLOVER_HOUR


def weekend_reference_date(local_now: datetime) -> date:
    """The date whose Mon-Sun week supplies the weekend a page shows: today,
    except that from Sunday 15:00 it is tomorrow (Monday), i.e. next weekend."""
    return local_now.date() + timedelta(days=1) if rolls_to_next_weekend(local_now) else local_now.date()


def weekend_label(local_now: datetime) -> str:
    """"This weekend" Friday to Sunday 15:00; "Next weekend" from Sunday 15:00
    until the following Friday (item 341)."""
    return "Next weekend" if rolls_to_next_weekend(local_now) or local_now.weekday() < 4 else "This weekend"


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


INDEXNOW_KEY_STATE_PATH = ROOT / "data" / "indexnow_key.json"
INDEXNOW_PROBE_BACKOFF_DAYS = 7


def load_indexnow_key_state(path: Path | None = None) -> dict:
    try:
        data = json.loads((path or INDEXNOW_KEY_STATE_PATH).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def active_indexnow_key(state: dict) -> str:
    """ROADMAP.md item 337: the key submissions use. The newer key unless a
    probe found that a retired key is the one Bing accepts."""
    chosen = state.get("active")
    return chosen if chosen in (INDEXNOW_KEY, *RETIRED_INDEXNOW_KEYS) else INDEXNOW_KEY


def probe_retired_indexnow_keys(
    state: dict, now: datetime, submit=None, *, log_path: Path | None = None, state_path: Path | None = None,
) -> str | None:
    """ROADMAP.md item 337: after the current key was refused with a 403, send
    ONE request (the homepage) under each retired key whose file is still
    published. A 200 or 202 makes that key the active one (state saved, its
    file then published permanently); if every key is refused, nothing is
    retried for INDEXNOW_PROBE_BACKOFF_DAYS. Each result is logged with the
    last four characters of the key only. Returns the accepted key or None."""
    submit = submit or submit_indexnow
    last = state.get("probe_failed_at")
    if last:
        try:
            if now - datetime.fromisoformat(last) < timedelta(days=INDEXNOW_PROBE_BACKOFF_DAYS):
                return None
        except ValueError:
            pass
    for old_key in RETIRED_INDEXNOW_KEYS:
        outcome: dict = {}
        ok = submit(host=CUSTOM_DOMAIN, key=old_key, key_location=f"{SITE_BASE_URL}{old_key}.txt", urls=[SITE_BASE_URL], outcome=outcome)
        accepted = ok and (outcome.get("status") in (200, 202))
        record_indexnow_outcome(log_path or INDEXNOW_LOG_PATH, now, 1, bool(accepted), dict(outcome, key_suffix=old_key[-4:], skipped=None))
        if accepted:
            state.update({"active": old_key, "switched_at": now.isoformat(timespec="seconds")})
            state.pop("probe_failed_at", None)
            (state_path or INDEXNOW_KEY_STATE_PATH).write_text(json.dumps(state, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            return old_key
    state["probe_failed_at"] = now.isoformat(timespec="seconds")
    (state_path or INDEXNOW_KEY_STATE_PATH).write_text(json.dumps(state, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return None


BING_HASHES_PATH = ROOT / "data" / "bing_hashes.json"


def order_bing_urls(urls: list[str], now: datetime, region_ids: list[str]) -> list[str]:
    """ROADMAP.md item 347: which changed URLs Bing's daily quota is spent on
    first - /trick-or-treat/ (until Nov 1), /this-weekend/, the region pages,
    then everything else - stable within each group."""
    local = now.astimezone(LOCAL_TZ).date()
    tiers = []
    if local <= date(local.year, 11, 1):
        tiers.append({SITE_BASE_URL + "trick-or-treat/"})
    tiers.append({SITE_BASE_URL + "this-weekend/"})
    tiers.append({SITE_BASE_URL + rid + "/" for rid in region_ids})

    def rank(url: str) -> int:
        if url.startswith(SITE_BASE_URL + "e/"):
            return -1  # item 369: new event pages are the newest original pages the site makes
        for i, tier in enumerate(tiers):
            if url in tier:
                return i
        return len(tiers)

    return sorted(urls, key=rank)


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
        # The same submission sent straight to Bing when the shared endpoint
        # refused it, and who ended up accepting it.
        "bing_status": outcome.get("bing_status"),
        "bing_body": outcome.get("bing_body"),
        "accepted_by": outcome.get("accepted_by"),
        "key_suffix": outcome.get("key_suffix"),
        **{k: outcome[k] for k in ("channel", "quota", "sent") if k in outcome},
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
    prime_event_page_paths(now)
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
    night_forecast = None
    link_health = load_link_health()
    link_candidates: list[dict] = []
    holidays_entries = []
    santa_entries: list[dict] = []
    leaf_entries: list[dict] = []
    warm_found: list[dict] = []  # item 387
    email_weather_by_region: dict[str, list[dict]] = {}
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

        tree_lighting = prepare_tree_lighting(region_cfg, now.year)
        if tree_lighting:
            holidays_entries.append(
                {
                    "region_id": region_id,
                    "region_name": region["name"],
                    "region_url": SITE_BASE_URL + region_id + "/",
                    "holiday_url": SITE_BASE_URL + region_id + "/holiday/",
                    "tree": tree_lighting,
                    "events": [],
                }
            )
        trick_or_treat = prepare_trick_or_treat(region_cfg, now.year)
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
        apply_link_health(blocks, link_health)
        link_candidates.extend(collect_link_candidates(blocks, local_today, region_id))
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
        blocks, _partisan_excluded = filter_partisan_events(blocks)
        blocks = filter_past_events(blocks, local_today)
        annotate_registration(blocks, local_today)
        # ROADMAP.md item 173: same single-insertion-point reasoning as
        # item 171's filter above - collapsing duplicates here, before
        # anything downstream reads blocks, means the main region page,
        # the RSS feed, calendar.ics, and every date-scoped view all see
        # the same deduped list instead of needing their own pass.
        blocks = dedupe_events(blocks)
        annotate_celebrations(blocks, local_today)
        # ROADMAP.md item 245: a paid Event Promo goes in after the filters
        # above, so it can never be deduped away or dropped, and goes first.
        blocks = apply_promotion(blocks, build_promotion_event(sponsors_cfg, region_cfg, local_today))
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
        region_days_off = build_days_off(blocks, local_today, official=region_cfg.get("days_off"))
        region_closures = build_closures(blocks, local_today)

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
            search_meta=build_search_meta(
                region["name"], region["state"],
                filter_events_by_dates(blocks, {local_today + timedelta(days=i) for i in range(7)}),
                when="Events This Week",
            ),
            days_off=region_days_off,
            days_off_sponsor=build_days_off_sponsor(sponsors_cfg, region_id, local_today),
            closures=region_closures,
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
        if trick_or_treat and region_id == "mount-prospect-60056" and region.get("lat") is not None:
            _halloween = date(local_today.year, 10, 31)
            if _halloween - timedelta(days=7) <= local_today <= _halloween:
                night_forecast = fetch_night_forecast(region["lat"], region["lon"], _halloween.isoformat(), region.get("timezone", "America/Chicago"))
        if trick_or_treat:
            trick_or_treat_entries[-1]["village_post"] = find_village_post(blocks, now.year)
            trick_or_treat_entries[-1]["events"] = [
                dict(e, town=e.get("town") or region["name"], state=e.get("state") or region.get("state"))
                for e in select_halloween_events(blocks, local_today)
            ]
        # ROADMAP.md item 269: feed items point at this site's own cards (the
        # anchors just assigned), copied now like `upcoming` above. The
        # site-wide feed and this town's own feed share them.
        region_feed_items = [
            {**e, "region_name": region["name"], "site_url": f"{region_page_url}#{e['anchor_id']}"}
            for b in blocks
            for e in b["events"]
            if e.get("title") and e.get("url") and e.get("date_iso")
        ]
        feed_items += region_feed_items
        (region_dir / "feed.xml").write_text(
            build_feed_xml(
                region_feed_items, now, source_completeness,
                title=f"{SITE_NAME} — Upcoming events in {region['name']}", scope=region["name"],
            ),
            encoding="utf-8",
        )
        events_json_groups.append((region["name"], region_page_url, upcoming))
        (region_dir / "events.json").write_text(
            build_events_json([(region["name"], region_page_url, upcoming)], f"Upcoming events in {region['name']} — {SITE_NAME}", now),
            encoding="utf-8",
        )
        logger.info("Wrote %s (%d events)", region_dir / "events.json", len(upcoming))

        local_now = now.astimezone(ZoneInfo(region.get("timezone") or "America/Chicago"))
        friday, saturday, sunday = weekend_dates(weekend_reference_date(local_now))
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
        email_weather_by_region[region_id] = weekend_weather
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
                "region_lat": region.get("lat"),
                "region_lon": region.get("lon"),
                "weekend_events": weekend_events,
                "evergreen": evergreen,
                "sponsor": sponsor,
                "days_off": region_days_off,
                "closures": region_closures,
                "signups": [dict(e, town=region["name"]) for e in build_signups_opening(blocks, local_today)],
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
            view_meta = (
                build_search_meta(region["name"], region["state"], items, when="This Weekend", date_range=weekend_date_range)
                if slug == "this-weekend"
                else None
            )
            view_blocks = [{"section": heading, "events": items}]
            if slug == "this-weekend":
                ideas = thin_week_ideas(evergreen, sum(1 for e in items if e.get("attendable", True)))
                if ideas:
                    view_blocks.append({"section": "Indoor ideas — anytime this week", "events": ideas})
            view_html = render_region_page(
                region_cfg,
                view_blocks,
                sponsor,
                [],
                now,
                heading=view_meta["h1"] if view_meta else heading,
                subheading=subheading,
                search_meta=view_meta,
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

        if tree_lighting:
            holidays_entries[-1]["events"] = [
                dict(e, town=e.get("town") or region["name"], state=e.get("state") or region.get("state"))
                for e in select_holiday_events(blocks, local_today)
            ]
        leaf = prepare_leaf_pickup(region_cfg)
        if leaf:
            leaf_entries.append({"name": region["name"], **leaf})
        warm_found += warm_prospects.collect_hosts([e for b in blocks for e in b.get("events", [])], region["name"])
        santa_entries.append({"region_name": region["name"], "region_url": SITE_BASE_URL + region_id + "/", "tree": tree_lighting, "links": santa_look_links(region_cfg), "events": [dict(e, town=e.get("town") or region["name"], state=e.get("state") or region.get("state")) for e in select_santa_events(blocks, local_today)]})
        # ROADMAP.md item 258: the town's holiday page - free events from its
        # own feeds plus any paid, labelled listings.
        holiday_listings = build_holiday_listings(sponsors_cfg, region_id, local_today)
        holiday_live = is_holiday_season(now) or bool(holiday_listings)
        if holiday_live:
            holiday_sections = []
            holiday_events = select_holiday_events(blocks, local_today)
            if holiday_events:
                holiday_sections.append({"section": "Holiday events", "events": holiday_events})
            if holiday_listings:
                holiday_sections.append({"section": "Local business listings", "events": holiday_listings})
            holiday_html = render_region_page(
                region_cfg,
                holiday_sections,
                sponsor,
                [],
                now,
                heading=f"Holiday Events and Shopping — {region['name']}",
                subheading=f"Tree lightings, holiday markets and local shops in {region['name']}, November and December.",
                empty_message="No holiday events posted yet. We list them here as the town's calendars publish them.",
                nav_current="holiday",
                canonical_suffix="holiday/",
                guides_url=guides_url,
                directory_url=directory_url,
                things_to_do_url=things_to_do_url,
                newsletter=newsletter,
                analytics=analytics,
            )
            holiday_dir = region_dir / "holiday"
            holiday_dir.mkdir(parents=True, exist_ok=True)
            (holiday_dir / "index.html").write_text(holiday_html, encoding="utf-8")
            logger.info("Wrote %s (%d event%s, %d listing%s)", holiday_dir / "index.html", len(holiday_events), "" if len(holiday_events) == 1 else "s", len(holiday_listings), "" if len(holiday_listings) == 1 else "s")

        # ROADMAP.md item 259: the winter-break camps page, Nov 1 - Jan 4.
        winter_live = winter_break_season(now)
        if winter_live:
            winter_events = select_winter_break_events(blocks, now)
            winter_sections = []
            if winter_events:
                winter_sections.append({"section": "Camps and school-break programmes", "events": winter_events})
            catalogues = winter_break_catalogues(evergreen)
            winter_html = render_region_page(
                region_cfg,
                winter_sections,
                sponsor,
                catalogues,
                now,
                heading=f"Winter Break Camps and Activities — {region['name']}",
                subheading=f"Camps and things to do while school is out, December 21 – January 3 in {region['name']}.",
                empty_message="No winter-break camps are listed in the town's calendars yet. We add them here as they are published; the park district's camp catalogue is linked below when it has one.",
                nav_current="winter-break",
                canonical_suffix="winter-break/",
                guides_url=guides_url,
                directory_url=directory_url,
                things_to_do_url=things_to_do_url,
                newsletter=newsletter,
                analytics=analytics,
                days_off_sponsor=build_days_off_sponsor(sponsors_cfg, region_id, local_today, key="winter_break_sponsor"),
            )
            winter_dir = region_dir / "winter-break"
            winter_dir.mkdir(parents=True, exist_ok=True)
            (winter_dir / "index.html").write_text(winter_html, encoding="utf-8")
            logger.info("Wrote %s (%d event%s)", winter_dir / "index.html", len(winter_events), "" if len(winter_events) == 1 else "s")

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
                "weekend_picks": hub_town_picks(weekend_events),
                "next_up": [] if weekend_events else hub_next_up(blocks, local_today),
                "weekend_count": sum(1 for e in weekend_events if e.get("attendable", True)),
                "path": f"{region_id}/",
                "guide_slugs": [g["slug"] for g in guides],
                "holiday": holiday_live,
                "winter_break": winter_live,
                "guides": [{"slug": g["slug"], "title": g["title"]} for g in guides],
            }
        )

    # ROADMAP.md item 369: single-event pages for the week's few events that matter.
    active_event_pages = write_event_pages(combined_email_sections, trick_or_treat_entries, now, newsletter, analytics, santa_entries)

    hub_stats = {
        "region_count": len(region_summaries),
        "event_count": total_events,
        "weekend_count": sum(len(s["events"]) for s in hub_weekend_sections),
        "weekend_date_range": hub_weekend_date_range or "",
        "weekend_label": weekend_label(now.astimezone(LOCAL_TZ)),
        "free_count": sum(len(s["events"]) for s in hub_free_sections),
        "today_count": sum(len(s["events"]) for s in hub_today_sections),
    }
    hub_html = render_hub_page(
        regions, region_summaries, now, newsletter, analytics, stats=hub_stats, contact_email=contact_email,
        halloween=build_halloween_banner(trick_or_treat_entries, now),
        holiday=build_holiday_banner(holidays_entries, now),
        winter=build_winter_banner(region_summaries, now),
    )
    (OUTPUT_DIR / "index.html").write_text(hub_html, encoding="utf-8")
    logger.info("Wrote %s", OUTPUT_DIR / "index.html")

    weekend_hub_html = render_merged_hub_page(
        hub_weekend_sections,
        now,
        analytics,
        newsletter=newsletter,
        signup_headline="Get this list every Thursday.",
        event_pages=[{"url": SITE_BASE_URL + e["path"], "title": display_title(e["title"]), "town": e.get("town"), "when": e["date_iso"][:10]} for e in active_event_pages],
        picks=build_join_picks(combined_email_sections, limit=6),  # item 360
        season_banner=weekend_season_banner(build_halloween_banner(trick_or_treat_entries, now)),
        slug="this-weekend",
        heading="Things to Do This Weekend in the Northwest Suburbs",
        subheading=f"{hub_weekend_date_range or ''} — everything with a known date, across every region.",
        meta_description=build_hub_weekend_description([s["region_name"] for s in hub_weekend_sections], hub_weekend_sections, hub_weekend_date_range or ""),
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
    combined_email_extra = {
        "halloween": build_halloween_banner(trick_or_treat_entries, now),
        "holiday": build_holiday_banner(holidays_entries, now),
        "halloween_extras": build_halloween_issue_extras(trick_or_treat_entries, now, build_halloween_night(night_forecast, now)),
        # One region's forecast stands for the five neighbouring towns; Mount
        # Prospect is central, else the first town that has one.
        "weather": email_weather_by_region.get("mount-prospect-60056")
        or next((w for w in email_weather_by_region.values() if w), None),
    }
    (OUTPUT_DIR / "combined-email-send.html").write_text(
        render_combined_email_digest(*combined_email_args, **combined_email_extra), encoding="utf-8"
    )
    logger.info("Wrote %s", OUTPUT_DIR / "combined-email-send.html")
    (OUTPUT_DIR / "combined-email-preview.html").write_text(
        render_combined_email_digest(*combined_email_args, preview=True, **combined_email_extra), encoding="utf-8"
    )
    logger.info("Wrote %s", OUTPUT_DIR / "combined-email-preview.html")

    sponsor_availability = build_sponsor_availability(sponsors_cfg, region_summaries)
    sponsor_stats = {
        "region_count": len(region_summaries),
        "next_week_count": count_next_seven_days(events_json_groups, now.astimezone(LOCAL_TZ).date()),
        "since": LAUNCH_DATE.strftime("%b %-d, %Y"),
        **sponsor_issue_stats(now),
    }
    sponsor_html = render_sponsor_page(
        sponsor_availability,
        now,
        analytics,
        contact_email=contact_email,
        stats=sponsor_stats,
        payment_links=sponsors_cfg.get("payment_links"),
        founding_promos_used=sponsors_cfg.get("founding_promos_used") or 0,
        audience=load_audience_line(),
    )
    sponsor_dir = OUTPUT_DIR / "sponsor"
    sponsor_dir.mkdir(parents=True, exist_ok=True)
    (sponsor_dir / "index.html").write_text(sponsor_html, encoding="utf-8")
    preview_dir = sponsor_dir / "preview"  # item 313: noindex, out of the sitemap, linked from nowhere
    preview_dir.mkdir(parents=True, exist_ok=True)
    (preview_dir / "index.html").write_text(render_sponsor_preview(combined_email_sections, sponsors_cfg.get("payment_links"), contact_email), encoding="utf-8")
    logger.info("Wrote %s", sponsor_dir / "index.html")

    about_html = render_about_page(now, analytics, contact_email=contact_email, source_completeness=source_completeness)
    about_dir = OUTPUT_DIR / "about"
    about_dir.mkdir(parents=True, exist_ok=True)
    (about_dir / "index.html").write_text(about_html, encoding="utf-8")
    logger.info("Wrote %s", about_dir / "index.html")

    trick_or_treat_html = render_trick_or_treat_page(trick_or_treat_entries, now, analytics, newsletter, load_tot_checked(now), night_forecast)
    trick_or_treat_dir = OUTPUT_DIR / "trick-or-treat"
    trick_or_treat_dir.mkdir(parents=True, exist_ok=True)
    (trick_or_treat_dir / "index.html").write_text(trick_or_treat_html, encoding="utf-8")
    logger.info("Wrote %s", trick_or_treat_dir / "index.html")
    issues = load_issues()
    for i, issue in enumerate(issues):
        issue_dir = OUTPUT_DIR / "issues" / issue["date"]
        issue_dir.mkdir(parents=True, exist_ok=True)
        (issue_dir / "index.html").write_text(
            render_issue_page(
                issue, newer=issues[i - 1] if i > 0 else None, older=issues[i + 1] if i + 1 < len(issues) else None,
                newsletter=newsletter, analytics=analytics, town_names=[r["name"] for r in region_summaries],
            ),
            encoding="utf-8",
        )
    if issues:
        (OUTPUT_DIR / "issues" / "index.html").write_text(render_issues_index(issues, now, analytics), encoding="utf-8")
        logger.info("Wrote %d archived issue(s) and the issues index", len(issues))
    join_dir = OUTPUT_DIR / "join"
    join_dir.mkdir(parents=True, exist_ok=True)
    recent_issue_url = f"{SITE_BASE_URL}issues/{issues[0]['date']}/" if issues else None
    (join_dir / "index.html").write_text(render_join_page(combined_email_sections, now, analytics, newsletter, hub_weekend_date_range or "", recent_issue_url), encoding="utf-8")
    logger.info("Wrote %s", join_dir / "index.html")
    holidays_dir = OUTPUT_DIR / "holidays"
    holidays_dir.mkdir(parents=True, exist_ok=True)
    (holidays_dir / "index.html").write_text(render_holidays_page(holidays_entries, now, analytics, newsletter, contact_email), encoding="utf-8")
    logger.info("Wrote %s", holidays_dir / "index.html")
    for tot in trick_or_treat_entries:  # item 398: "Also at" dealers are hosts of the same event
        warm_found += warm_prospects.collect_hosts([e for e in tot.get("events") or [] if e.get("also_at")], tot["region_name"])
    warm_registry = warm_prospects.update_registry(warm_prospects.load_registry(), warm_found + warm_prospects.issue_hosts(town_of=lambda t: next((r['region']['name'] for r in regions if r['region']['name'].lower() in t.lower()), '')), now.astimezone(LOCAL_TZ).date())
    warm_prospects.save_registry(warm_registry)
    try:  # item 391: the Warm section is refreshed at every build, in place
        prospects_path = ROOT / "OUTREACH_PROSPECTS.md"
        prospects_text = prospects_path.read_text(encoding="utf-8") if prospects_path.exists() else ""
        if prospects_text:
            prospects_path.write_text(warm_prospects.splice_section(prospects_text, warm_prospects.render_section(warm_registry, warm_prospects.venue_source_keys())), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not refresh OUTREACH_PROSPECTS.md: %s", exc)
    leaf_dir = OUTPUT_DIR / "leaf-pickup"
    leaf_dir.mkdir(parents=True, exist_ok=True)
    (leaf_dir / "index.html").write_text(render_leaf_pickup_page(leaf_entries, now, analytics, newsletter), encoding="utf-8")
    santa_dir = OUTPUT_DIR / "santa"
    santa_dir.mkdir(parents=True, exist_ok=True)
    (santa_dir / "index.html").write_text(render_santa_page(santa_entries, now, analytics, newsletter, {e["path"] for e in active_event_pages}), encoding="utf-8")
    logger.info("Wrote %s", santa_dir / "index.html")

    for kind in THANKS_PAGES:
        thanks_dir = OUTPUT_DIR / "thanks" / kind
        thanks_dir.mkdir(parents=True, exist_ok=True)
        (thanks_dir / "index.html").write_text(
            render_thanks_page(kind, [{"id": r["id"], "name": r["name"]} for r in region_summaries], analytics), encoding="utf-8"
        )
    known_regions = {r.get("id") for r in region_summaries}
    for rid, short in SHORT_PATHS.items():
        if rid in known_regions:
            (OUTPUT_DIR / short).mkdir(parents=True, exist_ok=True)
            (OUTPUT_DIR / short / "index.html").write_text(render_short_redirect(rid), encoding="utf-8")

    for flyer_index, cfg_path in enumerate(sorted((CONFIG_DIR / "regions").glob("*.yaml"))):
        region_cfg = load_yaml(cfg_path)
        rid, town = region_cfg["region"]["id"], region_cfg["region"]["name"]
        examples = [e["title"] for e in region_cfg.get("evergreen", []) if e.get("title")][:3]
        for variant in flyer_variants(sponsors_cfg.get("print_placements")):
            base = OUTPUT_DIR / "print" / rid / variant["id"]
            for copies, sub in ((1, ""), (2, "half")):
                out = base / sub
                out.mkdir(parents=True, exist_ok=True)
                (out / "index.html").write_text(render_flyer(rid, town, examples, variant["campaign"], copies, EMAIL_TOWN_COLORS[flyer_index % len(EMAIL_TOWN_COLORS)][0]), encoding="utf-8")

    sitemap_urls = collect_sitemap_urls(region_summaries, issues, active_event_pages, is_leaf_pickup_season(now))
    (OUTPUT_DIR / "sitemap.xml").write_text(build_sitemap_xml(region_summaries, now, issues, active_event_pages), encoding="utf-8")
    (OUTPUT_DIR / "robots.txt").write_text(build_robots_txt(), encoding="utf-8")
    (OUTPUT_DIR / "llms.txt").write_text(build_llms_txt(region_summaries, source_completeness, issues), encoding="utf-8")
    (OUTPUT_DIR / "events.json").write_text(
        build_events_json(events_json_groups, f"Upcoming events across every region — {SITE_NAME}", now), encoding="utf-8"
    )
    (OUTPUT_DIR / "llms-full.txt").write_text(build_llms_full_txt(llms_full_groups, weekend_date_range), encoding="utf-8")
    (OUTPUT_DIR / "CNAME").write_text(CUSTOM_DOMAIN + "\n", encoding="utf-8")
    indexnow_state = load_indexnow_key_state()
    indexnow_key = active_indexnow_key(indexnow_state)
    (OUTPUT_DIR / f"{INDEXNOW_KEY}.txt").write_text(INDEXNOW_KEY, encoding="utf-8")
    # Retired key files stay published until the cut-off date, and permanently
    # once a probe finds one of them is the key Bing accepts (item 337).
    if now.astimezone(LOCAL_TZ).date() <= RETIRED_INDEXNOW_KEYS_UNTIL or indexnow_key != INDEXNOW_KEY:
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
    # ROADMAP.md items 278 and 216: the weekly ad and social images.
    for name, image in build_weekly_cards(combined_email_sections, hub_weekend_date_range or "").items():
        image.save(og_dir / f"{name}.png", "PNG")
        logger.info("Wrote weekly card %s (%dx%d)", name, *image.size)
    # ROADMAP.md item 344: the Halloween ad creatives, regenerated each build from the page's own data.
    ads = build_tot_ads(trick_or_treat_entries, now)
    if ads:
        ads_dir = OUTPUT_DIR / "ads"
        ads_dir.mkdir(parents=True, exist_ok=True)
        for name, image in ads.items():
            image.save(ads_dir / f"{name}.png", "PNG")
            logger.info("Wrote Halloween ad %s (%dx%d)", name, *image.size)
    pins_today = region_local_date(regions[0]["region"], now)
    pins_friday, _pins_sat, pins_sunday = weekend_dates(weekend_reference_date(now.astimezone(ZoneInfo(regions[0]["region"].get("timezone") or "America/Chicago"))))
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
    # ROADMAP.md item 304: one weekly, Nextdoor-ready feed per town.
    weekly_history = load_weekly_feed_history()
    weekly_range = format_date_range(max(pins_friday, pins_today), pins_sunday)
    weekly_image_path = og_dir / "weekly-square.png"
    for section in combined_email_sections:
        region_id = section["region_url"].rstrip("/").rsplit("/", 1)[-1]
        image_name = "weekly-square" if weekly_image_path.exists() else region_id
        image_file = og_dir / f"{image_name}.png"
        image = {"url": f"{SITE_BASE_URL}og/{image_name}.png", "length": image_file.stat().st_size} if image_file.exists() else None
        item = build_weekly_item(region_id, section["region_name"], section["weekend_events"], pins_friday, weekly_range, now, image)
        if item:
            record_weekly_feed_item(weekly_history, region_id, item)
        items = weekly_history.get(region_id, [])
        if items:
            (OUTPUT_DIR / region_id).mkdir(parents=True, exist_ok=True)
            (OUTPUT_DIR / region_id / "weekly.xml").write_text(
                build_weekly_feed_xml(section["region_name"], region_id, items, now), encoding="utf-8"
            )
    WEEKLY_FEED_HISTORY_PATH.write_text(json.dumps(weekly_history, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    unique_links = sorted({(c["region"], c["url"]) for c in link_candidates})
    LINK_CANDIDATES_PATH.write_text(
        json.dumps({"links": [{"region": r, "url": u} for r, u in unique_links]}, indent=1) + "\n", encoding="utf-8"
    )
    logger.info("Wrote weekly.xml feeds for %d town(s)", sum(1 for v in weekly_history.values() if v))
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
            key=indexnow_key,
            key_location=f"{SITE_BASE_URL}{indexnow_key}.txt",
            urls=indexnow_urls,
            outcome=indexnow_outcome,
        )
        indexnow_outcome["key_suffix"] = indexnow_key[-4:]
        if not indexnow_ok and indexnow_outcome.get("status") == 403 and indexnow_key == INDEXNOW_KEY:
            # Item 337: one extra request under each retired key, then back off a week.
            probe_retired_indexnow_keys(indexnow_state, now)
        if indexnow_ok:
            INDEXNOW_HASHES_PATH.write_text(json.dumps(indexnow_current, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    else:
        indexnow_ok = True
        indexnow_outcome = {"status": None, "error": None, "skipped": "no page changed since the last accepted submission"}
        logger.info("IndexNow: no page changed since the last accepted submission; nothing sent.")
    record_indexnow_outcome(INDEXNOW_LOG_PATH, now, len(indexnow_urls), indexnow_ok, indexnow_outcome)
    # Items 340 and 347: Bing's own URL Submission API, only when the owner has set the secret.
    bing_key = os.environ.get("BING_WEBMASTER_API_KEY", "").strip()
    if not BING_HASHES_PATH.exists():  # build-digest.yml `git add`s this path, so it must always exist
        BING_HASHES_PATH.write_text("{}\n", encoding="utf-8")
    if bing_key:
        bing_changed, bing_current = changed_indexnow_urls(sitemap_urls, load_indexnow_hashes(BING_HASHES_PATH), OUTPUT_DIR)
        bing_outcome: dict = {}
        if bing_changed:
            sent = submit_bing_urls(
                SITE_BASE_URL.rstrip("/"), bing_key, order_bing_urls(bing_changed, now, [r["id"] for r in region_summaries]), outcome=bing_outcome,
            )
            bing_hashes = load_indexnow_hashes(BING_HASHES_PATH)
            bing_hashes.update({u: bing_current[u] for u in sent if u in bing_current})
            BING_HASHES_PATH.write_text(json.dumps(bing_hashes, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            record_indexnow_outcome(INDEXNOW_LOG_PATH, now, len(bing_changed), bool(sent), bing_outcome)
        else:
            logger.info("Bing URL submission: no page changed since the last accepted submission.")
    else:
        logger.info("Bing URL submission skipped: BING_WEBMASTER_API_KEY is not set.")
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
