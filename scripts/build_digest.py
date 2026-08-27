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

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlencode

import yaml
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).parent))
from fetchers import FETCHERS  # noqa: E402
from tagging import infer_tags, tag_display  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("build_digest")

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
REGIONS_DIR = CONFIG_DIR / "regions"
TEMPLATES_DIR = ROOT / "templates"
OUTPUT_DIR = ROOT / "docs"

DETAIL_MAX_LEN = 160

# Update this once a real domain is registered (see ROADMAP.md Phase 9) -
# used for canonical links and the sitemap. One line to change; nothing
# else in the pipeline depends on the domain.
SITE_BASE_URL = "https://randerson-23.github.io/agent-business/"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_regions() -> list[dict]:
    regions = []
    for path in sorted(REGIONS_DIR.glob("*.yaml")):
        cfg = load_yaml(path)
        if "region" not in cfg:
            logger.warning("Skipping %s: missing top-level `region` key", path)
            continue
        regions.append(cfg)
    return regions


def format_event_date(raw: str | None) -> str | None:
    """Best-effort: turn an RSS pubDate or ICS DTSTART into "Aug 28" style
    display text. Falls back to the raw string (or None) if it can't be
    parsed - a card with an odd raw date string is still useful; one that
    silently drops the date isn't.
    """
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).strftime("%b %-d")
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%b %-d")
        except ValueError:
            continue
    return raw


def parse_event_date_iso(raw: str | None) -> str | None:
    """Best-effort: turn an RSS pubDate or ICS DTSTART into an ISO 8601
    string for schema.org/Event structured data (which wants a real
    machine-readable date, unlike the "Aug 28" display text above).
    Returns None rather than a guess when the raw value can't be parsed -
    omitting startDate from structured data is valid; a wrong one isn't.
    """
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).isoformat()
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(raw, fmt).isoformat()
        except ValueError:
            continue
    return None


def truncate(text: str, max_len: int = DETAIL_MAX_LEN) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rsplit(" ", 1)[0] + "…"


def _ics_escape(text: str) -> str:
    """Inverse of fetchers._unescape_ics_text - escape TEXT values per
    RFC 5545 before writing them into an .ics file we generate."""
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )


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
        "PRODID:-//Weekend Trip Planner//EN",
        "BEGIN:VEVENT",
        f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{_ics_escape(event.get('title', ''))}",
    ]
    if event.get("detail"):
        lines.append(f"DESCRIPTION:{_ics_escape(event['detail'])}")
    if event.get("url"):
        lines.append(f"URL:{event['url']}")
    lines += ["END:VEVENT", "END:VCALENDAR", ""]
    return "data:text/calendar;charset=utf-8," + quote("\r\n".join(lines))


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


