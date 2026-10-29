import json
import yaml
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
    stats = {"region_count": 4, "next_week_count": 12, "since": "Aug 26, 2026", "issues_sent": 6, "issues_since": "Sep 17, 2026"}
    html = build_digest.render_sponsor_page([], datetime.now(timezone.utc), stats=stats)
    assert "4</strong> region" in html
    # ROADMAP.md item 351: reader-side facts only.
    assert "12</strong> events listed for the next 7 days across 4 towns" in html and "live update" not in html
    assert "6</strong> weekly email issues sent since Sep 17, 2026" in html
    assert "Reader numbers are published once the list passes 50 subscribers" in html
    assert "running since Aug 26, 2026" in html
    big = build_digest.render_sponsor_page([], datetime.now(timezone.utc), stats=stats, audience={"visits": 900, "subscribers": 60, "ai_referrals": None, "as_of": "x"})
    assert "once the list passes 50" not in big


def test_sponsor_issue_stats_count_the_send_history(tmp_path):
    path = tmp_path / "h.json"
    path.write_text(json.dumps([{"timestamp": "2026-09-17T03:02:00+00:00"}, {"timestamp": "2026-10-22T00:00:00+00:00"}, {"timestamp": "2026-11-05T00:00:00+00:00"}]))
    out = build_digest.sponsor_issue_stats(datetime(2026, 10, 25, tzinfo=timezone.utc), path)
    assert out == {"issues_sent": 2, "issues_since": "Sep 17, 2026"}
    assert build_digest.sponsor_issue_stats(datetime(2026, 10, 25, tzinfo=timezone.utc), tmp_path / "none.json")["issues_sent"] == 0


def test_render_sponsor_page_omits_stat_line_when_no_stats():
    html = build_digest.render_sponsor_page([], datetime.now(timezone.utc))
    assert '<p class="stat-line">' not in html


def test_render_sponsor_page_labels_each_tier_by_what_gates_it():
    # ROADMAP.md Phase 11 #118: newsletter tiers are audience-gated, but
    # the two membership tiers are delivered by the site itself (traffic
    # and search presence), not by list size - each tier card should say
    # which one applies, matching SPONSOR_KIT.md's "Value grows with" column
    # (renamed from "Gated by" in item 247: to a buyer "gated" read as
    # "unavailable").
    html = build_digest.render_sponsor_page([], datetime(2026, 6, 10, 15, tzinfo=timezone.utc))  # outside the Holiday listing's season
    assert "Gated by" not in html
    assert html.count("Value grows with: Newsletter reach") == 3  # Event Promo, Weekly Spot, Starter
    assert html.count("Value grows with: Site traffic &amp; search presence") == 2  # Annual Partner, Neighborhood Authority


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


def test_parse_event_date_iso_keeps_rss_pubdate_wall_clock():
    # Communico's real shape: the description says "4:00pm - 6:00pm" and
    # the pubDate carries 16:00 with a fake +0000. It stays 4 PM local.
    iso = build_digest.parse_event_date_iso("Wed, 28 Oct 2026 16:00:00 +0000")
    assert iso == "2026-10-28T16:00:00"
    assert build_digest.schema_start_date(iso) == "2026-10-28T16:00:00-05:00"


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
    assert result == {"url": "https://x/news", "hours": None, "no_official_hours": False, "note": None, "also": []}


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
    assert "3-7 PM" in html and "All on Saturday, October 31" in html  # the date is said once (item 318)
    assert "Not yet posted" not in html


def test_prepare_trick_or_treat_note_needs_hours():
    # ROADMAP.md item 218: a caveat only makes sense under real hours.
    with_hours = {"trick_or_treat": {"url": "https://x", "hours": "3:00–8:00 PM", "note": " Standing hours. "}}
    assert build_digest.prepare_trick_or_treat(with_hours)["note"] == "Standing hours."
    without = {"trick_or_treat": {"url": "https://x", "hours": None, "note": "Standing hours."}}
    assert build_digest.prepare_trick_or_treat(without)["note"] is None


def test_render_trick_or_treat_page_counts_its_towns_and_shows_notes():
    # ROADMAP.md item 218: the title said "Four Towns" over five entries.
    names = ["Mount Prospect", "Arlington Heights", "Des Plaines", "Palatine", "Wheeling"]
    entries = [
        {"region_name": n, "region_url": f"https://x/{i}/", "url": f"https://v/{i}", "hours": None, "note": None}
        for i, n in enumerate(names)
    ]
    entries[0].update(hours="3:00–8:00 PM, Saturday, October 31", note="The Village's standing hours.")
    html = build_digest.render_trick_or_treat_page(entries, datetime.now(timezone.utc))
    assert "<title>Trick-or-Treat Hours %d: Arlington Heights, Des Plaines, Mount Prospect, Palatine, Wheeling — Within Ten</title>" % datetime.now(timezone.utc).year in html
    assert "Four" not in html
    assert "Des Plaines, Palatine, and Wheeling" in html
    assert "The Village&#39;s standing hours." in html or "The Village's standing hours." in html
    assert '<a href="https://v/0">3–8 PM</a>' in html


def test_trick_or_treat_no_official_hours_is_its_own_state():
    # ROADMAP.md item 241: Des Plaines never sets hours, so "not yet
    # posted" would never change. Its note survives without hours.
    cfg = {"trick_or_treat": {"url": "https://x/halloween", "hours": None, "no_official_hours": True, "note": "Urges care after sunset."}}
    entry = build_digest.prepare_trick_or_treat(cfg)
    assert entry["no_official_hours"] is True and entry["note"] == "Urges care after sunset."
    html = build_digest.render_trick_or_treat_page(
        [{"region_id": "dp", "region_name": "Des Plaines", "region_url": "https://x/dp/", **entry}], datetime.now(timezone.utc)
    )
    assert '<a href="https://x/halloween">No official hours</a>' in html
    assert "Urges care after sunset." in html
    assert "Not yet posted" not in html
    # Real hours win over the flag.
    cfg["trick_or_treat"]["hours"] = "3:00–7:00 PM"
    assert build_digest.prepare_trick_or_treat(cfg)["no_official_hours"] is False


def _halloween_event(title, day, url=None):
    return {"title": title, "url": url or f"https://src/{title}", "date_iso": f"{day}T16:00:00", "detail": ""}


def test_select_halloween_events_matches_titles_in_the_window():
    # ROADMAP.md item 243.
    events = [
        _halloween_event("Mount Prospect Downtown Merchants Trick-or-Treat", "2026-10-28"),
        _halloween_event("Trunk or Treat", "2026-10-24"),
        _halloween_event("Halloween Storytime", "2026-10-29"),
        _halloween_event("Pumpkin Painting", "2026-10-10"),
        _halloween_event("Toddler Storytime", "2026-10-28"),  # not Halloween
        _halloween_event("Halloween Hangover Yoga", "2026-11-02"),  # after Nov 1
        _halloween_event("Costume Swap", "2026-10-05"),  # already past
        {"title": "Halloween Safety Tips", "url": "https://src/tips", "date_iso": None},  # undated
    ]
    events[4]["detail"] = "Halloween costumes welcome"  # detail alone doesn't count
    picked = build_digest.select_halloween_events([{"events": events}], date(2026, 10, 6))
    assert [e["title"] for e in picked] == [
        "Pumpkin Painting",
        "Trunk or Treat",
        "Mount Prospect Downtown Merchants Trick-or-Treat",
        "Halloween Storytime",
    ]


def test_select_halloween_events_caps_each_town():
    events = [_halloween_event(f"Halloween Craft {i}", f"2026-10-{10 + i}") for i in range(20)]
    picked = build_digest.select_halloween_events([{"events": events}], date(2026, 10, 6))
    assert len(picked) == build_digest.HALLOWEEN_EVENTS_PER_TOWN
    assert picked[0]["title"] == "Halloween Craft 0"


def test_render_trick_or_treat_page_lists_halloween_events_with_markup():
    event = dict(_halloween_event("Halloween Craft", "2026-10-24"), town="Arlington Heights", state="IL")
    build_digest.prepare_event_cards([{"events": [event]}])
    entries = [
        {"region_id": "arlington-heights-60005", "region_name": "Arlington Heights", "region_url": "https://x/ah/",
         "url": "https://v/ah", "hours": "3:00–7:00 PM, Saturday, October 31", "note": None, "events": [event]},
        {"region_id": "wheeling-60090", "region_name": "Wheeling", "region_url": "https://x/wh/",
         "url": "https://v/wh", "hours": None, "note": None, "events": []},
    ]
    html = build_digest.render_trick_or_treat_page(entries, datetime.now(timezone.utc))
    assert '<section class="town" id="arlington-heights-60005">' in html
    assert 'id="wheeling-60090"' not in html  # no events, no empty section
    assert '<a href="https://x/ah/#ev-halloween-craft-2026-10-24">Halloween Craft</a>' in html
    assert "Sat, Oct 24" in html
    payload = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
    (ev,) = payload["@graph"]
    assert ev["url"] == "https://x/ah/#ev-halloween-craft-2026-10-24"
    assert ev["startDate"] == "2026-10-24T16:00:00-05:00"
    assert ev["location"]["address"]["addressLocality"] == "Arlington Heights"


def test_render_trick_or_treat_page_without_events_has_no_events_section():
    entries = [{"region_id": "dp", "region_name": "Des Plaines", "region_url": "https://x/dp/", "url": "https://v", "hours": None, "note": None}]
    html = build_digest.render_trick_or_treat_page(entries, datetime.now(timezone.utc))
    assert "Halloween events, town by town" not in html
    assert "application/ld+json" not in html


def test_configured_trick_or_treat_hours_name_the_right_weekday():
    # ROADMAP.md items 218/219: search results kept presenting 2025 dates
    # as 2026, and the config's own example said "Friday, October 31" for
    # a year when it is a Saturday. Any "<Weekday>, <Month> <day>" in a
    # configured hours string must match the year the hours are for.
    year = 2026
    pattern = re.compile(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+([A-Z][a-z]+)\s+(\d{1,2})")
    checked = 0
    for region_cfg in build_digest.load_regions():
        tot = region_cfg.get("trick_or_treat") or {}
        for weekday, month, day in pattern.findall(tot.get("hours") or ""):
            actual = datetime.strptime(f"{month} {day} {year}", "%B %d %Y").strftime("%A")
            assert actual == weekday, f"{region_cfg['region']['id']}: {month} {day}, {year} is a {actual}, not {weekday}"
            checked += 1
    assert checked >= 1


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


def test_should_exit_for_health_regression_true_outside_smoke_test():
    # ROADMAP.md item 209: build-digest.yml's own real run relies on
    # this exit code to email the owner - it must still fire normally.
    assert build_digest.should_exit_for_health_regression(["a:b"], [], [], smoke_test=False) is True


def test_should_exit_for_health_regression_false_in_smoke_test():
    # tests.yml's "did the code crash" check sets smoke_test=True, so
    # a live content regression (e.g. a village calendar genuinely
    # going quiet) must not fail an unrelated PR's CI check.
    assert build_digest.should_exit_for_health_regression(["a:b"], [], [], smoke_test=True) is False


def test_should_exit_for_health_regression_false_with_no_regressions_even_outside_smoke_test():
    assert build_digest.should_exit_for_health_regression([], [], [], smoke_test=False) is False


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


def test_render_region_page_links_the_web_manifest_and_touch_icon():
    # ROADMAP.md item 205: lets a returning reader add the site to
    # their phone's Home Screen.
    html = build_digest.render_region_page(
        {"region": REGION}, [], {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc)
    )
    assert '<link rel="manifest" href="https://withintenmiles.com/manifest.webmanifest">' in html
    assert '<link rel="apple-touch-icon" href="https://withintenmiles.com/icons/icon-192.png">' in html


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


def test_render_region_page_cards_carry_date_iso_for_client_side_correction():
    # ROADMAP.md item 200: the client-side script hides a card whose
    # date has passed the viewer's own clock - it needs the raw
    # date_iso on the card itself, not just the human-readable date.
    blocks = [
        {
            "section": "Village News",
            "events": [
                {"title": "Board Meeting", "detail": "", "url": "https://x/1", "date": "Aug 24", "date_iso": "2026-08-24", "tags": []}
            ],
        }
    ]
    html = build_digest.render_region_page(
        {"region": REGION}, blocks, {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc)
    )
    assert 'data-date-iso="2026-08-24"' in html


def test_render_region_page_omits_build_scope_attributes_when_not_given():
    html = build_digest.render_region_page(
        {"region": REGION}, [], {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc)
    )
    main_tag = html.split("<main")[1].split(">")[0]
    assert "data-build-scope-end-iso" not in main_tag


def test_render_region_page_includes_build_scope_attributes_when_given():
    html = build_digest.render_region_page(
        {"region": REGION}, [], {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc),
        build_scope_end_iso="2026-09-25",
        stale_empty_message="Nothing listed for today yet —",
        empty_follow_url="https://withintenmiles.com/mount-prospect-60056/this-weekend/",
        empty_follow_label="here's this weekend",
    )
    assert 'data-build-scope-end-iso="2026-09-25"' in html
    assert 'data-stale-empty-message="Nothing listed for today yet —"' in html
    assert 'data-empty-follow-url="https://withintenmiles.com/mount-prospect-60056/this-weekend/"' in html


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
    # ROADMAP.md item 251: the link now stays on the domain, jumping to the
    # signup block on the page instead of sending the reader to buttondown.com.
    assert '<a href="#newsletter-signup">' in html
    assert 'href="https://buttondown.com/planner"' not in html
    assert html.count('id="newsletter-signup"') == 1


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


def test_filter_past_events_then_event_json_ld_never_emits_a_past_startdate():
    # ROADMAP.md item 202: Event JSON-LD is now read as a checkable
    # trust claim, not just a rich-result trigger, so a startDate before
    # the build date is a false claim, not just a stale one. This proves
    # the actual pipeline composition (filter_past_events feeding
    # build_event_json_ld, the same order main() uses) rather than
    # asserting either function in isolation.
    today = date(2026, 9, 21)
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    blocks = [
        {
            "section": "A",
            "events": [
                {"title": "stale", "url": "https://x/1", "date_iso": datetime.combine(yesterday, time(9, 0)).isoformat()},
                {"title": "future", "url": "https://x/2", "date_iso": datetime.combine(tomorrow, time(9, 0)).isoformat()},
            ],
        }
    ]
    filtered = build_digest.filter_past_events(blocks, today)
    json_ld = build_digest.build_event_json_ld(filtered)
    assert "stale" not in json_ld
    assert "future" in json_ld


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
    assert "live update" not in html and "Nothing dated in the next two weeks" in html


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


def test_render_merged_hub_page_cards_carry_date_iso():
    sections = [
        {
            "region_name": "Palatine",
            "region_url": f"{build_digest.SITE_BASE_URL}palatine-60067/",
            "events": [{"title": "Free Concert", "url": "https://x/", "detail": "", "date": "Sep 19", "date_iso": "2026-09-19", "tags": []}],
        }
    ]
    html = build_digest.render_merged_hub_page(
        sections, datetime.now(timezone.utc), slug="today", heading="Happening Today Near You",
        subheading="", meta_description="",
        empty_message="Nothing dated for today yet across any region.",
    )
    assert 'data-date-iso="2026-09-19"' in html


def test_render_merged_hub_page_includes_build_scope_attributes_when_given():
    # ROADMAP.md item 200: same client-side date correction as the
    # per-region pages, driven by the hub-level today/weekend crons.
    html = build_digest.render_merged_hub_page(
        [], datetime.now(timezone.utc), slug="today", heading="Happening Today Near You",
        subheading="", meta_description="",
        empty_message="Nothing dated for today yet across any region.",
        build_scope_end_iso="2026-09-25",
        stale_empty_message="Nothing listed for today yet —",
        empty_follow_url="https://withintenmiles.com/this-weekend/",
        empty_follow_label="here's this weekend",
    )
    assert 'data-build-scope-end-iso="2026-09-25"' in html
    assert 'data-empty-follow-url="https://withintenmiles.com/this-weekend/"' in html


def test_render_merged_hub_page_omits_build_scope_attributes_when_not_given():
    html = build_digest.render_merged_hub_page(
        [], datetime.now(timezone.utc), slug="free", heading="Free Things To Do Near You",
        subheading="", meta_description="",
        empty_message="Nothing tagged free yet across any region.",
    )
    main_tag = html.split("<main")[1].split(">")[0]
    assert "data-build-scope-end-iso" not in main_tag


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
    # ROADMAP.md item 238: a timed startDate carries the Chicago offset.
    assert event["startDate"] == "2026-09-19T10:00:00-05:00"


def test_build_event_json_ld_location_falls_back_to_the_town_without_inventing_an_address():
    # ROADMAP.md item 238 supersedes the seventh pass's "no location at
    # all": Google requires `location` for Event results. Without a known
    # venue the Place is the town itself - locality and state only, never
    # a street address or a ZIP the site can't back up.
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

    region = {"name": "Mount Prospect", "state": "IL"}
    location = _json.loads(build_digest.build_event_json_ld(blocks, region=region))["@graph"][0]["location"]
    assert location == {
        "@type": "Place",
        "name": "Mount Prospect, IL",
        "address": {"@type": "PostalAddress", "addressCountry": "US",
                    "addressLocality": "Mount Prospect", "addressRegion": "IL"},
    }


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


def test_render_app_icon_is_the_requested_square_size():
    img = build_digest.render_app_icon(192)
    assert img.size == (192, 192)
    assert img.mode == "RGB"


def test_build_app_icons_covers_every_declared_size():
    icons = build_digest.build_app_icons()
    assert set(icons) == set(build_digest.APP_ICON_SIZES)
    for size, img in icons.items():
        assert img.size == (size, size)


def test_build_web_manifest_is_valid_json_with_expected_fields():
    manifest = json.loads(build_digest.build_web_manifest())
    assert manifest["name"] == build_digest.SITE_NAME
    assert manifest["start_url"] == build_digest.SITE_BASE_URL
    assert manifest["display"] == "standalone"
    assert manifest["theme_color"] == "#ec3013"
    assert {(i["sizes"], i["type"]) for i in manifest["icons"]} == {
        (f"{size}x{size}", "image/png") for size in build_digest.APP_ICON_SIZES
    }


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
    assert subject == "Oktoberfest and Harvest Fest this weekend"


def test_build_combined_email_subject_line_excludes_regions_with_no_attendable_events():
    sections = [
        {"region_name": "Mount Prospect", "weekend_events": [{"title": "Oktoberfest", "attendable": True}]},
        {"region_name": "Arlington Heights", "weekend_events": [{"title": "Half-Day", "attendable": False}]},
    ]
    subject = build_digest.build_combined_email_subject_line(sections)
    assert subject == "Oktoberfest this weekend"


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


def test_build_email_preheader_honest_empty_state():
    assert build_digest.build_email_preheader(0, []) == "Nothing new dated yet this week — see what's evergreen and coming up"


def test_build_email_preheader_singular_with_one_title():
    preheader = build_digest.build_email_preheader(1, ["Fall Festival"])
    assert preheader == "1 thing this weekend — incl. Fall Festival"


def test_build_email_preheader_plural_with_two_titles():
    preheader = build_digest.build_email_preheader(3, ["Fall Festival", "Story Time"])
    assert preheader == "3 things this weekend — incl. Fall Festival and Story Time"


def test_build_email_preheader_falls_back_to_count_only_without_titles():
    assert build_digest.build_email_preheader(2, []) == "2 things this weekend"


def test_build_email_preheader_never_exceeds_the_safe_length():
    preheader = build_digest.build_email_preheader(
        16, ["A Very Long Farmers Market Name That Runs On", "An Equally Long Second Event Name Here Too"]
    )
    assert len(preheader) <= build_digest.PREHEADER_MAX_LEN


def test_build_email_preheader_does_not_name_a_region():
    # ROADMAP.md item 207: the subject line already names the region(s)
    # - the preheader's whole point is to add something the subject
    # doesn't already say.
    preheader = build_digest.build_email_preheader(1, ["Fall Festival"])
    assert "Mount Prospect" not in preheader
    assert "Arlington Heights" not in preheader


def test_pick_preheader_titles_skips_recurring_events():
    events = [
        {"title": "Weekly Farmers Market", "attendable": True, "recurring": True},
        {"title": "Fall Festival", "attendable": True, "recurring": False},
    ]
    assert build_digest._pick_preheader_titles(events) == ["Fall Festival"]


def test_pick_preheader_titles_skips_a_near_duplicate_second_title():
    events = [
        {"title": "Oktoberfest", "attendable": True, "recurring": False},
        {"title": "Fall Festival & Oktoberfest", "attendable": True, "recurring": False},
        {"title": "Story Time", "attendable": True, "recurring": False},
    ]
    assert build_digest._pick_preheader_titles(events) == ["Oktoberfest", "Story Time"]


def test_render_email_digest_includes_a_hidden_preheader():
    region = {"name": "Mount Prospect"}
    events = [{"title": "Fall Fest", "date": "Aug 29", "url": "https://x/1", "attendable": True}]
    html = build_digest.render_email_digest(region, events, [], "https://x/mount-prospect-60056/", "Aug 29–30", None)
    assert "1 thing this weekend — incl. Fall Fest" in html
    assert "display:none" in html


def test_render_combined_email_digest_includes_a_hidden_preheader():
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": "https://x/mount-prospect-60056/",
            "weekend_events": [{"title": "Fall Fest", "date": "Aug 29", "url": "https://x/1", "attendable": True}],
            "evergreen": [],
            "sponsor": None,
        }
    ]
    html = build_digest.render_combined_email_digest(sections, "Aug 29–30", datetime(2026, 8, 27, 12, tzinfo=timezone.utc))  # fixed: Halloween week changes the subject
    preheader = html.split("mso-hide:all;\">")[1].split("</div>")[0]
    # ROADMAP.md item 217: the subject now carries the event titles, so
    # the preview names the towns and never repeats a title.
    assert preheader.startswith("Across Mount Prospect")
    assert "Fall Fest" not in preheader
    assert "<title>Fall Fest this weekend</title>" in html


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


def _section(name, *events):
    return {"region_name": name, "weekend_events": [dict({"attendable": True}, **e) for e in events]}


def test_combined_subject_leads_with_events_and_counts_the_rest():
    # ROADMAP.md item 217: three sends in a row were titled with the same
    # town list. The subject now names what is happening.
    sections = [
        _section("Arlington Heights", {"title": "Harmony Fest"}, {"title": "Story Time"}, {"title": "Book Sale"}),
        _section("Mount Prospect", {"title": "Oktoberfest"}, {"title": "Movie Night"}),
    ]
    subject = build_digest.build_combined_email_subject_line(sections)
    assert subject == "Harmony Fest, Oktoberfest and 3 more this weekend"


def test_combined_subject_picks_titles_across_towns_not_all_from_the_first():
    sections = [
        _section("Arlington Heights", {"title": "Fall Fest"}, {"title": "Taste of Arlington Heights"}),
        _section("Wheeling", {"title": "Pumpkin Patch"}),
    ]
    assert "Pumpkin Patch" in build_digest.build_combined_email_subject_line(sections)


def test_combined_subject_skips_recurring_and_near_duplicate_titles():
    sections = [
        _section("Mount Prospect", {"title": "Farmers Market", "recurring": True}, {"title": "Oktoberfest"}),
        _section("Wheeling", {"title": "Fall Fest & Oktoberfest"}, {"title": "Movie Night"}),
    ]
    # Round-robin order is Farmers Market (recurring, skipped), Fall Fest &
    # Oktoberfest, Oktoberfest (near-duplicate, skipped), Movie Night.
    subject = build_digest.build_combined_email_subject_line(sections)
    assert subject == "Fall Fest & Oktoberfest and 3 more this weekend"  # the pair (60 characters) is over the 50 limit
    assert "Farmers Market" not in subject


def test_combined_subject_never_exceeds_the_safe_length():
    long_a = "The Annual Northwest Suburban Harvest and Heritage Celebration Weekend"
    long_b = "Community Chamber Orchestra Autumn Concert Series Finale and Reception"
    sections = [_section("A", {"title": long_a}), _section("B", {"title": long_b})]
    subject = build_digest.build_combined_email_subject_line(sections)
    # ROADMAP.md item 363: a title is never cut and no "…" appears; when no
    # whole title fits, the plain count is the subject.
    assert subject == "2 things to do this weekend in 2 towns"
    assert len(subject) <= build_digest.SUBJECT_MAX_LEN and "…" not in subject


