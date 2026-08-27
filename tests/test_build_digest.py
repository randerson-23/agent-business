import sys
from datetime import datetime, timezone
from pathlib import Path

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


def test_resolve_sponsor_falls_back_for_unconfigured_region():
    cfg = {"default_house_ad": {"title": "Sponsor this spot", "detail": "", "url": ""}, "regions": {}}
    sponsor = build_digest.resolve_sponsor(cfg, "some-new-region")
    assert sponsor["title"] == "Sponsor this spot"


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


def test_render_region_page_includes_canonical_link():
    html = build_digest.render_region_page({"region": REGION}, [], {"title": "", "detail": "", "url": ""}, [], datetime.now(timezone.utc))
    assert 'rel="canonical" href="https://randerson-23.github.io/agent-business/mount-prospect-60056/"' in html


def test_render_hub_page_includes_canonical_link():
    html = build_digest.render_hub_page([], [], datetime.now(timezone.utc))
    assert 'rel="canonical" href="https://randerson-23.github.io/agent-business/"' in html


def test_build_event_json_ld_returns_none_for_no_events():
    assert build_digest.build_event_json_ld(REGION, [{"section": "News", "events": []}]) is None


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
    result = build_digest.build_event_json_ld(REGION, blocks)
    payload = _json.loads(result)
    assert payload["@context"] == "https://schema.org"
    event = payload["@graph"][0]
    assert event["@type"] == "Event"
    assert event["name"] == "Fishing Derby"
    assert event["startDate"] == "2026-09-19T10:00:00"
    assert event["location"]["address"]["postalCode"] == "60056"


def test_build_event_json_ld_escapes_script_close_tag():
    blocks = [
        {
            "section": "News",
            "events": [
                {"title": "Weird</script>Title", "detail": "", "url": "https://x/", "date_iso": None}
            ],
        }
    ]
    result = build_digest.build_event_json_ld(REGION, blocks)
    assert "</script>" not in result


def test_build_event_json_ld_skips_events_missing_title_or_url():
    blocks = [{"section": "News", "events": [{"title": "", "url": "https://x/", "detail": ""}]}]
    assert build_digest.build_event_json_ld(REGION, blocks) is None


def test_build_sitemap_xml_lists_hub_and_region_urls():
    summaries = [{**REGION, "event_count": 1, "path": "mount-prospect-60056/"}]
    xml = build_digest.build_sitemap_xml(summaries, datetime.now(timezone.utc))
    assert "<loc>https://randerson-23.github.io/agent-business/</loc>" in xml
    assert "<loc>https://randerson-23.github.io/agent-business/mount-prospect-60056/</loc>" in xml


def test_build_robots_txt_references_sitemap():
    robots = build_digest.build_robots_txt()
    assert "Sitemap: https://randerson-23.github.io/agent-business/sitemap.xml" in robots
    assert "Allow: /" in robots
