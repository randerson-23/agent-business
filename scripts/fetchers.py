"""Fail-soft fetchers for Within Ten.

Each fetch_* function returns a list of dicts with keys:
    title, detail, url, date (optional, ISO string or None)

Any network/parsing error is caught and logged; callers never see a crash,
so one broken source never breaks the digest build. The event/news fetchers
(fetch_rss, fetch_ics, fetch_html_events) return `None` on that caught
failure rather than `[]`, distinct from a real `[]` (the fetch succeeded
and genuinely found nothing) - ROADMAP.md Phase 11 #55: a 403 or a timeout
is a different, softer signal than "worked, found zero," and build_digest.py's
source-health tracking (item 51) needs that distinction to avoid flagging a
transient block as a dead scraper. Every caller still treats `None` the
same as `[]` for rendering purposes - only the health tracker cares.
fetch_weather is unaffected (still `[]` on failure); it isn't part of
source-health tracking.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

logger = logging.getLogger("fetchers")

# ROADMAP.md item 161: was "60056Weekly/1.0", pointing at the GitHub repo -
# a stale name from before the "Within Ten" pivot, and the wrong link to
# hand a civic source asking who's hitting their site: a repo tells a
# reader nothing about what's requesting their calendar, where the live
# site does.
REQUEST_TIMEOUT = 15
USER_AGENT = "WithinTen/1.0 (+https://withintenmiles.com/)"
# ROADMAP.md item 178 (forty-second research pass): was 6, and every
# live source in data/source_health.json's real trailing history
# returned exactly 6 on every recorded build - not a coincidence about
# twenty different civic calendars, but this constant truncating each
# feed to its first six entries before build_digest.py's own date-window
# filtering (weekend_dates/filter_events_by_dates, filter_past_events)
# ever runs. A library publishing forty programmes a month contributed
# six of them; the weekend window was starved by truncation, not by
# quiet towns or broken sources.
#
# The fix this item asked for: gather across a date horizon and let the
# window select, rather than truncating by count first. fetch_ics
# already filters to upcoming-only (date >= today) before this limit
# ever applies, so raising it there directly implements "the window
# selects." fetch_rss and fetch_html_events have no per-item date
# ordering to exploit the same way, so this cap is their only real
# bound - raised here to the "a few hundred" runaway-guard size item
# 178 asked for (matching the existing FEED_MAX_ITEMS = 50 precedent
# for this file's own RSS *output*, sized up since 50 was tuned for a
# site-wide feed, not one civic source) rather than removed outright,
# so one pathological feed still can't dominate a region page or blow
# up build time.
MAX_ITEMS_PER_SOURCE = 200


def _unescape_ics_text(value: str) -> str:
    """Unescape RFC 5545 TEXT values (SUMMARY/DESCRIPTION).

    ICS exports escape commas, semicolons, backslashes, and encode
    newlines as the two literal characters `\\n` - left as-is, these show
    up verbatim as "\\n" in rendered cards instead of a line break/space.
    """
    unescaped = (
        value.replace("\\n", " ")
        .replace("\\N", " ")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )
    return " ".join(unescaped.split())


def _get(url: str) -> requests.Response:
    resp = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    return resp


def fetch_rss(url: str, limit: int = MAX_ITEMS_PER_SOURCE, **_ignored) -> list[dict] | None:
    """Parse a standard RSS 2.0 feed using only the stdlib XML parser.

    Returns `None` on a transport/parse failure (network error, bad XML) -
    distinct from a real `[]`, which means the fetch succeeded and simply
    found nothing (ROADMAP.md Phase 11 #55). A 403, a timeout, and a
    silently-broken feed all used to collapse into the same empty list,
    which is exactly right for the digest build (never crash, never show
    a wrong page) and exactly wrong for source-health tracking (a
    transient block looks identical to a source that's actually died).
    Callers that just want events still treat `None` as `[]`; only the
    health tracker in build_digest.py cares about the distinction.
    """
    try:
        resp = _get(url)
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall("./channel/item")[:limit]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            description = (item.findtext("description") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip() or None
            if not title:
                continue
            items.append(
                {
                    "title": title,
                    "detail": description,
                    # RSS's own spec says <link> should already be
                    # absolute, but this is a no-op on one that already
                    # is - cheap insurance against the same relative-href
                    # bug fetch_html_events had (a page-relative link
                    # meant for that site's own domain, not this one's).
                    "url": _resolve_url(resp.url, link),
                    "date": pub_date,
                }
            )
        return items
    except Exception as exc:  # noqa: BLE001 - fail soft by design
        logger.warning("RSS fetch failed for %s: %s", url, exc)
        return None


def fetch_ics(url: str, limit: int = MAX_ITEMS_PER_SOURCE, **_ignored) -> list[dict] | None:
    """Minimal ICS (iCalendar) VEVENT parser, upcoming events only.

    Deliberately dependency-free: handles the common single-line
    SUMMARY/DTSTART/URL fields that most municipal calendar exports use.

    Returns `None` on a transport/parse failure, distinct from a real
    `[]` (fetched fine, nothing upcoming) - see fetch_rss's docstring for
    why (ROADMAP.md Phase 11 #55).
    """
    try:
        # `webcal://` is a hint for calendar apps to subscribe, not a real
        # transport - every ICS export that publishes it also serves the
        # same file over https. requests has no adapter for webcal://, so
        # translate it or every fetch here silently no-ops.
        if url.startswith("webcal://"):
            url = "https://" + url[len("webcal://"):]
        resp = _get(url)
        text = resp.text
        events = []
        current: dict = {}
        now = datetime.now(timezone.utc)
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line == "BEGIN:VEVENT":
                current = {}
            elif line == "END:VEVENT":
                if current.get("title"):
                    events.append(current)
                current = {}
            elif line.startswith("SUMMARY:"):
                current["title"] = _unescape_ics_text(line[len("SUMMARY:"):].strip())
            elif line.startswith("DESCRIPTION:"):
                current["detail"] = _unescape_ics_text(line[len("DESCRIPTION:"):].strip())
            elif line.startswith("URL:"):
                current["url"] = line[len("URL:"):].strip()
            elif line.startswith("DTSTART"):
                value = line.split(":", 1)[-1].strip()
                current["date"] = value
                current["_sort_key"] = value

        def is_upcoming(ev: dict) -> bool:
            raw = ev.get("_sort_key")
            if not raw:
                return True
            try:
                date_part = raw[:8]
                parsed = datetime.strptime(date_part, "%Y%m%d").replace(
                    tzinfo=timezone.utc
                )
                return parsed >= now.replace(hour=0, minute=0, second=0, microsecond=0)
            except ValueError:
                return True

        upcoming = [e for e in events if is_upcoming(e)]
        upcoming.sort(key=lambda e: e.get("_sort_key") or "")
        limited = upcoming[:limit]
        for e in limited:
            e.pop("_sort_key", None)
            e.setdefault("detail", "")
            e.setdefault("url", "")
            # Same defensive resolution as fetch_rss/fetch_html_events - a
            # no-op if the ICS export's URL field is already absolute.
            # Resolved only after slicing to limit, and against resp.url
            # (the URL actually served, after redirects) rather than the
            # pre-fetch url, which would resolve against the wrong host
            # if this source ever moves behind a redirect.
            e["url"] = _resolve_url(resp.url, e["url"])
        return limited
    except Exception as exc:  # noqa: BLE001 - fail soft by design
        logger.warning("ICS fetch failed for %s: %s", url, exc)
        return None


class _EventLinkExtractor(HTMLParser):
    """Very small best-effort scraper: pulls <a> text/href pairs that look
    like event links. Sites that need real JS rendering won't work here —
    that's fine, this source degrades to the evergreen fallback.
    """

    def __init__(self):
        super().__init__()
        self._in_link = False
        self._href = ""
        self._text_parts: list[str] = []
        self.results: list[dict] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            if href:
                self._in_link = True
                self._href = href
                self._text_parts = []

    def handle_data(self, data):
        if self._in_link:
            self._text_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._in_link:
            text = " ".join("".join(self._text_parts).split())
            if text and len(text) > 8:
                self.results.append({"title": text, "url": self._href, "detail": "", "date": None})
            self._in_link = False


# Static nav/menu labels that keep showing up as false positives on library
# and park district listing pages - these are section links, not events.
#
# ROADMAP.md item 175 (the forty-first research pass): confirmed against
# the real committed docs/ output for Des Plaines, Palatine, and Wheeling,
# not guessed - three regions' Library/Park District/Village sources, none
# with a confirmed detail_link_pattern, were all falling into the crude
# keyword-fallback branch below and picking up generic nav/account/legal
# chrome purely because it happens to contain a keyword substring ("my
# EVENTS", "PROGRAM guide", "news & EVENTS"). Every entry here was seen
# verbatim in that real build, each linking to a standing nav/account/
# legal page, never a specific dated listing: "my events" is a LibCal
# personal-account page (calendar.dppl.org/myevents - the exact false
# positive item 9 first found on a different LibCal URL, recurring here
# because the denylist approach only ever covers strings actually seen,
# not the platform pattern); "copyright notices"/"public notices" are
# civicplus-template legal-footer links (confirmed on two unrelated
# domains, palatine.il.us and wheelingil.gov); "calendar of events" and
# "news & events" are self-referential links back to the listing page
# itself, not to any one event on it. Deliberately does NOT include
# titles seen in the same build that plausibly describe a real (if
# undated) standing program - "book groups", "summer camps", "museum
# pass programs" and the like read as legitimate content a family might
# click through to, the same category evergreen entries already cover
# elsewhere, and removing them would be guessing they're chrome rather
# than confirming it.
_NAV_LINK_DENYLIST = {
    "all events",
    "special events",
    "reading and activity programs",
    "presenters/program proposal",
    "youth events",
    "adult events",
    "teen events",
    "virtual events",
    "south branch",
    "my events",
    "subscribe to e-news",
    "city council",
    "copyright notices",
    "public notices",
    "program guide",
    "programs / event tickets",
    "search programs",
    "calendar of events",
    "news & events",
    "book discussion request form",
}

# Communico (the platform behind mppl.libnet.info and many other library
# sites) links each real event to /event/<numeric id>. This is the default
# "detail link" signal - preferred over keyword guessing whenever present.
# A source can override it via `detail_link_pattern` in config once its
# real link structure is known (e.g. vah.com's `news_detail_T\d+_R\d+\.php`),
# instead of relying on the keyword fallback until someone notices it's
# picking up nav links.
_EVENT_DETAIL_PATH = re.compile(r"/event/\d+")

DEFAULT_KEYWORDS = ("event", "story", "class", "program", "camp", "concert", "market", "festival")

# Calendar-grid widgets (e.g. AHML's Drupal calendar - confirmed 2026-08-28
# from real page source) commonly stamp each day's <td> with a
# `data-date="YYYY-MM-DD"` attribute. _EventLinkExtractor below is a flat
# HTMLParser with no DOM/ancestor context, so it can't see "which day cell
# is this link inside" - this regex-over-raw-text approach finds the
# nearest such attribute preceding a given link's href instead. Purely
# additive: sources without this attribute just get date=None, same as
# before this existed.
_DATA_DATE_ATTR = re.compile(r'data-date="(\d{4}-\d{2}-\d{2})"')

# Vision Internet-style calendar widgets (e.g. mountprospect.org's Calendar
# module - confirmed 2026-08-28 from real page source) have no data-date
# attribute; the only date signal is an accessible aria-label on the day
# cell like 'Scheduled events, Saturday, September 12, 2026'. Based on a
# single confirmed sample - if a differently-phrased real one turns up
# later, loosen this rather than guess now. Same fail-soft default as
# everything else: a phrasing that doesn't match this pattern just
# doesn't produce a date, it never mis-parses one.
_ARIA_LABEL_DATE = re.compile(r'aria-label="Scheduled events, [A-Za-z]+, ([A-Za-z]+ \d{1,2}, \d{4})"')


def _nearby_date_hint(html: str, href: str, window: int = 800) -> str | None:
    """Best-effort: find a date signal shortly before a link's href in the
    raw HTML, trying known calendar-grid patterns in order of confidence.
    """
    idx = html.find(href)
    if idx == -1:
        # _EventLinkExtractor (an HTMLParser) decodes entities in attribute
        # values (e.g. &amp; -> &, common in query strings like MP's
        # calendar links), but the raw source below still has them
        # escaped - retry with the escaped form before giving up.
        idx = html.find(href.replace("&", "&amp;"))
    if idx == -1:
        return None
    preceding = html[max(0, idx - window) : idx]
    data_date_matches = _DATA_DATE_ATTR.findall(preceding)
    if data_date_matches:
        return data_date_matches[-1]
    aria_matches = _ARIA_LABEL_DATE.findall(preceding)
    return aria_matches[-1] if aria_matches else None


def _resolve_url(base_url: str, href: str) -> str:
    """A site's own HTML/RSS/ICS often links with a page-relative href
    (e.g. AHML's Drupal calendar: `href="/scheduling/reservation/218675"`)
    rather than a full URL - fine for a browser rendering that page, but
    wrong once it's copied verbatim into this site's own pages/feed,
    where the reader's browser resolves it against *this* site's domain
    instead. `base_url` should be `resp.url` (the URL actually served,
    after redirects), not the pre-fetch URL passed in by config - a
    source that 301s to a new host/path would otherwise resolve every
    relative href against the wrong one even though the fetch succeeded.
    A no-op when `href` is already absolute or empty.
    """
    return urljoin(base_url, href) if href else href


def _resolve_urls(items: list[dict], base_url: str) -> list[dict]:
    """List version of `_resolve_url`, applied as the very last step
    after dedup/pattern-matching/_nearby_date_hint all run against the
    original raw href, which is what they need to match substrings in
    the source page's actual HTML.
    """
    for item in items:
        item["url"] = _resolve_url(base_url, item["url"])
    return items


def fetch_html_events(
    url: str,
    limit: int = MAX_ITEMS_PER_SOURCE,
    keywords: tuple[str, ...] | list[str] | None = None,
    detail_link_pattern: str | None = None,
    **_ignored,
) -> list[dict] | None:
    """Best-effort scrape of a listing page for relevant link text.

    Despite the name (kept for backward-compat config), this works for any
    "list of links to detail pages" page, not just events - e.g. a village
    news listing. Pass `keywords` to tune relevance per-source instead of
    hardcoding one keyword set for every kind of listing page, and pass
    `detail_link_pattern` (a regex string matched against each link's href)
    once you know the site's real per-item URL structure.

    Intentionally conservative: if the page needs JavaScript to render its
    content (common for calendar widgets), this returns a real `[]` (page
    reached, nothing matched) and the digest falls back to evergreen
    content for that section instead of guessing. A transport/parse
    failure (network error, non-2xx status, timeout) returns `None`
    instead - distinct from that real `[]` (ROADMAP.md Phase 11 #55): a
    403 or a timeout means the scraper never got a chance to work, which
    is a different, softer signal than "worked, found nothing."
    """
    try:
        resp = _get(url)
        parser = _EventLinkExtractor()
        parser.feed(resp.text)

        # Strongest signal first: individual detail-page links.
        pattern = re.compile(detail_link_pattern) if detail_link_pattern else _EVENT_DETAIL_PATH
        detail_links = [r for r in parser.results if pattern.search(r["url"])]
        if detail_links:
            # de-dupe by url, preserve order
            seen = set()
            deduped = []
            for r in detail_links:
                if r["url"] not in seen:
                    seen.add(r["url"])
                    if not r.get("date"):
                        r["date"] = _nearby_date_hint(resp.text, r["url"])
                    deduped.append(r)
            return _resolve_urls(deduped[:limit], resp.url)

        # Fallback: crude keyword relevance filter, minus known nav labels.
        active_keywords = tuple(keywords) if keywords else DEFAULT_KEYWORDS
        candidates = [
            r
            for r in parser.results
            if r["title"].lower() not in _NAV_LINK_DENYLIST
            and any(k in r["title"].lower() for k in active_keywords)
        ]
        # De-dupe by (title, url), not url alone - a real gap this branch
        # never had, found in a real production build (ROADMAP.md item
        # 140): Des Plaines' D62 calendar page (item 138) links the same
        # closure notice more than once (an "ICS:"/"All Schools:"-
        # prefixed add-to-calendar variant alongside the plain listing),
        # and every source in this fallback branch - unlike the
        # detail_links branch above, which exists precisely because it
        # has real per-event detail URLs - shares one generic listing-
        # page url across every item, since that's exactly why it fell
        # into this branch rather than the one above. Deduping by url
        # alone here would silently collapse two genuinely different
        # closures (Labor Day, Parent-Teacher Conferences) that happen to
        # share that one page url into a single card - title is part of
        # the identity a real duplicate has to match too. Preserves
        # order, same idiom as above.
        seen = set()
        deduped = []
        for r in candidates:
            key = (r["title"], r["url"])
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return _resolve_urls(deduped[:limit], resp.url)
    except Exception as exc:  # noqa: BLE001 - fail soft by design
        logger.warning("HTML events fetch failed for %s: %s", url, exc)
        return None


# WMO weather interpretation codes (the scheme Open-Meteo's `daily.weathercode`
# uses) mapped to a short label/emoji/is_precip flag. Codes not in this table
# (shouldn't happen per Open-Meteo's docs, but fail soft either way) render
# with an empty label rather than crashing the build.
WEATHER_CODES: dict[int, tuple[str, str, bool]] = {
    0: ("Clear sky", "☀️", False),
    1: ("Mostly clear", "\U0001f324️", False),
    2: ("Partly cloudy", "⛅", False),
    3: ("Overcast", "☁️", False),
    45: ("Fog", "\U0001f32b️", False),
    48: ("Fog", "\U0001f32b️", False),
    51: ("Light drizzle", "\U0001f326️", True),
    53: ("Drizzle", "\U0001f326️", True),
    55: ("Heavy drizzle", "\U0001f327️", True),
    56: ("Freezing drizzle", "\U0001f327️", True),
    57: ("Freezing drizzle", "\U0001f327️", True),
    61: ("Light rain", "\U0001f326️", True),
    63: ("Rain", "\U0001f327️", True),
    65: ("Heavy rain", "\U0001f327️", True),
    66: ("Freezing rain", "\U0001f328️", True),
    67: ("Freezing rain", "\U0001f328️", True),
    71: ("Light snow", "\U0001f328️", True),
    73: ("Snow", "\U0001f328️", True),
    75: ("Heavy snow", "❄️", True),
    77: ("Snow grains", "❄️", True),
    80: ("Rain showers", "\U0001f326️", True),
    81: ("Rain showers", "\U0001f327️", True),
    82: ("Violent rain showers", "\U0001f327️", True),
    85: ("Snow showers", "\U0001f328️", True),
    86: ("Snow showers", "❄️", True),
    95: ("Thunderstorm", "⛈️", True),
    96: ("Thunderstorm w/ hail", "⛈️", True),
    99: ("Thunderstorm w/ hail", "⛈️", True),
}


def fetch_weather(lat: float, lon: float, timezone_name: str = "America/Chicago") -> list[dict]:
    """Best-effort daily forecast from Open-Meteo (free, no API key, no
    account setup) - same fail-soft philosophy as every other fetcher here:
    a weather outage never blocks the digest build, the weekend view just
    omits the forecast block.

    Returns a list of dicts (one per forecast day, ~10 days ahead):
        {date, high_f, low_f, precip_percent, label, emoji, is_precip}
    Callers match by `date` (an ISO date string) rather than by list
    position, so a response with days in an unexpected order/count never
    mismatches a day's actual date.
    """
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
                "temperature_unit": "fahrenheit",
                "timezone": timezone_name,
                "forecast_days": 10,
            },
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        daily = resp.json().get("daily", {})
        dates = daily.get("time", [])
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])
        precip = daily.get("precipitation_probability_max", [])
        codes = daily.get("weathercode", [])

        def _round_or_none(values, i):
            value = values[i] if i < len(values) else None
            return round(value) if value is not None else None

        days = []
        for i, date_str in enumerate(dates):
            code = codes[i] if i < len(codes) else None
            label, emoji, is_precip = WEATHER_CODES.get(code, ("", "", False))
            days.append(
                {
                    "date": date_str,
                    "high_f": _round_or_none(highs, i),
                    "low_f": _round_or_none(lows, i),
                    "precip_percent": _round_or_none(precip, i),
                    "label": label,
                    "emoji": emoji,
                    "is_precip": is_precip,
                }
            )
        return days
    except Exception as exc:  # noqa: BLE001 - fail soft by design
        logger.warning("Weather fetch failed for (%s, %s): %s", lat, lon, exc)
        return []


def submit_indexnow(host: str, key: str, key_location: str, urls: list[str]) -> bool:
    """Tell IndexNow's single shared endpoint (ROADMAP.md Phase 11 #72) that
    these URLs changed, so Bing, Yandex and Seznam can recrawl promptly
    instead of waiting on their own schedule - Bing's index in turn feeds
    DuckDuckGo, Yahoo and ChatGPT's search. No account or API key
    negotiation: any string 8-128 chars of [A-Za-z0-9-] works as the key,
    as long as it's also published as a plain-text file at `key_location`
    (this repo's build already writes that file next to the sitemap).

    Same fail-soft philosophy as every other network call here: a failed
    ping is logged and swallowed, never allowed to break the build. Returns
    True/False only for the caller's own log line, not for any control
    flow - IndexNow is a courtesy notification, not something the build
    depends on succeeding.
    """
    try:
        resp = requests.post(
            "https://api.indexnow.org/indexnow",
            json={"host": host, "key": key, "keyLocation": key_location, "urlList": urls},
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json; charset=utf-8"},
        )
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 - fail soft by design
        logger.warning("IndexNow submission failed for %d URL(s): %s", len(urls), exc)
        return False


FETCHERS = {
    "rss": fetch_rss,
    "ics": fetch_ics,
    "html_events": fetch_html_events,
}