def test_combined_subject_drops_the_second_title_before_clipping_the_first():
    # Equal occasion scores, so item 222's ranking keeps A first.
    sections = [
        _section("A", {"title": "Taste of Arlington Heights (Friday)"}),
        _section("B", {"title": "Wheeling Community Book Swap Afternoon"}),
    ]
    subject = build_digest.build_combined_email_subject_line(sections)
    assert subject == "Taste of Arlington Heights and 1 more this weekend"


def test_combined_subject_prefers_a_shorter_whole_title_over_clipping():
    # Among equally ranked titles (item 222), a whole title still beats a
    # clipped one. Across ranks it no longer does - see the Harmony Fest
    # test below.
    sections = [
        _section("Arlington Heights", {"title": "Harmony Fest & Taste of Arlington Heights Weekend Two"}),
        _section("Wheeling", {"title": "Pumpkin Fest"}),
    ]
    subject = build_digest.build_combined_email_subject_line(sections)
    assert subject == "Pumpkin Fest and 1 more this weekend"
    assert "…" not in subject


def test_combined_preheader_names_every_town_including_empty_ones():
    sections = [
        _section("Arlington Heights", {"title": "Harmony Fest"}),
        _section("Des Plaines"),
        _section("Palatine"),
    ]
    preheader = build_digest.build_combined_email_preheader(sections)
    assert preheader == "Across Arlington Heights, Des Plaines, and Palatine"
    assert "Harmony Fest" not in preheader


def test_combined_preheader_keeps_the_honest_empty_state():
    sections = [_section("Des Plaines"), _section("Palatine")]
    assert build_digest.build_combined_email_preheader(sections) == build_digest.build_email_preheader(0, [])


def test_combined_subject_and_preheader_never_share_an_event_title():
    sections = [
        _section("Arlington Heights", {"title": "Harmony Fest"}, {"title": "Story Time"}),
        _section("Mount Prospect", {"title": "Oktoberfest"}),
    ]
    subject = build_digest.build_combined_email_subject_line(sections)
    preheader = build_digest.build_combined_email_preheader(sections)
    for title in ("Harmony Fest", "Story Time", "Oktoberfest"):
        assert not (title in subject and title in preheader)


def test_combined_subject_leads_with_a_festival_over_an_earlier_library_class():
    # ROADMAP.md item 222: a real subject read "Life Drawing at the Library
    # 2026 and 20 more this weekend" because round-robin order, not
    # notability, chose the lead.
    sections = [
        _section("Arlington Heights", {"title": "Life Drawing at the Library 2026"}, {"title": "Book Club"}),
        _section("Mount Prospect", {"title": "Teen Study Session"}),
        _section("Wheeling", {"title": "Wheeling Fall Festival"}),
    ]
    subject = build_digest.build_combined_email_subject_line(sections)
    assert subject.startswith("Wheeling Fall Festival")


def test_occasion_score_ties_keep_round_robin_order_across_towns():
    sections = [
        _section("Arlington Heights", {"title": "Harmony Fest"}, {"title": "Taste of AH Fest"}),
        _section("Wheeling", {"title": "Pumpkin Fest"}),
    ]
    subject = build_digest.build_combined_email_subject_line(sections)
    assert subject == "Harmony Fest, Pumpkin Fest and 1 more this weekend"


def test_free_and_kid_friendly_tags_lift_an_otherwise_plain_title():
    sections = [
        _section("A", {"title": "Movie Night"}),
        _section("B", {"title": "Puppet Show", "tags": ["free", "kid_friendly"]}),
    ]
    assert build_digest.build_combined_email_subject_line(sections).startswith("Puppet Show")


def test_subject_titles_drop_trailing_years_and_session_suffixes():
    clean = build_digest._clean_subject_title
    assert clean("Life Drawing at the Library 2026") == "Life Drawing at the Library"
    assert clean("Pumpkin Fest (2026)") == "Pumpkin Fest"
    assert clean("Fall Fair – 2026") == "Fall Fair"
    assert clean("Yoga (Week 5 of 5)") == "Yoga"
    assert clean("Class of 2026") == "Class of 2026"
    assert clean("2026") == "2026"


def test_subject_cleaning_never_changes_the_card_titles():
    events = [{"title": "Pumpkin Fest 2026", "attendable": True}]
    sections = [{"region_name": "A", "weekend_events": events}]
    assert build_digest.build_combined_email_subject_line(sections) == "Pumpkin Fest this weekend"
    assert events[0]["title"] == "Pumpkin Fest 2026"


def test_a_long_top_ranked_title_is_never_clipped_the_next_ranked_title_is_tried():
    # ROADMAP.md item 363: the 2026-10-02 data - Harmony Fest ranks first but
    # is too long to fit whole; the subject tries the next-ranked title
    # rather than cutting it.
    sections = [
        _section("Arlington Heights",
                 {"title": "Harmony Fest & Taste of Arlington Heights (Friday)"},
                 {"title": "Senior Center: Travelogue"}),
        _section("Des Plaines", {"title": "Film Screening"}, {"title": "Tinkercad for Adults"}),
    ]
    subject = build_digest.build_combined_email_subject_line(sections)
    assert "…" not in subject and "Harmony Fest & Taste of Arlington" not in subject
    assert len(subject) <= build_digest.SUBJECT_MAX_LEN


def test_subject_titles_drop_a_trailing_weekday_marker():
    assert build_digest._clean_subject_title("Harmony Fest (Saturday)") == "Harmony Fest"


def test_a_long_lead_title_is_dropped_not_cut_and_no_plus_form_is_used():
    # ROADMAP.md items 225 and 363: never "Harmony Fest & Taste of Arlington..."
    # and never "+ 27 more".
    sections = [
        _section("Arlington Heights", {"title": "Harmony Fest & Taste of Arlington Heights (Friday)"},
                 *[{"title": f"Library Program {n}"} for n in range(13)]),
        _section("Mount Prospect", *[{"title": f"Story Session {n}"} for n in range(14)]),
    ]
    subject = build_digest.build_combined_email_subject_line(sections)
    assert "…" not in subject and "+ " not in subject and "Harmony Fest" not in subject
    assert len(subject) <= build_digest.SUBJECT_MAX_LEN


def test_compact_form_is_only_used_when_the_full_form_does_not_fit():
    sections = [_section("A", {"title": "Harmony Fest"}), _section("B", {"title": "Book Swap"})]
    assert build_digest.build_combined_email_subject_line(sections) == "Harmony Fest and Book Swap this weekend"


def test_record_indexnow_outcome_appends_and_keeps_a_trailing_window(tmp_path):
    path = tmp_path / "indexnow_log.json"
    now = datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)
    for _ in range(build_digest.INDEXNOW_LOG_KEEP + 3):
        history = build_digest.record_indexnow_outcome(path, now, 61, False, {"status": 403, "error": "HTTPError"})
    assert len(history) == build_digest.INDEXNOW_LOG_KEEP
    assert history[-1] == {"timestamp": "2026-10-03T14:00:00+00:00", "url_count": 61, "ok": False,
                           "status": 403, "error": "HTTPError", "body": None, "key_file_ok": None, "skipped": None,
                           "bing_status": None, "bing_body": None, "accepted_by": None, "key_suffix": None}
    assert json.loads(path.read_text()) == history


def test_record_indexnow_outcome_keeps_the_reason_and_the_key_file_check(tmp_path):
    # ROADMAP.md item 265: Bing's own reason code, and evidence about the file side.
    path = tmp_path / "indexnow_log.json"
    now = datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc)
    outcome = {"status": 403, "error": "HTTPError", "body": '{"code":"UserForbiddedToAccessSite"}', "key_file_ok": True}
    entry = build_digest.record_indexnow_outcome(path, now, 4, False, outcome)[-1]
    assert entry["body"] == '{"code":"UserForbiddedToAccessSite"}' and entry["key_file_ok"] is True and entry["url_count"] == 4


# ---- ROADMAP.md item 265 (with item 235): submit only the pages that changed ----


def _write_pages(root, pages):
    for url_path, text in pages.items():
        target = root / url_path / "index.html" if url_path else root / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def test_page_fingerprint_ignores_the_generated_time_and_modified_stamp():
    a = '<p>Fest on Oct 10</p><br>Generated 2026-10-09 20:35 UTC.<script>{"dateModified": "2026-10-09T20:35:07.6+00:00"}</script>'
    b = '<p>Fest on Oct 10</p><br>Generated 2026-10-09 22:02 UTC.<script>{"dateModified": "2026-10-09T22:02:47.1+00:00"}</script>'
    assert build_digest.page_fingerprint(a) == build_digest.page_fingerprint(b)
    assert build_digest.page_fingerprint(a) != build_digest.page_fingerprint(a.replace("Oct 10", "Oct 11"))


def test_changed_urls_are_the_ones_whose_page_differs_from_the_last_accepted_run(tmp_path):
    base = build_digest.SITE_BASE_URL
    urls = [base, base + "about/", base + "palatine-60067/"]
    _write_pages(tmp_path, {"": "home", "about": "about", "palatine-60067": "pal v1"})
    changed, current = build_digest.changed_indexnow_urls(urls, {}, tmp_path)
    assert changed == urls  # nothing recorded yet: send everything once
    assert set(current) == set(urls)
    _write_pages(tmp_path, {"palatine-60067": "pal v2"})
    changed, current2 = build_digest.changed_indexnow_urls(urls, current, tmp_path)
    assert changed == [base + "palatine-60067/"]
    assert current2[base] == current[base]
    changed, _ = build_digest.changed_indexnow_urls(urls, current2, tmp_path)
    assert changed == []


def test_an_unreadable_page_counts_as_changed_and_is_not_recorded(tmp_path):
    base = build_digest.SITE_BASE_URL
    changed, current = build_digest.changed_indexnow_urls([base + "missing/"], {base + "missing/": "old"}, tmp_path)
    assert changed == [base + "missing/"] and current == {}


def test_load_indexnow_hashes_survives_missing_or_damaged_files(tmp_path):
    assert build_digest.load_indexnow_hashes(tmp_path / "none.json") == {}
    (tmp_path / "bad.json").write_text("{nope")
    assert build_digest.load_indexnow_hashes(tmp_path / "bad.json") == {}
    (tmp_path / "ok.json").write_text(json.dumps({"https://x/": "abc", "https://y/": 3}))
    assert build_digest.load_indexnow_hashes(tmp_path / "ok.json") == {"https://x/": "abc"}


def test_the_hashes_file_is_committed_and_the_workflow_adds_it():
    root = Path(__file__).resolve().parents[1]
    assert isinstance(json.loads((root / "data" / "indexnow_hashes.json").read_text()), dict)
    assert "data/indexnow_hashes.json" in (root / ".github" / "workflows" / "build-digest.yml").read_text()


def test_record_indexnow_outcome_starts_fresh_on_a_corrupt_file(tmp_path):
    path = tmp_path / "indexnow_log.json"
    path.write_text("{not json")
    now = datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)
    history = build_digest.record_indexnow_outcome(path, now, 5, True, {"status": 200, "error": None})
    assert [h["ok"] for h in history] == [True]


def test_a_lead_that_does_not_fit_gives_way_to_the_next_ranked_title_whole():
    sections = [
        _section("Arlington Heights", {"title": "Harmony Fest & Taste of Arlington Heights (Friday)"}),
        _section("Mount Prospect", {"title": "Trick or Treat Trail"}, {"title": "Book Club"}),
    ]
    subject = build_digest.build_combined_email_subject_line(sections)
    assert subject == "Trick or Treat Trail and 2 more this weekend"


def test_event_anchor_id_is_stable_slug_plus_date():
    # ROADMAP.md item 228: a citable id, the same on every rebuild.
    e = {"title": "Trick or Treat Trail!", "date_iso": "2026-10-04T08:00:00"}
    assert build_digest.event_anchor_id(e) == "ev-trick-or-treat-trail-2026-10-04"
    assert build_digest.event_anchor_id({"title": "Library"}) == "ev-library"
    assert build_digest.event_anchor_id({"title": "!!!"}) == "ev-event"


def test_event_date_label_names_the_weekday_and_never_a_time():
    # ROADMAP.md item 234. 2026-10-04 is a Sunday. No time of day: ICS
    # times often parse to naive UTC, so "7 PM" could be hours off.
    assert build_digest.event_date_label("2026-10-04T19:00:00") == "Sun, Oct 4"
    assert build_digest.event_date_label(None) is None
    assert build_digest.event_date_label("not-a-date") is None


def test_prepare_event_cards_dedupes_ids_within_a_page():
    a = {"title": "Story Time", "date_iso": "2026-10-04T10:00:00"}
    b = {"title": "Story Time", "date_iso": "2026-10-04T14:00:00"}
    build_digest.prepare_event_cards([{"events": [a]}, {"events": [b]}])
    assert (a["anchor_id"], b["anchor_id"]) == ("ev-story-time-2026-10-04", "ev-story-time-2026-10-04-2")
    assert a["date_label"] == "Sun, Oct 4"


def test_event_json_ld_points_url_at_the_on_page_anchor_and_keeps_the_source():
    e = {"title": "Fall Fest", "url": "https://village.example/fest", "date_iso": "2026-10-04T10:00:00"}
    blocks = [{"events": [e]}]
    build_digest.prepare_event_cards(blocks)
    graph = json.loads(build_digest.build_event_json_ld(blocks, page_url="https://withintenmiles.com/x/this-weekend/"))["@graph"]
    assert graph[0]["url"] == "https://withintenmiles.com/x/this-weekend/#ev-fall-fest-2026-10-04"
    assert graph[0]["sameAs"] == "https://village.example/fest"


def test_event_json_ld_without_a_page_url_keeps_the_source_url():
    e = {"title": "Fall Fest", "url": "https://village.example/fest", "date_iso": "2026-10-04T10:00:00"}
    graph = json.loads(build_digest.build_event_json_ld([{"events": [e]}]))["@graph"]
    assert graph[0]["url"] == "https://village.example/fest"
    assert "sameAs" not in graph[0]


def test_region_page_cards_are_articles_with_ids_and_time_elements():
    region_cfg = {"region": {"id": "mount-prospect-60056", "name": "Mount Prospect", "state": "IL", "zip": "60056",
                             "tagline": "t", "timezone": "America/Chicago"}}
    e = {"title": "Fall Fest", "url": "https://village.example/fest", "date": "Oct 4",
         "date_iso": "2026-10-04T10:00:00", "tags": [], "tag_badges": []}
    html = build_digest.render_region_page(region_cfg, [{"section": "Events", "events": [e]}], {}, [],
                                           datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc))
    assert '<article class="card" id="ev-fall-fest-2026-10-04"' in html
    # Item 268: the start time sits beside the date inside the same <time>.
    assert '<time datetime="2026-10-04T10:00:00">Sun, Oct 4 · 10:00 AM</time>' in html
    assert '<span class="where">Mount Prospect</span>' in html
    assert 'data-date-iso="2026-10-04T10:00:00"' in html


def test_events_json_is_an_itemlist_of_events_linking_to_on_site_cards():
    # ROADMAP.md item 230: the machine-readable index agents read.
    now = datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)
    later = {"title": "Movie Night", "date_iso": "2026-10-05T19:00:00", "url": "https://lib.example/movie"}
    sooner = {"title": "Fall Fest", "date_iso": "2026-10-04T10:00:00", "url": "https://village.example/fest",
              "detail": "Rides and food.", "tags": ["free"]}
    payload = json.loads(build_digest.build_events_json(
        [("Mount Prospect", "https://withintenmiles.com/mount-prospect-60056/", [later, sooner])], "Upcoming", now))
    assert payload["@type"] == "ItemList"
    assert payload["numberOfItems"] == 2
    assert payload["dateModified"] == "2026-10-03T14:00:00+00:00"
    first = payload["itemListElement"][0]
    assert first["position"] == 1
    assert first["item"]["name"] == "Fall Fest"
    assert first["item"]["url"] == "https://withintenmiles.com/mount-prospect-60056/#ev-fall-fest-2026-10-04"
    assert first["item"]["sameAs"] == "https://village.example/fest"
    assert first["item"]["isAccessibleForFree"] is True
    assert first["item"]["location"]["@type"] == "Place"
    assert first["item"]["startDate"] == "2026-10-04T10:00:00-05:00"
    assert "isAccessibleForFree" not in payload["itemListElement"][1]["item"]


def test_events_json_skips_undated_items_and_uses_a_dedupe_suffixed_anchor():
    now = datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)
    undated = {"title": "Library"}
    e = {"title": "Story Time", "date_iso": "2026-10-04T10:00:00", "anchor_id": "ev-story-time-2026-10-04-2"}
    payload = json.loads(build_digest.build_events_json([("A", "https://x/a/", [undated, e])], "n", now))
    assert payload["numberOfItems"] == 1
    assert payload["itemListElement"][0]["item"]["url"] == "https://x/a/#ev-story-time-2026-10-04-2"


def test_llms_full_txt_lists_weekend_events_by_town_with_card_links():
    groups = [
        ("Mount Prospect", "https://withintenmiles.com/mount-prospect-60056/this-weekend/",
         [{"title": "Fall Fest", "date_iso": "2026-10-04T10:00:00"}]),
        ("Palatine", "https://withintenmiles.com/palatine-60067/this-weekend/", []),
    ]
    text = build_digest.build_llms_full_txt(groups, "Oct 2–4")
    assert text.startswith("# Within Ten — this weekend (Oct 2–4)")
    assert "- Sun, Oct 4: Fall Fest — https://withintenmiles.com/mount-prospect-60056/this-weekend/#ev-fall-fest-2026-10-04" in text
    assert "## Palatine\n- Nothing dated yet this weekend." in text


def test_robots_txt_names_meta_and_apple_agents():
    robots = build_digest.build_robots_txt()
    for bot in ("Meta-ExternalAgent", "Meta-ExternalFetcher", "Applebot-Extended"):
        assert f"User-agent: {bot}\nAllow: /" in robots


def test_llms_txt_lists_the_event_indexes_and_full_text():
    summaries = [{"name": "Mount Prospect", "zip": "60056", "tagline": "t", "path": "mount-prospect-60056/"}]
    text = build_digest.build_llms_txt(summaries)
    assert "(https://withintenmiles.com/events.json)" in text
    assert "(https://withintenmiles.com/mount-prospect-60056/events.json)" in text
    assert "(https://withintenmiles.com/llms-full.txt)" in text


def test_ics_utc_times_are_converted_to_chicago_local():
    # ROADMAP.md item 238: "...Z" is UTC. 19:00Z on Oct 4 is 2 PM CDT.
    assert build_digest.parse_event_date_iso("20261004T190000Z") == "2026-10-04T14:00:00-05:00"
    # A late-evening UTC time can land on the previous local day.
    assert build_digest.parse_event_date_iso("20261005T030000Z").startswith("2026-10-04T22:00:00")
    # Naive local values are unchanged.
    assert build_digest.parse_event_date_iso("20261004T080000") == "2026-10-04T08:00:00"


def test_schema_start_date_carries_an_offset_and_never_a_placeholder_midnight():
    f = build_digest.schema_start_date
    assert f("2026-10-04T08:00:00") == "2026-10-04T08:00:00-05:00"
    assert f("2026-11-07T08:00:00") == "2026-11-07T08:00:00-06:00"  # after DST ends
    assert f("2026-10-04T00:00:00") == "2026-10-04"
    assert f("2026-10-04T14:00:00-05:00") == "2026-10-04T14:00:00-05:00"


def test_schema_location_prefers_the_configured_venue():
    loc = build_digest.schema_location({"venue": "Mount Prospect Public Library", "town": "Mount Prospect", "state": "IL"})
    assert loc["name"] == "Mount Prospect Public Library"
    assert loc["address"]["addressLocality"] == "Mount Prospect"
    assert "streetAddress" not in loc["address"] and "postalCode" not in loc["address"]


def test_event_json_ld_marks_free_events():
    e = {"title": "Story Time", "url": "https://x/1", "date_iso": "2026-10-04T10:00:00", "tags": ["free"]}
    graph = json.loads(build_digest.build_event_json_ld([{"events": [e]}]))["@graph"]
    assert graph[0]["isAccessibleForFree"] is True


def test_select_halloween_events_collapses_same_day_same_title_across_locations():
    # ROADMAP.md item 272.
    events = [
        dict(_halloween_event("Napleton Trunk or Treat at Arlington Heights Kia", "2026-10-24"), anchor_id="a1"),
        dict(_halloween_event("Napleton Trunk or Treat at Napleton Honda", "2026-10-24"), anchor_id="a2"),
        dict(_halloween_event("Napleton Trunk or Treat at Napleton Ford", "2026-10-25"), anchor_id="a3"),
    ]
    picked = build_digest.select_halloween_events([{"events": events}], date(2026, 10, 6))
    assert len(picked) == 2
    assert picked[0]["also_at"] == [{"label": "Napleton Honda", "anchor_id": "a2"}]
    assert "also_at" not in picked[1]


def test_trick_or_treat_page_has_trunk_or_treat_section():
    trunk = dict(_halloween_event("Trunk or Treat", "2026-10-24"), anchor_id="t1", date_label="Sat, Oct 24")
    craft = dict(_halloween_event("Halloween Craft", "2026-10-25"), anchor_id="c1", date_label="Sun, Oct 25")
    entries = [{"region_id": "ah", "region_name": "Arlington Heights", "region_url": "https://x/ah/", "url": "https://v", "hours": None, "note": None, "events": [trunk, craft]}]
    html = build_digest.render_trick_or_treat_page(entries, datetime(2026, 10, 11, tzinfo=timezone.utc))
    assert 'id="trunk-or-treat"' in html
    body = html.split('id="trunk-or-treat"')[1].split("<script")[0]
    section, town = body.split("Halloween events, town by town")
    assert "Trunk or Treat" in section and "Halloween Craft" not in section
    assert "Halloween Craft" in town and "Trunk or Treat" not in town


def test_build_holiday_listings_labels_and_expires():
    # ROADMAP.md item 258.
    cfg = {"regions": {"r1": {"holiday_listings": [
        {"name": "Bookshop", "url": "https://b", "category": "Bookstore", "address": "10 Main", "line": "Gift wrap."},
        {"name": "Old Shop", "url": "https://o", "until": "2026-11-10"},
        {"name": "", "url": "https://x"},
        {"name": "No Link"},
    ]}}}
    listings = build_digest.build_holiday_listings(cfg, "r1", date(2026, 11, 20))
    assert [l["title"] for l in listings] == ["Bookshop"]
    assert listings[0]["detail"] == "Local business listing · Bookstore · 10 Main — Gift wrap."
    assert [l["title"] for l in build_digest.build_holiday_listings(cfg, "r1", date(2026, 11, 5))] == ["Bookshop", "Old Shop"]
    assert build_digest.build_holiday_listings(cfg, "other", date(2026, 11, 5)) == []
    # Past December 31 of the listing year: default expiry drops it.
    assert build_digest.build_holiday_listings(cfg, "r1", date(2027, 1, 2)) == []


def test_select_holiday_events_window_and_titles():
    events = [
        _halloween_event("Village Tree Lighting", "2026-11-21"),
        _halloween_event("Santa Breakfast", "2026-12-05"),
        _halloween_event("Toddler Storytime", "2026-11-22"),
        _halloween_event("Holiday Market", "2026-11-03"),  # already past
        _halloween_event("Holiday Concert", "2027-01-05"),  # next year
        _halloween_event("Halloween Party", "2026-11-14"),
    ]
    picked = build_digest.select_holiday_events([{"events": events}], date(2026, 11, 10))
    assert [e["title"] for e in picked] == ["Village Tree Lighting", "Santa Breakfast"]


def test_is_holiday_season_and_sitemap():
    assert build_digest.is_holiday_season(datetime(2026, 11, 1)) and build_digest.is_holiday_season(datetime(2026, 12, 31))
    assert not build_digest.is_holiday_season(datetime(2026, 10, 31))
    urls = build_digest.collect_sitemap_urls([{"path": "a/", "holiday": True}, {"path": "b/", "holiday": False}])
    assert build_digest.SITE_BASE_URL + "a/holiday/" in urls
    assert build_digest.SITE_BASE_URL + "b/holiday/" not in urls


def test_prepare_tree_lighting_computes_weekday_and_rejects_old_years():
    # ROADMAP.md item 274.
    cfg = {"tree_lighting": {"url": "https://v", "date": "2026-11-21", "time": "4–7 PM", "place": "Towne Square"}}
    assert build_digest.prepare_tree_lighting(cfg, 2026)["label"] == "Saturday, November 21, 4–7 PM, Towne Square"
    assert build_digest.prepare_tree_lighting(cfg, 2027)["label"] is None  # last year's date is never shown
    assert build_digest.prepare_tree_lighting({"tree_lighting": {"url": "https://v", "date": None}}, 2026)["label"] is None
    assert build_digest.prepare_tree_lighting({"tree_lighting": {"date": "2026-11-21"}}, 2026) is None
    assert build_digest.prepare_tree_lighting({}, 2026) is None


