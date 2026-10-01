"""Answer "what does this page actually serve?" from a network-capable runner.

ROADMAP.md item 212. Both autonomous loops run in sandboxes that block
general web egress, so every question of that shape used to stall at
"needs a real page fetch". GitHub Actions can reach these hosts, so
.github/workflows/probe-urls.yml runs this script there and commits
data/url_probes.json, which both loops can then read from origin/main.

One request per URL, same identifying headers as the real build, no
retries (item 195), and no config changes: a probe only records what it
saw. Acting on an answer is a normal reviewed PR.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetchers import REQUEST_HEADERS, REQUEST_TIMEOUT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROBES_PATH = ROOT / "config" / "url_probes.yaml"
RESULTS_PATH = ROOT / "data" / "url_probes.json"

CALENDAR_HREF_MARKERS = (".ics", "ical", "webcal:", "rss", "feed", "icalfeed")
MAX_LINKS = 40
MAX_READ_BYTES = 2_000_000
MAX_MATCHES_PER_PATTERN = 20
CONTEXT_CHARS = 60


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self.alternates: list[dict] = []
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "link" and "alternate" in a.get("rel", "").lower().split() and a.get("href"):
            self.alternates.append({"href": a["href"], "type": a.get("type", ""), "title": a.get("title", "")})
        elif tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def normalize_url(url: str) -> str:
    """webcal:// is https:// with a calendar-app hint; requests can't fetch it."""
    return "https://" + url[len("webcal://"):] if url.startswith("webcal://") else url


def extract_page_signals(html: str, base_url: str) -> dict:
    parser = _LinkCollector()
    try:
        parser.feed(html)
    except Exception:  # malformed markup still yields whatever was parsed so far
        pass

    feed_links = []
    for alt in parser.alternates:
        entry = dict(alt, href=urljoin(base_url, alt["href"]))
        if entry not in feed_links:
            feed_links.append(entry)

    calendar_links = []
    for href in parser.hrefs:
        if any(m in href.lower() for m in CALENDAR_HREF_MARKERS):
            absolute = href if href.startswith("webcal:") else urljoin(base_url, href)
            if absolute not in calendar_links:
                calendar_links.append(absolute)

    return {
        "title": " ".join(parser.title.split())[:200],
        "feed_links": feed_links[:MAX_LINKS],
        "calendar_links": calendar_links[:MAX_LINKS],
    }


def find_pattern_matches(text: str, patterns: list[str]) -> dict:
    """Each regex's distinct matches in the raw body, with a little context.

    Item 215: LibCal and LibraryCalendar build their subscribe links in
    JavaScript, so the IDs a feed URL needs sit in scripts and data
    attributes, not in any <a href>. Matching the raw text finds them.
    """
    found = {}
    for pattern in patterns:
        hits, seen = [], set()
        for m in re.finditer(pattern, text):
            if m.group(0) in seen:
                continue
            seen.add(m.group(0))
            context = text[max(0, m.start() - CONTEXT_CHARS): m.end() + CONTEXT_CHARS]
            hits.append({"match": m.group(0), "context": " ".join(context.split())})
            if len(hits) >= MAX_MATCHES_PER_PATTERN:
                break
        found[pattern] = hits
    return found


def find_follow_url(html: str, base_url: str, pattern: str) -> str | None:
    """First link whose href matches `pattern`, other than the page itself."""
    parser = _LinkCollector()
    try:
        parser.feed(html)
    except Exception:
        pass
    here = base_url.split("#")[0].rstrip("/")
    for href in parser.hrefs:
        if href.startswith(("#", "mailto:", "tel:", "javascript:")) or not re.search(pattern, href):
            continue
        absolute = urljoin(base_url, href).split("#")[0]
        if absolute.rstrip("/") != here:
            return absolute
    return None


def _decode(resp, body: bytes, content_type: str) -> str:
    # requests assumes ISO-8859-1 for text/* without a charset, which
    # garbles UTF-8 pages (an em dash became "â€”" in a real run).
    encoding = resp.encoding if "charset=" in content_type.lower() and resp.encoding else "utf-8"
    return body.decode(encoding, errors="replace")


def probe(entry: dict, session=requests, now: datetime | None = None, allow_follow: bool = True) -> dict:
    url = entry["url"]
    result = {
        "url": url,
        "purpose": entry.get("purpose", ""),
        "item": entry.get("item"),
        "probed_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
    }
    try:
        resp = session.get(normalize_url(url), headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    except requests.RequestException as exc:
        result["error"] = type(exc).__name__
        return result

    body = resp.content[:MAX_READ_BYTES]
    content_type = resp.headers.get("Content-Type", "")
    result.update({
        "status": resp.status_code,
        "final_url": resp.url,
        "content_type": content_type,
        "bytes": len(resp.content),
    })
    text = _decode(resp, body, content_type)
    is_html = "html" in content_type.lower() or body.lstrip()[:15].lower().startswith((b"<!doctype html", b"<html"))
    if is_html:
        result.update(extract_page_signals(text, resp.url))
    elif body.lstrip().startswith(b"BEGIN:VCALENDAR"):
        result["ics_event_count"] = body.count(b"BEGIN:VEVENT")

    if entry.get("patterns"):
        result["pattern_matches"] = find_pattern_matches(text, entry["patterns"])

    if allow_follow and is_html and entry.get("follow"):
        target = find_follow_url(text, resp.url, entry["follow"])
        if target is None:
            result["followed"] = None
        else:
            # One level only: the followed page gets the same patterns but
            # never follows further, so a probe stays at most two requests.
            sub = {"url": target, "patterns": entry.get("patterns", [])}
            result["followed"] = probe(sub, session=session, now=now, allow_follow=False)
    return result


def load_probes(path: Path = PROBES_PATH) -> list[dict]:
    data = yaml.safe_load(path.read_text()) or {}
    probes = [p for p in data.get("probes", []) if p.get("url")]
    for p in probes:
        for pattern in p.get("patterns", []) + ([p["follow"]] if p.get("follow") else []):
            re.compile(pattern)  # fail the run loudly on a typo, before any request
    return probes


def main() -> int:
    probes = load_probes()
    results = [probe(p) for p in probes]
    RESULTS_PATH.write_text(json.dumps({"results": results}, indent=2, ensure_ascii=False) + "\n")
    for r in results:
        outcome = r.get("error") or r.get("status")
        matches = sum(len(v) for v in (r.get("pattern_matches") or {}).values())
        followed = (r.get("followed") or {}).get("url", "-")
        print(f"{outcome}\t{r['url']}\t{len(r.get('feed_links', []))} feed / {len(r.get('calendar_links', []))} calendar links / {matches} pattern hits / followed {followed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
