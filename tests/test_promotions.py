"""ROADMAP.md item 245: the $20 Event Promo, so it can actually be
delivered. One `promotions:` entry in config/sponsors.yaml features an
event first in its region's lists, labelled and carrying Schema.org
`sponsor`, and expires on its own."""

import json
import logging
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_digest  # noqa: E402

REGION = {"region": {"id": "mount-prospect-60056", "name": "Mount Prospect", "state": "IL"}}
TODAY = date(2026, 10, 14)


def promo(**over):
    base = {
        "region": "mount-prospect-60056",
        "title": "Lions Pancake Breakfast",
        "url": "https://lions.example/pancakes",
        "date": "2026-10-18",
        "sponsor": "Mount Prospect Lions Club",
        "blurb": "All you can eat, 8 to 11 a.m.",
    }
    base.update(over)
    return base


def cfg(*promos):
    return {"promotions": list(promos)}


def feed_event(title, day, url):
    return {"title": title, "url": url, "date_iso": f"{day}T10:00:00", "detail": "d", "tags": []}


def test_a_live_promotion_becomes_a_labelled_event():
    event = build_digest.build_promotion_event(cfg(promo()), REGION, TODAY)
    assert event["title"] == "Lions Pancake Breakfast"
    assert event["sponsored_by"] == "Mount Prospect Lions Club"
    assert event["detail"] == "All you can eat, 8 to 11 a.m."
    assert event["date_iso"] == "2026-10-18T00:00:00"
    assert event["attendable"] is True


def test_a_promotion_for_another_region_is_ignored():
    assert build_digest.build_promotion_event(cfg(promo(region="palatine-60067")), REGION, TODAY) is None


def test_the_window_runs_from_starts_to_ends_and_defaults_to_the_event_day():
    # No ends: featured through the event's own day, then gone.
    assert build_digest.build_promotion_event(cfg(promo()), REGION, date(2026, 10, 18))
    assert build_digest.build_promotion_event(cfg(promo()), REGION, date(2026, 10, 19)) is None
    # starts: not featured before it.
    early = promo(starts="2026-10-15")
    assert build_digest.build_promotion_event(cfg(early), REGION, date(2026, 10, 14)) is None
    assert build_digest.build_promotion_event(cfg(early), REGION, date(2026, 10, 15))
    # ends before the event day: stops early.
    short = promo(ends="2026-10-16")
    assert build_digest.build_promotion_event(cfg(short), REGION, date(2026, 10, 17)) is None


def test_yaml_date_objects_are_accepted():
    event = build_digest.build_promotion_event(cfg(promo(date=date(2026, 10, 18))), REGION, TODAY)
    assert event["date_iso"] == "2026-10-18T00:00:00"


def test_malformed_promotions_are_skipped_with_a_warning(caplog):
    bad = [
        promo(sponsor=""),
        promo(url=None),
        promo(date="next Saturday"),
        promo(starts="2026-10-20"),  # the event (10-18) is before it starts
        promo(starts="2026-10-16", ends="2026-10-15"),
    ]
    with caplog.at_level(logging.WARNING):
        for entry in bad:
            assert build_digest.build_promotion_event(cfg(entry), REGION, TODAY) is None
    assert len([r for r in caplog.records if "Skipping promotions[0]" in r.message]) == len(bad)


def test_only_one_promotion_is_featured_per_region(caplog):
    first = promo(title="Later Event", date="2026-10-25")
    second = promo(title="Sooner Event", date="2026-10-17", sponsor="Other Sponsor")
    with caplog.at_level(logging.WARNING):
        event = build_digest.build_promotion_event(cfg(first, second), REGION, TODAY)
    assert event["title"] == "Sooner Event"
    assert any("already has a featured promotion" in r.message and "Later Event" in r.message for r in caplog.records)


def test_apply_promotion_puts_the_featured_block_first_and_drops_the_duplicate():
    event = build_digest.build_promotion_event(cfg(promo()), REGION, TODAY)
    blocks = [
        {"section": "Village", "events": [
            feed_event("Lions Pancake Breakfast", "2026-10-18", "https://village.example/other"),  # same day, same title
            feed_event("Farmers Market", "2026-10-18", "https://village.example/market"),
        ]},
        {"section": "Library", "events": [feed_event("Different name", "2026-10-19", "https://lions.example/pancakes")]},  # same url
    ]
    out = build_digest.apply_promotion(blocks, event)
    assert out[0]["section"] == "Featured" and out[0]["events"] == [event]
    remaining = [e["title"] for b in out[1:] for e in b["events"]]
    assert remaining == ["Farmers Market"]
    # Weekend views read blocks in order, so the featured event leads them.
    weekend = build_digest.filter_events_by_dates(out, {date(2026, 10, 18)})
    assert [e["title"] for e in weekend] == ["Lions Pancake Breakfast", "Farmers Market"]