def test_every_configured_tree_lighting_date_is_a_real_weekday_in_the_current_season():
    import glob, yaml
    for path in glob.glob(str(build_digest.CONFIG_DIR / "regions" / "*.yaml")):
        block = (yaml.safe_load(open(path)) or {}).get("tree_lighting")
        assert block and block.get("url"), path
        if block.get("date"):
            assert str(block["date"]).startswith("2026-1"), path  # Nov/Dec only


def test_render_holidays_page_states_dates_and_not_posted():
    entries = [
        {"region_id": "p", "region_name": "Palatine", "region_url": "https://x/p/", "holiday_url": "https://x/p/holiday/",
         "tree": {"url": "https://v/p", "label": "Saturday, November 21, 4–7 PM", "date_iso": "2026-11-21"}, "events": []},
        {"region_id": "w", "region_name": "Wheeling", "region_url": "https://x/w/", "holiday_url": "https://x/w/holiday/",
         "tree": {"url": "https://v/w", "label": None, "date_iso": None}, "events": []},
    ]
    html = build_digest.render_holidays_page(entries, datetime(2026, 10, 11, tzinfo=timezone.utc))
    assert "<title>Holiday Tree Lightings 2026 — Palatine and Wheeling — Within Ten</title>" in html
    assert '<a href="https://v/p">Saturday, November 21, 4–7 PM</a>' in html
    assert "Not yet posted for 2026" in html and "https://v/w" in html
    assert "Holiday events, town by town" not in html


def _join_sections():
    def ev(title, day, url):
        return {"title": title, "url": url, "date_iso": f"{day}T10:00:00", "date": day, "detail": "", "tags": ["kid_friendly"]}
    return [
        {"region_name": "Palatine", "region_url": build_digest.SITE_BASE_URL + "palatine-60067/",
         "weekend_events": [ev("Family Fun Day", "2026-10-17", "https://src/p")]},
        {"region_name": "Wheeling", "region_url": build_digest.SITE_BASE_URL + "wheeling-60090/",
         "weekend_events": [ev("Pumpkin Patch", "2026-10-17", "https://src/w")]},
    ]


def test_join_page_is_noindex_with_picks_one_form_and_town_picker():
    # ROADMAP.md item 277.
    newsletter = {"configured": True, "buttondown_username": "withten", "headline": "H", "detail": "D"}
    html = build_digest.render_join_page(_join_sections(), datetime(2026, 10, 12, tzinfo=timezone.utc), None, newsletter)
    assert '<meta name="robots" content="noindex">' in html
    assert html.count('<form class="newsletter-form"') == 1
    assert '<option value="town:palatine-60067">Palatine</option>' in html
    assert '<option value="town:all" selected>All towns</option>' in html
    assert "Family Fun Day" in html and "Pumpkin Patch" in html
    assert 'q.get(k)' in html  # UTM values pass through from the URL
    assert 'name="utm_source"' in html and 'name="utm_campaign" value="join"' in html
    assert "<nav" not in html


def test_join_page_is_not_in_the_sitemap():
    assert not any("join" in u for u in build_digest.collect_sitemap_urls([{"path": "a/"}]))


def test_join_page_picks_are_cards_with_town_colours_and_a_recent_issue_link():
    # ROADMAP.md item 279.
    html = build_digest.render_join_page(_join_sections(), datetime(2026, 10, 12, tzinfo=timezone.utc), None, None, "Oct 16–18")
    assert html.count('<div class="pick" style="--town:') == 2
    colors = re.findall(r'<div class="dow" style="background:(#[0-9a-f]{6})">', html)
    assert len(colors) == 2 and len(set(colors)) == 2  # one colour per town
    assert "SAT" in html and "Oct 16–18" in html and "2 things to do in 2 towns" in html
    assert 'href="' + build_digest.SITE_BASE_URL + 'combined-email-preview.html">See a recent issue' in html
    assert 'noindex' in html and "<nav" not in html


def _issue(date="2026-10-15", body="<p>Fall Fest</p>"):
    html = (
        "<!doctype html><html><head><title>Your Thursday guide</title></head><body>\n"
        '<div style="display:none; font-size:1px; max-height:0px; opacity:0; overflow:hidden; mso-hide:all;">hidden preheader&#8203;</div>\n'
        f"{body}</body></html>"
    )
    return {"date": date, "subject": "Your Thursday guide", "html": html}


def test_render_issue_page_wraps_the_frozen_email_with_a_banner_title_h1_and_one_signup():
    # ROADMAP.md items 280 and 357.
    body = '<p>Fall Fest</p><div>DON\'T MISS</div><a href="x" style="font-size:19px; color:#000;">Harmony Fest</a><a href="y" style="font-size:19px;">Pumpkin Run</a>'
    newsletter = {"configured": True, "buttondown_username": "withinten", "headline": "Get it"}
    page = build_digest.render_issue_page(
        _issue(body=body), newer={"date": "2026-10-22"}, older={"date": "2026-10-08"}, newsletter=newsletter,
        town_names=["Wheeling", "Arlington Heights", "Des Plaines", "Mount Prospect", "Palatine"],
    )
    base = build_digest.SITE_BASE_URL
    assert "hidden preheader" not in page  # the preheader is stripped
    assert f'<link rel="canonical" href="{base}issues/2026-10-15/">' in page
    assert f'href="{base}this-weekend/">See this weekend&#39;s events' in page or "See this weekend's events" in page
    assert "<title>Things to do Oct 16–18, 2026 in Arlington Heights, Des Plaines, Mount Prospect, Palatine &amp; Wheeling | Within Ten</title>" in page
    assert "<h1>Weekend of Oct 16–18, 2026</h1>" in page and "This is the Oct 15, 2026 issue." in page
    assert 'name="description" content="The Within Ten issue of Oct 15, 2026: Harmony Fest and Pumpkin Run.' in page
    assert "&lt;p&gt;Fall Fest&lt;/p&gt;" in page and "&lt;base target=&#34;_top&#34;&gt;" in page  # the email, frozen, inside the iframe
    assert page.count("embed-subscribe") == 1 and page.count('id="newsletter-signup"') == 1
    assert f"{base}issues/2026-10-22/" in page and f"{base}issues/2026-10-08/" in page
    alone = build_digest.render_issue_page(_issue())
    assert "Previous issue" not in alone and "Next issue" not in alone and "embed-subscribe" not in alone
    assert "Things to do Oct 16–18, 2026 in the northwest suburbs | Within Ten" in alone


def test_load_issues_newest_first_and_ignores_other_files(tmp_path):
    (tmp_path / "2026-10-08.html").write_text("<title>A</title>", encoding="utf-8")
    (tmp_path / "2026-10-15.html").write_text("<title>B &amp; C</title>", encoding="utf-8")
    (tmp_path / "notes.html").write_text("x", encoding="utf-8")
    issues = build_digest.load_issues(tmp_path)
    assert [i["date"] for i in issues] == ["2026-10-15", "2026-10-08"]
    assert issues[0]["subject"] == "B & C"
    assert build_digest.load_issues(tmp_path / "missing") == []


def test_issues_index_sitemap_and_llms_list_each_issue():
    issues = [_issue("2026-10-15"), _issue("2026-10-08")]
    index = build_digest.render_issues_index(issues, datetime(2026, 10, 16, tzinfo=timezone.utc))
    assert index.index("2026-10-15") < index.index("2026-10-08")
    urls = build_digest.collect_sitemap_urls([{"path": "a/"}], issues)
    assert build_digest.SITE_BASE_URL + "issues/" in urls and build_digest.SITE_BASE_URL + "issues/2026-10-08/" in urls
    assert build_digest.SITE_BASE_URL + "issues/" not in build_digest.collect_sitemap_urls([{"path": "a/"}])
    assert "issues/2026-10-15/" in build_digest.build_llms_txt([{"name": "A", "zip": "1", "path": "a/", "tagline": "t"}], None, issues)


def test_join_page_links_the_newest_issue_when_there_is_one():
    html = build_digest.render_join_page(_join_sections(), datetime(2026, 10, 16, tzinfo=timezone.utc), None, None, "", build_digest.SITE_BASE_URL + "issues/2026-10-15/")
    assert 'href="' + build_digest.SITE_BASE_URL + 'issues/2026-10-15/">See a recent issue' in html


def test_halloween_banner_leads_the_homepage_in_season_and_disappears_after():
    # Owner request 2026-10-13: trick-or-treat hours at the very top of the
    # homepage in October, not only as a footer link.
    entries = [
        {"region_name": "Arlington Heights", "hours": "3:00–7:00 PM, Saturday, October 31", "no_official_hours": False},
        {"region_name": "Des Plaines", "hours": None, "no_official_hours": True},
        {"region_name": "Elsewhere", "hours": None, "no_official_hours": False},
    ]
    oct13 = datetime(2026, 10, 13, 17, tzinfo=timezone.utc)
    banner = build_digest.build_halloween_banner(entries, oct13)
    assert banner["countdown"] == "18 days to go" and banner["weekday"] == "Saturday"
    assert [t["hours"] for t in banner["towns"]] == ["3–7 PM", "No set hours", "Not posted yet"]
    assert build_digest.build_halloween_banner(entries, datetime(2026, 10, 31, 17, tzinfo=timezone.utc))["countdown"] == "Tonight!"
    assert build_digest.build_halloween_banner(entries, datetime(2026, 11, 1, 17, tzinfo=timezone.utc)) is None
    assert build_digest.build_halloween_banner(entries, datetime(2026, 6, 1, tzinfo=timezone.utc)) is None
    assert build_digest.build_halloween_banner([], oct13) is None

    summaries = [{**REGION, "event_count": 3, "path": "mount-prospect-60056/"}]
    html = build_digest.render_hub_page([], summaries, oct13, halloween=banner)
    top = html.index('class="halloween"')
    assert top < html.index('<header class="hero">')
    assert 'href="trick-or-treat/"' in html[top:]
    assert "Arlington Heights <strong>3–7 PM</strong>" in html


def _holiday_entries():
    return [
        {"region_name": "Palatine", "tree": {"date_iso": "2026-11-21"}},
        {"region_name": "Wheeling", "tree": {"date_iso": None}},
    ]


def test_holiday_banner_windows_and_handover_from_halloween():
    # ROADMAP.md item 285.
    banner = build_digest.build_holiday_banner
    at = lambda m, d: datetime(2026, m, d, 18, tzinfo=timezone.utc)
    assert banner(_holiday_entries(), at(10, 31)) is None  # Halloween banner's last day
    assert banner(_holiday_entries(), at(11, 1)) is not None
    assert banner(_holiday_entries(), at(12, 24)) is not None
    assert banner(_holiday_entries(), at(12, 25)) is None
    assert banner([], at(11, 5)) is None
    # Only one banner at a time: wherever the Halloween banner shows, this one does not.
    halloween = [{"region_name": "A", "hours": "3-7 PM"}]
    for m, d in ((10, 12), (10, 31), (11, 1), (11, 3)):
        assert not (build_digest.build_halloween_banner(halloween, at(m, d)) and banner(_holiday_entries(), at(m, d)))


def test_holiday_banner_pills_and_early_bird_offer():
    b = build_digest.build_holiday_banner(_holiday_entries(), datetime(2026, 11, 15, 18, tzinfo=timezone.utc))
    assert b["towns"] == [{"name": "Palatine", "date": "Sat Nov 21"}, {"name": "Wheeling", "date": "date TBA"}]
    assert b["offer"] is True
    assert build_digest.build_holiday_banner(_holiday_entries(), datetime(2026, 11, 16, 18, tzinfo=timezone.utc))["offer"] is False


def _at_local(y, m, d, hour=21):
    return datetime(y, m, d, hour, tzinfo=build_digest.LOCAL_TZ)


def test_email_edition_picks_the_halloween_and_holiday_kickoff_weeks():
    # ROADMAP.md item 289. Oct 31 is Saturday (2026), Sunday (2027) and Monday (2028).
    ed = build_digest.email_edition
    assert ed(_at_local(2026, 10, 28)) == "halloween"  # Friday Oct 30's weekend
    assert ed(_at_local(2026, 10, 21)) is None
    assert ed(_at_local(2027, 10, 27)) == "halloween"  # Friday Oct 29, Halloween Sunday
    assert ed(_at_local(2028, 10, 25)) == "halloween"  # Friday Oct 27, Halloween Monday
    assert ed(_at_local(2028, 11, 1)) is None
    # Thanksgiving 2026 is Nov 26; the send before it covers Black Friday weekend.
    assert ed(_at_local(2026, 11, 25)) == "holiday"
    assert ed(_at_local(2026, 11, 18)) is None
    assert ed(_at_local(2027, 11, 24)) == "holiday"  # Thanksgiving Nov 25, 2027


def test_each_year_has_exactly_one_halloween_and_one_holiday_edition():
    days = [datetime(2026, 1, 1, 12, tzinfo=build_digest.LOCAL_TZ) + timedelta(days=i) for i in range(365)]
    editions = {}
    for d in days:
        editions.setdefault(build_digest.weekend_dates(d.date())[0], build_digest.email_edition(d))
    assert sorted(v for v in editions.values() if v) == ["halloween", "holiday"]


def test_edition_block_content_and_seasonal_line_suppression():
    halloween = {"towns": [{"name": "Palatine", "hours": "3–7 PM"}, {"name": "Wheeling", "hours": "Not posted yet"}]}
    holiday = {"towns": [{"name": "Palatine", "date": "Sat Nov 21"}], "offer": True}
    h = build_digest.build_email_edition_block("halloween", halloween, holiday, _at_local(2026, 10, 28))
    assert h["pills"] == ["Palatine 3–7 PM", "Wheeling Not posted yet"] and "trick-or-treat/" in h["link"]
    k = build_digest.build_email_edition_block("holiday", halloween, holiday, _at_local(2026, 11, 25))
    assert k["pills"] == ["Palatine Sat Nov 21", "Small Business Saturday Nov 28"]
    assert build_digest.build_email_edition_block("holiday", halloween, None, _at_local(2026, 11, 25)) is None
    assert build_digest.build_email_edition_block(None, halloween, holiday, _at_local(2026, 10, 28)) is None
    html = build_digest.render_combined_email_digest(
        _join_sections(), "Oct 30–Nov 1", _at_local(2026, 10, 28), None, halloween=halloween, holiday=holiday
    )
    assert "THE HALLOWEEN WEEKEND ISSUE" in html and "#2a1646" in html
    assert "Palatine 3–7 PM" in html
    assert html.count("trick-or-treat/") == 1  # the edition block replaces the seasonal line
    plain = build_digest.render_combined_email_digest(_join_sections(), "Oct 16–18", _at_local(2026, 10, 14), None)
    assert "WEEKEND GUIDE" in plain and "#2a1646" not in plain
    assert len(html.encode("utf-8")) < 102_000


def _wx(day, high, precip, emoji="☀️"):
    return {"day_name": day, "high_f": high, "precip_percent": precip, "emoji": emoji}


def test_email_weather_line_dry_wet_and_missing():
    # ROADMAP.md item 291.
    dry = build_digest.build_email_weather_line([_wx("Friday", 60, 0), _wx("Saturday", 58.4, 10), _wx("Sunday", 61, 20)])
    assert dry == {"text": "☀️ Sat 58° · ☀️ Sun 61°", "rain": False}
    wet = build_digest.build_email_weather_line([_wx("Saturday", 58, 10), _wx("Sunday", 55, 70, "🌧️")])
    assert wet == {"text": "☀️ Sat 58° · 🌧️ Sun 55° 70% rain", "rain": True}
    assert build_digest.build_email_weather_line([_wx("Saturday", 50, 30)])["rain"] is False  # 30% is shown, not a rain plan
    assert build_digest.build_email_weather_line([]) is None
    assert build_digest.build_email_weather_line(None) is None


def test_rain_plan_picks_indoor_events_only_and_skips_promos_and_picks():
    def ev(title, tags, **kw):
        return dict({"title": title, "url": f"https://x/{title}", "date_iso": "2026-10-17T10:00:00", "tags": tags}, **kw)
    blocks = [{"region_name": "Palatine", "color": "#0f766e", "attendable_events": [
        ev("Indoor Play", ["indoor", "kid_friendly"]), ev("Hike", ["outdoor"]), ev("Paid Show", ["indoor"], sponsored_by="Acme"),
        ev("Already Picked", ["indoor", "kid_friendly"]),
    ]}]
    picks = build_digest.pick_rain_plan(blocks, [ev("Already Picked", [])])
    assert [p["title"] for p in picks] == ["Indoor Play"]
    assert picks[0]["pick_town"] == "Palatine"


def test_email_shows_weather_line_and_rain_plan_only_when_wet():
    sections = _join_sections()
    for s in sections:
        s["weekend_events"].append({"title": "Extra " + s["region_name"], "url": "https://src/x" + s["region_name"], "date_iso": "2026-10-18T10:00:00", "date": "2026-10-18", "detail": "", "tags": ["indoor"]})
        for e in s["weekend_events"]:
            e["tags"] = ["indoor", "kid_friendly"]
    now = datetime(2026, 10, 14, 18, tzinfo=timezone.utc)
    wet = build_digest.render_combined_email_digest(sections, "Oct 16–18", now, None, weather=[_wx("Saturday", 50, 80, "🌧️"), _wx("Sunday", 52, 20)])
    assert "🌧️ Sat 50° 80% rain" in wet and "RAIN PLAN" in wet
    dry = build_digest.render_combined_email_digest(sections, "Oct 16–18", now, None, weather=[_wx("Saturday", 60, 0), _wx("Sunday", 62, 10)])
    assert "☀️ Sat 60°" in dry and "RAIN PLAN" not in dry
    none = build_digest.render_combined_email_digest(sections, "Oct 16–18", now, None, weather=None)
    assert "RAIN PLAN" not in none and "% rain" not in none and "Sat 6" not in none
    assert len(wet.encode("utf-8")) < 102_000


def test_trick_or_treat_also_computes_weekday_and_drops_other_years():
    # ROADMAP.md item 292.
    also = {"label": "Downtown", "url": "https://d", "date": "2026-10-28", "time": "4–6 PM"}
    cfg = {"trick_or_treat": {"url": "https://x", "hours": None, "also": [also, {"label": "No date", "url": "https://d"}]}}
    assert build_digest.prepare_trick_or_treat(cfg, 2026)["also"] == [
        {"label": "Downtown", "url": "https://d", "when": "Wednesday, October 28, 4–6 PM", "place": None}
    ]
    assert build_digest.prepare_trick_or_treat(cfg, 2027)["also"] == []  # last year's date is never shown


def _tot_entries(n=5):
    names = ["Mount Prospect", "Arlington Heights", "Des Plaines", "Palatine", "Wheeling"][:n]
    return [{"region_id": f"r{i}", "region_name": nm, "region_url": f"https://x/{i}/", "url": f"https://v/{i}", "hours": "3–7 PM, Saturday, October 31", "note": None, "events": []} for i, nm in enumerate(names)]


def test_trick_or_treat_page_has_the_halloween_hero_cards_share_button_and_countdown():
    # ROADMAP.md item 293.
    entries = _tot_entries()
    entries[0]["also"] = [{"label": "Downtown merchants' trick-or-treat", "url": "https://d", "when": "Wednesday, October 28, 4–6 PM", "place": "Downtown Mount Prospect"}]
    html = build_digest.render_trick_or_treat_page(entries, datetime(2026, 10, 18, 18, tzinfo=timezone.utc))
    assert html.count('<div class="entry" id="tot-') == 5
    colors = re.findall(r'<div class="entry" id="tot-[^"]+" style="--town:(#[0-9a-f]{6})">', html)
    assert len(set(colors)) == 5  # a colour per town, as in the email
    assert 'id="share-btn"' in html and "navigator.share" in html and "clipboard" in html  # copy-link fallback
    assert "13 days to go" in html and "Saturday, October 31" in html
    assert "Also: " in html and "Wednesday, October 28, 4–6 PM" in html and "https://d" in html
    # On and after Oct 31 the countdown changes, then goes away.
    assert "Tonight!" in build_digest.render_trick_or_treat_page(_tot_entries(), datetime(2026, 10, 31, 18, tzinfo=timezone.utc))
    assert "days to go" not in build_digest.render_trick_or_treat_page(_tot_entries(), datetime(2026, 11, 1, 18, tzinfo=timezone.utc))
    assert "👻" not in build_digest.render_trick_or_treat_page(_tot_entries(), datetime(2026, 11, 1, 18, tzinfo=timezone.utc))


def test_holiday_listing_offer_price_switches_on_nov_16():
    # ROADMAP.md item 294.
    offer = build_digest.build_holiday_listing_offer
    at = lambda m, d: datetime(2026, m, d, 18, tzinfo=timezone.utc)
    assert offer(at(10, 15), "h@x.com")["price"] == "$20" and offer(at(11, 15), "h@x.com")["early"] is True
    assert offer(at(11, 16), "h@x.com")["price"] == "$50" and offer(at(11, 16), "h@x.com")["early"] is False
    assert offer(at(12, 31), "h@x.com") is not None
    assert offer(at(10, 15), None) is None
    assert offer(datetime(2027, 1, 2, 18, tzinfo=timezone.utc), "h@x.com") is None  # the season is over


def test_holidays_page_has_festive_hero_town_colours_emoji_and_the_listing_box():
    entries = [
        {"region_id": "p", "region_name": "Palatine", "region_url": "https://x/p/", "holiday_url": "https://x/p/holiday/",
         "tree": {"url": "https://v/p", "label": "Saturday, November 21, 4–7 PM", "date_iso": "2026-11-21"},
         "events": [{"title": "Santa Breakfast", "date_iso": "2026-12-05T09:00:00", "date_label": "Sat, Dec 5", "anchor_id": "ev-santa"}]},
        {"region_id": "w", "region_name": "Wheeling", "region_url": "https://x/w/", "holiday_url": "https://x/w/holiday/",
         "tree": {"url": "https://v/w", "label": None, "date_iso": None}, "events": []},
    ]
    early = build_digest.render_holidays_page(entries, datetime(2026, 11, 10, 18, tzinfo=timezone.utc), None, None, "h@x.com")
    assert 'class="h-hero"' in early and early.count('<div class="entry"') == 2
    assert len(set(re.findall(r'--town:(#[0-9a-f]{6})', early))) == 2
    assert 'class="emoji"' in early
    assert "Get listed in the holiday guide, $20 until Nov 15" in early and "mailto:h@x.com" in early
    late = build_digest.render_holidays_page(entries, datetime(2026, 11, 16, 18, tzinfo=timezone.utc), None, None, "h@x.com")
    assert "holiday guide, $50." in late and "until Nov 15" not in late.split('id="holiday-listing"')[1].split("</div>")[0]
    assert 'id="holiday-listing"' not in build_digest.render_holidays_page(entries, datetime(2026, 11, 16, 18, tzinfo=timezone.utc))


def _school_block(*events):
    return {"section": "School Calendar", "events": [dict(e, source=e.get("source", "Mount Prospect School District 57 — Calendar")) for e in events]}


def test_short_district_names():
    sd = build_digest.short_district
    assert sd("Mount Prospect School District 57 — Calendar") == "D57"
    assert sd("Wheeling CCSD 21 — Calendar") == "CCSD 21"
    assert sd("Township High School District 214 — Calendar") == "D214"
    assert sd("Some Academy — Calendar") == "Some Academy"


