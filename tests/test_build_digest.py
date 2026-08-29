import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_digest  # noqa: E402

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


def test_build_google_calendar_url_returns_none_without_date():
    assert build_digest.build_google_calendar_url({"title": "x", "date_iso": None}, "Mount Prospect") is None


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


def test_render_region_page_produces_html_even_with_empty_sources():
    blocks = [{"section": "Village News", "events": []}]
    sponsor = {"title": "Sponsor this spot", "detail": "", "url": ""}
    evergreen = [{"title": "Library", "detail": "Books.", "url": "https://mppl.org/", "tags": ["indoor"]}]
    region_cfg = {"region": REGION}
    html = build_digest.render_region_page(
        region_cfg, blocks, sponsor, evergreen, datetime.now(timezone.utc)
    )
    assert "Mount Prospect" in html
    assert "Village News" in html
    assert "No live updates fetched this week" in html
    assert "Library" in html


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
    assert "<title>This weekend in Mount Prospect — Weekend &amp; Trip Planner</title>" in html
    assert 'content="Aug 29–30"' in html


def test_render_region_page_empty_message_override():
    blocks = [{"section": "This Weekend", "events": []}]
    html = build_digest.render_region_page(
        {"region": REGION}, blocks, {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc),
        empty_message="Nothing dated for this weekend yet.",
    )
    assert "Nothing dated for this weekend yet." in html


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
    assert '<a href="https://randerson-23.github.io/agent-business/mount-prospect-60056/free/" class="active">Free</a>' in html


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


def test_render_hub_page_includes_region_coordinates_for_distance_feature():
    summaries = [{**REGION, "event_count": 3, "path": "mount-prospect-60056/"}]
    html = build_digest.render_hub_page([], summaries, datetime.now(timezone.utc))
    assert 'data-lat="42.0666"' in html
    assert 'data-lon="-87.9373"' in html


def test_render_hub_page_handles_no_regions():
    html = build_digest.render_hub_page([], [], datetime.now(timezone.utc))
    assert "No regions configured yet" in html


def test_render_weekend_hub_page_groups_events_by_region():
    sections = [
        {
            "region_name": "Mount Prospect",
            "region_url": "https://randerson-23.github.io/agent-business/mount-prospect-60056/",
            "events": [{"title": "Fishing Derby", "url": "https://x/", "detail": "", "date": "Sep 19", "tags": []}],
        }
    ]
    html = build_digest.render_weekend_hub_page(sections, "Sep 19–20", datetime.now(timezone.utc))
    assert "Mount Prospect" in html
    assert "Fishing Derby" in html
    assert "Sep 19–20" in html
    assert 'href="https://randerson-23.github.io/agent-business/mount-prospect-60056/"' in html


def test_render_weekend_hub_page_handles_no_events_anywhere():
    html = build_digest.render_weekend_hub_page([], "Sep 19–20", datetime.now(timezone.utc))
    assert "Nothing dated for this weekend yet across any region" in html


def test_render_region_page_includes_canonical_link():
    html = build_digest.render_region_page({"region": REGION}, [], {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc))
    assert 'rel="canonical" href="https://randerson-23.github.io/agent-business/mount-prospect-60056/"' in html


def test_render_hub_page_includes_canonical_link():
    html = build_digest.render_hub_page([], [], datetime.now(timezone.utc))
    assert 'rel="canonical" href="https://randerson-23.github.io/agent-business/"' in html


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
    assert "<loc>https://randerson-23.github.io/agent-business/</loc>" in xml
    assert "<loc>https://randerson-23.github.io/agent-business/mount-prospect-60056/</loc>" in xml


def test_build_sitemap_xml_includes_weekend_hub_url():
    summaries = [{**REGION, "event_count": 1, "path": "mount-prospect-60056/"}]
    xml = build_digest.build_sitemap_xml(summaries, datetime.now(timezone.utc))
    assert "<loc>https://randerson-23.github.io/agent-business/this-weekend/</loc>" in xml


def test_build_sitemap_xml_includes_sponsor_url():
    summaries = [{**REGION, "event_count": 1, "path": "mount-prospect-60056/"}]
    xml = build_digest.build_sitemap_xml(summaries, datetime.now(timezone.utc))
    assert "<loc>https://randerson-23.github.io/agent-business/sponsor/</loc>" in xml


def test_build_robots_txt_references_sitemap():
    robots = build_digest.build_robots_txt()
    assert "Sitemap: https://randerson-23.github.io/agent-business/sitemap.xml" in robots
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
    assert result.startswith("# Weekend & Trip Planner")
    assert "[Mount Prospect (60056)](https://randerson-23.github.io/agent-business/mount-prospect-60056/)" in result
    assert "[Mount Prospect — this weekend](https://randerson-23.github.io/agent-business/mount-prospect-60056/this-weekend/)" in result
    assert "## Sponsorship" in result


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
    assert "[Fall Family Guide — Mount Prospect](https://randerson-23.github.io/agent-business/mount-prospect-60056/guides/fall-family-guide/)" in result


def test_build_llms_txt_omits_guides_section_when_none_exist():
    summaries = [{"name": "Mount Prospect", "zip": "60056", "tagline": "x", "path": "mount-prospect-60056/", "guides": []}]
    result = build_digest.build_llms_txt(summaries)
    assert "## Guides" not in result


def test_build_answer_block_mentions_region_name_and_zip():
    region = {"name": "Mount Prospect", "zip": "60056", "state": "IL", "tagline": "Village news, library events, and park district programs."}
    result = build_digest.build_answer_block(region)
    assert "Mount Prospect" in result
    assert "60056" in result
    word_count = len(result.split())
    assert 30 <= word_count <= 70


def test_build_region_map_embed_url_uses_region_coordinates():
    region = {"lat": 42.0666, "lon": -87.9373}
    result = build_digest.build_region_map_embed_url(region)
    assert result == "https://maps.google.com/maps?q=42.0666,-87.9373&z=14&output=embed"


def test_build_region_map_embed_url_returns_none_without_coordinates():
    assert build_digest.build_region_map_embed_url({"name": "Nowhere"}) is None


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
    assert result.endswith("https://example.org/mount-prospect-60056/\n(Updated automatically, several times a week.)\n")


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
    }


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
