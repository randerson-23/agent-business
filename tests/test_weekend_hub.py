"""ROADMAP.md item 268: the weekend hub gets what the email already had:
date-and-time order, start times, a description without its date header,
family-first picks, and no days that have passed."""

import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_digest  # noqa: E402

NOW = datetime(2026, 10, 10, 13, tzinfo=timezone.utc)


def ev(title, iso, tags=(), **kw):
    base = {"title": title, "url": f"https://src/{title}", "date": "x", "date_iso": iso, "detail": "", "tags": list(tags),
            "tag_badges": [], "attendable": True}
    base.update(kw)
    return base


def test_family_relevance_scores_tags_up_and_adult_words_down():
    r = build_digest.family_relevance
    assert r(ev("Storytime", "2026-10-10T10:00:00", ["kid_friendly", "free"])) == 2
    assert r(ev("Pumpkin Walk", "2026-10-10T10:00:00", ["outdoor", "free", "kid_friendly"])) == 3
    assert r(ev("Small Claims Court and Arbitration Proceedings", "2026-10-10T10:00:00")) == -4
    assert r(ev("Medicare Basics", "2026-10-10T10:00:00", ["free"])) == -1
    assert r(ev("Harvest Fest", "2026-10-10T10:00:00")) == 0


def test_adult_words_match_whole_words_only():
    r = build_digest.family_relevance
    assert r(ev("Courtney's Puppet Show", "2026-10-10T10:00:00")) == 0  # "court" inside a name
    assert r(ev("Taxidermy for Kids", "2026-10-10T10:00:00")) == 0
    assert r(ev("Free Tax Help", "2026-10-10T10:00:00")) == -2
    assert r(ev("ESL Conversation Circle", "2026-10-10T10:00:00")) == -2


def test_the_word_list_comes_from_config():
    cfg = build_digest.load_relevance_config()
    assert "kid_friendly" in cfg["boost_tags"]
    assert cfg["adult_pattern"].search("Court")
    assert (Path(__file__).resolve().parents[1] / "config" / "relevance.yaml").exists()


def test_weekend_order_is_date_then_time_then_relevance_with_featured_first():
    events = [
        ev("Sun", "2026-10-11T09:00:00"),
        ev("Sat late", "2026-10-10T15:00:00"),
        ev("Legal talk", "2026-10-10T10:00:00"),
        ev("Storytime", "2026-10-10T10:00:00", ["kid_friendly", "free"]),
        ev("Paid", "2026-10-11T18:00:00", sponsored_by="Sponsor"),
    ]
    out = [e["title"] for e in build_digest.order_weekend_events(events)]
    assert out == ["Paid", "Storytime", "Legal talk", "Sat late", "Sun"]  # same moment: the family event first


def test_a_kid_friendly_event_outranks_a_legal_talk_at_the_same_time_but_both_stay():
    events = [ev("Small Claims Court Talk", "2026-10-10T10:00:00"), ev("Family Storytime", "2026-10-10T10:00:00", ["kid_friendly"])]
    out = build_digest.order_weekend_events(events)
    assert [e["title"] for e in out] == ["Family Storytime", "Small Claims Court Talk"]  # nothing hidden


def test_the_email_cap_keeps_family_picks_and_still_shows_them_in_date_order():
    events = [
        ev("Court Talk", "2026-10-09T09:00:00"),
        ev("Tax Help", "2026-10-09T10:00:00"),
        ev("Pumpkin Walk", "2026-10-11T10:00:00", ["outdoor", "free", "kid_friendly"]),
        ev("Storytime", "2026-10-10T10:00:00", ["kid_friendly", "free"]),
        ev("Harvest Fest", "2026-10-10T12:00:00"),
    ]
    shown = build_digest.prepare_email_events(events, limit=3)
    titles = [e["title"] for e in shown]
    assert set(titles) == {"Storytime", "Harvest Fest", "Pumpkin Walk"}  # the 3 most family-relevant, not the 3 soonest
    assert "Court Talk" not in titles and "Tax Help" not in titles
    assert titles == sorted(titles, key=lambda t: next(e["date_iso"] for e in events if e["title"] == t))
    assert len(build_digest.prepare_email_events(events)) == 5  # no cap: all shown


def test_hub_and_email_pick_the_same_short_list_from_the_same_input():
    events = [ev(f"Adult Court {i}", f"2026-10-10T0{i}:00:00") for i in range(1, 5)] + [
        ev(f"Kids {i}", f"2026-10-11T1{i}:00:00", ["kid_friendly"]) for i in range(1, 5)
    ]
    email = [e["title"] for e in build_digest.prepare_email_events(events, limit=4)]
    hub_first_four_family = [e["title"] for e in sorted(build_digest.order_weekend_events(events), key=lambda e: -build_digest.family_relevance(e))[:4]]
    assert set(email) == set(hub_first_four_family) == {f"Kids {i}" for i in range(1, 5)}


def test_cards_show_start_time_and_a_description_without_its_date_header():
    e = ev("Coaching", "2026-10-10T12:15:00", detail="Saturday, October 10 2026 12:15pm - 1:15pm \n Kickstart your career.")
    untimed = ev("Fest", "2026-10-10T00:00:00", detail="Rides and food.")
    build_digest.prepare_event_cards([{"events": [e, untimed]}])
    assert e["time_label"] == "12:15 PM" and e["card_detail"] == "Kickstart your career."
    assert untimed["time_label"] is None and untimed["card_detail"] == "Rides and food."


def test_the_hub_page_renders_time_and_clean_text():
    e = ev("Coaching", "2026-10-10T12:15:00", detail="Saturday, October 10 2026 12:15pm - 1:15pm \n Kickstart your career.")
    sections = [{"region_name": "Mount Prospect", "region_url": "https://x/mp/", "events": [e]}]
    html = build_digest.render_merged_hub_page(sections, NOW, None, slug="this-weekend", heading="H", subheading="s", meta_description="m", empty_message="none")
    assert "Sat, Oct 10 · 12:15 PM</time>" in html
    assert '<p class="detail">Kickstart your career.</p>' in html
    assert "12:15pm - 1:15pm" not in html


def test_the_date_range_header_drops_days_that_have_passed():
    fmt = build_digest.format_date_range
    assert fmt(date(2026, 10, 9), date(2026, 10, 11)) == "Oct 9–11"
    assert fmt(date(2026, 10, 10), date(2026, 10, 11)) == "Oct 10–11"  # Saturday
    assert fmt(date(2026, 10, 11), date(2026, 10, 11)) == "Oct 11"  # Sunday: a single day, not "Oct 11–11"
    friday, saturday, sunday = build_digest.weekend_dates(date(2026, 10, 10))
    window = [d for d in (friday, saturday, sunday) if d >= date(2026, 10, 10)]
    assert window == [saturday, sunday]
    assert [d for d in (friday, saturday, sunday) if d >= date(2026, 10, 7)] == [friday, saturday, sunday]  # Wednesday: all three