def test_days_off_window_wording_grouping_and_daytime_ideas():
    # ROADMAP.md item 296.
    today = date(2026, 11, 2)
    school = _school_block(
        {"title": "No School - Veterans Day", "date_iso": "2026-11-11T00:00:00"},
        {"title": "No School - Veterans Day", "date_iso": "2026-11-11T00:00:00", "source": "Wheeling CCSD 21 — Calendar"},
        {"title": "Parent-Teacher Conferences", "date_iso": "2026-11-05T00:00:00"},
        {"title": "Board of Education Meeting", "date_iso": "2026-11-09T19:00:00"},  # not a day off
        {"title": "No School - Winter Break", "date_iso": "2026-12-23T00:00:00"},  # beyond 45 days (Dec 17)
        {"title": "No School - Labor Day", "date_iso": "2026-09-07T00:00:00"},  # past
    )
    library = {"section": "Library Events", "events": [
        {"title": "Lego Club for Grades K-5", "url": "https://l/1", "date_iso": "2026-11-11T10:00:00", "tags": ["kid_friendly", "elementary"]},
        {"title": "Toddler Storytime", "url": "https://l/4", "date_iso": "2026-11-11T10:30:00", "tags": ["kid_friendly", "toddler"]},
        {"title": "AARP Driver Safety Course", "url": "https://l/5", "date_iso": "2026-11-11T11:00:00", "tags": []},
        {"title": "Evening Concert", "url": "https://l/2", "date_iso": "2026-11-11T19:00:00", "tags": []},  # after 5 p.m.
        {"title": "All-day Exhibit", "url": "https://l/3", "date_iso": "2026-11-11T00:00:00", "tags": []},  # no time given
    ]}
    days = build_digest.build_days_off([school, library], today)
    assert [d["label"] for d in days] == ["Thu Nov 5", "Wed Nov 11"]
    veterans = days[1]
    assert veterans["reasons"] == [
        {"district": "D57", "reason": "No School - Veterans Day"},
        {"district": "CCSD 21", "reason": "No School - Veterans Day"},
    ]
    assert [i["title"] for i in veterans["ideas"]] == ["Lego Club for Grades K-5"]  # no toddler or adult programme
    assert days[0]["ideas"] == []
    assert build_digest.build_days_off([library], today) == []  # nothing shown when no day off is listed


def test_days_off_email_line_only_within_seven_days():
    sections = [{"region_url": "https://x/mp/", "days_off": [
        {"date": date(2026, 11, 5), "label": "Thu Nov 5", "reasons": [{"district": "D57", "reason": "Conferences"}]},
        {"date": date(2026, 11, 20), "label": "Fri Nov 20", "reasons": [{"district": "D57", "reason": "No School"}]},
    ]}]
    now = datetime(2026, 11, 2, 18, tzinfo=timezone.utc)
    line = build_digest.build_days_off_email_line(sections, now)
    assert line == {"text": "📚 No school next week: D57 Thu Nov 5", "url": "https://x/mp/#days-off"}
    assert build_digest.build_days_off_email_line(sections, datetime(2026, 11, 8, 18, tzinfo=timezone.utc)) is None


def test_region_page_shows_the_days_off_box_with_honesty_line():
    days = [{"date": date(2026, 11, 11), "label": "Wed Nov 11", "reasons": [{"district": "D57", "reason": "No School"}],
             "ideas": [{"title": "Toddler Storytime", "url": "https://l/1", "clock": "10:00 AM"}]}]
    region_cfg = {"region": {"id": "mp", "name": "Mount Prospect", "zip": "60056", "state": "IL", "tagline": "t", "timezone": "America/Chicago"}}
    html = build_digest.render_region_page(region_cfg, [], None, [], datetime(2026, 11, 2, 18, tzinfo=timezone.utc), days_off=days)
    assert 'id="days-off"' in html and "D57: No School" in html and "Toddler Storytime" in html
    assert "Check your school&#39;s calendar for building-level changes." in html or "Check your school's calendar for building-level changes." in html
    assert 'id="days-off"' not in build_digest.render_region_page(region_cfg, [], None, [], datetime(2026, 11, 2, 18, tzinfo=timezone.utc))


def test_consecutive_days_off_from_the_same_district_are_one_row():
    # ROADMAP.md item 299: CCSD 15's Nov 23-27 recess was five identical rows.
    school = _school_block(*[
        {"title": "No School | Thanksgiving Break", "date_iso": f"2026-11-{d}T00:00:00", "source": "Palatine CCSD 15 — Calendar"}
        for d in (23, 24, 25, 26, 27)
    ] + [{"title": "No School | Conferences", "date_iso": "2026-11-02T00:00:00", "source": "Palatine CCSD 15 — Calendar"}])
    rink = {"section": "Park District Events", "events": [
        {"title": "Open Skate", "url": "https://p/1", "date_iso": "2026-11-24T13:00:00", "tags": ["kid_friendly", "elementary"]},
    ]}
    days = build_digest.build_days_off([school, rink], date(2026, 10, 30))
    assert [d["label"] for d in days] == ["Mon Nov 2", "Mon Nov 23 – Fri Nov 27"]
    assert days[1]["reasons"] == [{"district": "CCSD 15", "reason": "No School | Thanksgiving Break"}]
    assert days[1]["ideas"] == [{"title": "Open Skate", "url": "https://p/1", "clock": "Tue 1:00 PM"}]
    # A Friday and the next Monday are consecutive school days; a mid-week gap is not.
    gap = _school_block(
        {"title": "No School", "date_iso": "2026-11-20T00:00:00"}, {"title": "No School", "date_iso": "2026-11-23T00:00:00"},
        {"title": "No School", "date_iso": "2026-11-25T00:00:00"},
    )
    assert [d["label"] for d in build_digest.build_days_off([gap], date(2026, 11, 1))] == ["Fri Nov 20 – Mon Nov 23", "Wed Nov 25"]


def test_days_off_box_falls_back_to_the_library_and_park_district_when_no_pick_fits():
    days = [{"date": date(2026, 11, 11), "end": date(2026, 11, 11), "label": "Wed Nov 11", "reasons": [{"district": "D57", "reason": "No School"}], "ideas": []}]
    region_cfg = {"region": {"id": "mp", "name": "Mount Prospect", "zip": "60056", "state": "IL", "tagline": "t", "timezone": "America/Chicago"}}
    evergreen = [{"title": "Mount Prospect Public Library", "url": "https://lib/", "detail": "", "tags": []},
                 {"title": "Mount Prospect Park District", "url": "https://pd/", "detail": "", "tags": []}]
    html = build_digest.render_region_page(region_cfg, [], None, evergreen, datetime(2026, 11, 2, 18, tzinfo=timezone.utc), days_off=days)
    assert "No special programmes listed. Check the" in html and 'href="https://lib/"' in html and 'href="https://pd/"' in html


def test_weekly_cards_render_at_all_three_sizes_and_skip_when_there_are_no_picks():
    # ROADMAP.md items 278 and 216.
    cards = build_digest.build_weekly_cards(_join_sections(), "Oct 16–18")
    assert {n: i.size for n, i in cards.items()} == {"weekly-square": (1080, 1080), "weekly-portrait": (1080, 1350), "weekly-pin": (1000, 1500)}
    # Not blank: the red background plus white pick cards and a yellow pill.
    colors = {c for _n, c in cards["weekly-square"].getcolors(maxcolors=100000)}
    assert (236, 48, 19) in colors and (255, 255, 255) in colors and (255, 210, 63) in colors
    assert build_digest.build_weekly_cards(_join_sections(), "") == {}
    assert build_digest.build_weekly_cards([{"region_name": "A", "region_url": "https://x/a/", "weekend_events": []}], "Oct 16–18") == {}


def _weekly_events():
    base = {"url": "https://src/{}", "date_iso": "2026-10-17T10:00:00", "date": "2026-10-17", "detail": "Fun for the family.", "tags": ["kid_friendly"]}
    return [
        dict(base, title="Family Fun Day", url="https://src/a"),
        dict(base, title="Paid Promo", url="https://src/b", sponsored_by="Acme Dental"),
        dict(base, title="Half-Day Notice", url="https://src/c", attendable=False),
    ]


def test_weekly_item_excludes_sponsored_and_non_events_and_skips_empty_towns():
    # ROADMAP.md item 304.
    now = datetime(2026, 10, 14, 18, tzinfo=timezone.utc)
    item = build_digest.build_weekly_item("palatine-60067", "Palatine", _weekly_events(), date(2026, 10, 16), "Oct 16–18", now, {"url": "https://x/i.png", "length": 99})
    assert item["title"] == "This weekend in Palatine: 1 thing to do (Oct 16–18)"
    assert "Family Fun Day" in item["html"] and "Paid Promo" not in item["html"] and "Half-Day" not in item["html"]
    assert "utm_source=nextdoor&amp;utm_campaign=weekly" in item["html"]
    assert item["guid"].endswith("palatine-60067/this-weekend/#weekly-2026-10-16")
    assert build_digest.build_weekly_item("p", "P", [_weekly_events()[1]], date(2026, 10, 16), "Oct 16–18", now, None) is None


def test_weekly_feed_is_valid_rss_with_image_and_full_content():
    import xml.etree.ElementTree as ET
    now = datetime(2026, 10, 14, 18, tzinfo=timezone.utc)
    item = build_digest.build_weekly_item("palatine-60067", "Palatine", _weekly_events(), date(2026, 10, 16), "Oct 16–18", now, {"url": "https://x/i.png", "length": 99})
    xml = build_digest.build_weekly_feed_xml("Palatine", "palatine-60067", [item], now)
    root = ET.fromstring(xml)
    (it,) = root.findall("./channel/item")
    ns = {"content": "http://purl.org/rss/1.0/modules/content/", "media": "http://search.yahoo.com/mrss/"}
    assert "Family Fun Day" in it.find("content:encoded", ns).text
    assert it.find("enclosure").attrib == {"url": "https://x/i.png", "type": "image/png", "length": "99"}
    assert it.find("media:content", ns).attrib["url"] == "https://x/i.png"
    assert it.find("guid").attrib["isPermaLink"] == "false"


def test_weekly_history_keeps_eight_weekends_and_replaces_a_rebuilt_one():
    history = {}
    for i in range(10):
        friday = date(2026, 9, 4) + timedelta(days=7 * i)
        build_digest.record_weekly_feed_item(history, "r", {"guid": f"g{friday}", "weekend": friday.isoformat(), "title": f"w{i}"})
    items = history["r"]
    assert len(items) == 8 and items[0]["weekend"] == "2026-11-06" and items[-1]["weekend"] == "2026-09-18"
    build_digest.record_weekly_feed_item(history, "r", {"guid": "g2026-11-06", "weekend": "2026-11-06", "title": "rebuilt"})
    assert len(history["r"]) == 8 and history["r"][0]["title"] == "rebuilt"


def test_find_village_post_requires_a_this_year_trick_or_treat_item_in_a_news_section():
    # ROADMAP.md item 301.
    def blk(section, *events):
        return {"section": section, "events": [dict({"url": "https://v/" + e["title"]}, **e) for e in events]}
    news = blk("Village News",
               {"title": "Trick-or-Treat Hours Announced", "date_iso": "2026-10-14T00:00:00"},
               {"title": "Trick-or-Treat Hours", "date_iso": "2025-10-10T00:00:00"},
               {"title": "Trunk-or-Treat at the Park", "date_iso": "2026-10-20T00:00:00"},
               {"title": "Leaf Collection", "date_iso": "2026-10-15T00:00:00"})
    assert build_digest.find_village_post([news], 2026) == {"title": "Trick-or-Treat Hours Announced", "url": "https://v/Trick-or-Treat Hours Announced"}
    assert build_digest.find_village_post([news], 2027) is None
    assert build_digest.find_village_post([blk("Library Events", {"title": "Trick-or-Treat Storytime", "date_iso": "2026-10-14T00:00:00"})], 2026) is None
    undated = blk("Village News", {"title": "Trick-or-Treat Hours", "date_iso": None})
    assert build_digest.find_village_post([undated], 2026) is None


def test_village_post_shows_beside_configured_hours_without_changing_them():
    entries = _tot_entries(2)
    entries[0]["village_post"] = {"title": "Hours Announced", "url": "https://v/post"}
    html = build_digest.render_trick_or_treat_page(entries, datetime(2026, 10, 18, 18, tzinfo=timezone.utc))
    assert 'Village posted: <a href="https://v/post">Hours Announced</a>' in html
    assert html.count("3–7 PM") >= 4 and "All on Saturday, October 31" in html  # both towns' configured hours, unchanged, in the table and the cards
    banner = build_digest.build_halloween_banner(entries, datetime(2026, 10, 18, 18, tzinfo=timezone.utc))
    assert banner["towns"][0]["post"] == {"title": "Hours Announced", "url": "https://v/post"} and banner["towns"][1]["post"] is None


def test_official_district_days_off_merge_with_feed_entries_without_duplicates():
    # ROADMAP.md item 300.
    feed = _school_block({"title": "No School - Veterans Day", "date_iso": "2026-11-11T00:00:00"})
    official = [
        {"date": "2026-11-11", "district": "D57", "reason": "No School | Veterans Day", "source_url": "https://x"},  # duplicate district and date
        {"date": "2026-11-23", "district": "D25", "reason": "No School | Fall Break", "source_url": "https://x"},
        {"date": "2026-11-25", "district": "", "reason": "No School", "source_url": "https://x"},  # no district: ignored
    ]
    days = build_digest.build_days_off([feed], date(2026, 11, 2), official=official)
    assert [d["label"] for d in days] == ["Wed Nov 11", "Mon Nov 23"]
    assert days[0]["reasons"] == [{"district": "D57", "reason": "No School - Veterans Day"}]  # the feed's own wording wins
    assert days[1]["reasons"] == [{"district": "D25", "reason": "No School | Fall Break"}]


def test_configured_official_days_off_are_in_the_current_school_year():
    # ROADMAP.md item 300: a stale year cannot slip through.
    import glob, yaml
    for path in glob.glob(str(build_digest.CONFIG_DIR / "regions" / "*.yaml")):
        for entry in (yaml.safe_load(open(path)) or {}).get("days_off") or []:
            day = date.fromisoformat(str(entry["date"]))
            assert date(2026, 8, 1) <= day <= date(2027, 7, 31), (path, entry)
            assert entry.get("source_url", "").startswith("https://"), (path, entry)


def test_night_out_picks_the_earliest_evening_arts_event_and_never_a_promo():
    # ROADMAP.md item 284. 2026-10-16 is a Friday, 10-17 a Saturday, 10-18 a Sunday.
    def ev(title, day, hour, tags=("art_culture",), **kw):
        return dict({"title": title, "url": "https://x/" + title, "date_iso": f"2026-10-{day}T{hour}:00:00", "tags": list(tags)}, **kw)
    blocks = [{"region_name": "Arlington Heights", "attendable_events": [
        ev("Late Show", 17, 20, email_where="Metropolis"), ev("Matinee", 17, 14), ev("Sunday Show", 18, 19),
        ev("Paid Show", 16, 19, sponsored_by="Acme"), ev("Not Arts", 16, 19, tags=("indoor",)),
    ]}, {"region_name": "Des Plaines", "attendable_events": [ev("Friday Concert", 16, 19, email_where="Des Plaines Theatre")]}]
    pick = build_digest.pick_night_out(blocks)
    assert pick["title"] == "Friday Concert" and pick["venue"] == "Des Plaines Theatre" and pick["when"].startswith("Friday")
    assert build_digest.pick_night_out([{"region_name": "A", "attendable_events": [ev("Matinee", 17, 14), ev("Sunday Show", 18, 19)]}]) is None
    html = build_digest.render_combined_email_digest(_join_sections(), "Oct 16–18", datetime(2026, 10, 14, 18, tzinfo=timezone.utc), None)
    assert "Night out:" not in html


def test_night_out_line_renders_in_the_email_when_an_evening_arts_event_exists():
    sections = _join_sections()
    sections[0]["weekend_events"].append({"title": "Opening Night", "url": "https://src/o", "date_iso": "2026-10-16T19:30:00", "date": "2026-10-16", "detail": "", "tags": ["art_culture"], "venue": "Metropolis"})
    html = build_digest.render_combined_email_digest(sections, "Oct 16–18", datetime(2026, 10, 14, 18, tzinfo=timezone.utc), None)
    assert "NIGHT OUT" in html and "Opening Night" in html and "Friday 7:30 PM" in html


def test_celebration_windows_keywords_and_hub_block():
    # ROADMAP.md item 295.
    cels = [
        {"name": "Día de los Muertos", "start": "10-25", "end": "11-02", "keywords": ["dia de los muertos", "ofrenda"]},
        {"name": "Diwali", "date": "2026-11-08", "days_before": 21, "days_after": 3, "keywords": ["diwali", "rangoli"]},
    ]
    active = lambda d: [c["name"] for c in build_digest.active_celebrations(d, cels)]
    assert active(date(2026, 10, 17)) == [] and active(date(2026, 10, 18)) == ["Diwali"]  # Diwali opens 21 days before Nov 8
    assert active(date(2026, 10, 24)) == ["Diwali"] and active(date(2026, 10, 25)) == ["Día de los Muertos", "Diwali"]
    assert active(date(2026, 11, 2)) == ["Día de los Muertos", "Diwali"] and active(date(2026, 11, 3)) == ["Diwali"]
    assert active(date(2026, 11, 11)) == ["Diwali"] and active(date(2026, 11, 12)) == []
    assert active(date(2027, 10, 30)) == ["Día de los Muertos"]  # fixed dates recur; Diwali's 2026 date never opens in 2027
    blocks = [{"events": [
        {"title": "DIY Ofrendas Workshop", "detail": ""}, {"title": "Craft Hour", "detail": "Make a rangoli design"},
        {"title": "Chess Club", "detail": ""},
    ]}]
    build_digest.annotate_celebrations(blocks, date(2026, 10, 30), cels)
    assert [e.get("celebration") for e in blocks[0]["events"]] == ["Día de los Muertos", "Diwali", None]
    # A celebration adds one point of relevance and shows in the weekend hub's block; with none, no block.
    plain = {"title": "Craft Hour", "tags": []}
    assert build_digest.family_relevance(blocks[0]["events"][1]) == build_digest.family_relevance(plain) + 1
    sections = [{"region_name": "Mount Prospect", "region_url": "https://x/mp/", "events": blocks[0]["events"]}]
    block = build_digest.build_celebration_block(sections)
    assert [(g["name"], [e["title"] for e in g["events"]]) for g in block] == [("Día de los Muertos", ["DIY Ofrendas Workshop"]), ("Diwali", ["Craft Hour"])]
    assert build_digest.build_celebration_block([{"region_name": "A", "region_url": "u", "events": [{"title": "Chess Club"}]}]) == []


def test_election_day_line_windows_and_official_link():
    # ROADMAP.md item 298. Election Day 2026 is Tue Nov 3; 2027 has none in this rule's year-agnostic form: Nov 2.
    at = lambda m, d, y=2026: datetime(y, m, d, 18, tzinfo=timezone.utc)
    line = build_digest.election_day_line
    assert line(at(11, 1)) is None and line(at(11, 2))["text"].startswith("🗳️ Election Day is Tue Nov 3") and line(at(11, 3)) is not None and line(at(11, 4)) is None
    assert line(at(10, 26), email=True) is None and line(at(10, 27), email=True) is not None and line(at(11, 4), email=True) is None
    assert line(at(11, 2))["url"].startswith("https://www.cookcountyclerkil.gov")
    assert "candidate" not in line(at(11, 2))["text"].lower()
    assert line(at(11, 1, 2027))["text"].startswith("🗳️ Election Day is Tue Nov 2")  # the first Tuesday after the first Monday


def test_days_off_sponsor_needs_a_current_until_date_and_is_labelled_paid():
    # ROADMAP.md item 297.
    cfg = {"regions": {"r": {"days_off_sponsor": {"title": "Example Camps", "url": "https://c/", "detail": "Camps every day off.", "until": "2026-11-13"}}}}
    assert build_digest.build_days_off_sponsor(cfg, "r", date(2026, 11, 13))["title"] == "Example Camps"
    assert build_digest.build_days_off_sponsor(cfg, "r", date(2026, 11, 14)) is None
    assert build_digest.build_days_off_sponsor(cfg, "other", date(2026, 11, 1)) is None
    assert build_digest.build_days_off_sponsor({"regions": {"r": {"days_off_sponsor": {"title": "X", "url": "https://c/"}}}}, "r", date(2026, 11, 1)) is None  # no `until`
    days = [{"date": date(2026, 11, 11), "end": date(2026, 11, 11), "label": "Wed Nov 11", "reasons": [{"district": "D57", "reason": "No School"}], "ideas": []}]
    region_cfg = {"region": {"id": "r", "name": "R", "zip": "60056", "state": "IL", "tagline": "t", "timezone": "America/Chicago"}}
    html = build_digest.render_region_page(region_cfg, [], None, [], datetime(2026, 11, 2, 18, tzinfo=timezone.utc), days_off=days, days_off_sponsor=build_digest.build_days_off_sponsor(cfg, "r", date(2026, 11, 2)))
    assert "Sponsored" in html and "No school? Presented by" in html and "Example Camps" in html
    assert html.index("D57: No School") < html.index("Presented by")  # below the free listings
    assert "Election Day is Tue Nov 3" in html  # Nov 2 render


def test_winter_break_season_window_and_event_selection():
    # ROADMAP.md item 259.
    at = lambda y, m, d: datetime(y, m, d, 18, tzinfo=timezone.utc)
    assert not build_digest.winter_break_season(at(2026, 10, 31)) and build_digest.winter_break_season(at(2026, 11, 1))
    assert build_digest.winter_break_season(at(2027, 1, 4)) and not build_digest.winter_break_season(at(2027, 1, 5))
    assert build_digest.winter_break_window(at(2026, 11, 20)) == (date(2026, 12, 21), date(2027, 1, 3))
    assert build_digest.winter_break_window(at(2027, 1, 2)) == (date(2026, 12, 21), date(2027, 1, 3))  # still last year's break in January
    events = [
        {"title": "Winter Break Camp: Robotics", "url": "https://a", "date_iso": "2026-12-28T09:00:00"},
        {"title": "School's Out Lego Day", "url": "https://b", "date_iso": "2027-01-02T10:00:00"},
        {"title": "Camp Info Night", "url": "https://c", "date_iso": "2026-12-10T19:00:00"},  # before the break
        {"title": "Toddler Storytime", "url": "https://d", "date_iso": "2026-12-28T10:00:00"},  # not a camp
        {"title": "Holiday Camp", "url": "https://e", "date_iso": "2027-01-04T10:00:00"},  # after
    ]
    picked = build_digest.select_winter_break_events([{"events": events}], at(2026, 11, 20))
    assert [e["title"] for e in picked] == ["Winter Break Camp: Robotics", "School's Out Lego Day"]
    ever = [{"title": "Park District Camp Catalog", "detail": "", "url": "https://p"}, {"title": "Library", "detail": "Books and camp-fire stories", "url": "https://l"}, {"title": "Village Hall", "detail": "Permits", "url": "https://v"}]
    assert [e["title"] for e in build_digest.winter_break_catalogues(ever)] == ["Park District Camp Catalog", "Library"]
    assert "winter-break/" in " ".join(build_digest.collect_sitemap_urls([{"path": "a/", "winter_break": True}]))
    assert "winter-break/" not in " ".join(build_digest.collect_sitemap_urls([{"path": "a/"}]))


def test_winter_break_page_shows_the_labelled_sponsor_without_a_days_off_box():
    region_cfg = {"region": {"id": "r", "name": "R", "zip": "60056", "state": "IL", "tagline": "t", "timezone": "America/Chicago"}}
    sponsor = {"title": "Example Camps", "url": "https://c/", "detail": "Winter camps."}
    html = build_digest.render_region_page(region_cfg, [], None, [], datetime(2026, 11, 20, 18, tzinfo=timezone.utc), days_off_sponsor=sponsor)
    assert "Sponsored" in html and "Presented by" in html and "Example Camps" in html
    assert "Winter break camps" in html  # footer link in season


def test_outbound_click_listener_is_present_only_with_analytics_and_sends_only_the_hostname():
    # ROADMAP.md item 267.
    region_cfg = {"region": {"id": "r", "name": "R", "zip": "60056", "state": "IL", "tagline": "t", "timezone": "America/Chicago"}}
    analytics = {"configured": True, "goatcounter_code": "withinten"}
    now = datetime(2026, 11, 2, 18, tzinfo=timezone.utc)
    with_a = build_digest.render_region_page(region_cfg, [], None, [], now, analytics=analytics)
    assert 'goatcounter.count({path:"out/"+a.hostname,event:true})' in with_a
    assert "location.hostname" in with_a  # only links leaving the site
    assert "goatcounter.count({path:\"out/" not in build_digest.render_region_page(region_cfg, [], None, [], now)
    hub = build_digest.render_merged_hub_page([], now, analytics, subheading="s", meta_description="m", empty_message="e")
    assert 'path:"out/"+a.hostname' in hub


