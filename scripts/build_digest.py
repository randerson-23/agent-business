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
import math
import sys
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

import yaml
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).parent))
from fetchers import FETCHERS, fetch_weather  # noqa: E402
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

# The one canonical name for this site, used everywhere a page names its
# own publisher - <title>, og:title, and every WebPage's schema.org name.
# Before this constant existed, region pages independently built a
# shortened "{region} — Weekend Planner" title while every other page
# said "Weekend & Trip Planner" - two different strings for what should
# read as one entity to a search/AI crawler (ROADMAP.md Phase 11 #22
# follow-up, entity-naming audit).
SITE_NAME = "Weekend & Trip Planner"


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
    return {"configured": bool(code), "goatcounter_code": code}


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
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        pass
    for fmt in _EXTRA_DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
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
    return parsed.isoformat() if parsed else None


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
SPONSOR_TIERS = [
    {
        "name": "Annual Partner",
        "price": "$1,200/year",
        "detail": "A permanent business directory listing, a spotlight placement inside one relevant seasonal guide, a live SEO backlink, and priority consideration for Editor's Pick — the flagship membership.",
    },
    {
        "name": "Neighborhood Authority",
        "price": "$5,000/year, one business per region",
        "detail": "Everything in Annual Partner, held exclusively for your region year-round — built for real estate and other locally-budgeted categories seeking neighborhood-level presence, not just leads.",
    },
    {
        "name": "Weekly Spot",
        "price": "$50/week or $175/month",
        "detail": "Not ready for a year? The same top-of-page recommendation, available week-to-week or month-to-month.",
    },
    {
        "name": "Event Promo",
        "price": "$20 one-time",
        "detail": "Your single event or announcement boosted to the top of \"This Week.\"",
    },
]


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


