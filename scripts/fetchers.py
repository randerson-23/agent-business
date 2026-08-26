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
                current["title"] = line[len("SUMMARY:"):].strip()
            elif line.startswith("DESCRIPTION:"):
                current["detail"] = line[len("DESCRIPTION:"):].strip()
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
# sites) links each real event to /event/<numeric id>. Prefer that signal
# over keyword guessing whenever it's present.
_EVENT_DETAIL_PATH = re.compile(r"/event/\d+")

DEFAULT_KEYWORDS = ("event", "story", "class", "program", "camp", "concert", "market", "festival")


def fetch_html_events(
    url: str,
    limit: int = MAX_ITEMS_PER_SOURCE,
    keywords: tuple[str, ...] | list[str] | None = None,
    **_ignored,
) -> list[dict]:
    """Best-effort scrape of a listing page for relevant link text.

    Despite the name (kept for backward-compat config), this works for any
    "list of links to detail pages" page, not just events - e.g. a village
    news listing. Pass `keywords` to tune relevance per-source instead of
    hardcoding one keyword set for every kind of listing page.

    Intentionally conservative: if the page needs JavaScript to render its
    content (common for calendar widgets), this returns [] and the digest
    falls back to evergreen content for that section instead of guessing.
    """
    try:
        resp = _get(url)
        parser = _EventLinkExtractor()
        parser.feed(resp.text)

        # Strongest signal first: individual event detail-page links.
        detail_links = [r for r in parser.results if _EVENT_DETAIL_PATH.search(r["url"])]
        if detail_links:
            # de-dupe by url, preserve order
            seen = set()
            deduped = []
            for r in detail_links:
                if r["url"] not in seen:
                    seen.add(r["url"])
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


FETCHERS = {
    "rss": fetch_rss,
    "ics": fetch_ics,
    "html_events": fetch_html_events,
}