def test_audience_line_needs_a_snapshot_above_the_floor(tmp_path):
    # ROADMAP.md item 266.
    path = tmp_path / "audience.json"
    assert build_digest.load_audience_line(path) is None  # no file
    path.write_text(json.dumps({"as_of": "2026-11-02", "visits_30d": 499, "subscribers": 49, "ai_referrals_30d": 3}), encoding="utf-8")
    assert build_digest.load_audience_line(path) is None  # below both floors
    path.write_text(json.dumps({"as_of": "2026-11-02", "visits_30d": 500, "subscribers": None, "ai_referrals_30d": 0}), encoding="utf-8")
    assert build_digest.load_audience_line(path) == {"visits": 500, "subscribers": None, "ai_referrals": None, "as_of": "2026-11-02"}
    path.write_text(json.dumps({"visits_30d": 10, "subscribers": 50, "ai_referrals_30d": 4}), encoding="utf-8")
    assert build_digest.load_audience_line(path)["ai_referrals"] == 4
    path.write_text("not json", encoding="utf-8")
    assert build_digest.load_audience_line(path) is None


def test_sponsor_page_shows_the_audience_line_only_with_numbers():
    now = datetime(2026, 11, 2, 18, tzinfo=timezone.utc)
    with_a = build_digest.render_sponsor_page([], now, None, audience={"visits": 812, "subscribers": 61, "ai_referrals": 5, "as_of": "2026-11-02"})
    assert 'id="audience"' in with_a and "<strong>812</strong> visits" in with_a and "<strong>61</strong> email subscribers" in with_a and "5</strong> visits from AI assistants" in with_a
    assert 'id="audience"' not in build_digest.render_sponsor_page([], now, None)


def test_winter_strip_window_and_links():
    # ROADMAP.md item 285, third window.
    at = lambda y, m, d: datetime(y, m, d, 18, tzinfo=timezone.utc)
    towns = [{"name": "Palatine", "path": "palatine-60067/", "winter_break": True}, {"name": "Wheeling", "path": "wheeling-60090/", "winter_break": False}]
    f = build_digest.build_winter_banner
    assert f(towns, at(2026, 12, 14)) is None and f(towns, at(2026, 12, 15)) == {"links": [{"name": "Palatine", "url": "palatine-60067/winter-break/"}]}
    assert f(towns, at(2027, 1, 3)) is not None and f(towns, at(2027, 1, 4)) is None
    assert f([{"name": "X", "path": "x/"}], at(2026, 12, 20)) is None  # no winter-break page, no strip
    html = build_digest.render_hub_page([], [{"name": "Palatine", "zip": "60067", "path": "palatine-60067/", "tagline": "t", "event_count": 1, "id": "p"}], at(2026, 12, 20), None, None, winter=f(towns, at(2026, 12, 20)))
    assert "Kids off school?" in html and 'href="palatine-60067/winter-break/"' in html


def test_add_your_event_link_shows_only_once_the_form_url_is_configured():
    # ROADMAP.md item 246.
    region_cfg = {"region": {"id": "r", "name": "R", "zip": "60056", "state": "IL", "tagline": "t", "timezone": "America/Chicago"}}
    now = datetime(2026, 10, 16, 18, tzinfo=timezone.utc)
    cfg = build_digest.load_newsletter_config({"buttondown_username": "u", "event_form_url": " https://forms.gle/abc "})
    assert cfg["event_form_url"] == "https://forms.gle/abc"
    assert build_digest.load_newsletter_config({"buttondown_username": "u", "event_form_url": ""})["event_form_url"] is None
    page = build_digest.render_region_page(region_cfg, [], None, [], now, newsletter=cfg)
    assert 'href="https://forms.gle/abc" rel="noopener">Add your event, free' in page
    assert "Add your event, free" not in build_digest.render_region_page(region_cfg, [], None, [], now, newsletter=build_digest.load_newsletter_config({"buttondown_username": "u"}))
    email = build_digest.render_combined_email_digest(_join_sections(), "Oct 16–18", now, cfg)
    assert 'href="https://forms.gle/abc" style="color:#ffd23f;">Add it free' in email


def _meta_events(n, **kw):
    return [dict({"title": f"Event {i}", "url": f"https://x/{i}", "date_iso": "2026-10-17T10:00:00", "tags": ["kid_friendly"]}, **kw) for i in range(n)]


def test_search_meta_title_description_and_h1_match_the_query():
    # ROADMAP.md item 310.
    events = _meta_events(3) + [{"title": "Fishing Derby", "url": "https://x/f", "date_iso": "2026-10-17T09:00:00", "tags": ["kid_friendly", "free", "outdoor"]}]
    meta = build_digest.build_search_meta("Mount Prospect", "IL", events, when="This Weekend", date_range="Oct 16–18")
    assert meta["title"] == "Things to Do in Mount Prospect, IL This Weekend (Oct 16–18)"
    assert meta["h1"] == "Things to do in Mount Prospect this weekend"
    assert meta["description"].startswith("4 things to do Oct 16–18: Fishing Derby, ")
    assert "and more" not in meta["description"] or len(meta["description"]) <= build_digest.DESCRIPTION_LIMIT
    assert meta["description"].endswith("from the village, library and park district.")
    week = build_digest.build_search_meta("Mount Prospect", "IL", events, when="Events This Week")
    assert week["title"] == "Things to Do in Mount Prospect, IL: Events This Week"
    assert week["description"].startswith("4 things to do this week: ")


def test_search_meta_respects_length_limits_and_the_zero_count_fallback():
    long_events = [{"title": "A" * 70 + str(i), "url": "https://x", "date_iso": "2026-10-17T10:00:00", "tags": []} for i in range(5)]
    meta = build_digest.build_search_meta("Arlington Heights", "IL", long_events, when="This Weekend", date_range="October 16 – October 18, 2026")
    assert len(meta["title"]) <= build_digest.TITLE_LIMIT and "(" not in meta["title"]  # the date range is dropped first
    assert len(meta["description"]) <= build_digest.DESCRIPTION_LIMIT
    assert build_digest.build_search_meta("X", "IL", [], when="This Weekend", date_range="Oct 16–18") is None
    assert build_digest.build_search_meta("X", "IL", _meta_events(2, sponsored_by="Acme"), when="This Weekend") is None  # paid never counts
    # Paid and non-attendable events never become named picks.
    picks = build_digest.top_pick_titles(_meta_events(1, sponsored_by="Acme") + [{"title": "Real", "url": "u", "tags": []}, {"title": "Notice", "url": "u", "attendable": False}])
    assert picks == ["Real"]


def test_region_page_uses_search_meta_for_title_description_and_og():
    region_cfg = {"region": {"id": "mp", "name": "Mount Prospect", "zip": "60056", "state": "IL", "tagline": "t", "timezone": "America/Chicago"}}
    meta = build_digest.build_search_meta("Mount Prospect", "IL", _meta_events(3), when="This Weekend", date_range="Oct 16–18")
    html = build_digest.render_region_page(region_cfg, [], None, [], datetime(2026, 10, 14, 18, tzinfo=timezone.utc), search_meta=meta)
    assert "<title>Things to Do in Mount Prospect, IL This Weekend (Oct 16–18) | Within Ten</title>" in html
    assert html.count('3 things to do Oct 16–18') >= 2  # meta description and og:description stay in step


def test_hub_weekend_description_counts_the_towns_events():
    sections = [{"region_name": "Palatine", "events": _meta_events(2)}, {"region_name": "Wheeling", "events": _meta_events(1)}]
    desc = build_digest.build_hub_weekend_description(["Wheeling", "Palatine"], sections, "Oct 16–18")
    assert desc.startswith("3 things to do this weekend (Oct 16–18) in Palatine and Wheeling") and len(desc) <= build_digest.DESCRIPTION_LIMIT
    assert "Things to do this weekend in" in build_digest.build_hub_weekend_description(["Palatine"], [], "")


def test_region_page_has_no_html_comments_and_short_aria_labels():
    # ROADMAP.md item 305: developer notes are Jinja comments, never repeated per card.
    region_cfg = {"region": {"id": "r", "name": "R", "zip": "60056", "state": "IL", "tagline": "t", "timezone": "America/Chicago"}}
    long_title = "Water Main Work " + "very long " * 30
    block = {"section": "News", "events": [{"title": long_title, "url": "https://x/1", "detail": "", "date_iso": "2026-10-20T10:00:00", "date": "Oct 20", "tags": []}]}
    html = build_digest.render_region_page(region_cfg, [block], None, [], datetime(2026, 10, 14, 18, tzinfo=timezone.utc))
    assert "<!--" not in html
    label = re.search(r'aria-label="Add ([^"]*) to My Weekend"', html).group(1)
    assert len(label) <= 71 and label.endswith("…")
    for name in ("hub", "merged_hub", "sponsor", "about", "trick_or_treat"):
        assert "<!--" not in (build_digest.TEMPLATES_DIR / f"{name}.html.j2").read_text(encoding="utf-8") or name == "x"


def _ever(title, tags):
    return {"title": title, "url": f"https://e/{title}", "detail": "", "tags": tags}


def test_thin_week_ideas_threshold_order_and_label():
    # ROADMAP.md item 312.
    ever = [_ever("Museum Pass", ["indoor"]), _ever("Open Swim", ["indoor", "kid_friendly", "free"]), _ever("Hike", ["outdoor", "kid_friendly"]),
            _ever("Maker Space", ["indoor", "free"]), _ever("Play Cafe", ["indoor", "kid_friendly"]), {"title": "No link", "tags": ["indoor"]}]
    ideas = build_digest.thin_week_ideas(ever, 3)
    assert [e["title"] for e in ideas] == ["Open Swim", "Maker Space", "Play Cafe"]  # kid-friendly and free first, at most three, indoor only
    assert build_digest.thin_week_ideas(ever, 4) == [] and build_digest.thin_week_ideas(ever, 12) == []  # a busy week changes nothing


def test_thin_week_email_block_is_labelled_and_absent_on_a_busy_week():
    now = datetime(2026, 10, 14, 18, tzinfo=timezone.utc)
    sections = _join_sections()
    sections[0]["evergreen"] = [_ever("Open Swim", ["indoor", "kid_friendly", "free"])]
    thin = build_digest.render_combined_email_digest(sections, "Oct 16–18", now, None)
    assert "Indoor ideas, anytime this week" in thin and "Open Swim" in thin
    busy = _join_sections()
    busy[0]["evergreen"] = [_ever("Open Swim", ["indoor", "kid_friendly", "free"])]
    for i in range(5):
        busy[0]["weekend_events"].append({"title": f"Extra {i}", "url": f"https://x/{i}", "date_iso": "2026-10-17T10:00:00", "date": "2026-10-17", "detail": "", "tags": []})
    assert "Indoor ideas" not in build_digest.render_combined_email_digest(busy, "Oct 16–18", now, None)


def test_closure_windows():
    # ROADMAP.md item 307.
    w = build_digest.closure_window
    assert w(date(2026, 11, 22)) is None and w(date(2026, 11, 23)) == (date(2026, 11, 23), date(2026, 11, 29)) and w(date(2026, 11, 29)) is not None and w(date(2026, 11, 30)) is None
    assert w(date(2026, 12, 21))[1] == date(2026, 12, 27) and w(date(2026, 12, 28)) == (date(2026, 12, 28), date(2027, 1, 3)) and w(date(2027, 1, 2)) == (date(2026, 12, 28), date(2027, 1, 3))
    assert w(date(2027, 1, 4)) is None and w(date(2026, 7, 4)) is None


def test_closures_come_only_from_what_a_source_posts():
    news = {"section": "Village News", "events": [
        {"title": "Library closed Thursday for Thanksgiving", "url": "https://l/1", "date_iso": "2026-11-26T00:00:00"},
        {"title": "Refuse pickup delayed one day", "url": "https://v/2", "date_iso": "2026-11-27T00:00:00"},
        {"title": "Turkey Trot 5K", "url": "https://v/3", "date_iso": "2026-11-26T08:00:00"},  # not a closure
        {"title": "Library closed for renovations", "url": "https://l/4", "date_iso": "2026-12-04T00:00:00"},  # outside the window
    ]}
    school = {"section": "School Calendar", "events": [{"title": "Schools closed", "url": "https://s", "date_iso": "2026-11-26T00:00:00"}]}
    found = build_digest.build_closures([news, school], date(2026, 11, 24))
    assert [c["title"] for c in found] == ["Library closed Thursday for Thanksgiving", "Refuse pickup delayed one day"]
    assert build_digest.build_closures([news, school], date(2026, 11, 20)) == []  # not a holiday week: nothing shown
    assert build_digest.build_closures([{"section": "Village News", "events": []}], date(2026, 11, 24)) == []
    line = build_digest.build_closures_email_line([{"region_name": "Palatine", "region_url": "https://x/p/", "closures": found}], datetime(2026, 11, 24, tzinfo=timezone.utc))
    assert line["text"].startswith("🔒 Palatine: Library closed Thursday") and line["url"] == "https://x/p/#closures"
    region_cfg = {"region": {"id": "p", "name": "Palatine", "zip": "60067", "state": "IL", "tagline": "t", "timezone": "America/Chicago"}}
    html = build_digest.render_region_page(region_cfg, [], None, [], datetime(2026, 11, 24, 18, tzinfo=timezone.utc), closures=found)
    assert 'id="closures"' in html and "Closed or changed this week" in html
    assert 'id="closures"' not in build_digest.render_region_page(region_cfg, [], None, [], datetime(2026, 11, 24, 18, tzinfo=timezone.utc))


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _mix_white(hex_color: str, white_share: float) -> str:
    h = hex_color.lstrip("#")
    return "#%02x%02x%02x" % tuple(round(int(h[i:i + 2], 16) * (1 - white_share) + 255 * white_share) for i in (0, 2, 4))


def test_seasonal_page_text_meets_contrast_in_light_and_dark():
    # ROADMAP.md item 309: the pairs the seasonal pages use, in fixed colours.
    pairs = {
        "join hero white on red": ("#ffffff", "#c4280e"), "join hero kicker": ("#ffe9b3", "#c4280e"),
        "halloween kicker": ("#ffb347", "#1a0f2b"), "halloween pill text": ("#fff4e6", "#1a0f2b"), "halloween button": ("#1a0f2b", "#ff7a00"),
        "trick-or-treat sub": ("#e8dcff", "#1a0f2b"), "holiday gold on green": ("#f5c542", "#14532d"), "holiday text on dark red": ("#fdf6e3", "#7f1d1d"),
        "holiday offer button": ("#14301f", "#f5c542"), "holiday offer box": ("#14301f", "#f0f9f3"), "winter strip link": ("#1d4ed8", "#e8f1fb"),
        "rain plan heading": ("#1d4ed8", "#eaf4ff"),
    }
    for name, (fg, bg) in pairs.items():
        assert _contrast(fg, bg) >= 4.5, (name, round(_contrast(fg, bg), 2))
    # Town colours as text on the dark theme's card and page: lightened by the pages' own 45% mix.
    for color, _tint in build_digest.EMAIL_TOWN_COLORS:
        assert _contrast(color, "#ffffff") >= 4.5, color  # on a light page
        for dark_bg in ("#232120", "#171615"):
            assert _contrast(_mix_white(color, 0.55), dark_bg) >= 4.5, (color, dark_bg)


def test_seasonal_animations_only_run_without_reduced_motion():
    # ROADMAP.md item 309: every `animation:` sits inside a prefers-reduced-motion: no-preference block.
    for name in ("hub", "trick_or_treat", "holidays", "join", "region", "merged_hub"):
        css = re.sub(r"\{#.*?#\}", lambda m: " " * len(m.group(0)), (build_digest.TEMPLATES_DIR / f"{name}.html.j2").read_text(encoding="utf-8"), flags=re.S)
        safe = []
        for m in re.finditer(r"@media\s*\(prefers-reduced-motion:\s*no-preference\)\s*\{", css):
            depth, i = 1, m.end()
            while depth and i < len(css):
                depth += (css[i] == "{") - (css[i] == "}")
                i += 1
            safe.append((m.start(), i))
        for m in re.finditer(r"(?<![-\w])animation(?:-delay)?\s*:(?!\s*none)", css):
            assert any(a <= m.start() < b for a, b in safe), (name, css[max(0, m.start() - 60):m.start() + 40])


def test_tot_hours_helpers_and_calendar_window():
    # ROADMAP.md item 318.
    assert build_digest.short_tot_hours("3:00–7:00 PM, Saturday, October 31") == "3–7 PM"
    assert build_digest.short_tot_hours("3:00–8:30 PM, Saturday, October 31") == "3–8:30 PM"
    assert build_digest.tot_hours_date("3:00–7:00 PM, Saturday, October 31") == "Saturday, October 31" and build_digest.tot_hours_date("3–7 PM") is None
    start, end = build_digest.parse_tot_window("3:00–7:00 PM, Saturday, October 31", 2026)
    assert (start, end) == (datetime(2026, 10, 31, 15, 0), datetime(2026, 10, 31, 19, 0))
    assert build_digest.parse_tot_window("11 AM–1 PM, Saturday, October 31", 2026)[0].hour == 11
    assert build_digest.parse_tot_window("Evening, October 31", 2026) is None and build_digest.parse_tot_window(None, 2026) is None
    uri = build_digest.build_tot_ics_uri("Palatine", "3:00–7:00 PM, Saturday, October 31", "https://v/p", 2026)
    assert uri.startswith("data:text/calendar") and "DTSTART%3A20261031T150000" in uri and "DTEND%3A20261031T190000" in uri
    assert build_digest.build_tot_ics_uri("Des Plaines", None, "https://v/d", 2026) is None


def test_trick_or_treat_page_has_a_one_glance_table_chips_and_calendar_links():
    entries = _tot_entries(5)
    entries[2].update(hours=None, no_official_hours=True)  # Des Plaines-style: no set hours
    entries[4].update(hours=None)  # not yet posted
    html = build_digest.render_trick_or_treat_page(entries, datetime(2026, 10, 18, 18, tzinfo=timezone.utc))
    assert "<h1>Trick-or-treat hours 2026</h1>" in html
    table = html.split('<table class="glance">')[1].split("</table>")[0]
    rows = re.findall(r"<th scope=\"row\"><a href=\"#tot-([^\"]+)\">[^<]+</a></th>\s*<td>([^<]*)(?:<span.*?</span>)?</td>", table)
    assert [r[0] for r in rows] == ["r0", "r1", "r2", "r3", "r4"]  # region order
    assert [r[1] for r in rows] == ["3–7 PM", "3–7 PM", "No set hours", "3–7 PM", "Not posted yet"]
    assert "All on Saturday, October 31" in html
    assert html.count("Add to calendar") == 3  # only towns with parsable hours
    assert 'id="tot-r2"' in html
    # Hours on different dates are never collapsed into one shared date.
    mixed = _tot_entries(2)
    mixed[1]["hours"] = "3–7 PM, Friday, October 30"
    page = build_digest.render_trick_or_treat_page(mixed, datetime(2026, 10, 18, 18, tzinfo=timezone.utc))
    assert "All on" not in page and "Friday, October 30" in page and "Saturday, October 31" in page


def test_trunk_or_treat_rows_lead_with_a_town_chip():
    ev = {"title": "Trunk or Treat", "url": "https://s", "date_iso": "2026-10-24T10:00:00", "anchor_id": "a", "date_label": "Sat, Oct 24"}
    entries = _tot_entries(1)
    entries[0]["events"] = [ev]
    html = build_digest.render_trick_or_treat_page(entries, datetime(2026, 10, 18, 18, tzinfo=timezone.utc))
    assert re.search(r'<li><span class="chip" style="background:#[0-9a-f]{6}">Mount Prospect</span>', html)


def test_checked_label_shows_only_a_recent_check(tmp_path):
    # ROADMAP.md item 317.
    path = tmp_path / "watch.json"
    path.write_text(json.dumps({"p": {"checked_at": "2026-10-25T14:00+00:00"}, "w": {"checked_at": "2026-10-20T14:00+00:00"}, "bad": {"checked_at": "nonsense"}}), encoding="utf-8")
    now = datetime(2026, 10, 26, 13, tzinfo=timezone.utc)
    assert build_digest.load_tot_checked(now, path) == {"p": "Oct 25"}  # w is older than 72 hours
    entries = _tot_entries(1)
    entries[0]["region_id"] = "p"
    html = build_digest.render_trick_or_treat_page(entries, now, checked={"p": "Oct 25"})
    assert "Checked Oct 25 against the village page." in html
    assert "against the village page." not in build_digest.render_trick_or_treat_page(entries, now)


def _night_forecast(rain=20):
    return {"hours": {h: (50 + (h - 15), rain) for h in range(12, 22)}, "sunset": "2026-10-31T17:49"}


def test_halloween_night_averages_3_to_8_pm_and_formats_the_sunset():
    now = datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc)
    night = build_digest.build_halloween_night(_night_forecast(), now)
    assert night["temp"] == 52 and night["rain"] == 20 and night["sunset"] == "5:49 PM" and night["weekday"] == "Saturday"
    assert night["indoor"] == []


def test_halloween_night_is_gated_to_oct_24_through_31_and_needs_a_forecast():
    f = _night_forecast()
    assert build_digest.build_halloween_night(f, datetime(2026, 10, 23, 15, tzinfo=timezone.utc)) is None
    assert build_digest.build_halloween_night(f, datetime(2026, 10, 31, 15, tzinfo=timezone.utc)) is not None
    assert build_digest.build_halloween_night(f, datetime(2026, 11, 1, 15, tzinfo=timezone.utc)) is None
    assert build_digest.build_halloween_night(None, datetime(2026, 10, 28, 15, tzinfo=timezone.utc)) is None


def test_halloween_night_lists_three_indoor_events_only_at_60_percent_rain():
    events = [{"title": f"E{i}", "url": f"https://x/{i}", "tags": ["indoor"]} for i in range(5)] + [{"title": "Out", "url": "https://x/o", "tags": ["outdoor"]}]
    now = datetime(2026, 10, 28, 15, tzinfo=timezone.utc)
    assert build_digest.build_halloween_night(_night_forecast(59), now, events)["indoor"] == []
    wet = build_digest.build_halloween_night(_night_forecast(60), now, events)
    assert [e["title"] for e in wet["indoor"]] == ["E0", "E1", "E2"]


def test_trick_or_treat_page_shows_the_box_only_with_a_forecast():
    now = datetime(2026, 10, 28, 15, tzinfo=timezone.utc)
    entries = [{"region_id": "mount-prospect-60056", "region_name": "Mount Prospect", "region_url": "https://x/", "url": "https://v/", "hours": "3:00-7:00 PM, Saturday, October 31", "events": []}]
    with_box = build_digest.render_trick_or_treat_page(entries, now, night_forecast=_night_forecast())
    assert "Saturday 3&ndash;8 PM: 52&deg;F, 20% rain." in with_box and "Dark by 5:49 PM: bring a light." in with_box and "Forecast, updated Oct 28" in with_box
    assert 'class="night"' not in build_digest.render_trick_or_treat_page(entries, now)


def test_short_paths_point_at_real_region_pages_and_collide_with_nothing():
    regions = {json.loads(json.dumps(yaml.safe_load(p.read_text(encoding="utf-8"))))["region"]["id"] for p in (Path(__file__).resolve().parent.parent / "config" / "regions").glob("*.yaml")}
    assert set(build_digest.SHORT_PATHS) == regions
    reserved = {"this-weekend", "today", "free", "sponsor", "about", "trick-or-treat", "holidays", "join", "issues", "og", "feed", "later"}
    shorts = list(build_digest.SHORT_PATHS.values())
    assert len(set(shorts)) == len(shorts) and not (set(shorts) & (reserved | regions))
    page = build_digest.render_short_redirect("mount-prospect-60056")
    assert "utm_source=print&amp;utm_campaign=short" in page and 'content="noindex"' in page
    assert 'rel="canonical" href="' + build_digest.SITE_BASE_URL + 'mount-prospect-60056/"' in page


def test_short_paths_are_not_in_the_sitemap():
    urls = build_digest.collect_sitemap_urls([])
    assert not any(f"/{short}/" in u for u in urls for short in build_digest.SHORT_PATHS.values())


def test_flyer_url_and_variants_give_each_placement_its_own_campaign():
    assert build_digest.flyer_url("mount-prospect-60056", "flyer-general") == build_digest.SITE_BASE_URL + "mount-prospect-60056/?utm_source=print&utm_campaign=flyer-general#newsletter-signup"
    variants = build_digest.flyer_variants([{"id": "cafe-a", "label": "A"}, {"id": "lib-b", "label": "B"}, {"label": "no id"}])
    assert [v["campaign"] for v in variants] == ["flyer-general", "flyer-cafe-a", "flyer-lib-b"]


