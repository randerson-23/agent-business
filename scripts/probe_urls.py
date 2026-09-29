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


def probe(entry: dict, session=requests, now: datetime | None = None) -> dict:
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
    if "html" in content_type.lower() or body.lstrip()[:15].lower().startswith((b"<!doctype html", b"<html")):
        # requests assumes ISO-8859-1 for text/* without a charset, which
        # garbles UTF-8 pages (an em dash became "â€”" in a real run).
        encoding = resp.encoding if "charset=" in content_type.lower() and resp.encoding else "utf-8"
        result.update(extract_page_signals(body.decode(encoding, errors="replace"), resp.url))
    elif body.lstrip().startswith(b"BEGIN:VCALENDAR"):
        result["ics_event_count"] = body.count(b"BEGIN:VEVENT")
    return result


def load_probes(path: Path = PROBES_PATH) -> list[dict]:
    data = yaml.safe_load(path.read_text()) or {}
    return [p for p in data.get("probes", []) if p.get("url")]


def main() -> int:
    probes = load_probes()
    results = [probe(p) for p in probes]
    RESULTS_PATH.write_text(json.dumps({"results": results}, indent=2, ensure_ascii=False) + "\n")
    for r in results:
        outcome = r.get("error") or r.get("status")
        print(f"{outcome}\t{r['url']}\t{len(r.get('feed_links', []))} feed / {len(r.get('calendar_links', []))} calendar links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
