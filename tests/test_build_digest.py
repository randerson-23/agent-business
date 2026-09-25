import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_digest  # noqa: E402

def test_get_template_env_is_a_cached_singleton():
    # A code-review pass found 8 render_* functions each building their
    # own Environment(loader=FileSystemLoader(...)) with identical
    # arguments - re-parsing every .html.j2 file on every single page
    # render. get_template_env() replaced all 8 call sites; this guards
    # the one thing that makes the fix real rather than cosmetic.
    assert build_digest.get_template_env() is build_digest.get_template_env()


REGION = {
    "id": "mount-prospect-60056",
    "name": "Mount Prospect",
    "zip": "60056",
    "state": "IL",
    "tagline": "Test region.",
    "lat": 42.0666,
    "lon": -87.9373,
}


def test_resolve_sponsor_falls_back_to_default_house_ad():
    cfg = {
        "default_house_ad": {"title": "Sponsor this spot", "detail": "", "url": ""},
        "regions": {"mount-prospect-60056": {"active": "none", "house_ad": None, "history": []}},
    }
    sponsor = build_digest.resolve_sponsor(cfg, "mount-prospect-60056")
    assert sponsor["title"] == "Sponsor this spot"
    assert sponsor["is_active_sponsor"] is False


def test_resolve_sponsor_falls_back_for_unconfigured_region():
    cfg = {"default_house_ad": {"title": "Sponsor this spot", "detail": "", "url": ""}, "regions": {}}
    sponsor = build_digest.resolve_sponsor(cfg, "some-new-region")
    assert sponsor["title"] == "Sponsor this spot"
    assert sponsor["is_active_sponsor"] is False


def test_resolve_sponsor_finds_active_entry():
    cfg = {
        "default_house_ad": {"title": "house", "detail": "", "url": ""},
        "regions": {
            "mount-prospect-60056": {
                "active": "acme-2026-09-01",
                "house_ad": None,
                "history": [{"id": "acme-2026-09-01", "title": "Acme Dentistry", "detail": "", "url": ""}],
            }
        },
    }
    sponsor = build_digest.resolve_sponsor(cfg, "mount-prospect-60056")
    assert sponsor["title"] == "Acme Dentistry"
    assert sponsor["is_active_sponsor"] is True


def test_resolve_sponsor_passes_through_optional_why_field():
    cfg = {
        "default_house_ad": {"title": "house", "detail": "", "url": ""},
        "regions": {
            "mount-prospect-60056": {
                "active": "acme-2026-09-01",
                "house_ad": None,
                "history": [
                    {
                        "id": "acme-2026-09-01",
                        "title": "Acme Dentistry",
                        "detail": "",
                        "url": "",
                        "why": "Gentle with kids, and they sponsor the Little League team.",
                    }
                ],
            }
        },
    }
    sponsor = build_digest.resolve_sponsor(cfg, "mount-prospect-60056")
    assert sponsor["why"] == "Gentle with kids, and they sponsor the Little League team."


def test_build_sponsor_availability_marks_open_region():
    cfg = {
        "default_house_ad": {"title": "Sponsor this spot", "detail": "", "url": ""},
        "regions": {"mount-prospect-60056": {"active": "none", "house_ad": None, "history": []}},
    }
    summaries = [{**REGION, "event_count": 0, "path": "mount-prospect-60056/"}]
    availability = build_digest.build_sponsor_availability(cfg, summaries)
    assert availability[0]["booked"] is False
    assert availability[0]["sponsor_title"] is None


def test_build_sponsor_availability_marks_booked_region():
    cfg = {
        "default_house_ad": {"title": "house", "detail": "", "url": ""},
        "regions": {
            "mount-prospect-60056": {
                "active": "acme-2026-09-01",
                "house_ad": None,
                "history": [{"id": "acme-2026-09-01", "title": "Acme Dentistry", "detail": "", "url": ""}],
            }
        },
    }
    summaries = [{**REGION, "event_count": 0, "path": "mount-prospect-60056/"}]
    availability = build_digest.build_sponsor_availability(cfg, summaries)
    assert availability[0]["booked"] is True
    assert availability[0]["sponsor_title"] == "Acme Dentistry"


def test_render_sponsor_page_shows_tiers_and_availability():
    availability = [
        {"region_name": "Mount Prospect", "region_url": "https://x/mount-prospect-60056/", "booked": False, "sponsor_title": None},
        {"region_name": "Arlington Heights", "region_url": "https://x/arlington-heights-60005/", "booked": True, "sponsor_title": "Acme Dentistry"},
    ]
    html = build_digest.render_sponsor_page(availability, datetime.now(timezone.utc))
    assert "Annual Partner" in html
    assert "Neighborhood Authority" in html
    assert "Open this week" in html
    assert "Sponsored by Acme Dentistry" in html
    assert "issues/new" in html


def test_build_sponsor_cta_url_falls_back_to_github_issue_when_unconfigured():
    # ROADMAP.md Phase 11 #57: never guess or invent an owner contact
    # address - fall back to the (worse, but never dead) GitHub issue.
    url = build_digest.build_sponsor_cta_url(None)
    assert url.startswith("https://github.com/randerson-23/agent-business/issues/new?")
    assert "Sponsor+inquiry" not in url and "Sponsor%20inquiry" in url


def test_build_sponsor_cta_url_prefers_mailto_when_configured():
    url = build_digest.build_sponsor_cta_url("owner@example.com")
    assert url.startswith("mailto:owner@example.com?")
    assert "subject=Sponsor%20inquiry" in url
    # mailto: (RFC 6068) needs %20 for spaces, not urlencode's default '+'
    # - a mail client's subject/body would show literal '+' characters.
    assert "+" not in url


def test_build_corrections_cta_url_falls_back_to_github_issue_when_unconfigured():
    url = build_digest.build_corrections_cta_url(None)
    assert url.startswith("https://github.com/randerson-23/agent-business/issues/new?")
    assert "title=Correction" in url


def test_build_corrections_cta_url_prefers_mailto_when_configured():
    url = build_digest.build_corrections_cta_url("owner@example.com")
    assert url.startswith("mailto:owner@example.com?")
    assert "subject=Correction" in url


def test_render_sponsor_page_uses_mailto_cta_when_contact_email_configured():
    html = build_digest.render_sponsor_page(
        [], datetime.now(timezone.utc), contact_email="owner@example.com"
    )
    assert 'href="mailto:owner@example.com?' in html
    assert "issues/new" not in html


def test_render_sponsor_page_marks_annual_partner_recommended():
    html = build_digest.render_sponsor_page([], datetime.now(timezone.utc))
    assert 'class="tier recommended"' in html
    assert "Recommended" in html


def test_render_sponsor_page_shows_stat_line_when_stats_given():
    stats = {"region_count": 4, "event_count": 12, "since": "Aug 26, 2026"}
    html = build_digest.render_sponsor_page([], datetime.now(timezone.utc), stats=stats)
    assert "4</strong> region" in html
    assert "12</strong> live update" in html
    assert "running since Aug 26, 2026" in html


def test_render_sponsor_page_omits_stat_line_when_no_stats():
    html = build_digest.render_sponsor_page([], datetime.now(timezone.utc))
    assert '<p class="stat-line">' not in html


def test_render_sponsor_page_labels_each_tier_by_what_gates_it():
    # ROADMAP.md Phase 11 #118: newsletter tiers are audience-gated, but
    # the two membership tiers are delivered by the site itself (traffic
    # and search presence), not by list size - each tier card should say
    # which one applies, matching SPONSOR_KIT.md's "Gated by" column.
    html = build_digest.render_sponsor_page([], datetime.now(timezone.utc))
    assert html.count("Gated by: Newsletter reach") == 2  # Event Promo, Weekly Spot
    assert html.count("Gated by: Site traffic &amp; search presence") == 2  # Annual Partner, Neighborhood Authority


def test_render_sponsor_page_states_the_founding_partner_rate():
    # ROADMAP.md Phase 11 #119: a finite, stated discount for the first
    # three sponsors per region, not an open-ended negotiation - the
    # live self-serve page should say exactly what SPONSOR_KIT.md does.
    html = build_digest.render_sponsor_page([], datetime.now(timezone.utc))
    assert "Founding partner rate" in html
    assert "first 3 businesses per region" in html
    assert "25% off" in html


def test_render_about_page_states_who_why_and_how():
    # ROADMAP.md Phase 11 #99: the entity-clarity content itself - who
    # publishes this, why it exists, how it's built - not just the
    # schema.org markup.
    html = build_digest.render_about_page(datetime.now(timezone.utc))
    assert "local parent" in html
    assert "Mount Prospect" in html
    assert "automatically" in html
    assert "sponsor/" in html


def test_render_about_page_embeds_the_organization_json_ld():
    html = build_digest.render_about_page(datetime.now(timezone.utc))
    assert '"@type": "Organization"' in html
    assert build_digest.ORGANIZATION_ID in html


def test_render_about_page_includes_analytics_script_when_configured():
    html = build_digest.render_about_page(
        datetime.now(timezone.utc), analytics={"configured": True, "goatcounter_code": "example"}
    )
    assert "example.goatcounter.com/count" in html


def test_render_about_page_omits_analytics_script_when_unconfigured():
    html = build_digest.render_about_page(datetime.now(timezone.utc))
    assert "goatcounter.com/count" not in html


def test_render_about_page_states_nothing_is_written_by_ai():
    # ROADMAP.md Phase 11 #131: the one claim a generic-aggregation
    # competitor can't copy, stated precisely - true that listings
    # aren't written by AI, without overclaiming that nothing here is
    # processed at all (tagging/truncation/lead-selection are real).
    html = build_digest.render_about_page(datetime.now(timezone.utc))
    assert "Nothing on this site is written by AI" in html
    assert "tags events" in html


def test_render_about_page_offers_a_corrections_path_with_mailto_cta():
    # ROADMAP.md Phase 11 #132: a stated corrections posture, with a real
    # point of contact (not a dead link either way).
    html = build_digest.render_about_page(datetime.now(timezone.utc), contact_email="owner@example.com")
    assert "corrections get made the same week" in html
    assert 'href="mailto:owner@example.com?subject=Correction' in html


def test_render_about_page_states_source_completeness_when_given():
    # ROADMAP.md item 197: a real per-build completeness figure, not
    # just the timestamp this page already shows.
    html = build_digest.render_about_page(
        datetime.now(timezone.utc), source_completeness={"reporting": 22, "expected": 25}
    )
    assert "reached 22 of 25 configured sources" in html


def test_render_about_page_omits_source_completeness_when_not_given():
    html = build_digest.render_about_page(datetime.now(timezone.utc))
    assert "configured sources" not in html


def test_format_event_date_parses_rfc822():
    assert build_digest.format_event_date("Mon, 24 Aug 2026 12:00:00 GMT") == "Aug 24"


def test_format_event_date_parses_ics_datetime():
    assert build_digest.format_event_date("20260901T100000Z") == "Sep 1"


def test_format_event_date_falls_back_to_raw_on_unparseable():
    assert build_digest.format_event_date("sometime next week") == "sometime next week"


def test_format_event_date_handles_none():
    assert build_digest.format_event_date(None) is None


def test_parse_event_date_iso_parses_rfc822():
    iso = build_digest.parse_event_date_iso("Mon, 24 Aug 2026 12:00:00 GMT")
    assert iso.startswith("2026-08-24")


def test_parse_event_date_iso_parses_ics_datetime():
    iso = build_digest.parse_event_date_iso("20260901T100000Z")
    assert iso.startswith("2026-09-01")


def test_parse_event_date_iso_returns_none_when_unparseable():
    assert build_digest.parse_event_date_iso("sometime next week") is None


def test_parse_event_date_iso_handles_none():
    assert build_digest.parse_event_date_iso(None) is None


def test_parse_event_date_iso_parses_weekday_month_day_year():
    assert build_digest.parse_event_date_iso("Sat, Sep 6, 2026").startswith("2026-09-06")


def test_parse_event_date_iso_parses_full_month_name():
    assert build_digest.parse_event_date_iso("September 6, 2026").startswith("2026-09-06")


def test_parse_event_date_iso_parses_slash_date():
    assert build_digest.parse_event_date_iso("9/6/2026").startswith("2026-09-06")


def test_format_event_date_parses_slash_date():
    assert build_digest.format_event_date("9/6/2026") == "Sep 6"


def test_parse_event_date_iso_parses_iso_date():
    # The format fetchers._nearby_date_hint extracts from calendar-grid
    # data-date="YYYY-MM-DD" attributes (e.g. AHML's Drupal calendar).
    assert build_digest.parse_event_date_iso("2026-08-15").startswith("2026-08-15")


def test_format_event_date_parses_iso_date():
    assert build_digest.format_event_date("2026-08-15") == "Aug 15"


def test_structured_date_coverage_counts_dated_and_total():
    blocks = [
        {
            "section": "A",
            "events": [
                {"title": "x", "date_iso": "2026-09-06T00:00:00"},
                {"title": "y", "date_iso": None},
                {"title": "z", "date_iso": "2026-09-07T00:00:00"},
            ],
        }
    ]
    assert build_digest.structured_date_coverage(blocks) == (2, 3)


def test_structured_date_coverage_handles_no_events():
    assert build_digest.structured_date_coverage([{"section": "A", "events": []}]) == (0, 0)


def test_truncate_short_text_unchanged():
    assert build_digest.truncate("short text") == "short text"


def test_truncate_long_text_breaks_on_word_boundary():
    text = "word " * 60
    result = build_digest.truncate(text, max_len=50)
    assert len(result) <= 51
    assert result.endswith("…")
    assert not result[:-1].endswith(" ")


def test_prepare_evergreen_uses_explicit_tags_when_present():
    region_cfg = {"evergreen": [{"title": "Library", "detail": "Books.", "url": "https://x/", "tags": ["indoor"]}]}
    result = build_digest.prepare_evergreen(region_cfg)
    assert result[0]["tags"] == ["indoor"]


def test_prepare_evergreen_infers_tags_when_absent():
    region_cfg = {"evergreen": [{"title": "Dog Park", "detail": "Off-leash area for pups.", "url": "https://x/"}]}
    result = build_digest.prepare_evergreen(region_cfg)
    assert "dog_friendly" in result[0]["tags"]


def test_prepare_guides_uses_explicit_tags_when_present():
    region_cfg = {
        "guides": [
            {
                "slug": "fall-guide",
                "title": "Fall Guide",
                "summary": "Fall stuff.",
                "items": [{"title": "Library", "detail": "Books.", "url": "https://x/", "tags": ["indoor"]}],
            }
        ]
    }
    result = build_digest.prepare_guides(region_cfg)
    assert len(result) == 1
    assert result[0]["slug"] == "fall-guide"
    assert result[0]["title"] == "Fall Guide"
    assert result[0]["items"][0]["tags"] == ["indoor"]
    assert result[0]["items"][0]["tag_badges"][0]["id"] == "indoor"


def test_prepare_guides_infers_tags_when_absent():
    region_cfg = {
        "guides": [
            {
                "slug": "fall-guide",
                "title": "Fall Guide",
                "items": [{"title": "Dog Park", "detail": "Off-leash area for pups.", "url": "https://x/"}],
            }
        ]
    }
    result = build_digest.prepare_guides(region_cfg)
    assert "dog_friendly" in result[0]["items"][0]["tags"]


def test_prepare_guides_returns_empty_list_when_no_guides_configured():
    assert build_digest.prepare_guides({}) == []


def test_build_things_to_do_items_combines_evergreen_and_guide_items():
    evergreen = [{"title": "Library", "url": "https://library/", "tags": []}]
    guides = [
        {"slug": "fall", "title": "Fall", "summary": "", "items": [{"title": "Park", "url": "https://park/", "tags": []}]}
    ]
    result = build_digest.build_things_to_do_items(evergreen, guides)
    assert [i["title"] for i in result] == ["Library", "Park"]


def test_build_things_to_do_items_dedupes_by_url_across_guides():
    # ROADMAP.md item 158: a source that appears in several guides (the
    # park district's own site, say) should show once, not once per guide.
    shared = {"title": "Park District", "url": "https://parks/", "tags": []}
    guides = [
        {"slug": "a", "title": "A", "summary": "", "items": [shared]},
        {"slug": "b", "title": "B", "summary": "", "items": [dict(shared)]},
    ]
    result = build_digest.build_things_to_do_items([], guides)
    assert len(result) == 1


def test_build_things_to_do_items_dedupes_by_title_when_url_missing():
    guides = [
        {"slug": "a", "title": "A", "summary": "", "items": [{"title": "No URL Item", "url": None, "tags": []}]},
        {"slug": "b", "title": "B", "summary": "", "items": [{"title": "No URL Item", "url": None, "tags": []}]},
    ]
    result = build_digest.build_things_to_do_items([], guides)
    assert len(result) == 1


def test_build_things_to_do_items_empty_when_nothing_configured():
    assert build_digest.build_things_to_do_items([], []) == []


def test_prepare_trick_or_treat_returns_none_when_unconfigured():
    assert build_digest.prepare_trick_or_treat({}) is None


def test_prepare_trick_or_treat_honest_when_hours_not_yet_posted():
    # ROADMAP.md Phase 11 #101: `hours: null` in region YAML - the real
    # state for every region as of this pass, since villages post in
    # late Sept/early Oct - must come back as None, never a guess.
    region_cfg = {"trick_or_treat": {"url": "https://x/news", "hours": None}}
    result = build_digest.prepare_trick_or_treat(region_cfg)
    assert result == {"url": "https://x/news", "hours": None}


def test_prepare_trick_or_treat_passes_through_real_hours_once_posted():
    region_cfg = {"trick_or_treat": {"url": "https://x/news", "hours": "3:00-7:00 PM, Saturday, October 31"}}
    result = build_digest.prepare_trick_or_treat(region_cfg)
    assert result["hours"] == "3:00-7:00 PM, Saturday, October 31"


def test_render_trick_or_treat_page_shows_not_posted_state():
    entries = [{"region_name": "Mount Prospect", "region_url": "https://x/mount-prospect-60056/", "url": "https://x/village-news", "hours": None}]
    html = build_digest.render_trick_or_treat_page(entries, datetime.now(timezone.utc))
    assert "Mount Prospect" in html
    assert "Not yet posted" in html
    assert 'href="https://x/village-news"' in html


def test_render_trick_or_treat_page_shows_real_hours_once_posted():
    entries = [
        {
            "region_name": "Mount Prospect",
            "region_url": "https://x/mount-prospect-60056/",
            "url": "https://x/village-news",
            "hours": "3:00-7:00 PM, Saturday, October 31",
        }
    ]
    html = build_digest.render_trick_or_treat_page(entries, datetime.now(timezone.utc))
    assert "3:00-7:00 PM, Saturday, October 31" in html
    assert "Not yet posted" not in html


def test_prepare_annual_events_returns_none_when_none_configured():
    assert build_digest.prepare_annual_events({}, datetime.now(timezone.utc)) is None


def test_prepare_annual_events_builds_full_event_shape():
    region_cfg = {
        "region": {"name": "Mount Prospect"},
        "annual_events": [
            {
                "title": "Oktoberfest",
                "date": "2026-09-18",
                "detail": "German food & live music.",
                "url": "https://mpdowntown.com/oktoberfest-info/",
                "tags": ["outdoor"],
            }
        ],
    }
    block = build_digest.prepare_annual_events(region_cfg, datetime.now(timezone.utc))
    assert block["section"] == "Annual Events"
    event = block["events"][0]
    assert event["title"] == "Oktoberfest"
    assert event["date"] == "Sep 18"
    assert event["date_iso"] == "2026-09-18T00:00:00"
    assert event["tags"] == ["outdoor"]
    assert event["ics_href"] is not None
    assert event["google_calendar_url"] is not None


def test_prepare_annual_events_infers_tags_when_absent():
    region_cfg = {
        "region": {"name": "Mount Prospect"},
        "annual_events": [
            {"title": "Free Fall Festival", "date": "2026-09-19", "detail": "Free family event with crafts."}
        ],
    }
    block = build_digest.prepare_annual_events(region_cfg, datetime.now(timezone.utc))
    assert "free" in block["events"][0]["tags"]


def test_prepare_annual_events_passes_through_series_when_present():
    region_cfg = {
        "region": {"name": "Mount Prospect"},
        "annual_events": [
            {
                "title": "Oktoberfest",
                "series": "Fall Fest & Oktoberfest Weekend",
                "date": "2026-09-18",
                "detail": "German food & live music.",
            }
        ],
    }
    block = build_digest.prepare_annual_events(region_cfg, datetime.now(timezone.utc))
    assert block["events"][0]["series"] == "Fall Fest & Oktoberfest Weekend"


def test_prepare_annual_events_series_is_none_when_absent():
    region_cfg = {
        "region": {"name": "Mount Prospect"},
        "annual_events": [{"title": "Standalone Event", "date": "2026-09-18", "detail": "A one-off."}],
    }
    block = build_digest.prepare_annual_events(region_cfg, datetime.now(timezone.utc))
    assert block["events"][0]["series"] is None