def test_flyer_page_is_noindex_dateless_and_hides_chrome_in_print():
    page = build_digest.render_flyer("mount-prospect-60056", "Mount Prospect", ["Library", "Park District", "Village"], "flyer-general")
    assert 'content="noindex"' in page and "<svg" in page and "withintenmiles.com/mp/" in page
    assert "Not affiliated with the Village." in page and "@media print" in page and "nav, footer { display: none; }" in page
    assert "sponsor" not in page.lower()
    assert page.count('class="copy"') == 1
    assert build_digest.render_flyer("mount-prospect-60056", "Mount Prospect", [], "flyer-general", 2).count('class="copy"') == 2


def test_dead_links_are_swapped_for_the_source_page_only_after_two_strikes():
    def block():
        return [{"section": "S", "source_page": "https://src/cal", "events": [
            {"title": "A", "url": "https://x/a", "date": "Oct 20", "date_iso": "2026-10-20T10:00:00", "town": "T"},
            {"title": "B", "url": "https://x/b", "date": "Oct 20", "date_iso": "2026-10-20T10:00:00", "town": "T"},
            {"title": "C", "url": "https://x/c", "date": "Oct 20", "date_iso": "2026-10-20T10:00:00", "town": "T"},
        ]}]
    health = {"https://x/a": {"status": 404, "strikes": 2}, "https://x/b": {"status": 404, "strikes": 1}, "https://x/c": {"status": 403, "strikes": 0}}
    blocks = block()
    assert build_digest.apply_link_health(blocks, health) == 1
    a, b, c = blocks[0]["events"]
    assert a["url"] == "https://src/cal" and a["link_moved"] and b["url"] == "https://x/b" and c["url"] == "https://x/c"
    nopage = block(); nopage[0]["source_page"] = None
    assert build_digest.apply_link_health(nopage, health) == 0


def test_link_candidates_cover_only_the_next_14_days_with_http_urls():
    blocks = [{"events": [
        {"url": "https://x/in", "date_iso": "2026-10-30T10:00:00"},
        {"url": "https://x/far", "date_iso": "2026-11-20T10:00:00"},
        {"url": "", "date_iso": "2026-10-20T10:00:00"},
        {"url": "https://x/undated", "date_iso": None},
    ]}]
    assert build_digest.collect_link_candidates(blocks, date(2026, 10, 17), "r") == [{"url": "https://x/in", "region": "r"}]


def test_trick_or_treat_table_and_cards_carry_the_note_or_the_source():
    # ROADMAP.md item 324.
    entries = _tot_entries(3)
    entries[0]["note"] = "The Village's standing hours, not yet confirmed for 2026."
    html = build_digest.render_trick_or_treat_page(entries, datetime(2026, 10, 18, 18, tzinfo=timezone.utc))
    table = html.split('<table class="glance">')[1].split("</table>")[0]
    rows = table.split("</tr>")
    assert "standing hours, not yet confirmed for 2026." in rows[0] and "posted by the village" not in rows[0]
    assert "posted by the village" in rows[1] and "standing hours" not in rows[1]
    cards = html.split('<div class="entry" ')[1:4]
    assert len(cards) == 3
    # Same stacked shape for every card: town, hours, then a note-or-source line.
    for c in cards:
        assert c.index('class="region"') < c.index('class="hours"') < c.index('class="source-line"')
    assert "standing hours, not yet confirmed" in cards[0] and "Posted by the village" in cards[1]


def test_flyer_v2_has_the_band_tiles_scan_label_and_a_take_one_strip_on_the_full_page_only():
    # ROADMAP.md item 329.
    full = build_digest.render_flyer("mount-prospect-60056", "Mount Prospect", [], "flyer-general", 1, "#6d28d9")
    half = build_digest.render_flyer("mount-prospect-60056", "Mount Prospect", [], "flyer-general", 2, "#6d28d9")
    for page in (full, half):
        assert "FREE &middot; every Thursday" in page and "#6d28d9" in page and "print-color-adjust: exact" in page
        assert "Scan me" in page and "Storytimes &amp; library programmes" in page and "From the village, library and park district calendars." in page
        assert not re.search(r"\b(20\d\d|January|February|March|April|May|June|July|August|September|October|November|December)\b", page.split("</style>")[1])
    assert full.count('class="tab"') == 4 and "Take one" in full
    assert "Take one" not in half


def _surface_mismatches(html: str) -> list[tuple[str, str, str]]:
    """Every element whose `wt-*` surface class forces a colour that differs
    from its own inline background-color (ROADMAP.md item 330)."""
    bad = []
    for m in re.finditer(r"<(?:td|table|body|div)\b[^>]*>", html):
        tag = m.group(0)
        cls = re.search(r'class="([^"]*)"', tag)
        bg = re.search(r"background-color:\s*(#[0-9a-fA-F]{6})", tag)
        if not cls:
            continue
        for c in cls.group(1).split():
            if c in build_digest.EMAIL_SURFACES and (not bg or bg.group(1).lower() != build_digest.EMAIL_SURFACES[c].lower()):
                bad.append((c, build_digest.EMAIL_SURFACES[c], bg.group(1) if bg else ""))
    return bad


def test_every_email_surface_class_forces_the_colour_its_element_already_has():
    sections = [{
        "region_name": "Mount Prospect", "region_url": "https://x/mount-prospect-60056/",
        "weekend_events": [{"title": "Oktoberfest", "url": "https://x/1", "date": "Saturday", "date_iso": "2026-10-17T10:00:00", "tags": ["free"], "detail": "d"}],
        "evergreen": [{"title": "Library", "url": "https://x/2", "tags": ["free"]}],
        "sponsor": {"name": "Acme", "headline": "h", "detail": "d", "url": "https://x/s"},
    }]
    html = build_digest.render_combined_email_digest(sections, "Oct 17–18", datetime(2026, 10, 15, 15, tzinfo=timezone.utc))
    assert "wt-page" in html and "wt-paper" in html
    assert _surface_mismatches(html) == []
    css = html.split("prefers-color-scheme: dark")[1]
    for cls, hex in build_digest.EMAIL_SURFACES.items():
        assert f".{cls} {{ background-color:{hex} !important; }}" in css


def test_did_you_go_poll_links_carry_the_issue_date_and_the_pages_are_noindex():
    # ROADMAP.md item 331.
    sections = [{
        "region_name": "Mount Prospect", "region_url": "https://x/mount-prospect-60056/",
        "weekend_events": [{"title": "Oktoberfest", "url": "https://x/1", "date": "Saturday", "date_iso": "2026-10-17T10:00:00", "tags": ["free"], "detail": "d"}],
        "evergreen": [], "sponsor": None,
    }]
    html = build_digest.render_combined_email_digest(sections, "Oct 17–18", datetime(2026, 10, 15, 15, tzinfo=timezone.utc))
    assert "Did you go to something from last week's email?" in html
    assert build_digest.SITE_BASE_URL + "thanks/went/?w=2026-10-15" in html and build_digest.SITE_BASE_URL + "thanks/not-yet/?w=2026-10-15" in html
    for kind in ("went", "not-yet"):
        page = build_digest.render_thanks_page(kind, [{"id": "mount-prospect-60056", "name": "Mount Prospect"}])
        assert '<meta name="robots" content="noindex">' in page and "Thanks, that helps us keep this useful." in page
        assert "mailto:?subject=" in page and "Mount Prospect" in page
        assert "/thanks/" not in "".join(build_digest.collect_sitemap_urls([]))


def test_registration_opens_phrases_ordinals_and_rejections():
    # ROADMAP.md item 327.
    from tagging import parse_registration_opens as reg
    event = date(2026, 11, 10)
    assert reg("Registration required, beginning Oct. 21st.", event) == date(2026, 10, 21)
    assert reg("Registration opens Wed, October 21", event) == date(2026, 10, 21)
    assert reg("sign up starting Oct 21", event) == date(2026, 10, 21)
    assert reg("Registration begins Oct 21, 2026", event) == date(2026, 10, 21)
    assert reg("Registration begins Nov 12", event) is None  # after the event
    assert reg("Registration begins Nov 10", event) is None  # same day
    assert reg("Registration opens soon", event) is None
    assert reg("Registration begins Oct 1. Sign up starting Oct 21", event) is None  # two different dates: ambiguous
    assert reg("Registration begins Oct 21", None) is None


def test_registration_badge_and_the_email_block():
    ev = {"title": "Cooking class", "url": "https://x/c", "date_iso": "2026-11-07T10:00:00", "attendable": True, "registration_opens": "2026-10-21"}
    past = {"title": "Old", "url": "https://x/o", "date_iso": "2026-10-01T10:00:00", "registration_opens": "2026-09-20"}
    blocks = [{"events": [ev, past]}]
    build_digest.annotate_registration(blocks, date(2026, 10, 18))
    assert ev["reg_badge"] == "Sign-up opens Wed, Oct 21" and "reg_badge" not in past
    build_digest.annotate_registration(blocks, date(2026, 10, 22))
    assert ev["reg_badge"] == "Sign-up open"
    assert [e["title"] for e in build_digest.build_signups_opening(blocks, date(2026, 10, 18))] == ["Cooking class"]
    assert build_digest.build_signups_opening(blocks, date(2026, 10, 10)) == []  # more than 7 days out
    assert build_digest.build_signups_opening(blocks, date(2026, 10, 22)) == []  # already open


def test_signups_block_is_omitted_when_empty_and_listed_when_present():
    base = {"region_name": "Mount Prospect", "region_url": "https://x/mount-prospect-60056/", "weekend_events": [], "evergreen": [], "sponsor": None}
    now = datetime(2026, 10, 18, 15, tzinfo=timezone.utc)
    assert "SIGN-UPS OPENING THIS WEEK" not in build_digest.render_combined_email_digest([base], "Oct 17–18", now)
    sec = dict(base, signups=[{"title": "Cooking class", "url": "https://x/c", "opens": date(2026, 10, 21), "opens_label": "Wed, Oct 21", "sessions_label": "Sat Nov 7", "town": "Mount Prospect"}])
    html = build_digest.render_combined_email_digest([sec], "Oct 17–18", now)
    assert "SIGN-UPS OPENING THIS WEEK" in html and "Cooking class" in html and "Sat Nov 7" in html and "sign-ups open Wed, Oct 21" in html


def test_adult_events_lose_the_kid_friendly_badge_and_kids_crafts_keep_it():
    # ROADMAP.md item 333.
    from tagging import infer_tags
    speakeasy = infer_tags(
        "BOURBON 'N BRASS SPEAKEASY: LIVE JAZZ",
        "Join us in our intimate Speakeasy for an evening of Jazz. Food and hand-crafted cocktails are available. All are welcome, family friendly after 5.",
    )
    assert "kid_friendly" not in speakeasy
    assert "kid_friendly" in infer_tags("Kids' Craft Hour", "Make something at the library")
    assert "kid_friendly" not in infer_tags("Craft Beer Fest", "Sample local brews")
    assert "kid_friendly" not in infer_tags("Wine tasting for families", "kids welcome")  # veto removes only
    assert "adults" not in infer_tags("Bar crawl", "21+")


def test_leading_contact_token_is_dropped_from_descriptions():
    detail = "Saturday, October 17 2026 10:00am - 11:15am \n  DesPlainesLionsClub@gmail.com\nThe Des Plaines Lions Club is hosting a volunteer hour!"
    assert build_digest.strip_description_header(detail).startswith("The Des Plaines Lions Club is hosting")
    assert build_digest.strip_description_header("https://x.org/signup Bring a friend.") == "Bring a friend."
    assert build_digest.strip_description_header("Email info@x.org for details.") == "Email info@x.org for details."


def test_issue_pages_link_to_the_previous_and_next_issue():
    # ROADMAP.md item 338.
    page = build_digest.render_issue_page(_issue(), newer={"date": "2026-10-22"}, older={"date": "2026-10-08"})
    assert f"{build_digest.SITE_BASE_URL}issues/2026-10-22/" in page and f"{build_digest.SITE_BASE_URL}issues/2026-10-08/" in page
    alone = build_digest.render_issue_page(_issue())
    assert "Previous issue" not in alone and "Next issue" not in alone


def test_hub_town_cards_show_two_picks_and_the_weekend_count_not_live_updates():
    # ROADMAP.md item 339.
    events = [
        {"title": "Fall Festival", "date_iso": "2026-10-24T11:00:00", "date": "Oct 24", "tags": ["kid_friendly", "free"], "attendable": True},
        {"title": "Jazz Night", "date_iso": "2026-10-23T20:00:00", "date": "Oct 23", "tags": [], "attendable": True},
        {"title": "Storytime", "date_iso": "2026-10-24T10:00:00", "date": "Oct 24", "tags": ["kid_friendly"], "attendable": True},
        {"title": "Paid", "date_iso": "2026-10-24T09:00:00", "date": "Oct 24", "tags": [], "attendable": True, "sponsored_by": "X"},
        {"title": "Office closed", "date_iso": "2026-10-24T09:00:00", "date": "Oct 24", "tags": [], "attendable": False},
    ]
    picks = build_digest.hub_town_picks(events)
    assert len(picks) == 2 and {p["title"] for p in picks} == {"Fall Festival", "Storytime"}
    assert picks[0]["title"] == "Storytime"  # earlier first
    assert build_digest.hub_town_picks([]) == []
    summaries = [{"name": "Mount Prospect", "zip": "60056", "state": "IL", "tagline": "t", "path": "mount-prospect-60056/", "event_count": 287, "weekend_picks": picks, "weekend_count": 3, "guides": []}]
    html = build_digest.render_hub_page([], summaries, datetime(2026, 10, 20, 15, tzinfo=timezone.utc), stats={"region_count": 1, "event_count": 287, "weekend_count": 3, "weekend_date_range": "Oct 23–25", "free_count": 1, "today_count": 0})
    assert "live update" not in html and "See all 3 this weekend" in html and "Fall Festival" in html
    assert "From the village, library and park district." in html


def test_weekend_rolls_to_next_weekend_from_sunday_3_pm():
    # ROADMAP.md item 341.
    tz = build_digest.LOCAL_TZ
    sun_1459, sun_1501, mon = datetime(2026, 10, 18, 14, 59, tzinfo=tz), datetime(2026, 10, 18, 15, 1, tzinfo=tz), datetime(2026, 10, 19, 9, 0, tzinfo=tz)
    assert build_digest.weekend_dates(build_digest.weekend_reference_date(sun_1459))[0] == date(2026, 10, 16)
    assert build_digest.weekend_dates(build_digest.weekend_reference_date(sun_1501))[0] == date(2026, 10, 23)
    assert build_digest.weekend_dates(build_digest.weekend_reference_date(mon))[0] == date(2026, 10, 23)
    assert build_digest.weekend_label(sun_1459) == "This weekend" and build_digest.weekend_label(sun_1501) == "Next weekend" and build_digest.weekend_label(mon) == "Next weekend"
    assert build_digest.weekend_label(datetime(2026, 10, 23, 9, tzinfo=tz)) == "This weekend"  # Friday


def test_a_town_with_an_empty_window_shows_its_next_events_or_the_plain_line():
    # ROADMAP.md item 342.
    blocks = [{"events": [
        {"title": "Later A", "date_iso": "2026-10-27T10:00:00", "date": "Oct 27", "attendable": True},
        {"title": "Later B", "date_iso": "2026-10-29T10:00:00", "date": "Oct 29", "attendable": True},
        {"title": "Too far", "date_iso": "2026-12-01T10:00:00", "date": "Dec 1", "attendable": True},
        {"title": "Passed", "date_iso": "2026-10-10T10:00:00", "date": "Oct 10", "attendable": True},
    ]}]
    assert [p["title"] for p in build_digest.hub_next_up(blocks, date(2026, 10, 19))] == ["Later A", "Later B"]
    assert build_digest.hub_next_up(blocks, date(2026, 11, 5)) == []
    base = {"name": "Palatine", "zip": "60067", "state": "IL", "tagline": "t", "path": "palatine-60067/", "event_count": 1, "weekend_picks": [], "weekend_count": 0, "guides": []}
    stats = {"region_count": 1, "event_count": 1, "weekend_count": 0, "weekend_date_range": "Oct 23–25", "weekend_label": "Next weekend", "free_count": 0, "today_count": 0}
    now = datetime(2026, 10, 19, 15, tzinfo=timezone.utc)
    with_next = build_digest.render_hub_page([], [dict(base, next_up=[{"emoji": "🎃", "title": "Later A", "when": "Tue Oct 27"}])], now, stats=stats)
    assert "Next up" in with_next and "Later A" in with_next and "See what's on in Palatine" in with_next and "Next weekend" in with_next
    plain = build_digest.render_hub_page([], [dict(base, next_up=[])], now, stats=stats)
    assert "Nothing dated in the next two weeks" in plain and "Next up" not in plain and " yet" not in plain.split("region-grid")[1].split("</main>")[0]


def test_trick_or_treat_has_a_compact_signup_under_the_hours_table_and_the_full_one_below():
    # ROADMAP.md item 345.
    entries = _tot_entries(3)
    html = build_digest.render_trick_or_treat_page(
        entries, datetime(2026, 10, 20, 18, tzinfo=timezone.utc), newsletter={"configured": True, "buttondown_username": "withinten", "headline": "Get it"}
    )
    top = html.index('id="newsletter-signup-top"')
    assert html.index("</table>") < top < html.index('class="entry-list"') < html.index('id="newsletter-signup"')
    assert 'id="bd-email-top"' in html and 'id="bd-email"' in html
    assert "Halloween&#39;s a Saturday. Get the weekend&#39;s events by email on Thursday." in html
    assert html.count('name="bd-hidden-frame"') == 1


def test_halloween_ad_rows_match_the_page_and_the_creatives_render_at_three_sizes():
    # ROADMAP.md item 344.
    entries = _tot_entries(3)
    entries[0].update(hours="3:00–8:00 PM, Saturday, October 31", note="The Village's standing hours, not yet confirmed for 2026.")
    entries[1].update(hours="3:00–7:00 PM, Saturday, October 31", note="The Village's recommended hours, not an ordinance.")
    entries[2].update(hours=None, no_official_hours=True)
    rows, common = build_digest.tot_ad_rows(entries)
    assert common == "Saturday, October 31"
    assert [(r["hours"], r["qualifier"]) for r in rows] == [("3–8 PM", "standing"), ("3–7 PM", "recommended"), ("No set hours", None)]
    now = datetime(2026, 10, 20, 18, tzinfo=timezone.utc)
    ads = build_digest.build_tot_ads(entries, now)
    assert {n: im.size for n, im in ads.items()} == {"tot-square": (1080, 1080), "tot-portrait": (1080, 1350), "tot-story": (1080, 1920)}
    assert build_digest.build_tot_ads(entries, datetime(2026, 6, 1, tzinfo=timezone.utc)) == {}  # out of season
    assert build_digest.build_tot_ads([dict(entries[0]), dict(entries[2])], now) == {}  # fewer than two towns with hours


def test_meta_ad_kit_has_short_copy_and_a_utm_landing_url():
    # ROADMAP.md item 344.
    kit = (Path(__file__).resolve().parent.parent / "META_AD_KIT.md").read_text(encoding="utf-8")
    copies = re.findall(r"^\d\. `([^`]+)`$", kit, re.M)
    assert len(copies) == 3 and all(len(c) < 125 for c in copies)
    url = "https://withintenmiles.com/trick-or-treat/?utm_source=meta&utm_campaign=halloween-2026"
    assert url in kit
    for zip_code in ("60005", "60016", "60056", "60067", "60090"):
        assert zip_code in kit
    assert "Audience Network off" in kit and "No Meta pixel" in kit


def test_probe_retired_indexnow_keys_switches_back_on_a_200_and_backs_off_after_all_403(tmp_path):
    # ROADMAP.md item 337.
    now = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
    log, st = tmp_path / "log.json", tmp_path / "state.json"
    calls = []

    def refuse(**kw):
        calls.append(kw["key"]); kw["outcome"].update(status=403, error="HTTPError"); return False

    def accept(**kw):
        calls.append(kw["key"]); kw["outcome"].update(status=202, error=None); return True

    state = {}
    assert build_digest.probe_retired_indexnow_keys(state, now, refuse, log_path=log, state_path=st) is None
    assert calls == list(build_digest.RETIRED_INDEXNOW_KEYS) and "probe_failed_at" in state
    entry = json.loads(log.read_text())[-1]
    assert entry["key_suffix"] == build_digest.RETIRED_INDEXNOW_KEYS[0][-4:] and entry["status"] == 403 and len(json.dumps(entry)) and build_digest.RETIRED_INDEXNOW_KEYS[0] not in json.dumps(entry)
    # Inside the 7-day back-off nothing is sent.
    calls.clear()
    assert build_digest.probe_retired_indexnow_keys(state, now + timedelta(days=3), accept, log_path=log, state_path=st) is None and calls == []
    # After it, a 202 switches the active key back to the retired one and saves that.
    got = build_digest.probe_retired_indexnow_keys(state, now + timedelta(days=8), accept, log_path=log, state_path=st)
    assert got == build_digest.RETIRED_INDEXNOW_KEYS[0] and build_digest.active_indexnow_key(json.loads(st.read_text())) == got
    assert build_digest.active_indexnow_key({}) == build_digest.INDEXNOW_KEY
    assert build_digest.active_indexnow_key({"active": "not-a-known-key"}) == build_digest.INDEXNOW_KEY


def test_signups_group_sessions_cap_per_town_and_spread_across_towns():
    # ROADMAP.md item 334.
    def ev(title, day, venue="Library"):
        return {"title": title, "url": "https://x/" + title, "venue": venue, "date_iso": f"2026-11-{day:02d}T10:00:00", "attendable": True, "registration_opens": "2026-10-21"}
    blocks = [{"events": [ev("Family Storytime", 4), ev("Family Storytime", 11), ev("Family Storytime", 18), ev("Yoga", 5), ev("Chess", 6), ev("Family Storytime", 5, venue="Park")]}]
    lines = build_digest.build_signups_opening(blocks, date(2026, 10, 19))
    assert len(lines) == 2  # two lines per town
    storytime = next(l for l in lines if l["title"] == "Family Storytime")
    assert storytime["sessions_label"] == "Wed Nov 4, 11 & 18"  # three sessions, one line
    assert build_digest.format_session_dates([date(2026, 11, 25), date(2026, 12, 2)]) == "Wed Nov 25 & Dec 2"
    sections = [{"signups": [{"title": f"A{i}", "town": "A"} for i in range(2)]}, {"signups": [{"title": f"B{i}", "town": "B"} for i in range(2)]}, {"signups": [{"title": "C0", "town": "C"}]}]
    assert [l["title"] for l in build_digest.pick_signups_across_towns(sections)] == ["A0", "B0", "C0", "A1"]  # towns first, four in all


def test_shouting_titles_are_title_cased_for_display_only_and_acronyms_stay():
    assert build_digest.display_title("ESL CONVERSATION CIRCLE FOR ADULTS") == "ESL Conversation Circle for Adults"
    assert build_digest.display_title("LEGO ENGINEERING WORKSHOP FOR KIDS") == "LEGO Engineering Workshop for Kids"
    assert build_digest.display_title("Family Storytime") == "Family Storytime"
    assert build_digest.display_title("STEM CLUB") == "STEM CLUB"  # 12 characters or fewer is left alone
    assert build_digest.display_title("DON'T MISS THE FALL FESTIVAL") == "Don't Miss the Fall Festival"
    ev = {"title": "LEGO ENGINEERING WORKSHOP FOR KIDS", "url": "https://x/1", "date_iso": "2026-10-24T10:00:00", "date": "Oct 24", "tags": [], "tag_badges": [], "detail": ""}
    html = build_digest.render_region_page(next(r for r in build_digest.load_regions() if r["region"]["id"] == "mount-prospect-60056"), [{"section": "S", "events": [ev]}], {"title": "", "detail": "", "url": ""}, [], datetime(2026, 10, 20, tzinfo=timezone.utc))
    assert "LEGO Engineering Workshop for Kids</a>" in html and ev["title"] == "LEGO ENGINEERING WORKSHOP FOR KIDS"


def test_email_with_every_new_block_stays_under_the_gmail_clip():
    signups = [{"title": f"Class {i}", "url": "https://x/c", "opens": date(2026, 10, 21), "opens_label": "Wed, Oct 21", "sessions_label": "Sat Nov 7", "town": "Mount Prospect"} for i in range(4)]
    sections = _join_sections()
    sections[0]["signups"] = signups
    sections[0]["weekend_events"].append({"title": "Opening Night", "url": "https://src/o", "date_iso": "2026-10-23T19:30:00", "date": "2026-10-23", "detail": "", "tags": ["art_culture"], "venue": "Metropolis"})
    html = build_digest.render_combined_email_digest(sections, "Oct 23–25", datetime(2026, 10, 21, 18, tzinfo=timezone.utc), None)
    assert all(b in html for b in ("DID YOU GO?", "SIGN-UPS OPENING THIS WEEK", "NIGHT OUT"))
    assert len(html.encode("utf-8")) < 102_000