def render_sponsor_page(
    availability: list[dict], now: datetime, analytics: dict | None = None
) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("sponsor.html.j2")
    return template.render(
        tiers=SPONSOR_TIERS,
        availability=availability,
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        canonical_url=SITE_BASE_URL + "sponsor/",
        hub_url=SITE_BASE_URL,
        analytics=analytics,
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
    """
    candidates = [e for b in blocks for e in b["events"]] + evergreen
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

    return sorted(candidates, key=sort_key)[0]


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
    """
    return (
        f"{region['name']} ({region['zip']}), {region['state']}: {region['tagline']} "
        f"This page rebuilds automatically, usually several times a week, "
        f"and links directly to the official village, library, and park "
        f"district sources for full details on any listing."
    )


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
                f"Saturday-Sunday."
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
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": f"{region['name']} — {SITE_NAME}",
        "url": canonical_url,
        "dateModified": now.isoformat(),
        "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": SITE_BASE_URL},
    }
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def build_event_json_ld(region: dict, blocks: list[dict]) -> str | None:
    """schema.org/Event structured data for fetched events that have a
    real date (not the evergreen resource listings, and not an
    undated item - an "Event" with no date isn't a meaningful event,
    and some of these blocks are filtered views like /free that merge
    evergreen entries in alongside real events; date_iso is what tells
    them apart here). Returns None when there's nothing to embed rather
    than emitting an empty, pointless script block.

    Location is region-level (town + state + zip), not per-venue - we
    don't have structured addresses from the fetchers today. That's an
    honest approximation, not a precise one; schema.org doesn't require
    more precision than the data actually supports.
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
    weather: list[dict] | None = None,
    newsletter: dict | None = None,
    editors_pick: dict | None = None,
    analytics: dict | None = None,
    answer_block: str | None = None,
    include_faq: bool = False,
) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
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
    return template.render(
        region=region,
        issue_date=now.strftime("%B %d, %Y"),
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        sponsor=sponsor,
        blocks=blocks,
        evergreen=evergreen,
        available_tags=all_tags_present(all_events_flat),
        canonical_url=canonical_url,
        event_json_ld=build_event_json_ld(region, blocks),
        freshness_json_ld=build_freshness_json_ld(region, canonical_url, now),
        answer_block=answer_block,
        faq=faq,
        faq_json_ld=build_faq_json_ld(faq) if faq else None,
        heading=heading,
        subheading=subheading,
        empty_message=empty_message,
        empty_cta_url=empty_cta_url,
        empty_cta_label=empty_cta_label,
        nav_current=nav_current,
        region_base_url=region_base_url,
        page_title=page_title,
        page_description=page_description,
        hub_url=SITE_BASE_URL,
        guides_url=guides_url,
        directory_url=directory_url,
        weather=weather,
        newsletter=newsletter,
        editors_pick=editors_pick,
        analytics=analytics,
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


def render_hub_page(
    regions: list[dict],
    region_summaries: list[dict],
    now: datetime,
    newsletter: dict | None = None,
    analytics: dict | None = None,
    stats: dict | None = None,
) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("hub.html.j2")
    return template.render(
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        region_summaries=region_summaries,
        canonical_url=SITE_BASE_URL,
        newsletter=newsletter,
        region_map=build_region_map(region_summaries),
        analytics=analytics,
        stats=stats,
    )


def render_weekend_hub_page(
    region_sections: list[dict], date_range: str, now: datetime, analytics: dict | None = None
) -> str:
    """The hub-level 'This weekend near you' page: weekend events merged
    across every region, grouped by region so it's still clear where each
    one is. Deferred out of the per-region date-scoped-views slice to keep
    that one shippable; picked up here as the natural follow-up.
    """
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("weekend_hub.html.j2")
    return template.render(
        region_sections=region_sections,
        date_range=date_range,
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        canonical_url=SITE_BASE_URL + "this-weekend/",
        hub_url=SITE_BASE_URL,
        analytics=analytics,
    )


def build_sitemap_xml(region_summaries: list[dict], now: datetime) -> str:
    lastmod = now.strftime("%Y-%m-%d")
    urls = [SITE_BASE_URL, SITE_BASE_URL + "this-weekend/", SITE_BASE_URL + "sponsor/"]
    for r in region_summaries:
        base = SITE_BASE_URL + r["path"]
        urls += [base, base + "this-weekend/", base + "today/", base + "free/", base + "directory/"]
        if r.get("guide_slugs"):
            urls.append(base + "guides/")
            urls += [base + f"guides/{slug}/" for slug in r["guide_slugs"]]
    entries = "\n".join(
        f"  <url>\n    <loc>{u}</loc>\n    <lastmod>{lastmod}</lastmod>\n  </url>" for u in urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n"
        "</urlset>\n"
    )


def build_llms_txt(region_summaries: list[dict]) -> str:
    """llms.txt (llmstxt.org convention, ROADMAP.md Phase 11 #22 - GEO):
    a plain-language map of the site for an AI agent/crawler to read
    directly, generated at build time from the same region_summaries the
    sitemap uses - so it can never drift out of sync with what's actually
    live the way a hand-written one would.
    """
    lines = [
        "# Weekend & Trip Planner",
        "",
        "> A hyperlocal weekend/trip planner for Chicago-area ZIP codes. "
        "Aggregates village news, public library events, and park "
        "district programs per town, rebuilt automatically (usually "
        "multiple times a week), so it stays current without a human "
        "keeping it that way.",
        "",
        "## Regions",
    ]
    for r in region_summaries:
        base = SITE_BASE_URL + r["path"]
        lines.append(f"- [{r['name']} ({r['zip']})]({base}): {r['tagline']}")
    lines += ["", "## This weekend", f"- [Across every region]({SITE_BASE_URL}this-weekend/)"]
    for r in region_summaries:
        base = SITE_BASE_URL + r["path"]
        lines.append(f"- [{r['name']} — this weekend]({base}this-weekend/)")
    guide_lines = [
        f"- [{g['title']} — {r['name']}]({SITE_BASE_URL}{r['path']}guides/{g['slug']}/)"
        for r in region_summaries
        for g in r.get("guides", [])
    ]
    if guide_lines:
        lines += ["", "## Guides"] + guide_lines
    lines += ["", "## Sponsorship", f"- [Sponsor a region]({SITE_BASE_URL}sponsor/)"]
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
    """
    lines = [f"What's happening in {region['name']} this weekend ({weekend_date_range}):", ""]
    if weekend_events:
        for event in weekend_events[:6]:
            prefix = f"{event['date']} — " if event.get("date") else ""
            lines.append(f"- {prefix}{event['title']}")
    else:
        highlights = [e for e in evergreen if "free" in e.get("tags", [])][:3]
        if highlights:
            lines.append("Nothing new dated for this weekend yet, but a few things worth knowing about:")
            for item in highlights:
                lines.append(f"- {item['title']}")
        else:
            lines.append("Nothing dated for this weekend yet - the full guide has what's coming up.")
    lines.append("")
    lines.append(f"See everything: {region_url}")
    lines.append("(Updated automatically, several times a week.)")
    return "\n".join(lines) + "\n"


def weekend_dates(local_date: date) -> tuple[date, date]:
    """The Saturday/Sunday of the calendar week (Mon-Sun) containing
    local_date - correct whether local_date is itself a weekday (the
    upcoming weekend) or already Saturday/Sunday (this weekend, in
    progress).
    """
    monday = local_date - timedelta(days=local_date.weekday())
    return monday + timedelta(days=5), monday + timedelta(days=6)


def build_weekend_weather(region: dict, saturday: date, sunday: date) -> list[dict]:
    """Saturday/Sunday forecast for a region's /this-weekend/ page
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
    for target in (saturday, sunday):
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


def filter_free_items(blocks: list[dict], evergreen: list[dict]) -> list[dict]:
    """Every fetched event and evergreen entry tagged 'free', regardless
    of whether it has a resolved date - unlike the weekend/today views,
    "is this free" doesn't depend on knowing when it happens.
    """
    matched = [e for b in blocks for e in b["events"] if "free" in e.get("tags", [])]
    matched += [e for e in evergreen if "free" in e.get("tags", [])]
    return matched


def main() -> None:
    sponsors_cfg = load_yaml(CONFIG_DIR / "sponsors.yaml")
    newsletter = load_newsletter_config(load_yaml(CONFIG_DIR / "newsletter.yaml"))
    analytics = load_analytics_config(load_yaml(CONFIG_DIR / "analytics.yaml"))
    regions = load_regions()
    now = datetime.now(timezone.utc)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / ".nojekyll").touch()

    region_summaries = []
    hub_weekend_sections = []
    hub_weekend_date_range = None
    total_dated, total_events = 0, 0
    for region_cfg in regions:
        region = region_cfg["region"]
        region_id = region["id"]
        logger.info("=== Building region: %s (%s) ===", region["name"], region_id)

        blocks = fetch_region_sections(region_cfg)
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
        editors_pick = select_editors_pick(region_cfg, blocks, evergreen)

        html = render_region_page(
            region_cfg,
            blocks,
            sponsor,
            evergreen,
            now,
            guides_url=guides_url,
            directory_url=directory_url,
            newsletter=newsletter,
            analytics=analytics,
            editors_pick=editors_pick,
            answer_block=build_answer_block(region),
        )

        region_dir = OUTPUT_DIR / region_id
        region_dir.mkdir(parents=True, exist_ok=True)
        (region_dir / "index.html").write_text(html, encoding="utf-8")
        logger.info("Wrote %s", region_dir / "index.html")

        local_today = region_local_date(region, now)
        saturday, sunday = weekend_dates(local_today)
        weekend_events = filter_events_by_dates(blocks, {saturday, sunday})
        weekend_weather = build_weekend_weather(region, saturday, sunday)
        weekend_date_range = format_date_range(saturday, sunday)
        if hub_weekend_date_range is None:
            hub_weekend_date_range = weekend_date_range  # regions share a timezone today

        weekly_summary_txt = build_weekly_summary_txt(
            region, weekend_events, evergreen, SITE_BASE_URL + region_id + "/", weekend_date_range
        )
        (region_dir / "weekly-summary.txt").write_text(weekly_summary_txt, encoding="utf-8")
        logger.info("Wrote %s", region_dir / "weekly-summary.txt")
        if weekend_events:
            hub_weekend_sections.append(
                {
                    "region_name": region["name"],
                    "region_url": SITE_BASE_URL + region_id + "/",
                    "events": weekend_events,
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
                weather=weekend_weather if slug == "this-weekend" else None,
                newsletter=newsletter,
                analytics=analytics,
            )
            view_dir = region_dir / slug
            view_dir.mkdir(parents=True, exist_ok=True)
            (view_dir / "index.html").write_text(view_html, encoding="utf-8")
            logger.info("Wrote %s (%d item%s)", view_dir / "index.html", len(items), "" if len(items) == 1 else "s")

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
            newsletter=newsletter,
            analytics=analytics,
        )
        directory_dir = region_dir / "directory"
        directory_dir.mkdir(parents=True, exist_ok=True)
        (directory_dir / "index.html").write_text(directory_html, encoding="utf-8")
        logger.info("Wrote %s (%d listing%s)", directory_dir / "index.html", len(directory), "" if len(directory) == 1 else "s")

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
    }
    hub_html = render_hub_page(regions, region_summaries, now, newsletter, analytics, stats=hub_stats)
    (OUTPUT_DIR / "index.html").write_text(hub_html, encoding="utf-8")
    logger.info("Wrote %s", OUTPUT_DIR / "index.html")

    weekend_hub_html = render_weekend_hub_page(hub_weekend_sections, hub_weekend_date_range or "", now, analytics)
    weekend_hub_dir = OUTPUT_DIR / "this-weekend"
    weekend_hub_dir.mkdir(parents=True, exist_ok=True)
    (weekend_hub_dir / "index.html").write_text(weekend_hub_html, encoding="utf-8")
    logger.info("Wrote %s (%d region section%s)", weekend_hub_dir / "index.html", len(hub_weekend_sections), "" if len(hub_weekend_sections) == 1 else "s")

    sponsor_availability = build_sponsor_availability(sponsors_cfg, region_summaries)
    sponsor_html = render_sponsor_page(sponsor_availability, now, analytics)
    sponsor_dir = OUTPUT_DIR / "sponsor"
    sponsor_dir.mkdir(parents=True, exist_ok=True)
    (sponsor_dir / "index.html").write_text(sponsor_html, encoding="utf-8")
    logger.info("Wrote %s", sponsor_dir / "index.html")

    (OUTPUT_DIR / "sitemap.xml").write_text(build_sitemap_xml(region_summaries, now), encoding="utf-8")
    (OUTPUT_DIR / "robots.txt").write_text(build_robots_txt(), encoding="utf-8")
    (OUTPUT_DIR / "llms.txt").write_text(build_llms_txt(region_summaries), encoding="utf-8")
    logger.info("Wrote sitemap.xml, robots.txt, and llms.txt")
    if total_events:
        logger.info(
            "TOTAL structured-date coverage: %d/%d events (%.0f%%) have a machine-readable start date",
            total_dated, total_events, 100 * total_dated / total_events,
        )


if __name__ == "__main__":
    main()
