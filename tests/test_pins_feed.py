"""ROADMAP.md item 253: /pins.xml, a feed built for Pinterest's auto-publish
(a Pin per town per weekend, from pages on this domain, each with an image)."""

import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_digest  # noqa: E402

NOW = datetime(2026, 10, 8, 21, tzinfo=timezone.utc)
FRIDAY = date(2026, 10, 9)
RANGE = "Oct 9–11"
SIZES = {"default": 1000, "mount-prospect-60056": 2000, "palatine-60067": 3000, "wheeling-60090": 4000}


def ev(title, day="2026-10-10"):
    return {"title": title, "date_iso": f"{day}T10:00:00", "url": f"https://elsewhere.example/{title}"}


def groups():
    base = build_digest.SITE_BASE_URL
    return [
        ("mount-prospect-60056", "Mount Prospect", base + "mount-prospect-60056/", [ev("Farmers Market"), ev("Fall Fest"), ev("Chili Cook-off"), ev("Book Sale"), ev("Yoga")]),
        ("palatine-60067", "Palatine", base + "palatine-60067/", [ev("Oktoberfest")]),
        ("wheeling-60090", "Wheeling", base + "wheeling-60090/", []),  # nothing this weekend
    ]


def items(xml):
    return ET.fromstring(xml).findall("./channel/item")


def test_feed_is_well_formed_rss_with_one_pin_per_town_that_has_events():
    xml = build_digest.build_pins_xml(groups(), FRIDAY, RANGE, NOW, SIZES)
    root = ET.fromstring(xml)
    assert root.tag == "rss" and root.get("version") == "2.0"
    titles = [i.findtext("title") for i in items(xml)]
    assert titles == ["This weekend in Mount Prospect (Oct 9–11)", "This weekend in Palatine (Oct 9–11)"]  # no empty-weekend Pin for Wheeling


def test_every_link_is_on_the_site_domain_and_every_item_has_an_image():
    xml = build_digest.build_pins_xml(groups(), FRIDAY, RANGE, NOW, SIZES, trick_or_treat_in_season=True)
    host = f"https://{build_digest.CUSTOM_DOMAIN}/"
    found = items(xml)
    assert len(found) == 3
    for item in found:
        assert item.findtext("link").startswith(host)
        enc = item.find("enclosure")
        assert enc is not None and enc.get("type") == "image/png"
        assert enc.get("url").startswith(host + "og/") and int(enc.get("length")) > 0
        assert item.findtext("guid") and item.findtext("description") and item.findtext("pubDate")
    # Nothing in the feed points at a publisher's page: that is /feed.xml's job.
    assert "elsewhere.example" not in xml


def test_each_week_is_a_new_pin_and_each_town_a_distinct_one():
    first = {i.findtext("guid") for i in items(build_digest.build_pins_xml(groups(), FRIDAY, RANGE, NOW, SIZES))}
    nxt = {i.findtext("guid") for i in items(build_digest.build_pins_xml(groups(), date(2026, 10, 16), "Oct 16–18", NOW, SIZES))}
    assert len(first) == 2 and len(nxt) == 2 and not (first & nxt)
    assert all(g.endswith("#2026-10-09") for g in first)


def test_description_names_real_events_and_counts_the_rest():
    xml = build_digest.build_pins_xml(groups(), FRIDAY, RANGE, NOW, SIZES)
    mp, pal = [i.findtext("description") for i in items(xml)]
    assert mp == "Oct 9–11 in Mount Prospect: Farmers Market; Fall Fest; Chili Cook-off and 2 more."
    assert pal == "Oct 9–11 in Palatine: Oktoberfest."


def test_the_trick_or_treat_pin_follows_the_page_season_gate():
    off = build_digest.build_pins_xml(groups(), FRIDAY, RANGE, NOW, SIZES, trick_or_treat_in_season=False)
    on = build_digest.build_pins_xml(groups(), FRIDAY, RANGE, NOW, SIZES, trick_or_treat_in_season=True)
    assert "trick-or-treat" not in off
    pin = items(on)[-1]
    assert pin.findtext("link") == build_digest.SITE_BASE_URL + "trick-or-treat/"
    assert pin.find("enclosure").get("url").endswith("/og/default.png")
    assert build_digest.is_trick_or_treat_season(datetime(2026, 10, 8)) and not build_digest.is_trick_or_treat_season(datetime(2026, 7, 8))


def test_a_town_without_an_image_is_left_out_rather_than_published_blank():
    xml = build_digest.build_pins_xml(groups(), FRIDAY, RANGE, NOW, {"default": 1000, "palatine-60067": 3000})
    assert [i.findtext("title") for i in items(xml)] == ["This weekend in Palatine (Oct 9–11)"]


def test_titles_with_xml_characters_stay_well_formed():
    g = [("palatine-60067", "Palatine", build_digest.SITE_BASE_URL + "palatine-60067/", [ev("Beer & Brats <21+>")])]
    xml = build_digest.build_pins_xml(g, FRIDAY, RANGE, NOW, SIZES)
    assert "Beer &amp; Brats &lt;21+&gt;" in xml
    assert items(xml)[0].findtext("description").endswith("Beer & Brats <21+>.")


def test_domain_verify_meta_renders_on_the_home_page_only_when_set():
    def hub(analytics):
        return build_digest.render_hub_page([], [], NOW, None, analytics)

    assert 'name="p:domain_verify"' not in hub({"configured": False, "pinterest_domain_verify": ""})
    assert 'name="p:domain_verify"' not in hub(None)
    html = hub({"configured": False, "pinterest_domain_verify": "abc123"})
    assert html.count('<meta name="p:domain_verify" content="abc123">') == 1
    cfg = build_digest.load_analytics_config({"goatcounter_code": None, "pinterest_domain_verify": " tok "})
    assert cfg["pinterest_domain_verify"] == "tok"
    assert build_digest.load_analytics_config({})["pinterest_domain_verify"] == ""
    assert "pinterest_domain_verify" in (Path(__file__).resolve().parents[1] / "config" / "analytics.yaml").read_text()