def test_bing_urls_are_ordered_trick_or_treat_weekend_regions_then_the_rest():
    # ROADMAP.md item 347.
    base = build_digest.SITE_BASE_URL
    urls = [base + "about/", base + "palatine-60067/", base + "this-weekend/", base + "trick-or-treat/", base + "sponsor/", base + "wheeling-60090/"]
    ordered = build_digest.order_bing_urls(urls, datetime(2026, 10, 25, 15, tzinfo=timezone.utc), ["palatine-60067", "wheeling-60090"])
    assert ordered[:4] == [base + "trick-or-treat/", base + "this-weekend/", base + "palatine-60067/", base + "wheeling-60090/"]
    after = build_digest.order_bing_urls(urls, datetime(2026, 11, 3, 15, tzinfo=timezone.utc), ["palatine-60067", "wheeling-60090"])
    assert after[0] == base + "this-weekend/" and after.index(base + "trick-or-treat/") > after.index(base + "wheeling-60090/")  # no longer prioritised


def test_outdoor_badge_needs_a_real_outdoor_park_not_a_park_district_or_a_surname():
    # ROADMAP.md item 354.
    from tagging import infer_tags
    assert "outdoor" not in infer_tags("Lights Out: Tribute to UFO featuring Andy Parker", "Live at the theatre.")
    assert "outdoor" not in infer_tags("The Music Man Sr.", "Presented by the Park District. Parking is free.")
    assert "outdoor" not in infer_tags("Family night", "Hosted at the Park Ridge library, off Parkway Drive.")
    assert "outdoor" in infer_tags("Pumpkin Splash at Melas Park", "")
    assert "outdoor" in infer_tags("Concert in the Park", "")
    assert "outdoor" in infer_tags("Movie Night", "Bring a blanket to the park.")
    # The source's section name ("Park District Events") never makes an event outdoor.
    assert "outdoor" not in infer_tags("Ceramics class", "", section="Park District Events")
    assert "indoor" in infer_tags("Storytime", "", section="Library Events")  # the section still feeds the other tags


def test_venue_veto_tags_remove_outdoor_for_indoor_sources():
    import yaml as _yaml
    root = Path(__file__).resolve().parent.parent / "config" / "regions"
    vetoed = []
    for f in root.glob("*.yaml"):
        for src in (_yaml.safe_load(f.read_text(encoding="utf-8")).get("sources") or []):
            if src.get("veto_tags"):
                vetoed.append(src["name"])
                assert "outdoor" in src["veto_tags"] and "indoor" in (src.get("default_tags") or [])
    assert any("Theatre" in n for n in vetoed) and sum("Library" in n for n in vetoed) == 5


def test_no_event_appears_twice_across_the_emails_top_blocks():
    # ROADMAP.md item 355: Don't miss, then Night out, then Rain plan, then Sign-ups.
    def ev(title, hour, tags):
        return {"title": title, "url": "https://x/" + title, "date_iso": f"2026-10-23T{hour:02d}:00:00", "date": "Oct 23", "tags": tags, "attendable": True}
    shared = ev("Opening Night", 19, ["art_culture", "indoor", "kid_friendly"])
    blocks = [
        {"region_name": "A", "color": "#000", "attendable_events": [shared, ev("Gallery Talk", 20, ["art_culture", "indoor"])]},
        {"region_name": "B", "color": "#000", "attendable_events": [ev("Family Fest", 10, ["kid_friendly", "free"])]},
    ]
    top = build_digest.pick_email_top_picks(blocks)
    assert "Opening Night" in {p["title"] for p in top}
    night = build_digest.pick_night_out(blocks, top)
    assert night["title"] == "Gallery Talk"  # the next candidate, not the repeat
    assert build_digest.pick_night_out(blocks, top + [night]) is None  # nothing left: the block is omitted
    rain = build_digest.pick_rain_plan(blocks, top + [night])
    assert all(r["title"] not in {"Opening Night", "Gallery Talk"} for r in rain)


def test_holiday_listing_tier_shows_in_its_window_with_a_countdown_and_a_safe_example():
    # ROADMAP.md item 352.
    at = lambda m, d: datetime(2026, m, d, 15, tzinfo=timezone.utc)
    inside = build_digest.render_sponsor_page([], at(10, 20), contact_email="hello@x.org")
    assert "Holiday listing" in inside and 'id="holiday"' in inside and "$20 until Nov 15, then $50" in inside
    assert "Early-bird price ends Sun Nov 15 (26 days left)" in inside
    assert "mailto:hello@x.org?subject=Holiday%20listing" in inside
    assert "Holiday listing" not in build_digest.render_sponsor_page([], at(10, 14))
    assert "Holiday listing" not in build_digest.render_sponsor_page([], at(12, 16))
    after = build_digest.render_sponsor_page([], at(11, 16))
    assert "Holiday listing" in after and "Early-bird price ends" not in after
    assert build_digest.early_bird_line(date(2026, 11, 15)) == "Early-bird price ends Sun Nov 15 (today)"
    assert build_digest.early_bird_line(date(2026, 11, 14)) == "Early-bird price ends Sun Nov 15 (1 day left)"
    # The example is built by the same function as a real listing, and stays on /sponsor/ only.
    real = build_digest.format_holiday_listing({"name": "Real Shop", "url": "https://real.example/", "category": "Gifts", "line": "Sale."})
    assert set(real) == set(build_digest.SAMPLE_HOLIDAY_LISTING) and "Your Shop Name" in inside
    assert "Your Shop Name" not in build_digest.build_events_json([("R", "https://x/r/", [])], "n", at(11, 20))


def test_halloween_weekend_issue_has_a_fixed_subject_and_a_richer_lead_block():
    # ROADMAP.md item 348.
    sections = _join_sections()
    halloween = {"weekday": "Saturday", "countdown": "3 days to go", "towns": [
        {"name": "Mount Prospect", "hours": "3–8 PM", "qualifier": "standing"}, {"name": "Palatine", "hours": "3–7 PM", "qualifier": None}]}
    night = {"weekday": "Saturday", "temp": 52, "rain": 20, "sunset": "5:49 PM"}
    trunk = {"region_name": "Palatine", "events": [
        {"title": "Fire Dept Trunk-or-Treat", "url": "https://x/t", "date_iso": "2026-10-31T16:00:00"},
        {"title": "Trunk or Treat Sunday", "url": "https://x/u", "date_iso": "2026-11-01T14:00:00"},
        {"title": "Trunk-or-Treat Last Week", "url": "https://x/v", "date_iso": "2026-10-24T14:00:00"}]}
    wed = datetime(2026, 10, 28, 15, tzinfo=timezone.utc)
    extras = build_digest.build_halloween_issue_extras([trunk], wed, night)
    assert extras["night_line"] == "Halloween night, Saturday 3–8 PM: 52°F, 20% rain. Sunset 5:49 PM: bring a light."
    assert [t["title"] for t in extras["trunks"]] == ["Fire Dept Trunk-or-Treat", "Trunk or Treat Sunday"]  # the weekend's only
    assert build_digest.build_halloween_issue_extras([trunk], wed, None)["night_line"] is None
    html = build_digest.render_combined_email_digest(sections, "Oct 30–Nov 1", wed, None, halloween=halloween, halloween_extras=extras)
    assert "<title>Trick-or-treat hours, all two towns, plus Halloween weekend" in html or "Trick-or-treat hours, all" in html
    assert "Mount Prospect 3–8 PM (standing)" in html and "bring a light." in html and "Trunk-or-treats this weekend" in html
    assert len(html.encode("utf-8")) < 102_000
    # An ordinary week keeps its event-led subject and shows none of it.
    plain = build_digest.render_combined_email_digest(sections, "Oct 23–25", datetime(2026, 10, 21, 15, tzinfo=timezone.utc), None, halloween=halloween, halloween_extras=extras)
    assert "plus Halloween weekend" not in plain and "Trunk-or-treats this weekend" not in plain
    five = [dict(sections[0], region_name=f"T{i}") for i in range(5)]
    assert build_digest.build_combined_email_subject_line(five, wed) == "Trick-or-treat hours, all five towns, plus Halloween weekend"
    assert len(build_digest.build_combined_email_subject_line(five, wed)) <= build_digest.HALLOWEEN_SUBJECT_MAX_LEN
    assert "Halloween" not in build_digest.build_combined_email_subject_line(five, datetime(2026, 10, 21, 15, tzinfo=timezone.utc))


def test_partisan_meetings_are_excluded_and_civic_information_stays():
    # ROADMAP.md item 361.
    def ev(title, detail="", source="Library"):
        return {"title": title, "detail": detail, "source": source, "url": "https://x/" + title}
    blocks = [{"section": "S", "events": [
        ev("Indivisible Des Plaines", "Monthly meeting. Contact: group@example.org"),
        ev("Early Voting", "Vote early at the Village Hall."),
        ev("Candidate Forum", "Hosted by the library; Democrats and Republicans on the ballot will answer questions."),
        ev("Young Republicans Social"),
        ev("Monthly meeting", "Open to GOP supporters."),
        ev("Storytime", "Songs and a Democratic-style vote on the next book."),  # not a whole-word party name
        ev("League of Women Voters Forum"),
        ev("Gopher Gardening", "Not the GOP"),
    ]}]
    kept, excluded = build_digest.filter_partisan_events(blocks)
    assert {e["title"] for e in excluded} == {"Indivisible Des Plaines", "Young Republicans Social", "Monthly meeting", "Gopher Gardening"}
    titles = [e["title"] for e in kept[0]["events"]]
    assert titles == ["Early Voting", "Candidate Forum", "Storytime", "League of Women Voters Forum"]
    about = build_digest.render_about_page(datetime(2026, 10, 22, tzinfo=timezone.utc), None)
    assert "We don't list party or campaign meetings; we do list voting information." in about.replace("&#39;", "'")


def test_subject_title_cases_shouting_titles_and_never_ends_in_an_ellipsis():
    # ROADMAP.md item 363.
    sections = [_section("A", {"title": "ITALIAN BRED: A GANGSTER TRIBUTE SHOW"}, {"title": "Fall Fest"}), _section("B", {"title": "Movie Night"})]
    subject = build_digest.build_combined_email_subject_line(sections)
    assert "ITALIAN BRED" not in subject and "…" not in subject and len(subject) <= 50
    short = build_digest.build_combined_email_subject_line([_section("A", {"title": "ESL CONVERSATION CIRCLE FOR ADULTS"}), _section("B", {"title": "Fall Fest"})])
    assert "ESL Conversation Circle" in short or short.startswith("Fall Fest")


def test_subject_leads_with_the_first_dont_miss_pick_and_a_second_from_another_town():
    # ROADMAP.md item 364.
    sections = [
        _section("A", {"title": "Opera Gala Night", "tags": []}, {"title": "Harvest Fest", "tags": []}),
        _section("B", {"title": "Pumpkin Run", "tags": []}),
    ]
    picks = [
        {"title": "Craft Hour", "url": "u1", "pick_town": "A"},
        {"title": "Book Swap", "url": "u2", "pick_town": "A"},
        {"title": "Pumpkin Run", "url": "u3", "pick_town": "B"},
    ]
    subject = build_digest.build_combined_email_subject_line(sections, None, picks)
    assert subject.startswith("Craft Hour, Pumpkin Run")  # not Book Swap, which is the same town as the lead
    assert "Harvest Fest" not in subject.split(" and ")[0]
    # Without picks the old ranking still decides.
    assert build_digest.build_combined_email_subject_line(sections).startswith("Harvest Fest")


def test_archived_issue_pages_drop_the_did_you_go_poll_but_the_stored_issue_keeps_it():
    # ROADMAP.md item 368.
    poll_card = (
        '<tr>\\n<td class="wt-paper" style="background-color:#fffefc;">\\n<div>DID YOU GO?</div>\\n'
        '<a href="https://withintenmiles.com/thanks/went/?w=2026-10-22">Yes</a> <a href="https://withintenmiles.com/thanks/not-yet/?w=2026-10-22">Not this time</a>\\n</td>\\n</tr>\\n'
        '<tr><td style="padding:0 0 16px 0;"></td></tr>\\n'
    )
    issue = _issue(body="<table><tr><td>Before</td></tr>" + poll_card + "<tr><td>After</td></tr></table>")
    page = build_digest.render_issue_page(issue)
    assert "thanks/went" not in page and "thanks/not-yet" not in page and "DID YOU GO" not in page
    assert "Before" in page and "After" in page
    assert "thanks/went" in issue["html"]  # the stored file is untouched
    old_style = _issue(body='<table><tr><td class="wt-ink">Did you go? <a href="https://x/thanks/went/?w=1">Yes</a> <a href="https://x/thanks/not-yet/?w=1">No</a></td></tr><tr><td>Keep</td></tr></table>')
    assert "thanks/went" not in build_digest.render_issue_page(old_style) and "Keep" in build_digest.render_issue_page(old_style)


def test_trick_or_treat_page_looks_ahead_from_nov_1_with_last_years_hours_as_reference():
    # ROADMAP.md item 366.
    entries = _tot_entries(3)
    entries[0]["events"] = [{"title": "Fall Trunk-or-Treat", "url": "https://x/t", "date_iso": "2026-10-31T16:00:00", "date_label": "Sat Oct 31", "anchor_id": "a", "tags": [], "detail": ""}]
    newsletter = {"configured": True, "buttondown_username": "withinten", "headline": "Get it"}
    nov = build_digest.render_trick_or_treat_page(entries, datetime(2026, 11, 2, 15, tzinfo=timezone.utc), newsletter=newsletter)
    assert "<title>Trick-or-Treat Hours 2027:" in nov and "<h1>Trick-or-treat hours 2027</h1>" in nov
    assert "2026 hours (for reference)" in nov and "Halloween 2027 is a Sunday." in nov
    assert "Email me when the 2027 hours are posted" in nov and 'value="remind:halloween-2027"' in nov
    assert "Fall Trunk-or-Treat" not in nov and "days to go" not in nov and "👻" not in nov and 'class="entry-list"' not in nov
    assert "application/ld+json" not in nov and 'id="newsletter-signup"' in nov and nov.count("embed-subscribe") == 1
    # The year follows the date: next February the same page is still the 2027 one.
    feb = build_digest.render_trick_or_treat_page(entries, datetime(2027, 2, 3, 15, tzinfo=timezone.utc), newsletter=newsletter)
    assert "<h1>Trick-or-treat hours 2027</h1>" in feb and "2026 hours (for reference)" in feb
    # Oct 31 is still the 2026 page; from Sep 15 villages' hours come back in season.
    halloween = build_digest.render_trick_or_treat_page(entries, datetime(2026, 10, 31, 15, tzinfo=timezone.utc), newsletter=newsletter)
    assert "<h1>Trick-or-treat hours 2026</h1>" in halloween and "Fall Trunk-or-Treat" in halloween and "for reference" not in halloween
    sept = build_digest.render_trick_or_treat_page(entries, datetime(2026, 9, 20, 15, tzinfo=timezone.utc), newsletter=newsletter)
    assert "<h1>Trick-or-treat hours 2026</h1>" in sept


def _ep_event(title, day, **kw):
    return dict({"title": title, "url": "https://src/" + title.replace(" ", "-"), "date_iso": f"2026-10-{day:02d}T10:00:00", "date": f"Oct {day}", "tags": [], "detail": "A description.", "attendable": True, "town": "Palatine", "state": "IL", "source": "Palatine Park District — Events"}, **kw)


def test_event_pages_are_a_bounded_set_each_with_a_first_party_link():
    # ROADMAP.md item 369.
    sections = [{"region_name": "Palatine", "region_url": "https://x/palatine-60067/", "weekend_events": [
        _ep_event("Promo Open House", 24, sponsored_by="Acme Realty"), _ep_event("Fall Fest", 24, tags=["kid_friendly", "free"]),
        _ep_event("No Link", 24, url=""), _ep_event("Ordinary Class", 25)]},
        {"region_name": "Wheeling", "region_url": "https://x/wheeling-60090/", "weekend_events": [_ep_event("Pumpkin Run", 25, town="Wheeling", tags=["kid_friendly"])]}]
    tot = [{"region_name": "Palatine", "region_url": "https://x/palatine-60067/", "events": [_ep_event("Fire Dept Trunk-or-Treat", 24)]}]
    chosen = build_digest.select_event_page_events(sections, tot)
    titles = [e["title"] for e in chosen]
    assert titles[0] == "Promo Open House" and "Fall Fest" in titles and "Fire Dept Trunk-or-Treat" in titles
    assert "No Link" not in titles and "Ordinary Class" not in titles  # no first-party link, or simply not a pick
    assert all(e["url"].startswith("https://src/") for e in chosen) and len({e["path"] for e in chosen}) == len(chosen)
    assert chosen[0]["path"] == "e/2026-10-24-promo-open-house/"
    many = [{"region_name": "Palatine", "region_url": "https://x/p/", "weekend_events": [_ep_event(f"Promo {i}", 24, sponsored_by="A") for i in range(30)]}]
    assert len(build_digest.select_event_page_events(many)) == build_digest.EVENT_PAGE_CAP


def test_event_page_lifetime_noindex_after_7_days_and_deleted_after_60():
    selected = [dict(build_digest.select_event_page_events([{"region_name": "Palatine", "region_url": "https://x/palatine-60067/", "weekend_events": [_ep_event("Fall Fest", 24, sponsored_by="A")]}])[0])]
    reg, active, expired, deleted = build_digest.update_event_pages({}, selected, date(2026, 10, 23))
    assert [e["path"] for e in active] == ["e/2026-10-24-fall-fest/"] and not expired and not deleted
    assert build_digest.update_event_pages(reg, [], date(2026, 10, 31))[1] != []  # 7 days after: still indexable
    reg2, active2, expired2, deleted2 = build_digest.update_event_pages(reg, [], date(2026, 11, 1))  # 8 days after
    assert not active2 and [e["path"] for e in expired2] == ["e/2026-10-24-fall-fest/"]
    reg3, active3, expired3, deleted3 = build_digest.update_event_pages(reg2, [], date(2026, 12, 24))  # 61 days after
    assert deleted3 == ["e/2026-10-24-fall-fest/"] and reg3 == {}


def test_event_page_has_one_event_its_own_canonical_and_noindex_once_expired():
    entry = {**build_digest.select_event_page_events([{"region_name": "Palatine", "region_url": "https://x/palatine-60067/", "weekend_events": [_ep_event("Fall Fest", 24, sponsored_by="Acme", tags=["free"])]}])[0]}
    page = build_digest.render_event_page(entry, more=[{"title": "Other", "url": "https://x/o"}], newsletter={"configured": True, "buttondown_username": "w", "headline": "h"})
    assert page.count('"@type": "Event"') == 1 and f'<link rel="canonical" href="{build_digest.SITE_BASE_URL}e/2026-10-24-fall-fest/">' in page
    assert f'"url": "{build_digest.SITE_BASE_URL}e/2026-10-24-fall-fest/"' in page and '"sameAs": "https://src/Fall-Fest"' in page
    assert '"eventStatus": "https://schema.org/EventScheduled"' in page and '"organizer"' in page and '"offers"' not in page
    assert "<title>Fall Fest, Sat Oct 24, Palatine | Within Ten</title>" in page and 'noindex' not in page
    assert "Official listing" in page and "More this weekend" in page and page.count("embed-subscribe") == 1
    old = build_digest.render_event_page(entry, expired=True)
    assert 'content="noindex"' in old and "This event has passed" in old and "embed-subscribe" not in old
    assert build_digest.SITE_BASE_URL + entry["path"] in build_digest.collect_sitemap_urls([], None, [entry])
    assert build_digest.order_bing_urls([build_digest.SITE_BASE_URL + "about/", build_digest.SITE_BASE_URL + entry["path"]], datetime(2026, 10, 24, tzinfo=timezone.utc), [])[0].endswith(entry["path"])


def test_json_ld_for_script_tags_cannot_be_closed_by_feed_text():
    out = build_digest.json_for_script({"name": "</script><script>alert(1)</script><!-- x"})
    assert "<" not in out and json.loads(out)["name"] == "</script><script>alert(1)</script><!-- x"
    ev = {"title": "Fest </script><script>alert(1)</script>", "url": "https://x/e", "date_iso": "2026-10-24T10:00:00", "town": "T", "state": "IL", "source": "S — Events"}
    page = build_digest.render_event_page({**ev, "path": "e/x/", "tags": [], "detail": "d </script>", "region_url": "https://x/"})
    ld = page.split('application/ld+json">')[1].split("</script>")[0]
    assert "<script>" not in ld and "alert(1)" in ld  # present only as inert JSON text


def test_a_javascript_url_in_a_feed_item_never_reaches_a_card_link(monkeypatch):
    import fetchers
    item = {"title": "Evil", "detail": "d", "url": "javascript:alert(document.cookie)", "date": "2026-10-24"}
    monkeypatch.setitem(build_digest.FETCHERS, "stub", lambda url, **kw: [item, dict(item, title="Good", url="https://ok.example/e")])
    cfg = {"region": {"id": "r", "name": "R", "state": "IL"}, "sources": [{"name": "S", "type": "stub", "url": "https://x/", "section": "Events", "enabled": True}]}
    events = build_digest.fetch_region_sections(cfg)[0]["events"]
    assert {e["title"]: e["url"] for e in events} == {"Evil": "", "Good": "https://ok.example/e"}


def test_venue_table_resolves_named_and_described_venues_and_emits_a_full_address():
    # ROADMAP.md items 335 and 372.
    venues = build_digest.load_venues({"venues": [
        {"name": "Pioneer Park", "street_address": "1 Example Ave", "postal_code": "60004", "source_url": "https://agency.example/"},
        {"name": "Nameless", "street_address": ""},  # no address: ignored
        {"street_address": "2 No Name St"},  # no name: ignored
    ]})
    assert list(venues) == ["pioneer park"]
    row = build_digest.match_venue(venues, None, "Join us for Trunk or Treat at Pioneer Park from 10AM-12:30PM! Bring a bag.")
    assert row["street_address"] == "1 Example Ave" and row["postal_code"] == "60004"
    assert build_digest.match_venue(venues, None, "Join us at Smith Park for fun.") is None  # unknown stays town-only
    assert build_digest.match_venue(venues, None, "Fun all day. Parking is at Pioneer Park.") is None  # only the first sentence counts
    assert build_digest.match_venue(venues, "Pioneer Park", "") is row or build_digest.match_venue(venues, "Pioneer Park", "")["name"] == "Pioneer Park"
    event = {"title": "Trunk or Treat", "town": "Arlington Heights", "state": "IL", "venue": "Pioneer Park", "street_address": "1 Example Ave", "postal_code": "60004", "date_iso": "2026-10-24T10:00:00"}
    place = build_digest.schema_location(event)
    assert place["address"]["streetAddress"] == "1 Example Ave" and place["address"]["postalCode"] == "60004" and place["address"]["addressLocality"] == "Arlington Heights"
    unmatched = build_digest.schema_location({"town": "Palatine", "state": "IL", "venue": None})
    assert "streetAddress" not in unmatched["address"] and unmatched["name"] == "Palatine, IL"
    ics = build_digest.build_ics_data_uri(event)
    assert "LOCATION%3APioneer%20Park%5C%2C%201%20Example%20Ave%5C%2C%20Arlington%20Heights" in ics
    assert "LOCATION" not in build_digest.build_ics_data_uri({k: v for k, v in event.items() if k != "street_address"})


def test_an_event_page_with_a_matched_venue_has_the_address_in_its_line_title_and_markup():
    entry = {"path": "e/2026-10-24-trunk-or-treat/", "title": "Trunk or Treat", "date_iso": "2026-10-24T10:00:00", "detail": "d", "venue": "Pioneer Park",
             "street_address": "1 Example Ave", "postal_code": "60004", "town": "Arlington Heights", "state": "IL", "source": "Arlington Heights Park District — Events",
             "url": "https://agency.example/e", "tags": [], "region_url": "https://x/ah/"}
    page = build_digest.render_event_page(entry)
    assert "<title>Trunk or Treat, Sat Oct 24, Pioneer Park, Arlington Heights | Within Ten</title>" in page
    assert "Pioneer Park, 1 Example Ave, Arlington Heights" in page and '"streetAddress": "1 Example Ave"' in page and '"postalCode": "60004"' in page