def test_expand_recurring_annual_event_produces_weekly_occurrences():
    # ROADMAP.md item 141: the real case that motivated it - a Sunday
    # farmers market running mid-June through mid-October.
    item = {
        "title": "Farmers Market",
        "detail": "Local produce and crafts.",
        "url": "https://x/market",
        "recurrence": {"starts": "2026-06-14", "ends": "2026-10-11", "weekday": "Sunday", "time": "07:00"},
    }
    today = date(2026, 6, 1)
    events = build_digest.expand_recurring_annual_event(item, "Mount Prospect", today)
    assert len(events) > 1
    assert all(e["title"] == "Farmers Market" for e in events)
    assert all(e["attendable"] is True for e in events)
    assert all(e["recurring"] is True for e in events)
    # Every date_iso actually falls on a Sunday at 07:00.
    for e in events:
        parsed = datetime.fromisoformat(e["date_iso"])
        assert parsed.weekday() == 6
        assert parsed.hour == 7
    assert events[0]["date_iso"] == "2026-06-14T07:00:00"
    assert events[0]["recurrence_note"] == "Every Sunday through Oct 11"


def test_expand_recurring_annual_event_bounded_to_max_recurrence_days():
    item = {
        "title": "Farmers Market",
        "url": "https://x/market",
        "recurrence": {"starts": "2026-01-01", "ends": "2026-12-31", "weekday": "Sunday"},
    }
    today = date(2026, 1, 1)
    events = build_digest.expand_recurring_annual_event(item, "Mount Prospect", today)
    last = datetime.fromisoformat(events[-1]["date_iso"]).date()
    assert (last - today).days <= build_digest.MAX_RECURRENCE_DAYS


def test_expand_recurring_annual_event_skips_occurrences_already_passed():
    # A season that started weeks before `today` shouldn't surface a
    # Sunday that's already happened - only today-or-later occurrences.
    item = {
        "title": "Farmers Market",
        "url": "https://x/market",
        "recurrence": {"starts": "2026-06-01", "ends": "2026-10-11", "weekday": "Sunday"},
    }
    today = date(2026, 9, 1)  # a Tuesday
    events = build_digest.expand_recurring_annual_event(item, "Mount Prospect", today)
    first = datetime.fromisoformat(events[0]["date_iso"]).date()
    assert first >= today


def test_expand_recurring_annual_event_defaults_to_midnight_without_time():
    item = {
        "title": "Farmers Market",
        "url": "https://x/market",
        "recurrence": {"starts": "2026-06-14", "ends": "2026-06-28", "weekday": "Sunday"},
    }
    today = date(2026, 6, 1)
    events = build_digest.expand_recurring_annual_event(item, "Mount Prospect", today)
    assert events[0]["date_iso"] == "2026-06-14T00:00:00"


def test_expand_recurring_annual_event_fails_soft_on_bad_weekday():
    item = {"title": "x", "url": "https://x/1", "recurrence": {"starts": "2026-06-14", "ends": "2026-10-11", "weekday": "Someday"}}
    assert build_digest.expand_recurring_annual_event(item, "Mount Prospect", date(2026, 6, 1)) == []


def test_expand_recurring_annual_event_fails_soft_on_bad_dates():
    item = {"title": "x", "url": "https://x/1", "recurrence": {"starts": "not-a-date", "ends": "2026-10-11", "weekday": "Sunday"}}
    assert build_digest.expand_recurring_annual_event(item, "Mount Prospect", date(2026, 6, 1)) == []


def test_expand_recurring_annual_event_returns_empty_without_recurrence_block():
    assert build_digest.expand_recurring_annual_event({"title": "x"}, "Mount Prospect", date(2026, 6, 1)) == []


def test_prepare_annual_events_uses_the_regions_local_date_not_utc():
    # A real bug found before fixing, not a theoretical one: a build
    # running Sunday night Central time is already Monday in UTC. Passing
    # a bare UTC `now` into the recurrence window made the very next
    # occurrence skip the Sunday that was, locally, still in progress -
    # jumping a full week ahead instead of showing today's market.
    region_cfg = {
        "region": {"name": "Mount Prospect", "timezone": "America/Chicago"},
        "annual_events": [
            {
                "title": "Farmers Market",
                "url": "https://x/market",
                "recurrence": {"starts": "2026-06-07", "ends": "2026-10-25", "weekday": "Sunday", "time": "08:00"},
            }
        ],
    }
    # Sept 20, 2026 is a Sunday. 22:00 Central (CDT, UTC-5) on that Sunday
    # is 03:00 UTC the following Monday - still Sunday locally.
    now_utc = datetime(2026, 9, 21, 3, 0, tzinfo=timezone.utc)
    block = build_digest.prepare_annual_events(region_cfg, now_utc)
    first = datetime.fromisoformat(block["events"][0]["date_iso"]).date()
    assert first == date(2026, 9, 20)


def test_prepare_annual_events_expands_a_recurring_entry():
    region_cfg = {
        "region": {"name": "Mount Prospect"},
        "annual_events": [
            {
                "title": "Farmers Market",
                "url": "https://x/market",
                "recurrence": {"starts": "2026-06-14", "ends": "2026-10-11", "weekday": "Sunday", "time": "07:00"},
            }
        ],
    }
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    block = build_digest.prepare_annual_events(region_cfg, now)
    assert len(block["events"]) > 1
    assert all(e["recurring"] for e in block["events"])


def test_prepare_annual_events_mixes_single_dated_and_recurring_entries():
    region_cfg = {
        "region": {"name": "Mount Prospect"},
        "annual_events": [
            {"title": "Oktoberfest", "date": "2026-09-18", "detail": "German food & live music."},
            {
                "title": "Farmers Market",
                "url": "https://x/market",
                "recurrence": {"starts": "2026-06-14", "ends": "2026-10-11", "weekday": "Sunday"},
            },
        ],
    }
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    block = build_digest.prepare_annual_events(region_cfg, now)
    titles = {e["title"] for e in block["events"]}
    assert titles == {"Oktoberfest", "Farmers Market"}
    oktoberfest = next(e for e in block["events"] if e["title"] == "Oktoberfest")
    assert oktoberfest.get("recurring") is None
    assert oktoberfest.get("recurrence_note") is None


def test_build_business_directory_empty_when_no_history():
    cfg = {"regions": {"mount-prospect-60056": {"active": "none", "house_ad": None, "history": []}}}
    assert build_digest.build_business_directory(cfg, "mount-prospect-60056") == []


def test_build_business_directory_excludes_entries_not_opted_in():
    cfg = {
        "regions": {
            "mount-prospect-60056": {
                "active": "none",
                "house_ad": None,
                "history": [{"id": "x", "title": "Acme", "detail": "", "url": ""}],
            }
        }
    }
    assert build_digest.build_business_directory(cfg, "mount-prospect-60056") == []


def test_build_business_directory_includes_opted_in_entries_with_category():
    cfg = {
        "regions": {
            "mount-prospect-60056": {
                "active": "none",
                "house_ad": None,
                "history": [
                    {
                        "id": "acme-2026-09-01",
                        "title": "Acme Dentistry",
                        "detail": "Family dentistry on Main St.",
                        "url": "https://acme.example/",
                        "category": "Dentist",
                        "directory": True,
                    }
                ],
            }
        }
    }
    result = build_digest.build_business_directory(cfg, "mount-prospect-60056")
    assert len(result) == 1
    assert result[0]["title"] == "Acme Dentistry"
    assert result[0]["detail"] == "Dentist — Family dentistry on Main St."
    assert result[0]["url"] == "https://acme.example/"


def test_load_newsletter_config_unconfigured_without_username():
    result = build_digest.load_newsletter_config({"buttondown_username": None, "headline": "Sign up"})
    assert result["configured"] is False
    assert result["buttondown_username"] == ""
    assert result["headline"] == "Sign up"


def test_load_newsletter_config_unconfigured_with_blank_username():
    result = build_digest.load_newsletter_config({"buttondown_username": "   "})
    assert result["configured"] is False


def test_load_newsletter_config_configured_with_real_username():
    result = build_digest.load_newsletter_config({"buttondown_username": "weekendplanner"})
    assert result["configured"] is True
    assert result["buttondown_username"] == "weekendplanner"


def test_load_newsletter_config_defaults_headline_and_detail():
    result = build_digest.load_newsletter_config({})
    assert result["configured"] is False
    assert result["headline"]
    assert result["detail"] == ""


def test_load_analytics_config_unconfigured_without_code():
    result = build_digest.load_analytics_config({"goatcounter_code": None})
    assert result["configured"] is False
    assert result["goatcounter_code"] == ""


def test_load_analytics_config_unconfigured_with_blank_code():
    result = build_digest.load_analytics_config({"goatcounter_code": "   "})
    assert result["configured"] is False


def test_load_analytics_config_configured_with_real_code():
    result = build_digest.load_analytics_config({"goatcounter_code": "weekendplanner"})
    assert result["configured"] is True
    assert result["goatcounter_code"] == "weekendplanner"


def test_load_analytics_config_handles_missing_key():
    result = build_digest.load_analytics_config({})
    assert result["configured"] is False
    assert result["goatcounter_code"] == ""


def test_haversine_miles_known_distance():
    # Mount Prospect (60056) to Arlington Heights (60005) village centers -
    # real-world distance is a few miles, sanity-checked against a rough
    # known value rather than pinned to floating-point precision.
    miles = build_digest._haversine_miles(42.0666, -87.9373, 42.0883, -87.9806)
    assert 2.5 < miles < 4.0


def test_haversine_miles_zero_for_same_point():
    assert build_digest._haversine_miles(42.0, -88.0, 42.0, -88.0) == 0


def test_build_region_map_returns_none_with_fewer_than_two_regions():
    assert build_digest.build_region_map([]) is None
    assert build_digest.build_region_map([{"name": "A", "lat": 42.0, "lon": -88.0, "path": "a/"}]) is None


def test_build_region_map_returns_none_when_coordinates_missing():
    summaries = [
        {"name": "A", "lat": 42.0, "lon": -88.0, "path": "a/"},
        {"name": "B", "lat": None, "lon": None, "path": "b/"},
    ]
    assert build_digest.build_region_map(summaries) is None


def test_build_region_map_produces_a_pin_per_region_and_one_line():
    summaries = [
        {"name": "Mount Prospect", "lat": 42.0666, "lon": -87.9373, "path": "mount-prospect-60056/"},
        {"name": "Arlington Heights", "lat": 42.0883, "lon": -87.9806, "path": "arlington-heights-60005/"},
    ]
    result = build_digest.build_region_map(summaries)
    assert result is not None
    assert len(result["pins"]) == 2
    assert len(result["lines"]) == 1
    names = {p["name"] for p in result["pins"]}
    assert names == {"Mount Prospect", "Arlington Heights"}
    assert result["lines"][0]["miles"] > 0
    for pin in result["pins"]:
        assert 0 <= pin["x"] <= result["width"]
        assert 0 <= pin["y"] <= result["height"]


def test_build_region_map_handles_identical_coordinates_without_crashing():
    summaries = [
        {"name": "A", "lat": 42.0, "lon": -88.0, "path": "a/"},
        {"name": "B", "lat": 42.0, "lon": -88.0, "path": "b/"},
    ]
    result = build_digest.build_region_map(summaries)
    assert result is not None
    assert len(result["pins"]) == 2


def test_build_nearby_regions_sorts_nearest_first_and_excludes_self():
    current = {"id": "mount-prospect-60056", "lat": 42.0666, "lon": -87.9373}
    all_regions = [
        current,
        {"id": "arlington-heights-60005", "name": "Arlington Heights", "lat": 42.0883, "lon": -87.9806},
        {"id": "des-plaines-60016", "name": "Des Plaines", "lat": 42.0334, "lon": -87.8834},
        {"id": "palatine-60067", "name": "Palatine", "lat": 42.1103, "lon": -88.0342},
    ]
    result = build_digest.build_nearby_regions(current, all_regions)
    assert [r["name"] for r in result] == ["Arlington Heights", "Des Plaines", "Palatine"]
    assert all(r["miles"] > 0 for r in result)
    assert result[0]["path"] == "arlington-heights-60005/"


def test_build_nearby_regions_respects_limit():
    current = {"id": "a", "lat": 42.0, "lon": -88.0}
    all_regions = [current] + [
        {"id": str(i), "name": f"Region {i}", "lat": 42.0 + i * 0.01, "lon": -88.0} for i in range(5)
    ]
    result = build_digest.build_nearby_regions(current, all_regions, limit=2)
    assert len(result) == 2


def test_build_nearby_regions_returns_empty_with_fewer_than_two_regions():
    current = {"id": "a", "lat": 42.0, "lon": -88.0}
    assert build_digest.build_nearby_regions(current, [current]) == []


def test_build_nearby_regions_returns_empty_when_current_missing_coordinates():
    current = {"id": "a", "lat": None, "lon": None}
    all_regions = [current, {"id": "b", "name": "B", "lat": 42.0, "lon": -88.0}]
    assert build_digest.build_nearby_regions(current, all_regions) == []


def test_build_nearby_regions_skips_others_missing_coordinates():
    current = {"id": "a", "lat": 42.0, "lon": -88.0}
    all_regions = [
        current,
        {"id": "b", "name": "B", "lat": None, "lon": None},
        {"id": "c", "name": "C", "lat": 42.01, "lon": -88.0},
    ]
    result = build_digest.build_nearby_regions(current, all_regions)
    assert [r["name"] for r in result] == ["C"]


def test_select_editors_pick_returns_none_with_no_candidates():
    region_cfg = {"region": {"id": "x"}}
    assert build_digest.select_editors_pick(region_cfg, [], []) is None


def test_select_editors_pick_prefers_soonest_dated_item():
    region_cfg = {"region": {"id": "x"}}
    blocks = [
        {
            "section": "Events",
            "events": [
                {"title": "Later Event", "url": "https://x/later", "date_iso": "2026-09-10T10:00:00", "tags": []},
                {"title": "Sooner Event", "url": "https://x/sooner", "date_iso": "2026-08-29T10:00:00", "tags": []},
            ],
        }
    ]
    pick = build_digest.select_editors_pick(region_cfg, blocks, [])
    assert pick["title"] == "Sooner Event"


def test_select_editors_pick_dated_beats_evergreen():
    region_cfg = {"region": {"id": "x"}}
    blocks = [{"section": "Events", "events": [{"title": "Dated Event", "url": "https://x/dated", "date_iso": "2026-08-29T10:00:00", "tags": []}]}]
    evergreen = [{"title": "Library", "url": "https://x/library", "tags": []}]
    pick = build_digest.select_editors_pick(region_cfg, blocks, evergreen)
    assert pick["title"] == "Dated Event"


def test_select_editors_pick_breaks_ties_with_free_and_kid_friendly():
    region_cfg = {"region": {"id": "x"}}
    blocks = [
        {
            "section": "Events",
            "events": [
                {"title": "Plain", "url": "https://x/plain", "date_iso": "2026-08-29T10:00:00", "tags": []},
                {"title": "Free + Kid", "url": "https://x/free-kid", "date_iso": "2026-08-29T10:00:00", "tags": ["free", "kid_friendly"]},
            ],
        }
    ]
    pick = build_digest.select_editors_pick(region_cfg, blocks, [])
    assert pick["title"] == "Free + Kid"


def test_select_editors_pick_honors_override_url():
    region_cfg = {"region": {"id": "x", "editors_pick_url": "https://x/library"}}
    blocks = [{"section": "Events", "events": [{"title": "Dated Event", "url": "https://x/dated", "date_iso": "2026-08-29T10:00:00", "tags": []}]}]
    evergreen = [{"title": "Library", "url": "https://x/library", "tags": []}]
    pick = build_digest.select_editors_pick(region_cfg, blocks, evergreen)
    assert pick["title"] == "Library"


def test_select_editors_pick_falls_back_when_override_url_not_found():
    region_cfg = {"region": {"id": "x", "editors_pick_url": "https://x/nonexistent"}}
    blocks = [{"section": "Events", "events": [{"title": "Dated Event", "url": "https://x/dated", "date_iso": "2026-08-29T10:00:00", "tags": []}]}]
    pick = build_digest.select_editors_pick(region_cfg, blocks, [])
    assert pick["title"] == "Dated Event"


def test_select_editors_pick_skips_a_recurring_event_even_when_soonest():
    # ROADMAP.md item 141: the soonest-dated tiebreak would otherwise pick
    # the same standing weekly market every build for its whole season -
    # the same "reads as automated filler" risk item 141 raised for the
    # subject line, applied to this page's other headline slot.
    region_cfg = {"region": {"id": "x"}}
    blocks = [
        {
            "section": "Events",
            "events": [
                {"title": "Farmers Market", "url": "https://x/market", "date_iso": "2026-08-29T10:00:00", "tags": [], "recurring": True},
                {"title": "Later Real Event", "url": "https://x/later", "date_iso": "2026-09-10T10:00:00", "tags": []},
            ],
        }
    ]
    pick = build_digest.select_editors_pick(region_cfg, blocks, [])
    assert pick["title"] == "Later Real Event"


def test_select_editors_pick_falls_back_to_recurring_when_nothing_else_exists():
    # A recurring event is still real content - excluded from the
    # automatic heuristic, not deleted from the page entirely.
    region_cfg = {"region": {"id": "x"}}
    blocks = [
        {
            "section": "Events",
            "events": [
                {"title": "Farmers Market", "url": "https://x/market", "date_iso": "2026-08-29T10:00:00", "tags": [], "recurring": True},
            ],
        }
    ]
    pick = build_digest.select_editors_pick(region_cfg, blocks, [])
    assert pick["title"] == "Farmers Market"


def test_select_editors_pick_override_can_still_target_a_recurring_event():
    region_cfg = {"region": {"id": "x", "editors_pick_url": "https://x/market"}}
    blocks = [
        {
            "section": "Events",
            "events": [
                {"title": "Farmers Market", "url": "https://x/market", "date_iso": "2026-08-29T10:00:00", "tags": [], "recurring": True},
            ],
        }
    ]
    pick = build_digest.select_editors_pick(region_cfg, blocks, [])
    assert pick["title"] == "Farmers Market"


def test_select_editors_pick_ignores_items_missing_title_or_url():
    region_cfg = {"region": {"id": "x"}}
    blocks = [{"section": "Events", "events": [{"title": "", "url": "https://x/a", "tags": []}, {"title": "No URL", "url": "", "tags": []}]}]
    assert build_digest.select_editors_pick(region_cfg, blocks, []) is None


def test_build_weekend_weather_returns_empty_without_coordinates():
    region = {"name": "Nowhere", "timezone": "America/Chicago"}
    result = build_digest.build_weekend_weather(region, date(2026, 8, 28), date(2026, 8, 29), date(2026, 8, 30))
    assert result == []


@patch("build_digest.fetch_weather")
def test_build_weekend_weather_matches_by_date_not_position(mock_fetch):
    # Response includes extra/unrelated days before the target weekend -
    # matching must key off the date string, not list position.
    mock_fetch.return_value = [
        {"date": "2026-08-27", "high_f": 90, "low_f": 70, "precip_percent": 0, "label": "Clear sky", "emoji": "☀️", "is_precip": False},
        {"date": "2026-08-28", "high_f": 84, "low_f": 68, "precip_percent": 5, "label": "Clear sky", "emoji": "☀️", "is_precip": False},
        {"date": "2026-08-29", "high_f": 81, "low_f": 65, "precip_percent": 10, "label": "Mostly clear", "emoji": "🌤️", "is_precip": False},
        {"date": "2026-08-30", "high_f": 76, "low_f": 61, "precip_percent": 70, "label": "Light rain", "emoji": "🌦️", "is_precip": True},
    ]
    region = {"lat": 42.0666, "lon": -87.9373, "timezone": "America/Chicago"}
    result = build_digest.build_weekend_weather(region, date(2026, 8, 28), date(2026, 8, 29), date(2026, 8, 30))
    assert len(result) == 3
    assert result[0]["day_name"] == "Friday"
    assert result[0]["high_f"] == 84
    assert result[1]["day_name"] == "Saturday"
    assert result[1]["high_f"] == 81
    assert result[2]["day_name"] == "Sunday"
    assert result[2]["is_precip"] is True


@patch("build_digest.fetch_weather")
def test_build_weekend_weather_omits_days_missing_from_forecast(mock_fetch):
    mock_fetch.return_value = [
        {"date": "2026-08-29", "high_f": 81, "low_f": 65, "precip_percent": 10, "label": "Mostly clear", "emoji": "🌤️", "is_precip": False},
    ]
    region = {"lat": 42.0666, "lon": -87.9373, "timezone": "America/Chicago"}
    result = build_digest.build_weekend_weather(region, date(2026, 8, 28), date(2026, 8, 29), date(2026, 8, 30))
    assert len(result) == 1
    assert result[0]["day_name"] == "Saturday"


def test_build_ics_data_uri_returns_none_without_date():
    assert build_digest.build_ics_data_uri({"title": "x", "date_iso": None}) is None


def test_build_ics_data_uri_contains_essential_fields():
    from urllib.parse import unquote

    event = {"title": "Fishing Derby", "detail": "Bring your gear.", "url": "https://x/1", "date_iso": "2026-09-19T10:00:00"}
    uri = build_digest.build_ics_data_uri(event)
    assert uri.startswith("data:text/calendar;charset=utf-8,")
    decoded = unquote(uri.split(",", 1)[1])
    assert "BEGIN:VEVENT" in decoded
    assert "SUMMARY:Fishing Derby" in decoded
    assert "DTSTART:20260919T100000" in decoded
    assert "DTEND:20260919T110000" in decoded
    assert "URL:https://x/1" in decoded