def test_apply_promotion_is_a_no_op_without_a_promotion():
    blocks = [{"section": "Village", "events": []}]
    assert build_digest.apply_promotion(blocks, None) is blocks


def test_json_ld_and_events_json_carry_the_sponsor():
    event = build_digest.build_promotion_event(cfg(promo()), REGION, TODAY)
    blocks = build_digest.apply_promotion([], event)
    build_digest.prepare_event_cards(blocks)
    ld = json.loads(build_digest.build_event_json_ld(blocks, "https://x/mp/", REGION["region"]))
    assert ld["@graph"][0]["sponsor"] == {"@type": "Organization", "name": "Mount Prospect Lions Club"}
    plain = build_digest.build_promotion_event(cfg(promo()), REGION, TODAY)
    plain.pop("sponsored_by")
    assert "sponsor" not in json.loads(build_digest.build_event_json_ld([{"section": "x", "events": [plain]}]))["@graph"][0]
    listing = json.loads(build_digest.build_events_json([("Mount Prospect", "https://x/mp/", [dict(event, town="Mount Prospect", state="IL")])], "n", datetime(2026, 10, 14, tzinfo=timezone.utc)))
    assert listing["itemListElement"][0]["item"]["sponsor"]["name"] == "Mount Prospect Lions Club"


def test_cards_and_the_email_label_the_featured_event():
    region_cfg = next(r for r in build_digest.load_regions() if r["region"]["id"] == REGION["region"]["id"])
    event = build_digest.build_promotion_event(cfg(promo()), region_cfg, TODAY)
    blocks = build_digest.apply_promotion([], event)
    sponsor = {"title": "Sponsor this spot", "detail": "", "url": "", "is_active_sponsor": False}
    html = build_digest.render_region_page(region_cfg, blocks, sponsor, [], datetime(2026, 10, 14, 12, tzinfo=timezone.utc))
    assert 'class="featured-label">Featured · Presented by Mount Prospect Lions Club</div>' in html
    assert html.index("Featured · Presented by") < html.index("Lions Pancake Breakfast</a>")
    template_dir = Path(build_digest.get_template_env().get_template("region.html.j2").filename).parent
    for name in ("email_digest.html.j2", "combined_email_digest.html.j2"):
        assert "Featured &middot; Presented by {{ event.sponsored_by }}" in (template_dir / name).read_text(encoding="utf-8")


def test_a_featured_event_never_leads_the_subject_line_or_the_editors_pick():
    event = build_digest.build_promotion_event(cfg(promo(title="Pancake Fest")), REGION, TODAY)
    regular = dict(feed_event("Harvest Concert", "2026-10-17", "https://v.example/concert"), attendable=True)
    subject = build_digest.build_email_subject_line(REGION["region"], [event, regular])
    assert "Harvest Concert" in subject and "Pancake" not in subject
    sections = [{"region_name": "Mount Prospect", "weekend_events": [event, regular]}]
    assert [e["title"] for e in build_digest._round_robin_attendable(sections)] == ["Harvest Concert"]
    pick = build_digest.select_editors_pick({"region": {"id": "x"}}, [{"section": "Featured", "events": [event]}], [])
    assert pick is None


def test_weekly_summary_and_llms_full_say_featured():
    event = build_digest.build_promotion_event(cfg(promo()), REGION, TODAY)
    summary = build_digest.build_weekly_summary_txt(REGION["region"], [event], [], "https://x/mp/", "Oct 17-18")
    assert "Lions Pancake Breakfast (Featured, presented by Mount Prospect Lions Club)" in summary
    full = build_digest.build_llms_full_txt([("Mount Prospect", "https://x/mp/", [event])], "Oct 17-18")
    assert "(Featured, presented by Mount Prospect Lions Club)" in full


def test_sponsor_page_shows_buy_now_only_for_configured_payment_links():
    now = datetime(2026, 10, 14, tzinfo=timezone.utc)
    off = build_digest.render_sponsor_page([], now, payment_links={"event_promo": None, "weekly_spot": None})
    assert "Buy now" not in off
    on = build_digest.render_sponsor_page([], now, payment_links={"event_promo": "https://buy.stripe.com/abc", "weekly_spot": None})
    assert on.count("Buy now") == 1
    assert 'href="https://buy.stripe.com/abc"' in on
    assert re.search(r"Event Promo.*?Buy now", on, re.S)


def test_the_real_config_is_valid_and_uses_the_forwarded_address():
    cfg_real = build_digest.load_yaml(build_digest.CONFIG_DIR / "sponsors.yaml")
    assert cfg_real["contact_email"] == "hello@withintenmiles.com"
    assert set(cfg_real["payment_links"]) == {"event_promo", "weekly_spot"}
    region_ids = {r["region"]["id"] for r in build_digest.load_regions()}
    for entry in cfg_real.get("promotions") or []:
        assert entry["region"] in region_ids