def fetch_region_sections(region_cfg: dict) -> list[dict]:
    region_name = region_cfg["region"]["name"]
    blocks = []
    for source in region_cfg.get("sources", []):
        if not source.get("enabled", True):
            continue
        fetcher = FETCHERS.get(source["type"])
        if fetcher is None:
            logger.warning("Unknown source type %r for %s", source["type"], source["name"])
            raw_items = []
        else:
            logger.info("Fetching %s (%s)", source["name"], source["type"])
            raw_items = fetcher(
                source["url"],
                keywords=source.get("keywords"),
                detail_link_pattern=source.get("detail_link_pattern"),
            )
            logger.info("  -> %d item(s)", len(raw_items))

        events = []
        for item in raw_items:
            tags = infer_tags(item.get("title", ""), item.get("detail", ""), source["section"])
            event = {
                "title": item.get("title", ""),
                "detail": truncate(item.get("detail", "")),
                "url": item.get("url", ""),
                "date": format_event_date(item.get("date")),
                "date_iso": parse_event_date_iso(item.get("date")),
                "tags": tags,
                "tag_badges": [{"id": t, **tag_display(t)} for t in tags],
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


def resolve_sponsor(sponsors_cfg: dict, region_id: str) -> dict:
    default_house_ad = sponsors_cfg.get(
        "default_house_ad", {"title": "Sponsor this spot", "detail": "", "url": ""}
    )
    region_sponsor_cfg = sponsors_cfg.get("regions", {}).get(region_id, {})
    active_id = region_sponsor_cfg.get("active")
    if active_id and active_id != "none":
        for entry in region_sponsor_cfg.get("history", []):
            if entry.get("id") == active_id:
                return entry
    return region_sponsor_cfg.get("house_ad") or default_house_ad


def all_tags_present(*blocks_and_evergreen: list[dict]) -> list[dict]:
    """Collect every distinct tag actually in use, for the filter bar -
    no point rendering a filter chip for a tag nothing on the page has.
    """
    seen: set[str] = set()
    for group in blocks_and_evergreen:
        for item in group:
            seen.update(item.get("tags", []))
    return [{"id": t, **tag_display(t)} for t in sorted(seen)]


def build_event_json_ld(region: dict, blocks: list[dict]) -> str | None:
    """schema.org/Event structured data for the fetched events (not the
    evergreen resource listings - those aren't dated events, so Event
    schema doesn't fit them). Returns None when there's nothing to embed
    rather than emitting an empty, pointless script block.

    Location is region-level (town + state + zip), not per-venue - we
    don't have structured addresses from the fetchers today. That's an
    honest approximation, not a precise one; schema.org doesn't require
    more precision than the data actually supports.
    """
    events = [e for b in blocks for e in b["events"] if e.get("title") and e.get("url")]
    if not events:
        return None
    graph = []
    for e in events:
        entry = {
            "@type": "Event",
            "name": e["title"],
            "url": e["url"],
            "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
            "location": {
                "@type": "Place",
                "name": region["name"],
                "address": {
                    "@type": "PostalAddress",
                    "addressRegion": region["state"],
                    "postalCode": region["zip"],
                    "addressCountry": "US",
                },
            },
        }
        if e.get("detail"):
            entry["description"] = e["detail"]
        if e.get("date_iso"):
            entry["startDate"] = e["date_iso"]
        graph.append(entry)
    payload = {"@context": "https://schema.org", "@graph": graph}
    # Escape "</" so an event title/description containing it can't break
    # out of the <script> tag it's embedded in.
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def render_region_page(region_cfg: dict, blocks: list[dict], sponsor: dict, evergreen: list[dict], now: datetime) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("region.html.j2")
    all_events_flat = [e for b in blocks for e in b["events"]] + evergreen
    region = region_cfg["region"]
    return template.render(
        region=region,
        issue_date=now.strftime("%B %d, %Y"),
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        sponsor=sponsor,
        blocks=blocks,
        evergreen=evergreen,
        available_tags=all_tags_present(all_events_flat),
        canonical_url=SITE_BASE_URL + region["id"] + "/",
        event_json_ld=build_event_json_ld(region, blocks),
    )


def render_hub_page(regions: list[dict], region_summaries: list[dict], now: datetime) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("hub.html.j2")
    return template.render(
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        region_summaries=region_summaries,
        canonical_url=SITE_BASE_URL,
    )


def build_sitemap_xml(region_summaries: list[dict], now: datetime) -> str:
    lastmod = now.strftime("%Y-%m-%d")
    urls = [SITE_BASE_URL] + [SITE_BASE_URL + r["path"] for r in region_summaries]
    entries = "\n".join(
        f"  <url>\n    <loc>{u}</loc>\n    <lastmod>{lastmod}</lastmod>\n  </url>" for u in urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n"
        "</urlset>\n"
    )


def build_robots_txt() -> str:
    return f"User-agent: *\nAllow: /\nSitemap: {SITE_BASE_URL}sitemap.xml\n"


def main() -> None:
    sponsors_cfg = load_yaml(CONFIG_DIR / "sponsors.yaml")
    regions = load_regions()
    now = datetime.now(timezone.utc)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / ".nojekyll").touch()

    region_summaries = []
    for region_cfg in regions:
        region = region_cfg["region"]
        region_id = region["id"]
        logger.info("=== Building region: %s (%s) ===", region["name"], region_id)

        blocks = fetch_region_sections(region_cfg)
        evergreen = prepare_evergreen(region_cfg)
        sponsor = resolve_sponsor(sponsors_cfg, region_id)

        html = render_region_page(region_cfg, blocks, sponsor, evergreen, now)

        region_dir = OUTPUT_DIR / region_id
        region_dir.mkdir(parents=True, exist_ok=True)
        (region_dir / "index.html").write_text(html, encoding="utf-8")
        logger.info("Wrote %s", region_dir / "index.html")

        event_count = sum(len(b["events"]) for b in blocks)
        region_summaries.append(
            {
                **region,
                "event_count": event_count,
                "path": f"{region_id}/",
            }
        )

    hub_html = render_hub_page(regions, region_summaries, now)
    (OUTPUT_DIR / "index.html").write_text(hub_html, encoding="utf-8")
    logger.info("Wrote %s", OUTPUT_DIR / "index.html")

    (OUTPUT_DIR / "sitemap.xml").write_text(build_sitemap_xml(region_summaries, now), encoding="utf-8")
    (OUTPUT_DIR / "robots.txt").write_text(build_robots_txt(), encoding="utf-8")
    logger.info("Wrote sitemap.xml and robots.txt")


if __name__ == "__main__":
    main()