def test_build_ics_data_uri_escapes_commas_and_newlines():
    from urllib.parse import unquote

    event = {"title": "Ages 5, up\nBring water", "detail": "", "url": "", "date_iso": "2026-09-19T10:00:00"}
    uri = build_digest.build_ics_data_uri(event)
    decoded = unquote(uri.split(",", 1)[1])
    assert "SUMMARY:Ages 5\\, up\\nBring water" in decoded


def test_build_ics_data_uri_escapes_bare_carriage_returns():
    # A raw \r (not paired with \n) is plausible from an RSS/HTML source
    # - unlike fetch_ics's own parsing, those never run the value through
    # a line-splitting pass. Left unescaped, it would embed a real line
    # break into the SUMMARY value: many real-world calendar parsers
    # treat a bare CR as leniently as CRLF, letting the fetched title
    # inject what reads as extra ICS properties into the same VEVENT.
    from urllib.parse import unquote

    event = {
        "title": "Fake Event\rDTSTART:20260101T000000Z\rSUMMARY:Injected",
        "detail": "",
        "url": "",
        "date_iso": "2026-09-19T10:00:00",
    }
    uri = build_digest.build_ics_data_uri(event)
    decoded = unquote(uri.split(",", 1)[1])
    summary_line = next(line for line in decoded.split("\r\n") if line.startswith("SUMMARY:"))
    assert "\r" not in summary_line
    assert summary_line == "SUMMARY:Fake Event\\nDTSTART:20260101T000000Z\\nSUMMARY:Injected"


def test_build_ics_data_uri_strips_bare_carriage_returns_from_url():
    # The same bare-CR injection as the title test above, one more
    # unfixed instance (ROADMAP.md item 136): event['url'] is a real,
    # fetched RSS <link>/HTML href/ICS URL: value that never went through
    # _ics_escape() (it's a URI-typed field, not TEXT) - but a raw CR/LF
    # in it still corrupts the .ics line structure just like an
    # unescaped one in SUMMARY does. Confirmed with a real crafted URL
    # before fixing it, not assumed.
    from urllib.parse import unquote

    event = {
        "title": "Real-looking Event",
        "detail": "",
        "url": "https://evil.example/x\rDTSTART:20260101T000000Z\rSUMMARY:Injected",
        "date_iso": "2026-09-19T10:00:00",
    }
    uri = build_digest.build_ics_data_uri(event)
    decoded = unquote(uri.split(",", 1)[1])
    url_line = next(line for line in decoded.split("\r\n") if line.startswith("URL:"))
    assert "\r" not in url_line
    assert url_line == "URL:https://evil.example/xDTSTART:20260101T000000ZSUMMARY:Injected"


def test_build_google_calendar_url_returns_none_without_date():
    assert build_digest.build_google_calendar_url({"title": "x", "date_iso": None}, "Mount Prospect") is None


def test_build_region_calendar_ics_contains_calendar_headers():
    # ROADMAP.md Phase 11 #100: the subscribe-specific properties a
    # one-time per-event download never needed.
    region = {"id": "mount-prospect-60056", "name": "Mount Prospect"}
    ics = build_digest.build_region_calendar_ics(region, [], datetime.now(timezone.utc))
    assert ics.startswith("BEGIN:VCALENDAR\r\n")
    assert "X-WR-CALNAME:Within Ten — Mount Prospect" in ics
    assert "REFRESH-INTERVAL;VALUE=DURATION:PT12H" in ics
    assert "X-PUBLISHED-TTL:PT12H" in ics
    assert ics.endswith("END:VCALENDAR\r\n")


def test_build_region_calendar_ics_includes_dated_events_across_blocks():
    region = {"id": "mount-prospect-60056", "name": "Mount Prospect"}
    blocks = [
        {"section": "Library", "events": [{"title": "Story Time", "detail": "Books.", "url": "https://x/1", "date_iso": "2026-09-19T10:00:00", "attendable": True}]},
        {"section": "Park District", "events": [{"title": "Fishing Derby", "url": "https://x/2", "date_iso": "2026-09-20T09:00:00", "attendable": True}]},
    ]
    ics = build_digest.build_region_calendar_ics(region, blocks, datetime.now(timezone.utc))
    assert ics.count("BEGIN:VEVENT") == 2
    assert "SUMMARY:Story Time" in ics
    assert "SUMMARY:Fishing Derby" in ics
    assert "DTSTART:20260919T100000" in ics


def test_build_region_calendar_ics_omits_undated_events():
    region = {"id": "mount-prospect-60056", "name": "Mount Prospect"}
    blocks = [{"section": "Library", "events": [{"title": "Story Time", "url": "https://x/1", "date_iso": None}]}]
    ics = build_digest.build_region_calendar_ics(region, blocks, datetime.now(timezone.utc))
    assert "BEGIN:VEVENT" not in ics


def test_build_region_calendar_ics_strips_bare_carriage_returns_from_url():
    # Same real gap as test_build_ics_data_uri_strips_bare_carriage_returns_from_url
    # (ROADMAP.md item 136), for the subscribable region feed - a public,
    # continuously-refreshed .ics a real calendar app subscribes to, so
    # this instance is reachable without anyone ever clicking a card.
    region = {"id": "mount-prospect-60056", "name": "Mount Prospect"}
    blocks = [
        {
            "section": "Library",
            "events": [
                {
                    "title": "Real-looking Event",
                    "url": "https://evil.example/x\rDTSTART:20260101T000000Z\rSUMMARY:Injected",
                    "date_iso": "2026-09-19T10:00:00",
                    "attendable": True,
                }
            ],
        }
    ]
    ics = build_digest.build_region_calendar_ics(region, blocks, datetime.now(timezone.utc))
    url_line = next(line for line in ics.split("\r\n") if line.startswith("URL:"))
    assert "\r" not in url_line
    assert url_line == "URL:https://evil.example/xDTSTART:20260101T000000ZSUMMARY:Injected"


def test_build_region_calendar_ics_stable_uid_across_rebuilds():
    # Same event, two different build timestamps (as a rebuild would
    # produce) - the UID must not change, or a subscriber's calendar
    # sees a duplicate every time the site rebuilds instead of an update.
    region = {"id": "mount-prospect-60056", "name": "Mount Prospect"}
    blocks = [{"section": "Library", "events": [{"title": "Story Time", "url": "https://x/1", "date_iso": "2026-09-19T10:00:00"}]}]
    ics_a = build_digest.build_region_calendar_ics(region, blocks, datetime(2026, 9, 17, tzinfo=timezone.utc))
    ics_b = build_digest.build_region_calendar_ics(region, blocks, datetime(2026, 9, 18, tzinfo=timezone.utc))
    uid_a = next(line for line in ics_a.split("\r\n") if line.startswith("UID:"))
    uid_b = next(line for line in ics_b.split("\r\n") if line.startswith("UID:"))
    assert uid_a == uid_b


def test_build_region_calendar_ics_never_emits_organizer_attendee_or_x_properties():
    # ROADMAP.md Phase 11 #115: even if a future change to the event
    # dict's shape started carrying extra fields (organizer, attendee,
    # location, or an x_* key), this function must not become a
    # passthrough for them - it only emits the fields it's explicitly
    # coded to. This is the second half of the same guard as
    # fetchers.py's test_fetch_ics_never_captures_organizer_attendee_or_x_properties,
    # which checks that those fields never even reach this function's
    # input in the first place.
    region = {"id": "mount-prospect-60056", "name": "Mount Prospect"}
    blocks = [
        {
            "section": "Library",
            "events": [
                {
                    "title": "Storytime",
                    "detail": "Family storytime.",
                    "url": "https://x/1",
                    "date_iso": "2026-09-19T10:00:00",
                    "attendable": True,
                    "organizer": "Jane Doe <jane@example.org>",
                    "attendee": "John Smith <john@example.org>",
                    "location": "Room 204B, private staff entrance",
                    "x_internal_notes": "Confidential setup instructions",
                }
            ],
        }
    ]
    ics = build_digest.build_region_calendar_ics(region, blocks, datetime.now(timezone.utc))
    assert "ORGANIZER" not in ics
    assert "ATTENDEE" not in ics
    assert "LOCATION" not in ics
    assert "X-INTERNAL" not in ics
    assert "Jane Doe" not in ics
    assert "private staff entrance" not in ics
    assert "Confidential" not in ics


def test_build_region_calendar_ics_non_attendable_event_is_transparent_all_day():
    # ROADMAP.md Phase 11 #90 applied to #100: a school half-day belongs
    # in the feed, but as a transparent all-day entry, not a timed one
    # a calendar app would show as "busy" for.
    region = {"id": "mount-prospect-60056", "name": "Mount Prospect"}
    blocks = [
        {
            "section": "School",
            "events": [
                {"title": "Half-Day Student Attendance", "url": "https://x/1", "date_iso": "2026-09-19T00:00:00", "attendable": False}
            ],
        }
    ]
    ics = build_digest.build_region_calendar_ics(region, blocks, datetime.now(timezone.utc))
    assert "DTSTART;VALUE=DATE:20260919" in ics
    assert "TRANSP:TRANSPARENT" in ics
    assert "DTSTART:20260919T" not in ics


def test_build_llms_txt_lists_each_regions_calendar():
    summaries = [{"name": "Mount Prospect", "zip": "60056", "tagline": "x", "path": "mount-prospect-60056/", "guides": []}]
    result = build_digest.build_llms_txt(summaries)
    assert f"[Mount Prospect — subscribable calendar (.ics)]({build_digest.SITE_BASE_URL}mount-prospect-60056/calendar.ics)" in result


def test_build_llms_txt_trick_or_treat_line_counts_actual_regions():
    # ROADMAP.md item 170: "all four towns" was hardcoded and already
    # wrong once a fifth region (item 166) shipped.
    summaries = [
        {"name": "Mount Prospect", "zip": "60056", "tagline": "x", "path": "mount-prospect-60056/", "guides": []},
        {"name": "Wheeling", "zip": "60090", "tagline": "x", "path": "wheeling-60090/", "guides": []},
    ]
    result = build_digest.build_llms_txt(summaries)
    assert "all 2 towns" in result
    assert "all four towns" not in result


def test_build_google_calendar_url_has_expected_params():
    event = {"title": "Fishing Derby", "detail": "Bring gear", "date_iso": "2026-09-19T10:00:00"}
    url = build_digest.build_google_calendar_url(event, "Mount Prospect")
    assert url.startswith("https://www.google.com/calendar/render?")
    assert "action=TEMPLATE" in url
    assert "dates=20260919T100000%2F20260919T110000" in url
    assert "location=Mount+Prospect" in url


def test_fetch_region_sections_attaches_calendar_links(monkeypatch):
    def fake_fetcher(url, **kwargs):
        return [{"title": "Fishing Derby", "detail": "x", "url": "https://x/1", "date": "20990901T100000Z"}]

    monkeypatch.setitem(build_digest.FETCHERS, "ics", fake_fetcher)
    region_cfg = {
        "region": REGION,
        "sources": [{"name": "Park", "type": "ics", "url": "https://x/cal.ics", "section": "Events", "enabled": True}],
    }
    blocks = build_digest.fetch_region_sections(region_cfg)
    event = blocks[0]["events"][0]
    assert event["ics_href"].startswith("data:text/calendar")
    assert "location=Mount+Prospect" in event["google_calendar_url"]


def test_fetch_region_sections_marks_a_school_half_day_not_attendable(monkeypatch):
    # ROADMAP.md Phase 11 #90: the real title from the D57 feed that
    # shipped as a subject-line headline before this fix.
    def fake_fetcher(url, **kwargs):
        return [{"title": "Half-Day Student Attendance (Grades 1-8)", "detail": "", "url": "https://x/1", "date": None}]

    monkeypatch.setitem(build_digest.FETCHERS, "ics", fake_fetcher)
    region_cfg = {
        "region": REGION,
        "sources": [{"name": "D57", "type": "ics", "url": "https://x/cal.ics", "section": "School", "enabled": True}],
    }
    event = build_digest.fetch_region_sections(region_cfg)[0]["events"][0]
    assert event["attendable"] is False


def test_fetch_region_sections_a_real_event_is_attendable(monkeypatch):
    def fake_fetcher(url, **kwargs):
        return [{"title": "Fishing Derby", "detail": "x", "url": "https://x/1", "date": None}]

    monkeypatch.setitem(build_digest.FETCHERS, "ics", fake_fetcher)
    region_cfg = {
        "region": REGION,
        "sources": [{"name": "Park", "type": "ics", "url": "https://x/cal.ics", "section": "Events", "enabled": True}],
    }
    event = build_digest.fetch_region_sections(region_cfg)[0]["events"][0]
    assert event["attendable"] is True


def test_fetch_region_sections_source_level_informational_override(monkeypatch):
    # A source config's `informational: true` (for a feed like D57's
    # that's mostly closures/half-days) forces every item non-attendable
    # regardless of wording - even a title with no matching keyword.
    def fake_fetcher(url, **kwargs):
        return [{"title": "District Calendar Update", "detail": "", "url": "https://x/1", "date": None}]

    monkeypatch.setitem(build_digest.FETCHERS, "ics", fake_fetcher)
    region_cfg = {
        "region": REGION,
        "sources": [
            {
                "name": "D57",
                "type": "ics",
                "url": "https://x/cal.ics",
                "section": "School",
                "enabled": True,
                "informational": True,
            }
        ],
    }
    event = build_digest.fetch_region_sections(region_cfg)[0]["events"][0]
    assert event["attendable"] is False


def test_fetch_region_sections_records_source_health(monkeypatch):
    def fake_fetcher(url, **kwargs):
        return [{"title": "A", "detail": "x", "url": "https://x/1", "date": None}]

    monkeypatch.setitem(build_digest.FETCHERS, "ics", fake_fetcher)
    region_cfg = {
        "region": REGION,
        "sources": [{"name": "Park", "type": "ics", "url": "https://x/cal.ics", "section": "Events", "enabled": True}],
    }
    health = {}
    build_digest.fetch_region_sections(region_cfg, health=health)
    assert health["mount-prospect-60056:Park"] == [1]


def test_fetch_region_sections_counts_completeness_on_success(monkeypatch):
    # ROADMAP.md item 197: a successful fetch counts toward both the
    # numerator (reporting) and denominator (expected).
    def fake_fetcher(url, **kwargs):
        return [{"title": "A", "detail": "x", "url": "https://x/1", "date": None}]

    monkeypatch.setitem(build_digest.FETCHERS, "ics", fake_fetcher)
    region_cfg = {
        "region": REGION,
        "sources": [{"name": "Park", "type": "ics", "url": "https://x/cal.ics", "section": "Events", "enabled": True}],
    }
    completeness = {"expected": 0, "reporting": 0}
    build_digest.fetch_region_sections(region_cfg, completeness=completeness)
    assert completeness == {"expected": 1, "reporting": 1}


def test_fetch_region_sections_counts_expected_but_not_reporting_on_transport_failure(monkeypatch):
    def fake_fetcher(url, **kwargs):
        return None

    monkeypatch.setitem(build_digest.FETCHERS, "ics", fake_fetcher)
    region_cfg = {
        "region": REGION,
        "sources": [{"name": "Park", "type": "ics", "url": "https://x/cal.ics", "section": "Events", "enabled": True}],
    }
    completeness = {"expected": 0, "reporting": 0}
    build_digest.fetch_region_sections(region_cfg, completeness=completeness)
    assert completeness == {"expected": 1, "reporting": 0}


def test_fetch_region_sections_skips_health_recording_on_transport_failure(monkeypatch):
    # ROADMAP.md Phase 11 #55: a fetcher returning None (a real transport
    # failure - 403, timeout, connection reset) must not be recorded as a
    # 0 in source health, since that's indistinguishable from a source
    # that actually died and would produce a false regression alert the
    # next time it succeeds. Seed history with a real prior success so a
    # skip (not a 0) is the only way this test can pass.
    def fake_fetcher(url, **kwargs):
        return None

    monkeypatch.setitem(build_digest.FETCHERS, "ics", fake_fetcher)
    region_cfg = {
        "region": REGION,
        "sources": [{"name": "Park", "type": "ics", "url": "https://x/cal.ics", "section": "Events", "enabled": True}],
    }
    health = {"mount-prospect-60056:Park": [6, 6]}
    blocks = build_digest.fetch_region_sections(region_cfg, health=health)
    assert health["mount-prospect-60056:Park"] == [6, 6]
    assert blocks[0]["events"] == []


def test_update_source_health_appends_and_caps_history():
    health = {}
    for count in range(build_digest.SOURCE_HEALTH_HISTORY_LEN + 3):
        build_digest.update_source_health(health, "region:Source", count)
    history = health["region:Source"]
    assert len(history) == build_digest.SOURCE_HEALTH_HISTORY_LEN
    # Oldest entries dropped, most recent kept.
    assert history[-1] == build_digest.SOURCE_HEALTH_HISTORY_LEN + 2


def test_detect_source_regressions_flags_a_source_that_died():
    health = {"region:Library": [6, 6, 5, 6, 0]}
    assert build_digest.detect_source_regressions(health) == ["region:Library"]


def test_detect_source_regressions_ignores_a_source_that_always_returns_zero():
    # An unconfirmed/blocked source (e.g. a 403) legitimately stays at 0 -
    # its own trailing median is 0, so a current 0 is not a regression.
    health = {"region:UnconfirmedSource": [0, 0, 0, 0]}
    assert build_digest.detect_source_regressions(health) == []


def test_detect_source_regressions_ignores_a_source_with_too_little_history():
    health = {"region:NewSource": [0]}
    assert build_digest.detect_source_regressions(health) == []


def test_detect_source_regressions_ignores_a_source_still_returning_events():
    health = {"region:Healthy": [5, 6, 4, 5, 5]}
    assert build_digest.detect_source_regressions(health) == []


def test_detect_truncated_sources_flags_a_source_pinned_at_the_cap():
    # ROADMAP.md item 180 (forty-second research pass): a source landing
    # on exactly the cap three builds running is almost certainly being
    # cut off, not coincidentally exhausted at the same number every time
    # - the diagnostic that would have surfaced item 178 directly.
    health = {"region:Truncated": [6, 6, 6]}
    assert build_digest.detect_truncated_sources(health, cap=6) == ["region:Truncated"]


def test_detect_truncated_sources_ignores_a_source_below_the_cap():
    health = {"region:Healthy": [4, 5, 4]}
    assert build_digest.detect_truncated_sources(health, cap=6) == []


def test_detect_truncated_sources_ignores_one_coincidental_hit_at_the_cap():
    health = {"region:Coincidence": [4, 5, 6]}
    assert build_digest.detect_truncated_sources(health, cap=6) == []


def test_detect_newly_broken_sources_flags_the_third_consecutive_zero():
    health = {"region:JustDied": [6, 5, 0, 0, 0]}
    assert build_digest.detect_newly_broken_sources(health) == ["region:JustDied"]


def test_detect_newly_broken_sources_does_not_re_flag_a_source_already_dead():
    # A source that died weeks ago and has since fully aged into an
    # all-zero history (the four known Mount Prospect village sources,
    # items 161/179) should not re-trigger this every single build -
    # only the transition build, where the 4th-from-last entry was still
    # nonzero, does.
    health = {"region:LongDead": [0, 0, 0, 0, 0, 0]}
    assert build_digest.detect_newly_broken_sources(health) == []


def test_detect_newly_broken_sources_ignores_a_source_with_too_little_history():
    health = {"region:NewSource": [0, 0, 0]}
    assert build_digest.detect_newly_broken_sources(health) == []


def test_save_and_load_source_health_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(build_digest, "SOURCE_HEALTH_PATH", tmp_path / "source_health.json")
    health = {"region:Source": [1, 2, 3]}
    build_digest.save_source_health(health)
    assert build_digest.load_source_health() == health


def test_load_source_health_returns_empty_dict_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(build_digest, "SOURCE_HEALTH_PATH", tmp_path / "does-not-exist.json")
    assert build_digest.load_source_health() == {}


def test_load_source_health_returns_empty_dict_on_corrupt_json(tmp_path, monkeypatch):
    path = tmp_path / "source_health.json"
    path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(build_digest, "SOURCE_HEALTH_PATH", path)
    assert build_digest.load_source_health() == {}


def test_update_transport_failures_increments_on_failure():
    failures = {}
    build_digest.update_transport_failures(failures, "region:Source", transport_failed=True)
    build_digest.update_transport_failures(failures, "region:Source", transport_failed=True)
    assert failures["region:Source"] == 2


def test_update_transport_failures_resets_on_success():
    failures = {"region:Source": 5}
    build_digest.update_transport_failures(failures, "region:Source", transport_failed=False)
    assert failures["region:Source"] == 0


def test_detect_chronic_transport_failures_flags_at_threshold():
    failures = {"region:Dead": 3, "region:Fine": 1}
    assert build_digest.detect_chronic_transport_failures(failures, threshold=3) == ["region:Dead"]


def test_detect_chronic_transport_failures_ignores_below_threshold():
    failures = {"region:Blip": 2}
    assert build_digest.detect_chronic_transport_failures(failures, threshold=3) == []


