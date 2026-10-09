"""ROADMAP.md items 257 and 260: email entries a reader can act on without
clicking, and no developer notes in the send files."""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_digest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
NEWSLETTER = {"configured": True, "headline": "h", "detail": "d", "buttondown_username": "planner"}


def ev(title, iso, **kw):
    base = {"title": title, "url": f"https://src/{title}", "date": "Oct 10", "date_iso": iso, "detail": "", "tags": [], "attendable": True}
    base.update(kw)
    return base


def test_time_label_for_timed_and_untimed_events():
    t = build_digest.event_time_label
    assert t("2026-10-10T10:00:00") == "10:00 AM"
    assert t("2026-10-10T13:05:00-05:00") == "1:05 PM"
    assert t("2026-10-10T12:00:00") == "12:00 PM"
    assert t("2026-10-10T00:00:00") is None  # midnight is "no time given", never 12:00 AM
    assert t("2026-10-10") is None
    assert t(None) is None and t("not a date") is None


def test_blurb_trims_at_a_word_boundary_and_never_invents_text():
    long = "Join us for a screening of a very popular film with free popcorn for everyone who comes along to watch it"
    out = build_digest.email_blurb(long, "Movie")
    assert out.endswith("…") and len(out) <= 90
    assert not out[:-1].endswith(" ") and out[:-1] in long and long[len(out[:-1])] == " "  # cut between words
    assert build_digest.email_blurb("Short and sweet.", "Movie") == "Short and sweet."
    assert build_digest.email_blurb("", "Movie") is None
    assert build_digest.email_blurb(None, "Movie") is None
    assert build_digest.email_blurb("   \n  ", "Movie") is None
    assert build_digest.email_blurb("Movie", "Movie") is None  # only repeats the title


def test_blurb_drops_communico_date_header_and_collapses_whitespace():
    raw = "Sunday, October 04 2026 12:15pm - 1:15pm \n Kickstart your career\nwith one-on-one help."
    assert build_digest.email_blurb(raw, "Coaching") == "Kickstart your career with one-on-one help."
    assert build_digest.email_blurb("Saturday, October 10 2026 2:00pm - 3:00pm", "X") is None  # nothing left after the header


def test_where_prefers_the_venue_then_the_short_source_name():
    w = build_digest.email_event_where
    assert w({"venue": "Mount Prospect Public Library", "source": "Mount Prospect Public Library — Events"}) == "Mount Prospect Public Library"
    assert w({"source": "Village of Palatine — News"}) == "Village of Palatine"
    assert w({"source": "Wheeling Park District"}) == "Wheeling Park District"
    assert w({}) is None


def test_entries_sort_by_date_then_time_with_a_featured_promotion_first():
    events = [
        ev("Late", "2026-10-11T18:00:00"),
        ev("Sat noon", "2026-10-10T12:00:00"),
        ev("Sat morning", "2026-10-10T09:00:00"),
        ev("Fri", "2026-10-09T10:00:00"),
        ev("Paid", "2026-10-11T08:00:00", sponsored_by="A Sponsor"),
    ]
    out = build_digest.prepare_email_events(events)
    assert [e["title"] for e in out] == ["Paid", "Fri", "Sat morning", "Sat noon", "Late"]
    assert out[1]["email_when"] == "Fri Oct 9 · 10:00 AM"
    assert events[0].get("email_when") is None  # inputs are not mutated


def test_untimed_events_show_the_date_alone_and_undated_ones_fall_back():
    out = build_digest.prepare_email_events([ev("Fest", "2026-10-10T00:00:00"), ev("Odd", None, date="sometime")])
    by_title = {e["title"]: e for e in out}
    assert by_title["Fest"]["email_when"] == "Sat Oct 10"
    assert by_title["Odd"]["email_when"] == "sometime"


def combined(events_by_town):
    sections = [
        {"region_name": town, "region_url": f"https://x/{town}/", "weekend_events": evs, "evergreen": [], "sponsor": None}
        for town, evs in events_by_town.items()
    ]
    return build_digest.render_combined_email_digest(sections, "Oct 9–11", NOW, NEWSLETTER)


def test_the_combined_email_shows_time_place_and_blurb_for_each_entry():
    html = combined({"Palatine": [ev("Harvest Hustle", "2026-10-10T09:30:00", venue="Palatine Public Library", detail="Run or walk the course.")]})
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    assert "Sat Oct 10 · 9:30 AM Palatine Public Library Run or walk the course." in text


def test_the_per_town_cap_applies_after_sorting_so_the_soonest_four_show():
    events = [ev(f"E{i}", f"2026-10-{11 - i:02d}T10:00:00") for i in range(6)]  # E0 is the latest
    html = combined({"Palatine": events})
    shown = re.findall(r">(E\d)</a>", html)
    assert shown == ["E5", "E4", "E3", "E2"]


def test_the_single_town_email_renders_the_same_fields():
    region = {"id": "mount-prospect-60056", "name": "Mount Prospect"}
    events = [ev("Storytime", "2026-10-10T10:30:00", venue="Mount Prospect Public Library", detail="Songs and rhymes.")]
    html = build_digest.render_email_digest(region, events, [], "https://x/mp/", "Oct 9–11", None, NEWSLETTER)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    assert "Sat Oct 10 · 10:30 AM Mount Prospect Public Library Songs and rhymes." in text


def test_a_full_combined_issue_stays_well_under_gmails_clip():
    long = "A fairly long description line that will be cut at a sensible word boundary for the email. " * 3
    towns = {
        name: [ev(f"{name} event {i}", f"2026-10-{9 + i % 3:02d}T1{i % 10}:00:00", venue=f"{name} Public Library", detail=long) for i in range(12)]
        for name in ("Arlington Heights", "Des Plaines", "Mount Prospect", "Palatine", "Wheeling")
    }
    assert len(combined(towns).encode("utf-8")) < 90_000  # Gmail clips at ~102KB


def test_send_files_carry_no_developer_comments():
    # Item 260: notes to developers are Jinja comments, so they never reach a
    # subscriber's "view source". Only Outlook's conditional blocks remain.
    for name in ("email_digest.html.j2", "combined_email_digest.html.j2"):
        source = (ROOT / "templates" / name).read_text(encoding="utf-8")
        assert re.findall(r"<!--(?!\[if mso\])", source) == [], name
    region = {"id": "r", "name": "Mount Prospect"}
    rendered = [
        build_digest.render_email_digest(region, [], [], "https://x/", "Oct 9–11", None, NEWSLETTER),
        combined({"Palatine": [ev("A", "2026-10-10T10:00:00")]}),
    ]
    for html in rendered:
        assert re.findall(r"<!--(?!\[if mso\])", html) == []
        assert "ROADMAP.md" not in html and "item 1" not in html.lower()
