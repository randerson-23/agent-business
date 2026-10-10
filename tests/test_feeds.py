"""ROADMAP.md item 269: feeds that cite Within Ten, and one per town."""

import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_digest  # noqa: E402

NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
BASE = build_digest.SITE_BASE_URL


def item(title, day, region="Mount Prospect", rid="mount-prospect-60056", publisher="https://mppl.libnet.info/event/1", **kw):
    anchor = build_digest.event_anchor_id({"title": title, "date_iso": f"{day}T10:00:00"})
    base = {
        "title": title, "url": publisher, "detail": "Songs and rhymes.", "date_iso": f"{day}T10:00:00", "region_name": region,
        "source": "Mount Prospect Public Library — Events", "site_url": f"{BASE}{rid}/#{anchor}",
    }
    base.update(kw)
    return base


def parse(xml):
    return ET.fromstring(xml).findall("./channel/item")


def test_items_link_to_the_sites_own_cards_and_keep_the_publisher_reachable():
    xml = build_digest.build_feed_xml([item("Baby Storytime", "2026-10-12")], NOW)
    (entry,) = parse(xml)
    assert entry.findtext("link") == f"{BASE}mount-prospect-60056/#ev-baby-storytime-2026-10-12"
    guid = entry.find("guid")
    assert guid.text == entry.findtext("link") and guid.get("isPermaLink") == "true"
    assert entry.findtext("description") == "Songs and rhymes. Official listing: https://mppl.libnet.info/event/1"
    source = entry.find("source")
    assert source.get("url") == "https://mppl.libnet.info/event/1" and source.text == "Mount Prospect Public Library — Events"


def test_every_link_is_on_the_site_domain_and_the_publisher_url_is_always_present():
    items = [item("A", "2026-10-12"), item("B", "2026-10-13", publisher="https://ahpd.org/b", region="Arlington Heights", rid="arlington-heights-60005")]
    for entry in parse(build_digest.build_feed_xml(items, NOW)):
        assert entry.findtext("link").startswith(f"https://{build_digest.CUSTOM_DOMAIN}/")
        assert entry.findtext("guid").startswith(f"https://{build_digest.CUSTOM_DOMAIN}/")
        assert "Official listing: https://" in entry.findtext("description")


def test_guids_are_stable_across_builds_and_unique_per_card():
    a = parse(build_digest.build_feed_xml([item("Same Title", "2026-10-12"), item("Same Title", "2026-10-19")], NOW))
    b = parse(build_digest.build_feed_xml([item("Same Title", "2026-10-12"), item("Same Title", "2026-10-19")], datetime(2026, 10, 11, tzinfo=timezone.utc)))
    guids_a = [e.findtext("guid") for e in a]
    assert guids_a == [e.findtext("guid") for e in b]  # nothing re-notifies subscribers
    assert len(set(guids_a)) == 2  # a recurring event's dates are different cards


def test_a_description_with_no_detail_is_just_the_official_listing():
    (entry,) = parse(build_digest.build_feed_xml([item("Quiet", "2026-10-12", detail="")], NOW))
    assert entry.findtext("description") == "Official listing: https://mppl.libnet.info/event/1"


def test_an_item_without_a_site_url_still_links_to_the_publisher():
    legacy = {"title": "Old", "url": "https://village.example/old", "detail": "d", "date_iso": "2026-10-12T10:00:00", "region_name": "Town"}
    (entry,) = parse(build_digest.build_feed_xml([legacy], NOW))
    assert entry.findtext("link") == "https://village.example/old" and entry.find("source") is None


def test_a_town_feed_has_its_own_title_and_description():
    xml = build_digest.build_feed_xml([item("A", "2026-10-12")], NOW, title="Within Ten — Upcoming events in Mount Prospect", scope="Mount Prospect")
    channel = ET.fromstring(xml).find("channel")
    assert channel.findtext("title") == "Within Ten — Upcoming events in Mount Prospect"
    assert channel.findtext("description").startswith("Upcoming events in Mount Prospect, soonest first")
    assert build_digest.build_feed_xml([], NOW).count("across every Within Ten region") == 1
    assert "<item>" not in xml.split("</channel>")[0].split("<lastBuildDate>")[0]


def test_the_region_page_advertises_its_feed_and_llms_txt_lists_every_feed():
    region_cfg = next(r for r in build_digest.load_regions() if r["region"]["id"] == "mount-prospect-60056")
    html = build_digest.render_region_page(
        region_cfg, [{"section": "S", "events": []}], {"title": "", "detail": "", "url": ""}, [], NOW,
    )
    assert '<link rel="alternate" type="application/rss+xml" title="Upcoming events in Mount Prospect (RSS)" href="' in html
    assert re.search(r'type="application/rss\+xml"[^>]*href="https://withintenmiles.com/mount-prospect-60056/feed.xml"', html)
    summaries = [
        {"id": "a", "name": "Mount Prospect", "path": "mount-prospect-60056/", "zip": "60056", "state": "IL", "tagline": "t", "event_count": 0, "guide_slugs": []},
        {"id": "b", "name": "Palatine", "path": "palatine-60067/", "zip": "60067", "state": "IL", "tagline": "t", "event_count": 0, "guide_slugs": []},
    ]
    txt = build_digest.build_llms_txt(summaries)
    assert f"[RSS: upcoming events across every region]({BASE}feed.xml)" in txt
    assert f"[RSS: Palatine]({BASE}palatine-60067/feed.xml)" in txt