def test_save_and_load_transport_failures_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(build_digest, "TRANSPORT_FAILURE_PATH", tmp_path / "transport_failures.json")
    failures = {"region:Source": 4}
    build_digest.save_transport_failures(failures)
    assert build_digest.load_transport_failures() == failures


def test_load_transport_failures_returns_empty_dict_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(build_digest, "TRANSPORT_FAILURE_PATH", tmp_path / "does-not-exist.json")
    assert build_digest.load_transport_failures() == {}


def test_update_transport_failure_details_records_a_failure():
    # ROADMAP.md item 185: "403 on every request" and "DNS does not
    # resolve" used to record identically - this is the detail that
    # tells them apart.
    details = {}
    build_digest.update_transport_failure_details(
        details, "region:Source", {"exception_class": "HTTPError", "status_code": 403}
    )
    assert details["region:Source"] == {"exception_class": "HTTPError", "status_code": 403}


def test_update_transport_failure_details_clears_on_success():
    # A source that recovers shouldn't keep showing a stale "last failed
    # with a 403" next to a health count that's currently fine.
    details = {"region:Source": {"exception_class": "HTTPError", "status_code": 403}}
    build_digest.update_transport_failure_details(details, "region:Source", {})
    assert "region:Source" not in details


def test_save_and_load_transport_failure_details_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(build_digest, "TRANSPORT_FAILURE_DETAIL_PATH", tmp_path / "details.json")
    details = {"region:Source": {"exception_class": "ConnectionError", "status_code": None}}
    build_digest.save_transport_failure_details(details)
    assert build_digest.load_transport_failure_details() == details


def test_load_transport_failure_details_returns_empty_dict_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(build_digest, "TRANSPORT_FAILURE_DETAIL_PATH", tmp_path / "missing.json")
    assert build_digest.load_transport_failure_details() == {}


def test_fetch_region_sections_records_failure_detail_on_transport_failure(monkeypatch):
    # End-to-end through fetch_region_sections rather than just the
    # helper - confirms the wiring, not just the pieces in isolation.
    region_cfg = {
        "region": {"id": "test-region", "name": "Test Region"},
        "sources": [
            {
                "name": "Flaky Source", "type": "html_events", "enabled": True,
                "url": "https://example.org", "section": "Test Section",
            }
        ],
    }

    def fake_fetch_html_events(url, **kwargs):
        kwargs["failure_info"]["exception_class"] = "HTTPError"
        kwargs["failure_info"]["status_code"] = 403
        return None

    monkeypatch.setitem(build_digest.FETCHERS, "html_events", fake_fetch_html_events)
    details: dict = {}
    build_digest.fetch_region_sections(region_cfg, transport_failure_details=details)
    assert details["test-region:Flaky Source"] == {"exception_class": "HTTPError", "status_code": 403}


def test_expected_source_keys_includes_only_enabled_sources():
    regions = [
        {
            "region": {"id": "mount-prospect-60056"},
            "sources": [
                {"name": "Village News", "enabled": True},
                {"name": "Disabled Source", "enabled": False},
                {"name": "Default Enabled"},
            ],
        }
    ]
    assert build_digest.expected_source_keys(regions) == {
        "mount-prospect-60056:Village News",
        "mount-prospect-60056:Default Enabled",
    }


def test_detect_missing_sources_flags_a_configured_source_never_recorded():
    # ROADMAP.md item 181 (forty-third research pass): a source that
    # fails transport on every build never earns a key in
    # source_health.json at all (item 55's own design) - the three
    # detectors above can't see an absent key by iterating present
    # ones. This is the check that catches the absence itself.
    regions = [
        {
            "region": {"id": "wheeling-60090"},
            "sources": [
                {"name": "Indian Trails Public Library — Events", "enabled": True},
                {"name": "Wheeling Park District — Events", "enabled": True},
            ],
        }
    ]
    health = {"wheeling-60090:Indian Trails Public Library — Events": [6, 6, 6]}
    assert build_digest.detect_missing_sources(regions, health) == [
        "wheeling-60090:Wheeling Park District — Events"
    ]


def test_detect_missing_sources_ignores_a_disabled_source():
    regions = [
        {
            "region": {"id": "wheeling-60090"},
            "sources": [{"name": "Disabled Source", "enabled": False}],
        }
    ]
    assert build_digest.detect_missing_sources(regions, {}) == []


def test_detect_missing_sources_returns_empty_when_everything_recorded():
    regions = [
        {
            "region": {"id": "mount-prospect-60056"},
            "sources": [{"name": "Village News", "enabled": True}],
        }
    ]
    health = {"mount-prospect-60056:Village News": [6]}
    assert build_digest.detect_missing_sources(regions, health) == []


def test_update_weekend_history_appends_and_trims_to_history_len():
    history = {}
    for count in range(build_digest.WEEKEND_HISTORY_LEN + 3):
        build_digest.update_weekend_history(history, "des-plaines-60016", count)
    assert len(history["des-plaines-60016"]) == build_digest.WEEKEND_HISTORY_LEN
    # oldest entries (0, 1, 2) dropped, most recent kept, in order
    assert history["des-plaines-60016"][0] == 3
    assert history["des-plaines-60016"][-1] == build_digest.WEEKEND_HISTORY_LEN + 2


def test_save_and_load_weekend_history_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "weekend_signal_history.json"
    monkeypatch.setattr(build_digest, "WEEKEND_HISTORY_PATH", path)
    history = {"des-plaines-60016": [0, 0, 3]}
    build_digest.save_weekend_history(history)
    assert build_digest.load_weekend_history() == history


def test_load_weekend_history_returns_empty_dict_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(build_digest, "WEEKEND_HISTORY_PATH", tmp_path / "missing.json")
    assert build_digest.load_weekend_history() == {}


def test_detect_zero_weekend_regions_flags_at_threshold():
    # ROADMAP.md item 186: Des Plaines' own real shape - reachable,
    # un-truncated sources, still 0 weekend events for 3+ builds running.
    history = {
        "des-plaines-60016": [5, 0, 0, 0],
        "mount-prospect-60056": [7, 6, 8, 7],
    }
    assert build_digest.detect_zero_weekend_regions(history) == ["des-plaines-60016"]


def test_detect_zero_weekend_regions_ignores_below_threshold():
    # Only 2 trailing zeros, threshold is 3 - a genuinely quiet weekend
    # that hasn't yet earned the "still zero" label.
    history = {"palatine-60067": [3, 0, 0]}
    assert build_digest.detect_zero_weekend_regions(history) == []


def test_detect_zero_weekend_regions_ignores_a_recent_nonzero_build():
    # The most recent `threshold` builds must ALL be zero - a region
    # that just recovered (item 182's Wheeling fix) shouldn't be flagged
    # by older zeros still sitting earlier in its history.
    history = {"wheeling-60090": [0, 0, 0, 7]}
    assert build_digest.detect_zero_weekend_regions(history) == []


def test_render_region_page_produces_html_even_with_empty_sources():
    # On the main page (nav_current="all", the default - real call sites
    # for every other view always pass their own nav_current), an empty
    # section is omitted entirely rather than printed as an apology
    # (ROADMAP.md Phase 11 #54) - the evergreen content leads instead.
    blocks = [{"section": "Village News", "events": []}]
    sponsor = {"title": "Sponsor this spot", "detail": "", "url": ""}
    evergreen = [{"title": "Library", "detail": "Books.", "url": "https://mppl.org/", "tags": ["indoor"]}]
    region_cfg = {"region": REGION}
    html = build_digest.render_region_page(
        region_cfg, blocks, sponsor, evergreen, datetime.now(timezone.utc)
    )
    assert "Mount Prospect" in html
    assert "Village News" not in html
    assert "No live updates fetched this week" not in html
    assert "Library" in html
    assert "quiet week" in html


def test_render_region_page_shows_calendar_subscribe_link_on_main_page():
    # ROADMAP.md Phase 11 #100: shown once, on the main region page
    # (nav_current="all", the default) - a subscription is the whole
    # calendar, not a date-scoped view.
    blocks = [{"section": "Village News", "events": []}]
    sponsor = {"title": "Sponsor this spot", "detail": "", "url": ""}
    region_cfg = {"region": REGION}
    html = build_digest.render_region_page(region_cfg, blocks, sponsor, [], datetime.now(timezone.utc))
    assert 'href="https://withintenmiles.com/mount-prospect-60056/calendar.ics"' in html
    assert 'href="webcal://withintenmiles.com/mount-prospect-60056/calendar.ics"' in html


def test_render_region_page_shows_a_human_readable_freshness_note():
    # ROADMAP.md item 163: dateModified in the JSON-LD is machine-only -
    # this is the visible half of the same claim, near the listings
    # rather than buried in the footer's "Generated ..." line.
    blocks = [{"section": "Village News", "events": []}]
    sponsor = {"title": "Sponsor this spot", "detail": "", "url": ""}
    region_cfg = {"region": REGION}
    html = build_digest.render_region_page(
        region_cfg, blocks, sponsor, [], datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)
    )
    assert "Updated automatically — last checked Sunday, September 20." in html


def test_is_trick_or_treat_season_true_in_september_and_october():
    assert build_digest.is_trick_or_treat_season(datetime(2026, 9, 1, tzinfo=timezone.utc))
    assert build_digest.is_trick_or_treat_season(datetime(2026, 10, 31, tzinfo=timezone.utc))


def test_is_trick_or_treat_season_true_a_few_days_into_november():
    assert build_digest.is_trick_or_treat_season(datetime(2026, 11, 5, tzinfo=timezone.utc))


def test_is_trick_or_treat_season_false_outside_the_window():
    assert not build_digest.is_trick_or_treat_season(datetime(2026, 11, 6, tzinfo=timezone.utc))
    assert not build_digest.is_trick_or_treat_season(datetime(2026, 3, 15, tzinfo=timezone.utc))
    assert not build_digest.is_trick_or_treat_season(datetime(2026, 8, 31, tzinfo=timezone.utc))


def test_render_region_page_links_trick_or_treat_in_season():
    # A found bug: the /trick-or-treat/ page (item 101) has been live
    # and in the sitemap since it shipped, but no region or hub page
    # ever linked to it - reachable only by a crawler reading the
    # sitemap or llms.txt, never by an actual visitor.
    blocks = [{"section": "Village News", "events": []}]
    sponsor = {"title": "Sponsor this spot", "detail": "", "url": ""}
    region_cfg = {"region": REGION}
    html = build_digest.render_region_page(
        region_cfg, blocks, sponsor, [], datetime(2026, 10, 1, tzinfo=timezone.utc)
    )
    assert 'href="https://withintenmiles.com/trick-or-treat/"' in html


def test_render_region_page_omits_trick_or_treat_link_outside_season():
    blocks = [{"section": "Village News", "events": []}]
    sponsor = {"title": "Sponsor this spot", "detail": "", "url": ""}
    region_cfg = {"region": REGION}
    html = build_digest.render_region_page(
        region_cfg, blocks, sponsor, [], datetime(2026, 3, 1, tzinfo=timezone.utc)
    )
    assert "trick-or-treat" not in html


def test_render_region_page_omits_calendar_subscribe_link_on_other_views():
    blocks = [{"section": "Village News", "events": []}]
    sponsor = {"title": "Sponsor this spot", "detail": "", "url": ""}
    region_cfg = {"region": REGION}
    html = build_digest.render_region_page(
        region_cfg, blocks, sponsor, [], datetime.now(timezone.utc), nav_current="today"
    )
    assert "calendar.ics" not in html


def test_render_region_page_lists_fetched_events_and_tags():
    blocks = [
        {
            "section": "Village News",
            "events": [
                {"title": "Board Meeting", "detail": "7pm", "url": "https://x/1", "date": "Aug 24", "tags": ["free"]}
            ],
        }
    ]
    sponsor = {"title": "Sponsor this spot", "detail": "", "url": ""}
    region_cfg = {"region": REGION}
    html = build_digest.render_region_page(region_cfg, blocks, sponsor, [], datetime.now(timezone.utc))
    assert "Board Meeting" in html
    assert "No live updates fetched this week" not in html
    assert 'data-tag="free"' in html


def test_render_region_page_heading_and_subheading_overrides():
    html = build_digest.render_region_page(
        {"region": REGION}, [], {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc),
        heading="This weekend in Mount Prospect", subheading="Aug 29–30",
    )
    assert "<h1>This weekend in Mount Prospect</h1>" in html
    assert "Aug 29–30" in html
    assert "<h1>What's happening in Mount Prospect</h1>" not in html
    assert f"<title>This weekend in Mount Prospect — {build_digest.SITE_NAME}</title>" in html
    assert 'content="Aug 29–30"' in html


def test_render_region_page_empty_message_override():
    # A filtered single-block view (weekend/today/free) always passes its
    # own nav_current in real call sites - it keeps its heading and
    # custom empty message even when empty, unlike the main page's
    # omit-and-lead-with-evergreen behavior (ROADMAP.md Phase 11 #54).
    blocks = [{"section": "This Weekend", "events": []}]
    html = build_digest.render_region_page(
        {"region": REGION}, blocks, {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc),
        empty_message="Nothing dated for this weekend yet.",
        nav_current="weekend",
    )
    assert "This Weekend" in html
    assert "Nothing dated for this weekend yet." in html


def test_render_region_page_omits_empty_sections_but_keeps_populated_ones():
    blocks = [
        {"section": "Village News", "events": []},
        {
            "section": "Library Events",
            "events": [{"title": "Storytime", "detail": "", "url": "https://x/1", "date": "Aug 24", "tags": []}],
        },
        {"section": "Park District Events", "events": []},
    ]
    sponsor = {"title": "Sponsor this spot", "detail": "", "url": ""}
    html = build_digest.render_region_page(
        {"region": REGION}, blocks, sponsor, [], datetime.now(timezone.utc)
    )
    assert "Village News" not in html
    assert "Park District Events" not in html
    assert "Library Events" in html
    assert "Storytime" in html
    # At least one real section has content, so this isn't the "quiet
    # week, lead with evergreen" case.
    assert "quiet week" not in html


def test_render_region_page_shows_map_with_a_link_not_an_iframe():
    # ROADMAP.md Phase 11 #53: the original iframe + reveal-on-load design
    # was dropped after testing showed an iframe's load event fires even
    # when navigation is blocked - it never actually caught a failure. The
    # reliable inline SVG is the map now; a plain outbound link sits next
    # to it, never an iframe that can silently look fine while broken.
    region_map = {
        "width": 320,
        "height": 220,
        "pins": [{"name": "Arlington Heights", "path": "arlington-heights-60005/", "x": 50.0, "y": 60.0}],
        "lines": [],
    }
    html = build_digest.render_region_page(
        {"region": REGION}, [], {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc),
        map_link_url="https://www.google.com/maps/search/?api=1&query=1,2",
        region_map=region_map,
    )
    assert 'class="map-fallback"' in html
    assert "Arlington Heights" in html
    assert 'class="map-link"' in html
    assert "<iframe" not in html


def test_render_region_page_map_fallback_alone_when_no_link_url():
    region_map = {
        "width": 320,
        "height": 220,
        "pins": [{"name": "Arlington Heights", "path": "arlington-heights-60005/", "x": 50.0, "y": 60.0}],
        "lines": [],
    }
    html = build_digest.render_region_page(
        {"region": REGION}, [], {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc),
        region_map=region_map,
    )
    assert 'class="map-fallback"' in html
    assert 'class="map-link"' not in html


def test_render_region_page_hides_evergreen_section_when_empty():
    html = build_digest.render_region_page(
        {"region": REGION}, [], {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc)
    )
    assert "Around Mount Prospect" not in html


def test_render_region_page_view_nav_marks_active_view():
    html = build_digest.render_region_page(
        {"region": REGION}, [], {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc),
        nav_current="free",
    )
    assert f'<a href="{build_digest.SITE_BASE_URL}mount-prospect-60056/free/" class="active">Free</a>' in html


def test_render_region_page_omits_newsletter_when_not_configured():
    # ROADMAP.md Phase 11 #56: same fix as the hub page - "(Signup coming
    # soon.)" was shipping to production on a page used to pitch sponsors.
    newsletter = {"configured": False, "headline": "Get it in your inbox", "detail": "Weekly.", "buttondown_username": ""}
    html = build_digest.render_region_page(
        {"region": REGION}, [], {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc),
        newsletter=newsletter,
    )
    assert '<div class="newsletter">' not in html
    assert "Signup coming soon" not in html


def test_render_region_page_shows_newsletter_form_when_configured():
    newsletter = {"configured": True, "headline": "Get it in your inbox", "detail": "Weekly.", "buttondown_username": "planner"}
    html = build_digest.render_region_page(
        {"region": REGION}, [], {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc),
        newsletter=newsletter,
    )
    assert 'buttondown.com/api/emails/embed-subscribe/planner' in html
    assert "Signup coming soon" not in html


def test_render_region_page_newsletter_form_uses_hidden_iframe_not_popup():
    # ROADMAP.md item 191: a popup gives a blocked-popup reader zero
    # feedback, and the page never disclosed that a confirmation email
    # (Buttondown's own double opt-in, item 190) was coming.
    newsletter = {"configured": True, "headline": "Get it in your inbox", "detail": "Weekly.", "buttondown_username": "planner"}
    html = build_digest.render_region_page(
        {"region": REGION}, [], {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc),
        newsletter=newsletter,
    )
    assert 'target="bd-hidden-frame"' in html
    assert 'popupwindow' not in html
    assert 'window.open' not in html
    assert '<iframe name="bd-hidden-frame"' in html
    assert "We'll send one email to confirm." in html
    assert "check your email and click the confirmation link" in html


def test_render_region_page_calendar_box_includes_email_link_when_configured():
    # ROADMAP.md item 183's own follow-up: the bottom-of-page signup form
    # sits 99%+ of the way down a real region page, unreachable by a
    # reader who doesn't scroll through every event first - one plain
    # link folded into the existing above-the-fold calendar-subscribe
    # box instead.
    newsletter = {"configured": True, "headline": "Get it in your inbox", "detail": "Weekly.", "buttondown_username": "planner"}
    html = build_digest.render_region_page(
        {"region": REGION}, [], {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc),
        newsletter=newsletter,
    )
    assert "Get it by email instead" in html
    assert 'href="https://buttondown.com/planner"' in html


def test_render_region_page_calendar_box_omits_email_link_when_unconfigured():
    newsletter = {"configured": False, "headline": "Get it in your inbox", "detail": "Weekly.", "buttondown_username": ""}
    html = build_digest.render_region_page(
        {"region": REGION}, [], {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc),
        newsletter=newsletter,
    )
    assert "Get it by email instead" not in html


def test_region_local_date_uses_region_timezone():
    # noon UTC is still the same calendar day in America/Chicago (UTC-5/6)
    now_utc = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    assert build_digest.region_local_date(REGION, now_utc) == date(2026, 8, 27)


def test_region_local_date_falls_back_to_utc_on_bad_timezone():
    now_utc = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    bad_region = {**REGION, "timezone": "Not/AZone"}
    assert build_digest.region_local_date(bad_region, now_utc) == date(2026, 8, 27)


def test_weekend_dates_from_a_weekday_returns_upcoming_friday_saturday_sunday():
    tuesday = date(2026, 8, 25)  # confirmed Tuesday
    assert build_digest.weekend_dates(tuesday) == (date(2026, 8, 28), date(2026, 8, 29), date(2026, 8, 30))


def test_weekend_dates_from_saturday_returns_same_weekend():
    saturday = date(2026, 8, 29)
    assert build_digest.weekend_dates(saturday) == (date(2026, 8, 28), date(2026, 8, 29), date(2026, 8, 30))


def test_format_date_range_same_month():
    assert build_digest.format_date_range(date(2026, 8, 29), date(2026, 8, 30)) == "Aug 29–30"


def test_format_date_range_different_months():
    assert build_digest.format_date_range(date(2026, 8, 31), date(2026, 9, 1)) == "Aug 31–Sep 1"


def test_filter_events_by_dates_matches_only_target_dates():
    blocks = [
        {
            "section": "A",
            "events": [
                {"title": "x", "date_iso": "2026-08-29T10:00:00"},
                {"title": "y", "date_iso": "2026-09-01T10:00:00"},
                {"title": "z", "date_iso": None},
            ],
        }
    ]
    matched = build_digest.filter_events_by_dates(blocks, {date(2026, 8, 29)})
    assert [e["title"] for e in matched] == ["x"]


def test_filter_past_events_drops_yesterday_keeps_today_and_future():
    # ROADMAP.md item 171: the bug this regression test exists to catch
    # was invisible to every date-scoped test in this file until now,
    # because they all use fixed 2026 dates that happened to be in the
    # future when written. A fixture computed relative to the real
    # clock at test-run time is the only way to actually exercise "is
    # this in the past" rather than coincidentally testing "is this
    # after some hardcoded date."
    today = date(2026, 9, 21)
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    blocks = [
        {
            "section": "A",
            "events": [
                {"title": "stale", "date_iso": datetime.combine(yesterday, time(9, 0)).isoformat()},
                {"title": "today", "date_iso": datetime.combine(today, time(9, 0)).isoformat()},
                {"title": "future", "date_iso": datetime.combine(tomorrow, time(9, 0)).isoformat()},
                {"title": "undated", "date_iso": None},
            ],
        }
    ]
    filtered = build_digest.filter_past_events(blocks, today)
    assert [e["title"] for e in filtered[0]["events"]] == ["today", "future", "undated"]


