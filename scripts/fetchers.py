"""Fail-soft fetchers for the 60056 Weekly digest.

Each fetch_* function returns a list of dicts with keys:
    title, detail, url, date (optional, ISO string or None)

Any network/parsing error is caught and logged; callers get an empty list
back instead of a crash, so one broken source never breaks the digest build.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser

import requests

logger = logging.getLogger("fetchers")

REQUEST_TIMEOUT = 15
USER_AGENT = "60056Weekly/1.0 (+https://github.com/randerson-23/agent-business)"
MAX_ITEMS_PER_SOURCE = 6


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


def fetch_rss(url: str, limit: int = MAX_ITEMS_PER_SOURCE, **_ignored) -> list[dict]:
    """Parse a standard RSS 2.0 feed using only the stdlib XML parser."""
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
                    "url": link,
                    "date": pub_date,
                }
            )
        return items
    except Exception as exc:  # noqa: BLE001 - fail soft by design
        logger.warning("RSS fetch failed for %s: %s", url, exc)
        return []


def fetch_ics(url: str, limit: int = MAX_ITEMS_PER_SOURCE, **_ignored) -> list[dict]:
    """Minimal ICS (iCalendar) VEVENT parser, upcoming events only.

    Deliberately dependency-free: handles the common single-line
    SUMMARY/DTSTART/URL fields that most municipal calendar exports use.
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
        for e in upcoming:
            e.pop("_sort_key", None)
            e.setdefault("detail", "")
            e.setdefault("url", "")
        return upcoming[:limit]
    except Exception as exc:  # noqa: BLE001 - fail soft by design
        logger.warning("ICS fetch failed for %s: %s", url, exc)
        return []


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


def fetch_html_events(
    url: str,
    limit: int = MAX_ITEMS_PER_SOURCE,
    keywords: tuple[str, ...] | list[str] | None = None,
    detail_link_pattern: str | None = None,
    **_ignored,
) -> list[dict]:
    """Best-effort scrape of a listing page for relevant link text.

    Despite the name (kept for backward-compat config), this works for any
    "list of links to detail pages" page, not just events - e.g. a village
    news listing. Pass `keywords` to tune relevance per-source instead of
    hardcoding one keyword set for every kind of listing page, and pass
    `detail_link_pattern` (a regex string matched against each link's href)
    once you know the site's real per-item URL structure.

    Intentionally conservative: if the page needs JavaScript to render its
    content (common for calendar widgets), this returns [] and the digest
    falls back to evergreen content for that section instead of guessing.
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
            return deduped[:limit]

        # Fallback: crude keyword relevance filter, minus known nav labels.
        active_keywords = tuple(keywords) if keywords else DEFAULT_KEYWORDS
        candidates = [
            r
            for r in parser.results
            if r["title"].lower() not in _NAV_LINK_DENYLIST
            and any(k in r["title"].lower() for k in active_keywords)
        ]
        return candidates[:limit]
    except Exception as exc:  # noqa: BLE001 - fail soft by design
        logger.warning("HTML events fetch failed for %s: %s", url, exc)
        return []


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


FETCHERS = {
    "rss": fetch_rss,
    "ics": fetch_ics,
    "html_events": fetch_html_events,
}