def test_the_real_venue_tables_only_hold_addresses_with_a_source_page():
    import yaml as _yaml
    for f in (Path(__file__).resolve().parent.parent / "config" / "regions").glob("*.yaml"):
        for row in _yaml.safe_load(f.read_text(encoding="utf-8")).get("venues") or []:
            assert row["name"] and row["street_address"] and str(row["source_url"]).startswith("https://"), (f.name, row)


def test_every_event_markup_output_shares_one_builder_with_the_same_location_and_organizer():
    # ROADMAP.md item 375.
    event = {"title": "Storytime Playdate", "url": "https://mppl.org/events/1", "date_iso": "2026-10-23T10:00:00", "detail": "Songs and stories.", "tags": ["free"],
             "venue": "Mount Prospect Public Library", "street_address": "125 S Emerson St", "town": "Mount Prospect", "state": "IL",
             "source": "Mount Prospect Public Library — Events"}
    now = datetime(2026, 10, 22, 15, tzinfo=timezone.utc)
    region_page = json.loads(build_digest.build_events_json([("Mount Prospect", "https://x/mp/", [event])], "n", now))["itemListElement"][0]["item"]
    tot = json.loads(build_digest.build_halloween_json_ld([{"region_url": "https://x/mp/", "events": [event]}]))["@graph"][0]
    page_html = build_digest.render_event_page({**event, "path": "e/2026-10-23-storytime-playdate/", "region_url": "https://x/mp/"})
    page = json.loads(page_html.split('application/ld+json">')[1].split("</script>")[0].replace("\\u003c", "<"))
    outputs = [region_page, tot, page]
    assert all(o["location"] == outputs[0]["location"] and o["organizer"] == outputs[0]["organizer"] for o in outputs)
    assert outputs[0]["location"]["address"]["streetAddress"] == "125 S Emerson St" and outputs[0]["organizer"]["name"] == "Mount Prospect Public Library"
    for o in outputs:
        assert o["eventStatus"] == "https://schema.org/EventScheduled" and o["isAccessibleForFree"] is True and "offers" not in o
    # Only the url differs: the card anchor on listings, the page itself on /e/.
    assert "#ev-storytime-playdate-2026-10-23" in region_page["url"] and page["url"].endswith("/e/2026-10-23-storytime-playdate/")


def test_a_listing_points_its_event_at_the_events_own_page_when_one_exists(monkeypatch):
    event = {"title": "Fall Fest", "url": "https://x.org/e", "date_iso": "2026-10-24T10:00:00", "town": "T", "state": "IL", "source": "S — Events"}
    path = build_digest.event_page_path(event)
    monkeypatch.setattr(build_digest, "ACTIVE_EVENT_PAGE_PATHS", {path})
    assert build_digest._event_list_item(event, "https://x/t/", 1)["item"]["url"] == build_digest.SITE_BASE_URL + path
    monkeypatch.setattr(build_digest, "ACTIVE_EVENT_PAGE_PATHS", set())
    assert build_digest._event_list_item(event, "https://x/t/", 1)["item"]["url"].startswith("https://x/t/#ev-fall-fest")


def test_the_real_dppl_theatre_and_metropolis_venues_are_seeded_from_their_own_pages():
    import yaml as _yaml
    rows = {}
    for f in (Path(__file__).resolve().parent.parent / "config" / "regions").glob("*.yaml"):
        for row in _yaml.safe_load(f.read_text(encoding="utf-8")).get("venues") or []:
            rows[row["name"]] = row
    assert rows["Des Plaines Public Library"]["street_address"] == "1501 Ellinwood Street" and rows["Des Plaines Public Library"]["postal_code"] == "60016"
    assert rows["Des Plaines Theatre"]["street_address"] == "1476 Miner Street" and rows["Metropolis Performing Arts Centre"]["street_address"] == "111 W Campbell Street"


def test_event_page_description_is_whole_sentences_and_more_links_fall_back_to_nearby_towns():
    # ROADMAP.md item 373.
    long = " ".join(f"Sentence number {i} tells you something about the day." for i in range(40))
    cut = build_digest.sentence_cut(long)
    assert len(cut) <= 600 and cut.endswith(".") and "…" not in cut and len(cut) > 400
    assert build_digest.sentence_cut("Short one.") == "Short one."
    entry = {"path": "e/2026-10-24-fall-fest/", "title": "Fall Fest", "date_iso": "2026-10-24T10:00:00", "town": "Palatine", "state": "IL", "source": "Palatine Park District — Events",
             "url": "https://src/f", "tags": [], "detail": "Short.", "detail_long": cut, "region_url": "https://x/palatine-60067/", "region_id": "palatine-60067", "venue": "Palatine Park", "town_color": "#0f766e"}
    page = build_digest.render_event_page(entry)
    assert cut in page
    assert "<title>Fall Fest, Sat Oct 24, Palatine Park, Palatine | Within Ten</title>" in page
    assert "#0f766e" in page and ">SAT<" in page and ">24<" in page
    sections = [
        {"region_name": "Palatine", "region_url": "https://x/palatine-60067/", "region_lat": 42.11, "region_lon": -88.04, "weekend_events": [_ep_event("Fall Fest", 24), _ep_event("Pumpkin Patch", 25)]},
        {"region_name": "Far", "region_url": "https://x/far/", "region_lat": 43.5, "region_lon": -88.0, "weekend_events": [_ep_event("Far Event", 24, town="Far")]},
        {"region_name": "Near", "region_url": "https://x/near/", "region_lat": 42.12, "region_lon": -88.05, "weekend_events": [_ep_event("Near Event", 24, town="Near"), _ep_event("Info", 24, attendable=False)]},
    ]
    more = build_digest.event_page_more_links(entry, sections)
    assert [m["title"] for m in more] == ["Pumpkin Patch", "Near Event", "Far Event"]
    assert more[0]["same_town"] and not more[1]["same_town"]
    one = build_digest.event_page_more_links(entry, sections, limit=1)
    assert [m["title"] for m in one] == ["Pumpkin Patch"]


def test_picks_have_a_quality_floor_and_a_weak_town_gives_its_slot_away():
    # ROADMAP.md item 380.
    def ev(title, tags=(), day=24):
        return {"title": title, "url": "https://s/" + title, "date_iso": f"2026-10-{day}T10:00:00", "tags": list(tags), "attendable": True}
    assert not build_digest.is_pick_worthy(ev("CPR Class", ["free", "kid_friendly"]))
    assert not build_digest.is_pick_worthy(ev("Play Packs", ["free", "kid_friendly"]))
    assert not build_digest.is_pick_worthy(ev("Take & Make: Craft Kit", ["free"]))
    assert not build_digest.is_pick_worthy(ev("Quiet Evening", []))  # score 0
    assert build_digest.is_pick_worthy(ev("Fall Fest", ["free"]))
    colors = [c for c, _ in build_digest.EMAIL_TOWN_COLORS]
    blocks = [
        {"region_name": "A", "color": colors[0], "attendable_events": [ev("CPR Class", ["free", "kid_friendly"]), ev("Quiet Evening")]},
        {"region_name": "B", "color": colors[1], "attendable_events": [ev("Fall Fest", ["free", "kid_friendly"]), ev("Pumpkin Run", ["free", "outdoor"], 25)]},
        {"region_name": "C", "color": colors[2], "attendable_events": [ev("Hayride", ["kid_friendly", "outdoor"])]},
        {"region_name": "D", "color": colors[3], "attendable_events": [ev("Trunk Night", ["free", "kid_friendly", "outdoor"], 25)]},
    ]
    picks = build_digest.pick_email_top_picks(blocks, limit=6)
    titles = [p["title"] for p in picks]
    assert "CPR Class" not in titles and "Quiet Evening" not in titles and "A" not in [p["pick_town"] for p in picks[:3]]
    assert titles[:3] == ["Trunk Night", "Fall Fest", "Hayride"] and len(picks) <= 6
    assert "Pumpkin Run" in titles  # a spare strong event fills a slot a weak town gave up
    assert build_digest.pick_email_top_picks(blocks[:1] + blocks[1:2][:0], limit=3) == []


def test_next_seven_days_count_is_a_rolling_window_not_the_weekend():
    # ROADMAP.md item 384.
    def ev(title, day, **kw):
        return dict({"title": title, "date_iso": f"2026-10-{day:02d}T10:00:00"}, **kw)
    groups = [("A", "u", [ev("Fri", 23), ev("Sat", 24), ev("Sun", 25), ev("Mon", 26), ev("Next Fri", 30), ev("Far", 31), ev("Sat", 24), ev("Info", 27, attendable=False)]),
              ("B", "u", [ev("Tue", 27), {"title": "Undated"}])]
    sunday = build_digest.count_next_seven_days(groups, date(2026, 10, 25))
    friday = build_digest.count_next_seven_days(groups, date(2026, 10, 23))
    assert sunday == 5 and friday == 5  # Sun..Fri-after vs Fri..Tue: similar either day; no double count, no info items


def _santa_blocks():
    def ev(title, iso, **kw):
        return dict({"title": title, "url": "https://src/" + title.replace(" ", "-"), "date_iso": iso, "detail": "", "tags": [], "attendable": True}, **kw)
    return [{"section": "Events", "events": [
        ev("Breakfast with Santa", "2026-12-05T09:00:00", registration_opens="2026-11-10", reg_badge="Sign-up opens Tue, Nov 10"),
        ev("Santa's Workshop", "2026-11-14T10:00:00", detail="This event is sold out."),
        ev("Photos with Santa", "2026-10-30T10:00:00"),   # before Nov 1
        ev("Santa Run 5K", "2026-12-26T08:00:00"),         # after Dec 24
        ev("Pumpkin Patch", "2026-11-14T10:00:00"),
        ev("Breakfast with Santa", "2026-12-05T09:00:00"),  # duplicate
    ]}]


_NL = {"configured": True, "buttondown_username": "w", "headline": "h"}


def test_santa_page_window_keywords_badges_and_empty_state():
    # ROADMAP.md item 379.
    today = date(2026, 10, 25)
    picked = build_digest.select_santa_events(_santa_blocks(), today)
    assert [e["title"] for e in picked] == ["Santa's Workshop", "Breakfast with Santa"]
    entries = [{"region_name": "Palatine", "region_url": "https://x/palatine-60067/", "events": picked}, {"region_name": "Wheeling", "region_url": "https://x/wheeling-60090/", "events": []}]
    page = build_digest.render_santa_page(entries, datetime(2026, 10, 25, 12, tzinfo=timezone.utc), None, _NL)
    assert "<title>Breakfast with Santa &amp; Santa Visits 2026: Palatine and Wheeling | Within Ten</title>" in page
    assert page.index("Sat, Nov 14") < page.index("Sat, Dec 5") and "Sign-up opens Tue, Nov 10" in page
    assert page.count("Source says: sold out") == 1  # only where the source's own text says so
    assert "remind:santa-2026" in page  # not yet in season: reminder signup
    empty = build_digest.render_santa_page([{"region_name": "Palatine", "region_url": "https://x/p/", "events": []}], datetime(2026, 10, 25, 12, tzinfo=timezone.utc), None, _NL)
    assert "Park districts usually post Santa events in early November" in empty
    live = build_digest.render_santa_page(entries, datetime(2026, 11, 20, 12, tzinfo=timezone.utc), None, _NL)
    assert "remind:santa" not in live and 'value="town:all"' in live
    off = build_digest.render_santa_page(entries, datetime(2026, 12, 28, 12, tzinfo=timezone.utc), None, _NL)
    assert "Santa Visits 2027" in off and "remind:santa-2027" in off
    assert build_digest.SITE_BASE_URL + "santa/" in build_digest.collect_sitemap_urls([])
    chosen = build_digest.select_event_page_events([], None, santa_entries=entries)
    assert [e["title"] for e in chosen] == ["Santa's Workshop", "Breakfast with Santa"]


def test_repeated_sessions_render_as_one_card_but_keep_one_event_each():
    # ROADMAP.md item 381.
    def sess(iso, **kw):
        return dict({"title": "The Music Man Jr.", "url": "https://src/mm", "date_iso": iso, "date": "x", "detail": "A musical.", "tags": [], "tag_badges": [], "venue": "Theatre", "source": "S", "town": "Palatine", "state": "IL", "attendable": True,
                     "ics_href": "data:text/calendar,ics" + iso[8:10], "google_calendar_url": "https://calendar.google.com/x"}, **kw)
    a, b = sess("2026-10-24T17:00:00"), sess("2026-10-25T14:00:00")
    other = sess("2026-10-25T14:00:00", title="Other Show", url="https://src/o")
    far = sess("2026-11-20T14:00:00")
    blocks = [{"section": "Events", "events": [a, b, other, far]}]
    sections = [{"region_name": "Palatine", "region_url": "https://x/palatine-60067/", "events": blocks[0]["events"]}]
    html = build_digest.render_merged_hub_page(sections, datetime(2026, 10, 24, 12, tzinfo=timezone.utc), None, slug="this-weekend", heading="H", subheading="s", meta_description="m", empty_message="none")
    assert html.count("The Music Man Jr.</a>") == 2  # one card for the Oct sessions, one for November
    assert "Sat 5:00 PM" in html and "Sun 2:00 PM" in html
    assert "📅 Sat 5:00 PM" in html and "📅 Sun 2:00 PM" in html and html.count("The Music Man Jr.") >= 2
    assert b["merged_away"] and "sessions" in a and "merged_away" not in far
    ld = json.loads(build_digest.build_event_json_ld(blocks, "https://x/p/"))
    names = [e["name"] for e in (ld["@graph"] if "@graph" in ld else [ld])]
    assert names.count("The Music Man Jr.") == 3  # unchanged: one Event per session


def test_founding_promo_offer_shows_only_while_spots_remain_and_before_jan_1():
    # ROADMAP.md item 388.
    assert build_digest.founding_offer(0, date(2026, 10, 26)) == {"left": 5, "total": 5, "ends": "Dec 31"}
    assert build_digest.founding_offer(3, date(2026, 12, 31))["left"] == 2
    assert build_digest.founding_offer(5, date(2026, 10, 26)) is None
    assert build_digest.founding_offer(0, date(2027, 1, 1)) is None
    now = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
    assert "2 of 5 spots left" in build_digest.render_sponsor_page([], now, founding_promos_used=3)
    assert "Founding offer" not in build_digest.render_sponsor_page([], now, founding_promos_used=5)
    assert "Founding offer" not in build_digest.render_sponsor_page([], datetime(2027, 1, 2, 12, tzinfo=timezone.utc))


def test_santa_page_empty_state_points_to_each_towns_calendars_and_confirmed_tree_dates():
    # ROADMAP.md item 389.
    now = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
    entries = [
        {"region_name": "Arlington Heights", "region_url": "https://x/ah/", "events": [], "links": [{"title": "Arlington Heights Park District", "url": "https://www.ahpd.org/"}], "tree": {"label": "Friday, November 27, 4:30–6:30 PM, North School Park", "url": "https://u"}},
        {"region_name": "Wheeling", "region_url": "https://x/w/", "events": [], "links": [{"title": "Wheeling Park District", "url": "https://www.wheelingparkdistrict.com/"}], "tree": {"label": None, "url": "https://u"}},
    ]
    page = build_digest.render_santa_page(entries, now, None, _NL)
    assert page.count("Where to look meanwhile") == 1 and "Park districts usually post Santa events" in page
    assert "https://www.ahpd.org/" in page and "https://www.wheelingparkdistrict.com/" in page
    assert "Tree lighting: Friday, November 27" in page and "Tree lighting: date TBA" in page and page.count("Tree lighting:") == 2
    with_events = [dict(entries[0], events=[{"title": "Breakfast with Santa", "url": "https://s", "date_iso": "2026-12-05T09:00:00"}]), entries[1]]
    full = build_digest.render_santa_page(with_events, now, None, _NL)
    assert full.index("Breakfast with Santa") < full.index("Where to look meanwhile")  # moves below the list
    cfg = {"evergreen": [{"title": "Palatine Public Library District", "url": "https://l"}, {"title": "Palatine Park District", "url": "https://p"}, {"title": "Village of Palatine", "url": "https://v"}]}
    assert [l["url"] for l in build_digest.santa_look_links(cfg)] == ["https://p", "https://v"]


def test_leaf_pickup_page_is_sourced_season_bound_and_never_guesses_a_date():
    # ROADMAP.md item 323.
    def at(m, d):
        return datetime(2026, m, d, 12, tzinfo=timezone.utc)
    assert build_digest.is_leaf_pickup_season(at(10, 15)) and build_digest.is_leaf_pickup_season(at(12, 15))
    assert not build_digest.is_leaf_pickup_season(at(10, 14)) and not build_digest.is_leaf_pickup_season(at(12, 16))
    assert build_digest.prepare_leaf_pickup({}) is None
    assert build_digest.prepare_leaf_pickup({"leaf_pickup": {"url": "javascript:alert(1)"}})["url"] in (None, "")
    entries = [
        {"name": "Des Plaines", "url": "https://dp/leaf", "summary": "Residential leaf collection starting Monday, October 19, 2026.", "note": None},
        {"name": "Wheeling", "url": "https://w/yard", "summary": None, "note": "States no leaf dates."},
    ]
    page = build_digest.render_leaf_pickup_page(entries, at(10, 27), None, _NL)
    assert "Residential leaf collection starting Monday, October 19, 2026." in page and 'href="https://dp/leaf"' in page
    assert page.count("No dates confirmed here yet.") == 1 and "noindex" not in page
    assert 'name="robots" content="noindex"' in build_digest.render_leaf_pickup_page(entries, at(12, 20), None, _NL)
    assert build_digest.SITE_BASE_URL + "leaf-pickup/" in build_digest.collect_sitemap_urls([], None, None, True)
    assert build_digest.SITE_BASE_URL + "leaf-pickup/" not in build_digest.collect_sitemap_urls([], None, None, False)
    import yaml
    for cfg in build_digest.load_regions():  # every shipped block has a village URL, and only quoted-source summaries
        block = build_digest.prepare_leaf_pickup(cfg)
        assert block and block["url"].startswith("https://")


def test_thanksgiving_weekend_issue_has_a_fixed_subject_a_santa_link_and_stays_under_the_clip():
    # ROADMAP.md item 393.
    holiday = {"towns": [{"name": "Arlington Heights", "date": "Fri Nov 27"}, {"name": "Palatine", "date": "Sat Nov 21"}], "offer": True}
    wed, earlier = _at_local(2026, 11, 25), _at_local(2026, 11, 18)
    subject = build_digest.build_combined_email_subject_line(_join_sections(), wed)
    assert subject == "Thanksgiving weekend: lights, shops & more" and len(subject) <= build_digest.SUBJECT_MAX_LEN
    assert build_digest.build_combined_email_subject_line(_join_sections(), earlier) != subject
    html = build_digest.render_combined_email_digest(_join_sections(), "Nov 27–29", wed, None, holiday=holiday)
    assert "TREE LIGHTINGS AND SMALL BUSINESS SATURDAY" in html and "santa/?utm_source=email" in html and "Small Business Saturday Nov 28" in html
    plain = build_digest.render_combined_email_digest(_join_sections(), "Nov 20–22", earlier, None, holiday=holiday)
    assert "TREE LIGHTINGS AND SMALL BUSINESS SATURDAY" not in plain and "santa/?utm_source=email" not in plain
    assert len(html.encode("utf-8")) < 102_000


def test_nth_weekday_recurrence_and_craft_fair_keywords_reach_the_holiday_selection():
    # ROADMAP.md items 395 and 397.
    item = {"title": "Winter Market", "url": "https://x", "recurrence": {"starts": "2026-11-07", "ends": "2027-01-31", "weekday": "Saturday", "time": "09:00", "nth": [1, 3]}}
    days = [e["date_iso"][:10] for e in build_digest.expand_recurring_annual_event(item, "Palatine", date(2026, 11, 1))]
    assert days == ["2026-11-07", "2026-11-21", "2026-12-05", "2026-12-19", "2027-01-02", "2027-01-16"]
    assert build_digest.expand_recurring_annual_event(item, "Palatine", date(2026, 11, 1))[0]["recurrence_note"] == "1st and 3rd Saturdays through Jan 31"
    for title in ("Holiday Bazaar", "Fall Craft Fair", "Merry Makers Market", "Holiday Market", "Vendor Fair at the Rec Center", "Holiday Boutique"):
        assert build_digest.HOLIDAY_TITLE.search(title), title
    assert not build_digest.HOLIDAY_TITLE.search("Farmers Market")
    blocks = [{"events": [{"title": "Holiday Bazaar", "url": "https://x/b", "date_iso": "2026-11-14T10:00:00"}, {"title": "Pickleball", "url": "https://x/p", "date_iso": "2026-11-14T10:00:00"}]}]
    assert [e["title"] for e in build_digest.select_holiday_events(blocks, date(2026, 11, 2))] == ["Holiday Bazaar"]
    cfg = next(c for c in build_digest.load_regions() if c["region"]["id"] == "palatine-60067")
    titles = [e["title"] for e in build_digest.prepare_annual_events(cfg, datetime(2026, 11, 2, 12, tzinfo=timezone.utc))["events"]]
    assert "Palatine High School Boosters Present: Fall Craft Fair" in titles and titles.count("Palatine Winter Farmers' Market") >= 3


def test_sponsor_preview_is_noindex_escapes_by_construction_and_shows_both_products():
    # ROADMAP.md item 313.
    sections = [
        {"region_name": "Palatine", "region_url": "https://x/p/", "weekend_events": [{"title": "Fall Fest", "date_iso": "2026-10-31T10:00:00", "attendable": True}, {"title": "Sponsored", "date_iso": "2026-10-31T11:00:00", "attendable": True, "sponsored_by": "Acme"}, {"title": "Hike", "date_iso": "2026-11-01T10:00:00", "attendable": True}]},
        {"region_name": "Wheeling", "region_url": "https://x/w/", "weekend_events": []},
    ]
    html = build_digest.render_sponsor_preview(sections, {"event_promo": "https://buy.example/e", "weekly_spot": None}, "hello@x.org")
    assert 'name="robots" content="noindex, nofollow"' in html and "Preview, not live" in html
    assert "As a Featured event" in html and "Weekly Spot" in html and 'href="https://buy.example/e"' in html
    assert "mailto:hello@x.org" in html  # no Stripe link for the weekly spot: email instead
    script = html.split("<script>", 1)[1]
    assert "innerHTML" not in script and "document.write" not in script and "textContent" in script
    assert "Sponsored" not in html.split('id="preview-data">')[1].split("</script>")[0]  # a paid event is not shown as a "real" neighbour
    data = json.loads(html.split('id="preview-data">')[1].split("</script>")[0])
    assert [t["name"] for t in data["towns"]] == ["Palatine", "Wheeling"] and [e["title"] for e in data["towns"][0]["events"]] == ["Fall Fest", "Hike"]
    assert build_digest.SITE_BASE_URL + "sponsor/preview/" not in build_digest.collect_sitemap_urls([], None, None, True)


def test_starter_pack_tier_is_135_for_three_weeks_with_its_own_payment_slot():
    # ROADMAP.md item 314.
    now = datetime(2026, 6, 10, 15, tzinfo=timezone.utc)
    html = build_digest.render_sponsor_page([], now, payment_links={"starter": "https://buy.stripe.com/starter"})
    assert "Starter: 3 weeks" in html and "$135 for 3 weeks" in html and "https://buy.stripe.com/starter" in html
    assert "Starter: 3 weeks" in (Path(__file__).resolve().parents[1] / "SPONSOR_KIT.md").read_text(encoding="utf-8")
    assert 3 * 50 * 0.9 == 135


def test_a_configured_annual_event_with_a_time_gets_a_real_date():
    # The Palatine HS fair's "2026-11-07T09:00:00" had no date_iso, so it never reached a weekend view.
    assert build_digest.parse_event_date_iso("2026-11-07T09:00:00") == "2026-11-07T09:00:00"
    assert build_digest.parse_event_date_iso("2026-11-07 09:00") == "2026-11-07T09:00:00"
    assert build_digest.format_event_date("2026-11-07T09:00:00") == "Nov 7"
    cfg = next(c for c in build_digest.load_regions() if c["region"]["id"] == "palatine-60067")
    fair = next(e for e in build_digest.prepare_annual_events(cfg, datetime(2026, 10, 29, 12, tzinfo=timezone.utc))["events"] if "Craft Fair" in e["title"])
    assert fair["date_iso"] == "2026-11-07T09:00:00"