def test_filter_past_events_keeps_each_day_of_a_multi_day_series_independently():
    # A multi-day festival modeled as one dict per day (the `series`
    # kicker) should have its already-passed days drop while its
    # upcoming days remain - "survives until its end date" falls out of
    # filtering per-occurrence, with no separate start/end range needed.
    today = date(2026, 9, 21)
    blocks = [
        {
            "section": "Annual Events",
            "events": [
                {"title": "Fest (Fri)", "series": "Fest", "date_iso": "2026-09-18T18:00:00"},
                {"title": "Fest (Sat)", "series": "Fest", "date_iso": "2026-09-19T12:00:00"},
                {"title": "Fest (Sun)", "series": "Fest", "date_iso": "2026-09-21T12:00:00"},
                {"title": "Fest (Mon)", "series": "Fest", "date_iso": "2026-09-22T12:00:00"},
            ],
        }
    ]
    filtered = build_digest.filter_past_events(blocks, today)
    assert [e["title"] for e in filtered[0]["events"]] == ["Fest (Sun)", "Fest (Mon)"]


def test_write_weekend_signal_writes_total_and_per_region_counts(tmp_path, monkeypatch):
    path = tmp_path / "weekend_signal.json"
    monkeypatch.setattr(build_digest, "WEEKEND_SIGNAL_PATH", path)
    build_digest.write_weekend_signal(
        {"mount-prospect-60056": 4, "palatine-60067": 0},
        datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
    )
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["total"] == 4
    assert written["region_counts"] == {"mount-prospect-60056": 4, "palatine-60067": 0}
    assert written["generated_at"] == "2026-09-21T12:00:00+00:00"


def test_dedupe_events_collapses_same_day_near_duplicate_titles_across_sources():
    # ROADMAP.md item 173: exactly the live-build pair the fortieth pass
    # found - one source's bare title, another's fuller one, same day.
    blocks = [
        {
            "section": "Village Feed",
            "events": [
                {"title": "Palatine Oktoberfest", "date_iso": "2026-09-25T18:00:00", "detail": "", "url": ""},
            ],
        },
        {
            "section": "Downtown Merchants",
            "events": [
                {
                    "title": "Palatine Oktoberfest (Friday)",
                    "date_iso": "2026-09-25T18:00:00",
                    "detail": "German beer, food & music.",
                    "url": "https://palatinerotary.org/Oktoberfest.php",
                },
            ],
        },
    ]
    deduped = build_digest.dedupe_events(blocks)
    all_events = [e for b in deduped for e in b["events"]]
    assert len(all_events) == 1
    # The fuller entry (has both detail and url) survives, not whichever
    # source happened to be fetched first.
    assert all_events[0]["title"] == "Palatine Oktoberfest (Friday)"


def test_dedupe_events_keeps_same_titled_events_on_different_days():
    # A weekly-recurring farmers market named identically on two
    # different Sundays is not a duplicate - only same-day collisions
    # should ever collapse.
    blocks = [
        {
            "section": "Annual Events",
            "events": [
                {"title": "Farmers Market", "date_iso": "2026-09-21T09:00:00", "detail": "", "url": ""},
                {"title": "Farmers Market", "date_iso": "2026-09-28T09:00:00", "detail": "", "url": ""},
            ],
        }
    ]
    deduped = build_digest.dedupe_events(blocks)
    assert len(deduped[0]["events"]) == 2


def test_dedupe_events_leaves_distinct_titles_on_the_same_day_alone():
    blocks = [
        {
            "section": "A",
            "events": [
                {"title": "Fall Fest", "date_iso": "2026-09-25T18:00:00", "detail": "", "url": ""},
                {"title": "Library Story Time", "date_iso": "2026-09-25T10:00:00", "detail": "", "url": ""},
            ],
        }
    ]
    deduped = build_digest.dedupe_events(blocks)
    assert len(deduped[0]["events"]) == 2


def test_dedupe_events_ignores_undated_items():
    blocks = [
        {
            "section": "A",
            "events": [
                {"title": "Same Undated Thing", "date_iso": None, "detail": "", "url": ""},
                {"title": "Same Undated Thing", "date_iso": None, "detail": "", "url": ""},
            ],
        }
    ]
    deduped = build_digest.dedupe_events(blocks)
    assert len(deduped[0]["events"]) == 2


def test_dedupe_events_breaks_ties_by_keeping_the_earliest_occurrence():
    blocks = [
        {
            "section": "A",
            "events": [
                {"title": "Oktoberfest", "date_iso": "2026-09-25T18:00:00", "detail": "", "url": ""},
                {"title": "Palatine Oktoberfest", "date_iso": "2026-09-25T18:00:00", "detail": "", "url": ""},
            ],
        }
    ]
    deduped = build_digest.dedupe_events(blocks)
    all_events = [e for b in deduped for e in b["events"]]
    assert len(all_events) == 1
    assert all_events[0]["title"] == "Oktoberfest"


def test_filter_free_items_merges_events_and_evergreen():
    blocks = [{"section": "A", "events": [{"title": "Fair", "tags": ["free"]}, {"title": "Gala", "tags": []}]}]
    evergreen = [{"title": "Library", "tags": ["free"]}, {"title": "Village Hall", "tags": []}]
    matched = build_digest.filter_free_items(blocks, evergreen)
    assert {e["title"] for e in matched} == {"Fair", "Library"}


def test_render_hub_page_lists_regions():
    summaries = [{**REGION, "event_count": 3, "path": "mount-prospect-60056/"}]
    html = build_digest.render_hub_page([], summaries, datetime.now(timezone.utc))
    assert "Mount Prospect" in html
    assert "mount-prospect-60056/" in html
    assert "3 live update" in html


def test_render_hub_page_subheading_counts_actual_regions():
    # ROADMAP.md item 170: the subheading used to hardcode "four towns",
    # which was already wrong the moment a fifth region (item 166)
    # shipped - the same class of stale-count bug flagged for the
    # combined email's headline. Computed from region_summaries instead.
    summaries = [
        {**REGION, "event_count": 3, "path": "mount-prospect-60056/"},
        {**REGION, "id": "wheeling-60090", "name": "Wheeling", "event_count": 1, "path": "wheeling-60090/"},
    ]
    html = build_digest.render_hub_page([], summaries, datetime.now(timezone.utc))
    assert "for 2 towns" in html
    assert "four towns" not in html


def test_render_hub_page_offers_a_corrections_path_with_mailto_cta():
    # ROADMAP.md Phase 11 #132: the corrections line item 132 asked for
    # in "the footer" - the hub is the site's front door, so it's the
    # one footer that needs to carry it site-wide (region pages already
    # link to the About page, where the fuller version lives).
    summaries = [{**REGION, "event_count": 3, "path": "mount-prospect-60056/"}]
    html = build_digest.render_hub_page([], summaries, datetime.now(timezone.utc), contact_email="owner@example.com")
    assert "corrections get made the same week" in html
    assert 'href="mailto:owner@example.com?subject=Correction' in html


def test_render_hub_page_has_no_distance_from_me_feature():
    """The geolocation "Show distance from me" bar was removed at the
    owner's request on 2026-09-15, along with its ZIP fallback, its
    per-card distance label and the coordinate attributes that only it
    read. The build-time "Nearby: ... ~2.7 mi" strip on region pages and
    the distances drawn on the inline SVG map are unrelated and stay.
    """
    summaries = [{**REGION, "event_count": 3, "path": "mount-prospect-60056/"}]
    html = build_digest.render_hub_page([], summaries, datetime.now(timezone.utc))
    assert "Show distance from me" not in html
    assert "haversineMiles" not in html
    assert "data-distance-label" not in html
    assert 'data-lat="42.0666"' not in html


def test_render_hub_page_handles_no_regions():
    html = build_digest.render_hub_page([], [], datetime.now(timezone.utc))
    assert "No regions configured yet" in html


def test_render_hub_page_links_trick_or_treat_in_season():
    summaries = [{**REGION, "event_count": 3, "path": "mount-prospect-60056/"}]
    html = build_digest.render_hub_page([], summaries, datetime(2026, 9, 20, tzinfo=timezone.utc))
    assert 'href="trick-or-treat/"' in html


def test_render_hub_page_omits_trick_or_treat_link_outside_season():
    summaries = [{**REGION, "event_count": 3, "path": "mount-prospect-60056/"}]
    html = build_digest.render_hub_page([], summaries, datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert "trick-or-treat" not in html


def test_render_hub_page_separates_region_cards_from_bento_grid():
    # ROADMAP.md Phase 11 #56: region cards used to share a CSS grid with
    # the "this weekend"/stat tiles, which stranded a lone last-row card
    # next to an empty gap (grid only collapses a track with zero items
    # anywhere in the grid, not one merely unused in one row). They now
    # live in their own flex-wrap .region-grid, which can actually
    # stretch a lone last card to fill its row.
    summaries = [{**REGION, "event_count": 3, "path": "mount-prospect-60056/"}]
    html = build_digest.render_hub_page([], summaries, datetime.now(timezone.utc))
    assert '<div class="bento-grid">' in html
    assert '<div class="region-grid" id="region-grid">' in html
    assert html.index('<div class="region-grid" id="region-grid">') > html.index('<div class="bento-grid">')


def test_render_hub_page_never_embeds_event_json_ld():
    # ROADMAP.md Phase 11 #120: Google's 2026 structured-data eligibility
    # narrowed to schema matching a page's *primary content purpose*.
    # The hub aggregates four regions - no single event is its primary
    # purpose - so Event schema belongs only on region.html.j2's own
    # views (region/this-weekend/today/free), never here. Guards against
    # the tempting-but-now-counter-productive future change of adding
    # Event markup to the hub "to help the home page rank."
    summaries = [{"name": "Mount Prospect", "url": "https://x/mount-prospect-60056/", "event_count": 5}]
    html = build_digest.render_hub_page([], summaries, datetime.now(timezone.utc))
    assert '"@type": "Event"' not in html


def _render_weekend_hub_page(sections, date_range, now, analytics=None):
    """The /this-weekend hub call site's exact kwargs (ROADMAP.md item
    149 generalized render_merged_hub_page to also drive /today and
    /free) - kept as one helper so these tests read the same as before
    the signature change.
    """
    return build_digest.render_merged_hub_page(
        sections,
        now,
        analytics,
        slug="this-weekend",
        heading="This Weekend Near You",
        subheading=f"{date_range} — everything with a known date, across every region.",
        meta_description=f"Everything with a known date this weekend ({date_range}), across every region — one page for planning a trip nearby.",
        empty_message="Nothing dated for this weekend yet across any region — check back, or browse a region's full page.",
    )


def test_render_weekend_hub_page_never_embeds_event_json_ld():
    # Same guard as above, for the other hub-level page - the merged
    # "This weekend near you" view spans every region, so it isn't any
    # one event's primary content purpose either.
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": f"{build_digest.SITE_BASE_URL}mount-prospect-60056/",
            "events": [{"title": "Fishing Derby", "url": "https://x/", "detail": "", "date": "Sep 19", "tags": []}],
        }
    ]
    html = _render_weekend_hub_page(sections, "Sep 19–20", datetime.now(timezone.utc))
    assert '"@type": "Event"' not in html


def test_render_merged_hub_page_supports_a_different_slug_and_copy():
    # ROADMAP.md item 149: render_merged_hub_page (formerly
    # render_weekend_hub_page) now also drives /today and /free at the
    # hub level - the same template, a different heading/canonical/slug.
    sections = [
        {
            "region_name": "Palatine",
            "region_url": f"{build_digest.SITE_BASE_URL}palatine-60067/",
            "events": [{"title": "Free Concert in the Park", "url": "https://x/", "detail": "", "date": None, "tags": []}],
        }
    ]
    html = build_digest.render_merged_hub_page(
        sections,
        datetime.now(timezone.utc),
        slug="free",
        heading="Free Things To Do Near You",
        subheading="Everything tagged free, any date, across every region.",
        meta_description="Everything tagged free, any date, across every region.",
        empty_message="Nothing tagged free yet across any region.",
    )
    assert "<h1>Free Things To Do Near You</h1>" in html
    assert "Free Concert in the Park" in html
    assert f'rel="canonical" href="{build_digest.SITE_BASE_URL}free/"' in html


def test_render_merged_hub_page_shows_its_own_empty_message():
    html = build_digest.render_merged_hub_page(
        [],
        datetime.now(timezone.utc),
        slug="today",
        heading="Happening Today Near You",
        subheading="Everything happening today, across every region.",
        meta_description="Everything happening today, across every region.",
        empty_message="Nothing dated for today yet across any region.",
    )
    assert "Nothing dated for today yet across any region." in html


def test_render_hub_page_links_to_the_today_and_free_hub_views():
    # ROADMAP.md item 149: the hub-level /today and /free pages exist but
    # are worthless if nothing on the hub page links to them.
    stats = {"region_count": 1, "event_count": 3, "weekend_count": 2, "weekend_date_range": "Sep 19-20", "today_count": 1, "free_count": 2}
    summaries = [{**REGION, "event_count": 1, "path": "mount-prospect-60056/"}]
    html = build_digest.render_hub_page([], summaries, datetime.now(timezone.utc), stats=stats)
    assert 'href="today/"' in html
    assert 'href="free/"' in html
    assert "Today (1)" in html
    assert "Free things to do (2)" in html


def test_render_hub_page_omits_newsletter_when_not_configured():
    # ROADMAP.md Phase 11 #56: "(Signup coming soon.)" was shipping to
    # production on the exact pages used to pitch sponsors, reading as
    # unfinished. Hide the block entirely until signup actually works
    # instead of showing a pending state.
    newsletter = {"configured": False, "headline": "Get it in your inbox", "detail": "Weekly.", "buttondown_username": ""}
    html = build_digest.render_hub_page([], [], datetime.now(timezone.utc), newsletter=newsletter)
    assert '<div class="newsletter">' not in html
    assert "Signup coming soon" not in html
    assert "Get it in your inbox" not in html


def test_render_hub_page_shows_newsletter_form_when_configured():
    newsletter = {"configured": True, "headline": "Get it in your inbox", "detail": "Weekly.", "buttondown_username": "planner"}
    html = build_digest.render_hub_page([], [], datetime.now(timezone.utc), newsletter=newsletter)
    assert 'buttondown.com/api/emails/embed-subscribe/planner' in html


def test_render_hub_page_newsletter_form_uses_hidden_iframe_not_popup():
    # Same fix as the region page (item 191) - see that test's comment.
    newsletter = {"configured": True, "headline": "Get it in your inbox", "detail": "Weekly.", "buttondown_username": "planner"}
    html = build_digest.render_hub_page([], [], datetime.now(timezone.utc), newsletter=newsletter)
    assert 'target="bd-hidden-frame"' in html
    assert 'popupwindow' not in html
    assert 'window.open' not in html
    assert '<iframe name="bd-hidden-frame"' in html
    assert "We'll send one email to confirm." in html
    assert "check your email and click the confirmation link" in html
    assert "Signup coming soon" not in html


def test_render_weekend_hub_page_groups_events_by_region():
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": f"{build_digest.SITE_BASE_URL}mount-prospect-60056/",
            "events": [{"title": "Fishing Derby", "url": "https://x/", "detail": "", "date": "Sep 19", "tags": []}],
        }
    ]
    html = _render_weekend_hub_page(sections, "Sep 19–20", datetime.now(timezone.utc))
    assert "Mount Prospect" in html
    assert "Fishing Derby" in html
    assert "Sep 19–20" in html
    assert f'href="{build_digest.SITE_BASE_URL}mount-prospect-60056/"' in html


def test_render_weekend_hub_page_handles_no_events_anywhere():
    html = _render_weekend_hub_page([], "Sep 19–20", datetime.now(timezone.utc))
    assert "Nothing dated for this weekend yet across any region" in html


def _assert_tray_render_uses_safe_dom_methods(html: str):
    """A found bug: the itinerary tray's JS used to build each item's DOM
    by splicing item.title/item.url straight into an HTML string
    (`'<a href="' + item.url + '">' + item.title + '</a>'`) and assigning
    it via .innerHTML. item.* is event data ultimately sourced from
    external RSS/ICS/HTML feeds this site doesn't control - any
    HTML-significant character in a title or url would have executed as
    markup. Verified live with a headless Chromium render (a malicious
    title containing `<img onerror=...>` and a `javascript:` url neither
    executed nor produced a live element - not automated here, same
    reasoning as item 92's dark-mode verification: it would make
    Playwright a CI dependency for one script's worth of coverage). This
    guards the fix by asserting the vulnerable concatenation pattern is
    gone and the safe DOM-construction pattern replaced it.
    """
    assert "'<a href=\"' + item.url" not in html
    assert "+ item.title + '</a>'" not in html
    assert "titleEl.textContent = item.title" in html
    assert 'removeBtn.setAttribute("aria-label", "Remove " + item.title)' in html


def test_render_region_page_tray_uses_safe_dom_methods_not_innerhtml_concat():
    blocks = [{"section": "Village News", "events": []}]
    sponsor = {"title": "Sponsor this spot", "detail": "", "url": ""}
    region_cfg = {"region": REGION}
    html = build_digest.render_region_page(region_cfg, blocks, sponsor, [], datetime.now(timezone.utc))
    _assert_tray_render_uses_safe_dom_methods(html)


def test_render_weekend_hub_page_tray_uses_safe_dom_methods_not_innerhtml_concat():
    html = _render_weekend_hub_page([], "Sep 19–20", datetime.now(timezone.utc))
    _assert_tray_render_uses_safe_dom_methods(html)


def test_render_region_page_includes_canonical_link():
    html = build_digest.render_region_page({"region": REGION}, [], {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc))
    assert f'rel="canonical" href="{build_digest.SITE_BASE_URL}mount-prospect-60056/"' in html


def test_render_hub_page_includes_canonical_link():
    html = build_digest.render_hub_page([], [], datetime.now(timezone.utc))
    assert f'rel="canonical" href="{build_digest.SITE_BASE_URL}"' in html


def test_build_event_json_ld_returns_none_for_no_events():
    assert build_digest.build_event_json_ld([{"section": "News", "events": []}]) is None


def test_build_event_json_ld_produces_valid_json_with_expected_fields():
    import json as _json

    blocks = [
        {
            "section": "Park District Events",
            "events": [
                {
                    "title": "Fishing Derby",
                    "detail": "Grab your gear.",
                    "url": "https://example.org/fishing",
                    "date_iso": "2026-09-19T10:00:00",
                }
            ],
        }
    ]
    result = build_digest.build_event_json_ld(blocks)
    payload = _json.loads(result)
    assert payload["@context"] == "https://schema.org"
    event = payload["@graph"][0]
    assert event["@type"] == "Event"
    assert event["name"] == "Fishing Derby"
    assert event["startDate"] == "2026-09-19T10:00:00"


def test_build_event_json_ld_omits_location_without_a_real_venue():
    # ROADMAP.md's seventh research pass: region-level location (town
    # centre) used to be emitted as an approximation. Once AI systems
    # cross-reference schema against live sources, an event at a specific
    # venue marked up with the town centre reads as wrong, not
    # approximate - so no venue data means no location claim at all.
    blocks = [
        {
            "section": "Park District Events",
            "events": [
                {
                    "title": "Fishing Derby",
                    "detail": "",
                    "url": "https://example.org/fishing",
                    "date_iso": "2026-09-19T10:00:00",
                }
            ],
        }
    ]
    import json as _json

    payload = _json.loads(build_digest.build_event_json_ld(blocks))
    assert "location" not in payload["@graph"][0]


def test_build_event_json_ld_escapes_script_close_tag():
    blocks = [
        {
            "section": "News",
            "events": [
                {
                    "title": "Weird</script>Title",
                    "detail": "",
                    "url": "https://x/",
                    "date_iso": "2026-09-19T10:00:00",
                }
            ],
        }
    ]
    result = build_digest.build_event_json_ld(blocks)
    assert "</script>" not in result


def test_build_event_json_ld_excludes_undated_items():
    # /free merges evergreen entries (never dated) into the same
    # events list as real fetched events - undated items must not show
    # up as schema.org Events, which requires a real startDate to mean
    # anything.
    blocks = [
        {
            "section": "Free",
            "events": [
                {"title": "Library", "detail": "", "url": "https://x/", "date_iso": None},
                {"title": "Fishing Derby", "detail": "", "url": "https://x/2", "date_iso": "2026-09-19T10:00:00"},
            ],
        }
    ]
    result = build_digest.build_event_json_ld(blocks)
    import json as _json

    payload = _json.loads(result)
    names = [e["name"] for e in payload["@graph"]]
    assert names == ["Fishing Derby"]


def test_build_event_json_ld_skips_events_missing_title_or_url():
    blocks = [{"section": "News", "events": [{"title": "", "url": "https://x/", "detail": ""}]}]
    assert build_digest.build_event_json_ld(blocks) is None


def test_build_sitemap_xml_lists_hub_and_region_urls():
    summaries = [{**REGION, "event_count": 1, "path": "mount-prospect-60056/"}]
    xml = build_digest.build_sitemap_xml(summaries, datetime.now(timezone.utc))
    assert f"<loc>{build_digest.SITE_BASE_URL}</loc>" in xml
    assert f"<loc>{build_digest.SITE_BASE_URL}mount-prospect-60056/</loc>" in xml


def test_build_sitemap_xml_includes_weekend_hub_url():
    summaries = [{**REGION, "event_count": 1, "path": "mount-prospect-60056/"}]
    xml = build_digest.build_sitemap_xml(summaries, datetime.now(timezone.utc))
    assert f"<loc>{build_digest.SITE_BASE_URL}this-weekend/</loc>" in xml


def test_build_sitemap_xml_includes_today_and_free_hub_urls():
    # ROADMAP.md item 149: the two new hub-level merged views need to be
    # discoverable the same way /this-weekend already is, or a search
    # engine never learns they exist.
    summaries = [{**REGION, "event_count": 1, "path": "mount-prospect-60056/"}]
    xml = build_digest.build_sitemap_xml(summaries, datetime.now(timezone.utc))
    assert f"<loc>{build_digest.SITE_BASE_URL}today/</loc>" in xml
    assert f"<loc>{build_digest.SITE_BASE_URL}free/</loc>" in xml


def test_build_sitemap_xml_includes_sponsor_url():
    summaries = [{**REGION, "event_count": 1, "path": "mount-prospect-60056/"}]
    xml = build_digest.build_sitemap_xml(summaries, datetime.now(timezone.utc))
    assert f"<loc>{build_digest.SITE_BASE_URL}sponsor/</loc>" in xml


def test_build_sitemap_xml_includes_about_url():
    summaries = [{**REGION, "event_count": 1, "path": "mount-prospect-60056/"}]
    xml = build_digest.build_sitemap_xml(summaries, datetime.now(timezone.utc))
    assert f"<loc>{build_digest.SITE_BASE_URL}about/</loc>" in xml


def test_build_sitemap_xml_includes_trick_or_treat_url():
    summaries = [{**REGION, "event_count": 1, "path": "mount-prospect-60056/"}]
    xml = build_digest.build_sitemap_xml(summaries, datetime.now(timezone.utc))
    assert f"<loc>{build_digest.SITE_BASE_URL}trick-or-treat/</loc>" in xml


def test_collect_sitemap_urls_never_contains_a_year():
    # ROADMAP.md item 160 / DESIGN_PRINCIPLES.md "Permanent URLs": seasonal
    # and recurring pages keep one permanent URL forever, with the year in
    # the content, never the path - a new URL per year starts the
    # backlink/rank clock over from zero. This is the enforcement: no path
    # this function emits may contain a bare four-digit year.
    summaries = [
        {**REGION, "path": "mount-prospect-60056/", "guide_slugs": ["fall-family-guide", "seasonal-circuit-guide"]}
    ]
    urls = build_digest.collect_sitemap_urls(summaries)
    assert urls, "expected at least the hub-level URLs"
    # (?<!\d)\d{4}(?!\d): an isolated 4-digit run, so a 5-digit ZIP in the
    # path (e.g. mount-prospect-60056) doesn't false-positive as a year.
    for url in urls:
        assert not re.search(r"(?<!\d)\d{4}(?!\d)", url), f"URL contains a year: {url}"


def test_build_sitemap_xml_includes_things_to_do_url():
    # ROADMAP.md item 158: the new evergreen page needs to be discoverable
    # the same way /directory/ already is.
    summaries = [{**REGION, "event_count": 1, "path": "mount-prospect-60056/"}]
    xml = build_digest.build_sitemap_xml(summaries, datetime.now(timezone.utc))
    assert f"<loc>{build_digest.SITE_BASE_URL}mount-prospect-60056/things-to-do/</loc>" in xml


def test_build_feed_xml_produces_valid_rss():
    items = [
        {"title": "Fall Fest", "url": "https://x/1", "detail": "Food & drink.", "date_iso": "2026-09-19", "region_name": "Mount Prospect"},
    ]
    xml = build_digest.build_feed_xml(items, datetime.now(timezone.utc))
    root = ET.fromstring(xml)
    assert root.tag == "rss"
    channel = root.find("channel")
    assert channel.find("title").text == "Within Ten — Upcoming Local Events"
    item = channel.find("item")
    assert item.find("title").text == "Mount Prospect: Fall Fest"
    assert item.find("link").text == "https://x/1"
    assert item.find("description").text == "Food & drink."


def test_build_feed_xml_states_source_completeness_when_given():
    # ROADMAP.md item 197
    items = [
        {"title": "Fall Fest", "url": "https://x/1", "detail": "", "date_iso": "2026-09-19", "region_name": "Mount Prospect"},
    ]
    xml = build_digest.build_feed_xml(items, datetime.now(timezone.utc), {"reporting": 22, "expected": 25})
    root = ET.fromstring(xml)
    description = root.find("channel").find("description").text
    assert "reached 22 of 25 configured sources" in description


def test_build_feed_xml_orders_soonest_first():
    items = [
        {"title": "Later", "url": "https://x/2", "detail": "", "date_iso": "2026-10-01", "region_name": "Palatine"},
        {"title": "Sooner", "url": "https://x/1", "detail": "", "date_iso": "2026-09-19", "region_name": "Mount Prospect"},
    ]
    xml = build_digest.build_feed_xml(items, datetime.now(timezone.utc))
    titles = [item.find("title").text for item in ET.fromstring(xml).find("channel").findall("item")]
    assert titles == ["Mount Prospect: Sooner", "Palatine: Later"]


def test_build_feed_xml_caps_at_fifty_items():
    items = [
        {"title": f"Event {i}", "url": f"https://x/{i}", "detail": "", "date_iso": "2026-09-19", "region_name": "Mount Prospect"}
        for i in range(75)
    ]
    xml = build_digest.build_feed_xml(items, datetime.now(timezone.utc))
    assert len(ET.fromstring(xml).find("channel").findall("item")) == 50


def test_build_feed_xml_handles_no_items():
    xml = build_digest.build_feed_xml([], datetime.now(timezone.utc))
    root = ET.fromstring(xml)
    assert root.find("channel").findall("item") == []


def test_build_feed_xml_gives_a_unique_guid_to_events_sharing_one_url():
    # ROADMAP.md item 145: a real bug found in the live feed.xml after
    # item 141 shipped - a recurring event's every occurrence links the
    # same organiser page, and the feed used to emit the byte-identical
    # <guid isPermaLink="true"> for every one of them. Most RSS readers
    # dedupe by guid, so only one of several real, distinct occurrences
    # would ever reach a subscriber.
    items = [
        {"title": "Farmers Market", "url": "https://x/market", "detail": "", "date_iso": "2026-09-20", "region_name": "Mount Prospect"},
        {"title": "Farmers Market", "url": "https://x/market", "detail": "", "date_iso": "2026-09-27", "region_name": "Mount Prospect"},
    ]
    xml = build_digest.build_feed_xml(items, datetime.now(timezone.utc))
    guid_elements = [item.find("guid") for item in ET.fromstring(xml).find("channel").findall("item")]
    guids = [g.text for g in guid_elements]
    assert len(set(guids)) == 2, "each occurrence must get a distinct guid"
    assert all(g.get("isPermaLink") == "false" for g in guid_elements)


def test_build_feed_xml_keeps_a_simple_permalink_guid_when_urls_dont_collide():
    items = [
        {"title": "Fall Fest", "url": "https://x/1", "detail": "", "date_iso": "2026-09-19", "region_name": "Mount Prospect"},
        {"title": "Oktoberfest", "url": "https://x/2", "detail": "", "date_iso": "2026-09-20", "region_name": "Mount Prospect"},
    ]
    xml = build_digest.build_feed_xml(items, datetime.now(timezone.utc))
    for item in ET.fromstring(xml).find("channel").findall("item"):
        guid = item.find("guid")
        assert guid.get("isPermaLink") == "true"
        assert guid.text == item.find("link").text


def test_render_og_image_is_the_expected_raster_size():
    img = build_digest.render_og_image("Mount Prospect", "What's happening — updated weekly")
    assert img.size == (1200, 630)
    assert img.mode == "RGB"


def test_render_og_image_wraps_a_long_title_without_crashing():
    img = build_digest.render_og_image(
        "A Very Long Region Name That Would Never Fit On One Line At This Size",
        "An equally long subtitle that also needs to wrap across more than one line of text",
    )
    assert img.size == (1200, 630)


def test_build_og_images_includes_default_and_one_per_region():
    summaries = [{**REGION, "event_count": 1, "path": "mount-prospect-60056/"}]
    images = build_digest.build_og_images(summaries)
    assert set(images) == {"default", "mount-prospect-60056"}
    assert all(img.size == (1200, 630) for img in images.values())


def test_build_og_images_caption_matches_the_sites_own_update_cadence_claim(monkeypatch):
    # The OG image is what a shared region link actually shows in a
    # preview card - its caption used to say "updated weekly" while
    # every other surface (tagline, the answer block, llms.txt) says
    # "several times a week", the real cadence. Captured via the
    # subtitle argument rather than OCR on the rendered pixels.
    captured = []
    monkeypatch.setattr(
        build_digest, "render_og_image", lambda title, subtitle: captured.append(subtitle)
    )
    summaries = [{**REGION, "event_count": 1, "path": "mount-prospect-60056/"}]
    build_digest.build_og_images(summaries)
    region_subtitle = next(s for s in captured if "Mount Prospect" in s)
    assert "several times a week" in region_subtitle
    assert "weekly" not in region_subtitle


def test_build_robots_txt_references_sitemap():
    robots = build_digest.build_robots_txt()
    assert f"Sitemap: {build_digest.SITE_BASE_URL}sitemap.xml" in robots
    assert "Allow: /" in robots


def test_build_robots_txt_explicitly_allows_ai_crawlers():
    robots = build_digest.build_robots_txt()
    for bot in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"):
        assert f"User-agent: {bot}" in robots
    # Every named crawler must be paired with its own Allow, not just
    # inherit the wildcard block textually above it.
    lines = robots.splitlines()
    for i, line in enumerate(lines):
        if line == "User-agent: GPTBot":
            assert lines[i + 1] == "Allow: /"


def test_build_llms_txt_lists_regions_and_weekend_links():
    summaries = [
        {"name": "Mount Prospect", "zip": "60056", "tagline": "Village news.", "path": "mount-prospect-60056/", "guides": []},
        {"name": "Arlington Heights", "zip": "60005", "tagline": "Village news too.", "path": "arlington-heights-60005/", "guides": []},
    ]
    result = build_digest.build_llms_txt(summaries)
    assert result.startswith(f"# {build_digest.SITE_NAME}")
    assert f"[Mount Prospect (60056)]({build_digest.SITE_BASE_URL}mount-prospect-60056/)" in result
    assert f"[Mount Prospect — this weekend]({build_digest.SITE_BASE_URL}mount-prospect-60056/this-weekend/)" in result
    # ROADMAP.md item 149: same GEO discoverability for the two hub-level
    # views it added.
    assert f"[Across every region]({build_digest.SITE_BASE_URL}today/)" in result
    assert f"[Mount Prospect — today]({build_digest.SITE_BASE_URL}mount-prospect-60056/today/)" in result
    assert f"[Across every region]({build_digest.SITE_BASE_URL}free/)" in result
    assert f"[Mount Prospect — free]({build_digest.SITE_BASE_URL}mount-prospect-60056/free/)" in result
    assert "## Sponsorship" in result
    assert f"## About\n- [Who publishes this, and why]({build_digest.SITE_BASE_URL}about/)" in result


def test_build_llms_txt_states_source_completeness_when_given():
    # ROADMAP.md item 197
    summaries = [
        {"name": "Mount Prospect", "zip": "60056", "tagline": "Village news.", "path": "mount-prospect-60056/", "guides": []},
    ]
    result = build_digest.build_llms_txt(summaries, {"reporting": 22, "expected": 25})
    assert "22 of 25 configured sources reported successfully" in result


def test_build_llms_txt_omits_source_completeness_when_not_given():
    summaries = [
        {"name": "Mount Prospect", "zip": "60056", "tagline": "Village news.", "path": "mount-prospect-60056/", "guides": []},
    ]
    result = build_digest.build_llms_txt(summaries)
    assert "configured sources reported" not in result


def test_build_llms_txt_includes_guides_when_present():
    summaries = [
        {
            "name": "Mount Prospect",
            "zip": "60056",
            "tagline": "Village news.",
            "path": "mount-prospect-60056/",
            "guides": [{"slug": "fall-family-guide", "title": "Fall Family Guide"}],
        }
    ]
    result = build_digest.build_llms_txt(summaries)
    assert "## Guides" in result
    assert f"[Fall Family Guide — Mount Prospect]({build_digest.SITE_BASE_URL}mount-prospect-60056/guides/fall-family-guide/)" in result


def test_build_llms_txt_omits_guides_section_when_none_exist():
    summaries = [{"name": "Mount Prospect", "zip": "60056", "tagline": "x", "path": "mount-prospect-60056/", "guides": []}]
    result = build_digest.build_llms_txt(summaries)
    assert "## Guides" not in result


def test_build_llms_txt_includes_things_to_do_section():
    # ROADMAP.md item 158: the evergreen page needs the same GEO
    # discoverability the This weekend/Today/Free sections already get.
    summaries = [{"name": "Mount Prospect", "zip": "60056", "tagline": "x", "path": "mount-prospect-60056/", "guides": []}]
    result = build_digest.build_llms_txt(summaries)
    assert "## Things to do (evergreen)" in result
    assert f"[Mount Prospect — things to do]({build_digest.SITE_BASE_URL}mount-prospect-60056/things-to-do/)" in result


def test_build_answer_block_mentions_region_name_and_zip():
    # Real current tagline shape (item 126) - a stale generic fixture here
    # would silently stop reflecting what actually renders on the page.
    region = {
        "name": "Mount Prospect",
        "zip": "60056",
        "state": "IL",
        "tagline": "Pulled automatically from the Village, Public Library, and Park "
        "District — plus Randhurst Village, Melas Park, Lions Park, and downtown "
        "Emerson & Busse — several times a week.",
    }
    result = build_digest.build_answer_block(region)
    assert "Mount Prospect" in result
    assert "60056" in result
    word_count = len(result.split())
    assert 30 <= word_count <= 70


def test_build_answer_block_does_not_repeat_taglines_automation_claim():
    # ROADMAP.md Phase 11 #126 rewrote every region's tagline to lead
    # with "Pulled automatically from ... several times a week" - this
    # text is always rendered directly after that tagline in the same
    # on-page paragraph, so it shouldn't say the same thing again in
    # different words right next to it.
    region = {
        "name": "Mount Prospect",
        "zip": "60056",
        "state": "IL",
        "tagline": "Pulled automatically from the Village, Public Library, and Park "
        "District — plus Randhurst Village, Melas Park, Lions Park, and downtown "
        "Emerson & Busse — several times a week.",
    }
    result = build_digest.build_answer_block(region)
    assert result.count("automatically") == 1
    assert "several times a week" not in result.split(region["tagline"])[1]


def test_build_region_map_link_url_uses_region_coordinates():
    region = {"lat": 42.0666, "lon": -87.9373}
    result = build_digest.build_region_map_link_url(region)
    assert result == "https://www.google.com/maps/search/?api=1&query=42.0666,-87.9373"


def test_build_region_map_link_url_returns_none_without_coordinates():
    assert build_digest.build_region_map_link_url({"name": "Nowhere"}) is None


def test_build_freshness_json_ld_is_valid_json_with_date_modified():
    region = {"name": "Mount Prospect"}
    now = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
    result = build_digest.build_freshness_json_ld(region, "https://example.org/mount-prospect-60056/", now)
    parsed = json.loads(result)
    assert parsed["@type"] == "WebPage"
    assert parsed["url"] == "https://example.org/mount-prospect-60056/"
    assert parsed["dateModified"] == now.isoformat()


def test_build_freshness_json_ld_escapes_script_close_tag():
    region = {"name": "Mount Prospect </script><script>alert(1)"}
    now = datetime(2026, 8, 27, tzinfo=timezone.utc)
    result = build_digest.build_freshness_json_ld(region, "https://example.org/", now)
    assert "</script>" not in result


def test_build_weekly_summary_txt_lists_dated_weekend_events():
    region = {"name": "Mount Prospect"}
    events = [
        {"title": "Fall Fest", "date": "Aug 29", "url": "https://x/1"},
        {"title": "Story Time", "date": "Aug 30", "url": "https://x/2"},
    ]
    result = build_digest.build_weekly_summary_txt(
        region, events, [], "https://example.org/mount-prospect-60056/", "Aug 29–30"
    )
    assert "Mount Prospect" in result
    assert "Aug 29–30" in result
    assert "- Aug 29 — Fall Fest" in result
    assert "- Aug 30 — Story Time" in result
    assert result.endswith(
        "https://example.org/mount-prospect-60056/\n"
        "(Pulled automatically from the village, library, and park district — several times a week.)\n"
    )


def test_build_weekly_summary_txt_caps_at_six_events():
    region = {"name": "Mount Prospect"}
    events = [{"title": f"Event {i}", "date": "Aug 29", "url": "https://x"} for i in range(10)]
    result = build_digest.build_weekly_summary_txt(region, events, [], "https://x/", "Aug 29–30")
    assert result.count("- Aug 29") == 6


def test_build_weekly_summary_txt_falls_back_to_free_evergreen_when_nothing_dated():
    region = {"name": "Mount Prospect"}
    evergreen = [
        {"title": "Library Passes", "tags": ["free"]},
        {"title": "Paid Class", "tags": []},
    ]
    result = build_digest.build_weekly_summary_txt(region, [], evergreen, "https://x/", "Aug 29–30")
    assert "- Library Passes" in result
    assert "Paid Class" not in result


def test_build_weekly_summary_txt_honest_empty_state():
    region = {"name": "Mount Prospect"}
    result = build_digest.build_weekly_summary_txt(region, [], [], "https://x/", "Aug 29–30")
    assert "Nothing dated for this weekend yet" in result


def test_build_weekly_summary_txt_keeps_the_link_out_of_the_post_body():
    # ROADMAP.md Phase 11 #76: Facebook down-weights posts with an
    # external link, so the URL must live only in the first-comment
    # block, never in the post body the owner pastes as the post itself.
    region = {"name": "Mount Prospect"}
    events = [{"title": "Fall Fest", "date": "Aug 29", "url": "https://x/1"}]
    result = build_digest.build_weekly_summary_txt(
        region, events, [], "https://example.org/mount-prospect-60056/", "Aug 29–30"
    )
    post_section, comment_section = result.split("FIRST COMMENT")
    assert "https://example.org/mount-prospect-60056/" not in post_section
    assert "https://example.org/mount-prospect-60056/" in comment_section


def test_build_weekly_summary_txt_leads_with_a_subject_line():
    # ROADMAP.md Phase 11 #91: a third, unpasteable place to find the
    # subject line, matching this file's own POST/FIRST COMMENT
    # convention - a label for the reader, not text to copy into
    # Facebook.
    region = {"name": "Mount Prospect"}
    events = [{"title": "Fall Fest", "date": "Aug 29", "url": "https://x/1"}]
    result = build_digest.build_weekly_summary_txt(region, events, [], "https://x/", "Aug 29–30")
    subject = build_digest.build_email_subject_line(region, events)
    assert result.startswith(f"SUBJECT: {subject}\n\n")


def test_build_weekly_summary_txt_post_ends_on_a_question():
    # A reply to your own post is worth roughly 27x a like (same pass's
    # research) - the post should invite that reply, not close on a
    # parenthetical the way the old single-block format did.
    region = {"name": "Mount Prospect"}
    result = build_digest.build_weekly_summary_txt(region, [], [], "https://x/", "Aug 29–30")
    post_section = result.split("FIRST COMMENT")[0]
    assert post_section.strip().endswith("Anything I've missed this weekend?")


def test_build_email_subject_line_names_town_and_leads_with_specific():
    region = {"name": "Mount Prospect"}
    events = [
        {"title": "Oktoberfest", "date": "Sep 18", "url": "https://x/1"},
        {"title": "Fall Festival", "date": "Sep 19", "url": "https://x/2"},
        {"title": "Story Time", "date": "Sep 19", "url": "https://x/3"},
    ]
    subject = build_digest.build_email_subject_line(region, events)
    assert subject == "This weekend in Mount Prospect: Oktoberfest, Fall Festival, and 1 more"


def test_build_email_subject_line_handles_exactly_two_events():
    region = {"name": "Mount Prospect"}
    events = [
        {"title": "Oktoberfest", "date": "Sep 18", "url": "https://x/1"},
        {"title": "Fall Festival", "date": "Sep 19", "url": "https://x/2"},
    ]
    subject = build_digest.build_email_subject_line(region, events)
    assert subject == "This weekend in Mount Prospect: Oktoberfest and Fall Festival"


def test_build_email_subject_line_handles_a_single_event():
    region = {"name": "Mount Prospect"}
    events = [{"title": "Oktoberfest", "date": "Sep 18", "url": "https://x/1"}]
    subject = build_digest.build_email_subject_line(region, events)
    assert subject == "This weekend in Mount Prospect: Oktoberfest"


def test_build_email_subject_line_honest_empty_state():
    region = {"name": "Mount Prospect"}
    subject = build_digest.build_email_subject_line(region, [])
    assert subject == "This weekend in Mount Prospect: what's coming up"


def test_build_email_subject_line_never_names_a_recurring_event():
    # ROADMAP.md item 141: the explicit design caveat - the same standing
    # farmers market named in twenty consecutive subject lines is exactly
    # how a digest starts reading as automated filler. A recurring event
    # still counts toward the "and N more" tally, just never gets named.
    region = {"name": "Mount Prospect"}
    events = [
        {"title": "Farmers Market", "date": "Sep 20", "url": "https://x/1", "recurring": True},
        {"title": "Oktoberfest", "date": "Sep 19", "url": "https://x/2"},
    ]
    subject = build_digest.build_email_subject_line(region, events)
    assert subject == "This weekend in Mount Prospect: Oktoberfest, and 1 more"


def test_build_email_subject_line_falls_back_when_only_recurring_events_exist():
    region = {"name": "Mount Prospect"}
    events = [{"title": "Farmers Market", "date": "Sep 20", "url": "https://x/1", "recurring": True}]
    subject = build_digest.build_email_subject_line(region, events)
    assert subject == "This weekend in Mount Prospect: what's coming up"


def test_build_email_subject_line_skips_a_near_duplicate_second_title():
    # ROADMAP.md Phase 11 #86: the real pair that shipped and prompted
    # this fix - a synthetic "Event A"/"Event B" pair would pass a
    # broken implementation, so this uses the actual colliding titles.
    region = {"name": "Mount Prospect"}
    events = [
        {"title": "Oktoberfest", "date": "Sep 18", "url": "https://x/1"},
        {"title": "Fall Festival & Oktoberfest", "date": "Sep 19", "url": "https://x/2"},
        {"title": "Fishing Derby", "date": "Sep 19", "url": "https://x/3"},
    ]
    subject = build_digest.build_email_subject_line(region, events)
    assert subject == "This weekend in Mount Prospect: Oktoberfest, Fishing Derby, and 1 more"


def test_build_email_subject_line_never_names_an_informational_event():
    # ROADMAP.md Phase 11 #90: the actual live bug this fixes - the real
    # pair from item 86's test plus the real D57 title that got named in
    # production ("This weekend in Mount Prospect: Oktoberfest, Half-Day
    # Student Attendance (Grades 1-8), and 1 more"). With the near-dup
    # excluded from naming and the half-day now excluded from naming
    # entirely, only Oktoberfest is left to name and the count carries
    # the rest - never the half-day, even though it's real content.
    region = {"name": "Mount Prospect"}
    events = [
        {"title": "Oktoberfest", "date": "Sep 18", "url": "https://x/1"},
        {"title": "Fall Festival & Oktoberfest", "date": "Sep 19", "url": "https://x/2"},
        {"title": "Half-Day Student Attendance (Grades 1-8)", "date": "Sep 18", "url": "https://x/3", "attendable": False},
    ]
    subject = build_digest.build_email_subject_line(region, events)
    assert "Half-Day" not in subject
    assert subject == "This weekend in Mount Prospect: Oktoberfest, and 1 more"


def test_build_email_subject_line_falls_back_when_only_informational_events_exist():
    region = {"name": "Mount Prospect"}
    events = [{"title": "Half-Day Student Attendance", "date": "Sep 18", "url": "https://x/1", "attendable": False}]
    subject = build_digest.build_email_subject_line(region, events)
    assert subject == "This weekend in Mount Prospect: what's coming up"


def test_build_combined_email_subject_line_names_regions_with_events():
    # ROADMAP.md Phase 11 #105: one subject line for every region, since
    # Buttondown's free-plan list has no per-region segmentation.
    sections = [
        {"region_name": "Mount Prospect", "weekend_events": [{"title": "Oktoberfest", "attendable": True}]},
        {"region_name": "Arlington Heights", "weekend_events": [{"title": "Harvest Fest", "attendable": True}]},
    ]
    subject = build_digest.build_combined_email_subject_line(sections)
    assert subject == "This weekend across Mount Prospect and Arlington Heights"


def test_build_combined_email_subject_line_excludes_regions_with_no_attendable_events():
    sections = [
        {"region_name": "Mount Prospect", "weekend_events": [{"title": "Oktoberfest", "attendable": True}]},
        {"region_name": "Arlington Heights", "weekend_events": [{"title": "Half-Day", "attendable": False}]},
    ]
    subject = build_digest.build_combined_email_subject_line(sections)
    assert subject == "This weekend across Mount Prospect"


def test_build_combined_email_subject_line_falls_back_when_no_region_has_events():
    sections = [
        {"region_name": "Mount Prospect", "weekend_events": []},
        {"region_name": "Arlington Heights", "weekend_events": []},
        {"region_name": "Des Plaines", "weekend_events": []},
    ]
    subject = build_digest.build_combined_email_subject_line(sections)
    assert subject == "This week across Mount Prospect, Arlington Heights, and Des Plaines: what's coming up"


def test_join_names_handles_an_empty_list_without_crashing():
    # A found bug: with 0 names the old code fell through both length
    # checks into `names[-1]`, an IndexError on an empty list. Only
    # reachable if load_regions() ever returns zero valid region
    # configs, but a malformed build should fail with a clear error,
    # not crash inside string formatting.
    assert build_digest._join_names([]) == ""


def test_build_combined_email_subject_line_does_not_crash_on_no_sections():
    assert build_digest.build_combined_email_subject_line([]) == "This week across : what's coming up"


def test_build_email_subject_line_names_only_the_first_when_everything_collides():
    region = {"name": "Mount Prospect"}
    events = [
        {"title": "Oktoberfest", "date": "Sep 18", "url": "https://x/1"},
        {"title": "Fall Festival & Oktoberfest", "date": "Sep 19", "url": "https://x/2"},
        {"title": "Oktoberfest Weekend", "date": "Sep 19", "url": "https://x/3"},
    ]
    subject = build_digest.build_email_subject_line(region, events)
    assert subject == "This weekend in Mount Prospect: Oktoberfest, and 2 more"


def test_render_email_digest_lists_weekend_events():
    region = {"name": "Mount Prospect"}
    events = [{"title": "Fall Fest", "date": "Aug 29", "url": "https://x/1"}]
    html = build_digest.render_email_digest(region, events, [], "https://x/mount-prospect-60056/", "Aug 29–30", None)
    assert "Fall Fest" in html
    assert "Mount Prospect" in html
    assert "Aug 29–30" in html


def test_render_email_digest_asks_for_a_reply_in_the_footer():
    # ROADMAP.md item 157: a reply is a stronger deliverability signal
    # than the click-through CTA, and replies now reach a real inbox
    # (item 93) - a quiet footer line asking for one, not a competing
    # button.
    region = {"name": "Mount Prospect"}
    html = build_digest.render_email_digest(region, [], [], "https://x/mount-prospect-60056/", "Aug 29–30", None)
    assert "Hit reply" in html


def test_render_email_digest_shows_subscribe_link_when_newsletter_configured():
    # ROADMAP.md item 183: a forwarded email had nowhere for a new
    # reader to click to join - one quiet subscribe link, gated the
    # same way the rest of the newsletter feature is (item 34).
    region = {"name": "Mount Prospect"}
    newsletter = {"configured": True, "buttondown_username": "withinten"}
    html = build_digest.render_email_digest(
        region, [], [], "https://x/", "Aug 29–30", None, newsletter
    )
    assert "https://buttondown.com/withinten" in html
    assert "Forwarded this?" in html


def test_render_email_digest_omits_subscribe_link_when_newsletter_unconfigured():
    region = {"name": "Mount Prospect"}
    html = build_digest.render_email_digest(region, [], [], "https://x/", "Aug 29–30", None, None)
    assert "Forwarded this?" not in html
    assert "buttondown.com" not in html


def test_render_email_digest_body_type_meets_the_16px_mobile_floor():
    # ROADMAP.md Phase 11 #97: 55%+ of opens are mobile and the stated
    # floor is 16px, but event titles shipped at 15px and dates/details
    # at 13px. Titles (and title-style links like a sponsor recommendation
    # or an evergreen highlight) are 16px; secondary lines (dates,
    # details, informational items, sponsor spotlight quotes) are 14px.
    # Eyebrow labels/footer/wordmark are deliberately smaller kickers,
    # not body copy, and are unaffected.
    region = {"name": "Mount Prospect"}
    events = [
        {"title": "Fall Fest", "date": "Aug 29", "url": "https://x/1", "detail": "Live music."},
        {"title": "Half-Day Student Attendance", "date": "Aug 29", "url": "https://x/2", "attendable": False},
    ]
    sponsor = {
        "title": "Acme Dentistry",
        "url": "https://x/3",
        "detail": "Family dentistry",
        "is_active_sponsor": True,
        "spotlight": {"years_in_town": "Open since 1998."},
    }
    html = build_digest.render_email_digest(region, events, [], "https://x/", "Aug 29–30", sponsor)
    assert "font-size:15px" not in html
    # The wordmark ("WITHIN TEN") deliberately stays at 13px - a brand
    # mark, not body copy - so this checks the specific event/sponsor
    # rows rather than asserting no 13px survives anywhere in the file.
    assert 'font-size:16px; color:#201e1d; padding-bottom:2px;">\n<a href="https://x/1"' in html
    assert "font-size:14px; color:#ae1800;" in html  # event date
    assert "font-size:14px; color:#605d5d; padding-top:2px;" in html  # event detail
    assert "font-size:16px; color:#201e1d;\">\n<a href=\"https://x/3\"" in html  # sponsor title link
    assert "Open since 1998." in html


def test_render_email_digest_shows_the_event_detail_line():
    # ROADMAP.md Phase 11 #87: the row used to stop at title + date,
    # even though detail was already fetched, truncated, and passed
    # into this same event dict.
    region = {"name": "Mount Prospect"}
    events = [
        {"title": "Fall Fest", "date": "Aug 29", "url": "https://x/1", "detail": "Live music and food trucks."}
    ]
    html = build_digest.render_email_digest(region, events, [], "https://x/", "Aug 29–30", None)
    assert "Live music and food trucks." in html


def test_render_email_digest_omits_detail_row_when_none_given():
    region = {"name": "Mount Prospect"}
    events = [{"title": "Fall Fest", "date": "Aug 29", "url": "https://x/1"}]
    html = build_digest.render_email_digest(region, events, [], "https://x/", "Aug 29–30", None)
    # No crash, no stray empty <td> content - just confirms the {% if
    # event.detail %} guard works when the key is genuinely absent.
    assert "Fall Fest" in html


def test_render_email_digest_shows_house_ad_when_sponsor_is_inactive():
    # ROADMAP.md Phase 11 #88: an unsold slot falls back to the house ad
    # on the region page already - the email used to fall back to
    # nothing, so the artifact most likely to reach a local business
    # owner never mentioned the slot was for sale.
    region = {"name": "Mount Prospect"}
    house_ad = {
        "title": "Sponsor this spot",
        "detail": "Reach local families every week.",
        "url": "https://withintenmiles.com/sponsor/",
        "is_active_sponsor": False,
    }
    html = build_digest.render_email_digest(region, [], [], "https://x/", "Aug 29–30", house_ad)
    assert "SPONSOR THIS SPOT" in html
    assert "Reach local families every week." in html
    assert "https://withintenmiles.com/sponsor/" in html


def test_render_email_digest_omits_house_ad_when_sponsor_is_none():
    region = {"name": "Mount Prospect"}
    html = build_digest.render_email_digest(region, [], [], "https://x/", "Aug 29–30", None)
    assert "SPONSOR THIS SPOT" not in html


def test_render_email_digest_always_shows_the_subject_line_in_title():
    region = {"name": "Mount Prospect"}
    events = [{"title": "Fall Fest", "date": "Aug 29", "url": "https://x/1"}]
    html = build_digest.render_email_digest(region, events, [], "https://x/", "Aug 29–30", None)
    subject = build_digest.build_email_subject_line(region, events)
    assert f"<title>{subject}</title>" in html


def test_render_email_digest_preview_shows_subject_annotation_in_body():
    # ROADMAP.md Phase 11 #91: the annotation only belongs in the
    # preview file - a real send shipped it as body copy because the
    # paste-this-whole-file workflow pastes the warning along with it.
    region = {"name": "Mount Prospect"}
    events = [{"title": "Fall Fest", "date": "Aug 29", "url": "https://x/1"}]
    subject = build_digest.build_email_subject_line(region, events)
    preview_html = build_digest.render_email_digest(region, events, [], "https://x/", "Aug 29–30", None, preview=True)
    assert "PREVIEW ONLY" in preview_html
    assert subject in preview_html.split("</title>")[1]


def test_render_email_digest_send_file_omits_preview_annotation():
    region = {"name": "Mount Prospect"}
    events = [{"title": "Fall Fest", "date": "Aug 29", "url": "https://x/1"}]
    send_html = build_digest.render_email_digest(region, events, [], "https://x/", "Aug 29–30", None)
    assert "PREVIEW ONLY" not in send_html


def test_render_email_digest_falls_back_to_free_evergreen_when_nothing_dated():
    region = {"name": "Mount Prospect"}
    evergreen = [{"title": "Library Passes", "url": "https://x/2", "tags": ["free"]}, {"title": "Paid Class", "url": "https://x/3", "tags": []}]
    html = build_digest.render_email_digest(region, [], evergreen, "https://x/", "Aug 29–30", None)
    assert "Library Passes" in html
    assert "Paid Class" not in html


def test_render_email_digest_groups_informational_events_under_also_this_week():
    # ROADMAP.md Phase 11 #90: a school half-day still belongs in the
    # email as real content, but grouped under its own line rather than
    # rendered as an equal-weight event card.
    region = {"name": "Mount Prospect"}
    events = [
        {"title": "Fall Fest", "date": "Aug 29", "url": "https://x/1", "attendable": True},
        {"title": "Half-Day Student Attendance", "date": "Aug 29", "url": "https://x/2", "attendable": False},
    ]
    html = build_digest.render_email_digest(region, events, [], "https://x/", "Aug 29–30", None)
    assert "ALSO THIS WEEK" in html
    assert "Half-Day Student Attendance" in html
    # Not rendered as its own linked event card - the informational
    # line has no <a href> for it.
    assert '<a href="https://x/2"' not in html


def test_render_email_digest_omits_also_this_week_when_nothing_informational():
    region = {"name": "Mount Prospect"}
    events = [{"title": "Fall Fest", "date": "Aug 29", "url": "https://x/1", "attendable": True}]
    html = build_digest.render_email_digest(region, events, [], "https://x/", "Aug 29–30", None)
    assert "ALSO THIS WEEK" not in html


def test_render_email_digest_shows_also_this_week_even_with_no_attendable_events():
    region = {"name": "Mount Prospect"}
    events = [{"title": "Half-Day Student Attendance", "date": "Aug 29", "url": "https://x/1", "attendable": False}]
    html = build_digest.render_email_digest(region, events, [], "https://x/", "Aug 29–30", None)
    assert "ALSO THIS WEEK" in html
    assert "Half-Day Student Attendance" in html
    assert "Nothing dated for this weekend yet" in html


def test_render_email_digest_honest_empty_state():
    region = {"name": "Mount Prospect"}
    html = build_digest.render_email_digest(region, [], [], "https://x/", "Aug 29–30", None)
    assert "Nothing dated for this weekend yet" in html


def test_render_combined_email_digest_shows_every_region():
    # ROADMAP.md Phase 11 #105: the real defect this closes - a
    # subscriber from any region besides Mount Prospect got the wrong
    # town's weekend. Every region must appear in the one issue.
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": "https://x/mount-prospect-60056/",
            "weekend_events": [{"title": "Oktoberfest", "date": "Sep 18", "url": "https://x/1", "attendable": True}],
            "evergreen": [],
            "sponsor": None,
        },
        {
            "region_name": "Arlington Heights",
            "region_url": "https://x/arlington-heights-60005/",
            "weekend_events": [],
            "evergreen": [{"title": "Memorial Library", "url": "https://x/2", "tags": ["free"]}],
            "sponsor": None,
        },
    ]
    html = build_digest.render_combined_email_digest(sections, "Sep 18–20", datetime.now(timezone.utc))
    assert "Mount Prospect" in html
    assert "Oktoberfest" in html
    assert "Arlington Heights" in html
    assert "Memorial Library" in html
    assert 'href="https://x/mount-prospect-60056/"' in html
    assert 'href="https://x/arlington-heights-60005/"' in html


def test_render_combined_email_digest_asks_for_a_reply_in_the_footer():
    # ROADMAP.md item 157: same reply-ask footer line as the per-region
    # email, once for the whole combined issue.
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": "https://x/mount-prospect-60056/",
            "weekend_events": [],
            "evergreen": [],
            "sponsor": None,
        }
    ]
    html = build_digest.render_combined_email_digest(sections, "Sep 18–20", datetime.now(timezone.utc))
    assert "Hit reply" in html


def test_render_combined_email_digest_shows_subscribe_link_when_newsletter_configured():
    # ROADMAP.md item 183: same forward-dead-end fix as the per-region
    # email, applied to the combined issue.
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": "https://x/mount-prospect-60056/",
            "weekend_events": [],
            "evergreen": [],
            "sponsor": None,
        }
    ]
    newsletter = {"configured": True, "buttondown_username": "withinten"}
    html = build_digest.render_combined_email_digest(
        sections, "Sep 18–20", datetime.now(timezone.utc), newsletter
    )
    assert "https://buttondown.com/withinten" in html
    assert "Forwarded this?" in html


def test_render_combined_email_digest_omits_subscribe_link_when_newsletter_unconfigured():
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": "https://x/mount-prospect-60056/",
            "weekend_events": [],
            "evergreen": [],
            "sponsor": None,
        }
    ]
    html = build_digest.render_combined_email_digest(sections, "Sep 18–20", datetime.now(timezone.utc))
    assert "Forwarded this?" not in html
    assert "buttondown.com" not in html


def test_render_combined_email_digest_groups_informational_events_per_region():
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": "https://x/mount-prospect-60056/",
            "weekend_events": [
                {"title": "Oktoberfest", "date": "Sep 18", "url": "https://x/1", "attendable": True},
                {"title": "Half-Day Student Attendance", "date": "Sep 18", "url": "https://x/2", "attendable": False},
            ],
            "evergreen": [],
            "sponsor": None,
        }
    ]
    html = build_digest.render_combined_email_digest(sections, "Sep 18–20", datetime.now(timezone.utc))
    assert "ALSO THIS WEEK" in html
    assert "Half-Day Student Attendance" in html


def test_render_combined_email_digest_shows_active_sponsor_per_region():
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": "https://x/mount-prospect-60056/",
            "weekend_events": [],
            "evergreen": [],
            "sponsor": {"title": "Acme Dentistry", "url": "https://x/3", "is_active_sponsor": True},
        }
    ]
    html = build_digest.render_combined_email_digest(sections, "Sep 18–20", datetime.now(timezone.utc))
    assert "Acme Dentistry" in html
    assert "LOCAL RECOMMENDATION" in html


def test_render_combined_email_digest_shows_house_ad_for_inactive_sponsor():
    # A real bug found by a code-review pass: the combined email (the
    # one actually mailed, item 105) originally had no house-ad
    # fallback at all for an unsold slot, unlike the single-region
    # email and the region page - contradicting item 88's own point
    # that the email shouldn't be the one artifact that never mentions
    # a slot is for sale.
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": "https://x/mount-prospect-60056/",
            "weekend_events": [],
            "evergreen": [],
            "sponsor": {"title": "Sponsor this spot", "detail": "Reach local families.", "url": "https://x/sponsor/", "is_active_sponsor": False},
        }
    ]
    html = build_digest.render_combined_email_digest(sections, "Sep 18–20", datetime.now(timezone.utc))
    assert "LOCAL RECOMMENDATION" not in html
    assert "SPONSOR THIS SPOT" in html
    assert "Reach local families." in html


def test_render_combined_email_digest_shows_house_ad_once_not_per_region():
    # ROADMAP.md item 169: a real bug found by reading what Wednesday's
    # issue actually sends - every unsold region rendered its own
    # "SPONSOR THIS SPOT" block, so a free digest with one subscriber
    # and no sponsors carried five sales pitches. House ads are
    # inventory notices and appear at most once per artifact.
    house_ad = {"title": "Sponsor this spot", "detail": "Reach local families.", "url": "https://x/sponsor/", "is_active_sponsor": False}
    sections = [
        {
            "region_name": name,
            "region_url": f"https://x/{name}/",
            "weekend_events": [],
            "evergreen": [],
            "sponsor": house_ad,
        }
        for name in ["Mount Prospect", "Arlington Heights", "Des Plaines", "Palatine", "Wheeling"]
    ]
    html = build_digest.render_combined_email_digest(sections, "Sep 18–20", datetime.now(timezone.utc))
    assert html.count("SPONSOR THIS SPOT") == 1


def test_render_combined_email_digest_shows_active_sponsor_and_house_ad_together():
    # A real paying sponsor keeps its own per-region placement (that's
    # what the tier sells) even while the one shared house-ad notice
    # still runs once for every other region with nothing sold.
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": "https://x/mount-prospect-60056/",
            "weekend_events": [],
            "evergreen": [],
            "sponsor": {"title": "Acme Dentistry", "url": "https://x/3", "is_active_sponsor": True},
        },
        {
            "region_name": "Arlington Heights",
            "region_url": "https://x/arlington-heights-60005/",
            "weekend_events": [],
            "evergreen": [],
            "sponsor": {"title": "Sponsor this spot", "detail": "Reach local families.", "url": "https://x/sponsor/", "is_active_sponsor": False},
        },
    ]
    html = build_digest.render_combined_email_digest(sections, "Sep 18–20", datetime.now(timezone.utc))
    assert html.count("LOCAL RECOMMENDATION") == 1
    assert html.count("SPONSOR THIS SPOT") == 1
    assert "Acme Dentistry" in html


def test_render_combined_email_digest_omits_sponsor_block_when_sponsor_is_none():
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": "https://x/mount-prospect-60056/",
            "weekend_events": [],
            "evergreen": [],
            "sponsor": None,
        }
    ]
    html = build_digest.render_combined_email_digest(sections, "Sep 18–20", datetime.now(timezone.utc))
    assert "LOCAL RECOMMENDATION" not in html
    assert "SPONSOR THIS SPOT" not in html


def test_render_combined_email_digest_shows_informational_events_with_no_attendable_events():
    # The real bug: a region with only a non-attendable event (a school
    # half-day) and no attendable events or evergreen highlights used to
    # silently drop it, because the template only checked
    # informational_events inside the attendable_events branch.
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": "https://x/mount-prospect-60056/",
            "weekend_events": [
                {"title": "Half-Day Student Attendance", "date": "Sep 18", "url": "https://x/1", "attendable": False}
            ],
            "evergreen": [],
            "sponsor": None,
        }
    ]
    html = build_digest.render_combined_email_digest(sections, "Sep 18–20", datetime.now(timezone.utc))
    assert "ALSO THIS WEEK" in html
    assert "Half-Day Student Attendance" in html
    # Not the honest-empty-state message too - that would read as a
    # contradiction alongside the real informational item just shown.
    assert "Nothing dated for this weekend yet" not in html


def test_render_combined_email_digest_shows_informational_events_alongside_evergreen():
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": "https://x/mount-prospect-60056/",
            "weekend_events": [
                {"title": "Half-Day Student Attendance", "date": "Sep 18", "url": "https://x/1", "attendable": False}
            ],
            "evergreen": [{"title": "Library Passes", "url": "https://x/2", "tags": ["free"]}],
            "sponsor": None,
        }
    ]
    html = build_digest.render_combined_email_digest(sections, "Sep 18–20", datetime.now(timezone.utc))
    assert "ALSO THIS WEEK" in html
    assert "Half-Day Student Attendance" in html
    assert "Library Passes" in html


def test_render_combined_email_digest_preview_shows_annotation():
    sections = [{"region_name": "Mount Prospect", "region_url": "https://x/", "weekend_events": [], "evergreen": [], "sponsor": None}]
    preview_html = build_digest.render_combined_email_digest(sections, "Sep 18–20", datetime.now(timezone.utc), preview=True)
    send_html = build_digest.render_combined_email_digest(sections, "Sep 18–20", datetime.now(timezone.utc))
    assert "PREVIEW ONLY" in preview_html
    assert "PREVIEW ONLY" not in send_html


def test_pick_evergreen_highlights_draws_from_more_than_one_source():
    # ROADMAP.md item 177: every region's evergreen list only ever has
    # one "free"-tagged entry (the library), so the old
    # `[e for e in evergreen if "free" in tags][:3]` filter always
    # returned exactly that one item regardless of its own slice limit -
    # this is the real shape (library, park district, village) each
    # region's config actually has.
    evergreen = [
        {"title": "Mount Prospect Public Library", "url": "https://x/1", "tags": ["free"]},
        {"title": "Mount Prospect Park District", "url": "https://x/2", "tags": ["outdoor"]},
        {"title": "Village of Mount Prospect", "url": "https://x/3", "tags": []},
    ]
    picks = build_digest._pick_evergreen_highlights(evergreen, limit=2)
    titles = [p["title"] for p in picks]
    assert titles == ["Mount Prospect Public Library", "Mount Prospect Park District"]


def test_pick_evergreen_highlights_fills_from_other_sources_with_no_free_tag():
    evergreen = [
        {"title": "Village of X", "url": "https://x/1", "tags": []},
        {"title": "X High School Athletics", "url": "https://x/2", "tags": []},
    ]
    picks = build_digest._pick_evergreen_highlights(evergreen, limit=1)
    assert [p["title"] for p in picks] == ["Village of X"]


def test_render_combined_email_digest_collapses_two_or_more_empty_regions():
    # ROADMAP.md item 177 (forty-first research pass): a real thin-week
    # build had four of five region blocks read the identical "Nothing
    # new dated for this weekend yet, but worth knowing about:"
    # sentence. Two or more genuinely empty regions (no attendable
    # event, no informational note, no active sponsor) now collapse
    # into one shared block instead of repeating that sentence once
    # per region.
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": "https://x/mount-prospect-60056/",
            "weekend_events": [{"title": "Farmers Market", "date": "Sep 20", "url": "https://x/0", "attendable": True}],
            "evergreen": [],
            "sponsor": None,
        }
    ] + [
        {
            "region_name": name,
            "region_url": f"https://x/{name}/",
            "weekend_events": [],
            "evergreen": [{"title": f"{name} Library", "url": f"https://x/{name}/lib", "tags": ["free"]}],
            "sponsor": None,
        }
        for name in ["Arlington Heights", "Des Plaines", "Palatine", "Wheeling"]
    ]
    html = build_digest.render_combined_email_digest(sections, "Sep 18–20", datetime.now(timezone.utc))
    # The identical per-region sentence never repeats...
    assert "Nothing new dated for this weekend yet, but worth knowing about:" not in html
    # ...replaced by one shared line naming every empty region...
    assert "Nothing dated yet in Arlington Heights, Des Plaines, Palatine, or Wheeling" in html
    # ...each still linking to its own real evergreen pick.
    assert "Arlington Heights Library" in html
    assert "Des Plaines Library" in html
    assert "Palatine Library" in html
    assert "Wheeling Library" in html
    assert "Farmers Market" in html


def test_render_combined_email_digest_does_not_collapse_a_single_empty_region():
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": "https://x/mount-prospect-60056/",
            "weekend_events": [{"title": "Farmers Market", "date": "Sep 20", "url": "https://x/0", "attendable": True}],
            "evergreen": [],
            "sponsor": None,
        },
        {
            "region_name": "Arlington Heights",
            "region_url": "https://x/arlington-heights-60005/",
            "weekend_events": [],
            "evergreen": [{"title": "AH Library", "url": "https://x/ah-lib", "tags": ["free"]}],
            "sponsor": None,
        },
    ]
    html = build_digest.render_combined_email_digest(sections, "Sep 18–20", datetime.now(timezone.utc))
    assert "Nothing new dated for this weekend yet, but worth knowing about:" in html
    assert "Nothing dated yet in" not in html


def test_render_combined_email_digest_excludes_sponsored_region_from_collapse():
    # A paying sponsor's placement (item 169's per-region tier) must not
    # get folded into the shared empty-regions block even when every
    # other region collapses - that placement is what the tier sells.
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": "https://x/mount-prospect-60056/",
            "weekend_events": [],
            "evergreen": [],
            "sponsor": {"title": "Acme Dentistry", "url": "https://x/3", "is_active_sponsor": True},
        }
    ] + [
        {
            "region_name": name,
            "region_url": f"https://x/{name}/",
            "weekend_events": [],
            "evergreen": [],
            "sponsor": None,
        }
        for name in ["Arlington Heights", "Des Plaines"]
    ]
    html = build_digest.render_combined_email_digest(sections, "Sep 18–20", datetime.now(timezone.utc))
    assert "LOCAL RECOMMENDATION" in html
    assert "Acme Dentistry" in html
    assert "Nothing dated yet in Arlington Heights or Des Plaines" in html


def test_render_email_digest_shows_sponsor_only_when_active():
    region = {"name": "Mount Prospect"}
    inactive = {"title": "Sponsor this spot", "detail": "", "url": "", "is_active_sponsor": False}
    html = build_digest.render_email_digest(region, [], [], "https://x/", "Aug 29–30", inactive)
    assert "LOCAL RECOMMENDATION" not in html

    active = {"title": "Acme Cafe", "detail": "Coffee.", "url": "https://acme.example/", "is_active_sponsor": True}
    html = build_digest.render_email_digest(region, [], [], "https://x/", "Aug 29–30", active)
    assert "LOCAL RECOMMENDATION" in html
    assert "Acme Cafe" in html


def test_render_email_digest_shows_sponsor_spotlight_answers_when_present():
    region = {"name": "Mount Prospect"}
    sponsor = {
        "title": "Acme Cafe",
        "detail": "Coffee.",
        "url": "https://acme.example/",
        "is_active_sponsor": True,
        "spotlight": {
            "years_in_town": "On Main Street since 1998.",
            "regulars_pick": "Everyone asks for the cinnamon roll.",
        },
    }
    html = build_digest.render_email_digest(region, [], [], "https://x/", "Aug 29–30", sponsor)
    assert "On Main Street since 1998." in html
    assert "Everyone asks for the cinnamon roll." in html


def test_render_email_digest_omits_spotlight_block_when_absent():
    region = {"name": "Mount Prospect"}
    sponsor = {"title": "Acme Cafe", "detail": "Coffee.", "url": "https://acme.example/", "is_active_sponsor": True}
    html = build_digest.render_email_digest(region, [], [], "https://x/", "Aug 29–30", sponsor)
    assert "years_in_town" not in html


def test_render_email_digest_shows_only_the_spotlight_fields_that_were_answered():
    # A business shouldn't have to answer all three questions to get a
    # clean render - each field is independently optional.
    region = {"name": "Mount Prospect"}
    sponsor = {
        "title": "Acme Cafe",
        "detail": "Coffee.",
        "url": "https://acme.example/",
        "is_active_sponsor": True,
        "spotlight": {"hidden_gem": "We roast our own beans on Tuesdays."},
    }
    html = build_digest.render_email_digest(region, [], [], "https://x/", "Aug 29–30", sponsor)
    assert "We roast our own beans on Tuesdays." in html


def test_render_email_digest_uses_only_table_based_layout_no_flexbox_or_grid():
    # ROADMAP.md Phase 11 #36's whole reason to exist: Outlook renders
    # through Word's engine, which understands tables but not flexbox or
    # CSS grid - so neither may ever appear in this template's output.
    region = {"name": "Mount Prospect"}
    html = build_digest.render_email_digest(region, [], [], "https://x/", "Aug 29–30", None)
    assert "display:flex" not in html
    assert "display: flex" not in html
    assert "display:grid" not in html
    assert "display: grid" not in html
    assert "<table" in html


def test_render_email_digest_stays_well_under_gmails_clipping_limit():
    # Gmail clips anything over ~102KB of HTML and hides the CTA behind a
    # "message clipped" notice - a real per-region digest should never be
    # anywhere close, even with a full six-event weekend and an active
    # sponsor block.
    region = {"name": "Mount Prospect"}
    events = [{"title": f"Event {i}", "date": "Aug 29", "url": "https://x/" + str(i)} for i in range(6)]
    sponsor = {"title": "Acme Cafe", "detail": "Coffee and pastries.", "url": "https://acme.example/", "is_active_sponsor": True}
    html = build_digest.render_email_digest(region, events, [], "https://x/", "Aug 29–30", sponsor)
    assert len(html.encode("utf-8")) < 20_000


def test_build_freshness_json_ld_names_the_site_consistently():
    # Entity-naming audit (ROADMAP.md Phase 11 #22 follow-up): every page
    # should name the site the same way, and link back to one canonical
    # WebSite entity rather than leaving identity to be inferred.
    region = {"name": "Mount Prospect"}
    now = datetime(2026, 8, 27, tzinfo=timezone.utc)
    result = build_digest.build_freshness_json_ld(region, "https://example.org/mount-prospect-60056/", now)
    parsed = json.loads(result)
    assert parsed["name"] == f"Mount Prospect — {build_digest.SITE_NAME}"
    assert parsed["isPartOf"] == {
        "@type": "WebSite",
        "name": build_digest.SITE_NAME,
        "url": build_digest.SITE_BASE_URL,
        "publisher": {"@id": build_digest.ORGANIZATION_ID},
    }


def test_build_organization_json_ld_defines_the_referenced_entity():
    # ROADMAP.md Phase 11 #99: the WebSite's publisher above is only a
    # reference (@id) - this is the one place the Organization entity
    # is fully defined, so the @id has to actually match.
    result = build_digest.build_organization_json_ld()
    parsed = json.loads(result)
    assert parsed["@type"] == "Organization"
    assert parsed["@id"] == build_digest.ORGANIZATION_ID
    assert parsed["name"] == build_digest.SITE_NAME
    assert parsed["url"] == build_digest.SITE_BASE_URL
    # No fabricated logo/sameAs - neither a logo asset nor a real social
    # profile exists yet, and inventing either breaks every other GEO
    # item's never-fabricate-a-fact discipline.
    assert "logo" not in parsed
    assert "sameAs" not in parsed
    # ROADMAP.md item 130: a real name is now known, so it belongs here
    # too - the same entity-authority signal as the About page's prose.
    assert parsed["founder"] == {"@type": "Person", "name": "Ryan Anderson"}


def test_render_region_page_title_uses_canonical_site_name():
    # Regression guard for the bug this audit found: region pages
    # independently built a shortened "Weekend Planner" title while every
    # other page said "Weekend & Trip Planner" - one entity, two strings.
    html = build_digest.render_region_page(
        {"region": REGION}, [], {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc),
    )
    assert build_digest.SITE_NAME in html
    assert "Weekend Planner<" not in html


def test_render_region_page_instruments_sponsor_click_when_analytics_configured():
    sponsor = {"title": "Acme Dentistry", "detail": "Gentle with kids.", "url": "https://acme.example/", "is_active_sponsor": True}
    html = build_digest.render_region_page(
        {"region": REGION}, [], sponsor, [], datetime.now(timezone.utc),
        analytics={"configured": True, "goatcounter_code": "example"},
    )
    assert 'data-goatcounter-click="sponsor-click-mount-prospect-60056"' in html


def test_render_region_page_omits_sponsor_click_tracking_when_analytics_unconfigured():
    sponsor = {"title": "Acme Dentistry", "detail": "Gentle with kids.", "url": "https://acme.example/", "is_active_sponsor": True}
    html = build_digest.render_region_page(
        {"region": REGION}, [], sponsor, [], datetime.now(timezone.utc),
        analytics={"configured": False, "goatcounter_code": None},
    )
    assert "data-goatcounter-click" not in html


def test_build_guide_faq_returns_four_real_questions():
    region = {"name": "Mount Prospect", "zip": "60056", "state": "IL"}
    faq = build_digest.build_guide_faq(region, "https://example.org/mount-prospect-60056/")
    assert len(faq) == 4
    for item in faq:
        assert item["question"].strip()
        assert item["answer"].strip()


def test_build_guide_faq_links_point_at_the_regions_own_pages():
    region = {"name": "Mount Prospect", "zip": "60056", "state": "IL"}
    faq = build_digest.build_guide_faq(region, "https://example.org/mount-prospect-60056/")
    weekend_answer = next(i["answer"] for i in faq if "weekend" in i["question"].lower())
    assert "https://example.org/mount-prospect-60056/this-weekend/" in weekend_answer


def test_build_faq_json_ld_matches_visible_answer_text():
    faq = [{"question": "Q1?", "answer": "A1 with a <a href=\"https://example.org/\">link</a>."}]
    result = build_digest.build_faq_json_ld(faq)
    parsed = json.loads(result)
    assert parsed["@type"] == "FAQPage"
    entity = parsed["mainEntity"][0]
    assert entity["name"] == "Q1?"
    # The JSON-LD answer text must be the exact same string rendered
    # visibly on the page - Google's FAQPage guidance treats a mismatch,
    # or hidden-only answer text, as unreliable.
    assert entity["acceptedAnswer"]["text"] == faq[0]["answer"]


def test_build_faq_json_ld_escapes_script_close_tag():
    faq = [{"question": "Q</script><script>alert(1)", "answer": "A"}]
    result = build_digest.build_faq_json_ld(faq)
    assert "</script>" not in result


def _stub_fetcher(items):
    return lambda *a, **k: items


def test_fetch_region_sections_applies_source_default_tags(monkeypatch):
    """A source's `default_tags` reach the rendered event, merged with the
    heuristic ones rather than replacing them.

    Covers the wiring a live fetch would exercise - Randhurst Village's
    listings rarely use the word "free", so without this the Free filter
    and the /free/ view would never surface them.
    """
    monkeypatch.setitem(
        build_digest.FETCHERS, "html_events",
        _stub_fetcher([{"title": "Street Fest", "detail": "Rides and inflatables in the park.",
                        "url": "https://example.test/fest", "date": None}]),
    )
    region_cfg = {
        "region": {"id": "testville", "name": "Testville"},
        "sources": [{
            "name": "Randhurst Village — Events", "type": "html_events",
            "url": "https://example.test/events", "section": "Randhurst Village",
            "default_tags": ["free"], "enabled": True,
        }],
    }
    tags = build_digest.fetch_region_sections(region_cfg)[0]["events"][0]["tags"]
    assert "free" in tags, tags
    # the heuristic still contributes on top - "park" implies outdoor
    assert "outdoor" in tags, tags


def test_fetch_region_sections_without_default_tags_is_unchanged(monkeypatch):
    monkeypatch.setitem(
        build_digest.FETCHERS, "html_events",
        _stub_fetcher([{"title": "Ticketed Show", "detail": "A concert.",
                        "url": "https://example.test/show", "date": None}]),
    )
    region_cfg = {
        "region": {"id": "testville", "name": "Testville"},
        "sources": [{
            "name": "Some Venue", "type": "html_events", "url": "https://example.test/e",
            "section": "Venue", "enabled": True,
        }],
    }
    assert "free" not in build_digest.fetch_region_sections(region_cfg)[0]["events"][0]["tags"]


def test_load_maps_config_defaults_to_osm():
    cfg = build_digest.load_maps_config({})
    assert cfg["provider"] == "osm"


def test_load_maps_config_falls_back_when_google_key_missing():
    # A keyless Google embed renders a grey "for development purposes
    # only" wash, which is worse than OSM working - so fall back.
    cfg = build_digest.load_maps_config({"provider": "google", "google_api_key": None})
    assert cfg["provider"] == "osm"


def test_load_maps_config_uses_google_when_key_present():
    cfg = build_digest.load_maps_config({"provider": "google", "google_api_key": "abc123"})
    assert cfg["provider"] == "google"
    assert cfg["google_api_key"] == "abc123"


def test_build_region_map_embed_url_osm_includes_bbox_and_marker():
    url = build_digest.build_region_map_embed_url(
        {"lat": 42.0666, "lon": -87.9373}, {"provider": "osm"}
    )
    assert url.startswith("https://www.openstreetmap.org/export/embed.html")
    assert "bbox=" in url and "marker=42.0666,-87.9373" in url


def test_build_region_map_embed_url_google_when_configured():
    url = build_digest.build_region_map_embed_url(
        {"lat": 42.0666, "lon": -87.9373},
        {"provider": "google", "google_api_key": "k e y"},
    )
    assert url.startswith("https://www.google.com/maps/embed/v1/view")
    # the key is percent-encoded, not interpolated raw
    assert "key=k%20e%20y" in url
    assert "center=42.0666,-87.9373" in url


def test_build_region_map_embed_url_none_without_coordinates():
    assert build_digest.build_region_map_embed_url({}, {"provider": "osm"}) is None


# ROADMAP.md Phase 11 #116: each region's tagline must name at least two
# real venues, not the generic "village news, library events, and park
# district programs" sentence that used to name no place at all - an
# unstable entity signal, since which venues fetched this week is an
# accident of the calendar. Checked against the real, live config files
# (not fixtures) - a regression here would only otherwise surface as a
# quiet drift back to genericness, exactly the failure mode this item
# exists to close off. The expected venues are each already a real,
# independently-sourced entity elsewhere in that same config file
# (a configured source, an annual event's location, or a WebSearch-
# verified civic landmark) - not invented for this test.
_EXPECTED_TAGLINE_VENUES = {
    "mount-prospect-60056": ["Randhurst", "Melas", "Lions Park", "Emerson"],
    "arlington-heights-60005": ["Harmony Park", "Lake Arlington"],
    "des-plaines-60016": ["Lake Park", "Public Library"],
    "palatine-60067": ["Downtown Palatine", "Train Station"],
    "wheeling-60090": ["Heritage Park", "Chicago Executive Airport"],
}


def test_every_region_tagline_names_at_least_two_real_venues():
    for region_cfg in build_digest.load_regions():
        region = region_cfg["region"]
        tagline = region["tagline"]
        assert tagline != "Village news, library events, and park district programs.", (
            f"{region['id']}: tagline regressed to the generic, place-less sentence"
        )
        expected = _EXPECTED_TAGLINE_VENUES[region["id"]]
        matches = [v for v in expected if v in tagline]
        assert len(matches) >= 2, (
            f"{region['id']}: tagline {tagline!r} names fewer than 2 of the expected "
            f"real venues {expected}"
        )
