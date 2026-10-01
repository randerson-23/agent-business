import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import REQUEST_HEADERS  # noqa: E402
from probe_urls import (  # noqa: E402
    MAX_MATCHES_PER_PATTERN,
    PROBES_PATH,
    extract_page_signals,
    find_follow_url,
    find_pattern_matches,
    load_probes,
    normalize_url,
    probe,
)

NOW = datetime(2026, 9, 29, 14, 0, tzinfo=timezone.utc)


class _Resp:
    def __init__(self, body: bytes, status=200, content_type="text/html; charset=utf-8", url="https://example.org/events"):
        self.content = body
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        self.url = url
        self.encoding = "utf-8"


class _Session:
    def __init__(self, resp=None, exc=None, by_url=None):
        self.resp, self.exc, self.by_url, self.calls = resp, exc, by_url or {}, []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.exc:
            raise self.exc
        return self.by_url.get(url, self.resp)


def test_extract_page_signals_finds_feeds_calendar_links_and_title():
    html = """<html><head><title>  Upcoming
      Events </title>
    <link rel="alternate" type="application/rss+xml" href="/events/feed" title="Events RSS">
    <link rel="stylesheet" href="/site.css"></head><body>
    <a href="/calendar?_wrapper_format=lc_calendar_feed&type=ical">iCal</a>
    <a href="webcal://example.org/cal.ics">Subscribe</a>
    <a href="/about">About</a>
    <a href="/calendar?_wrapper_format=lc_calendar_feed&type=ical">iCal again</a>
    </body></html>"""
    signals = extract_page_signals(html, "https://example.org/events/upcoming")
    assert signals["title"] == "Upcoming Events"
    assert signals["feed_links"] == [
        {"href": "https://example.org/events/feed", "type": "application/rss+xml", "title": "Events RSS"}
    ]
    assert signals["calendar_links"] == [
        "https://example.org/calendar?_wrapper_format=lc_calendar_feed&type=ical",
        "webcal://example.org/cal.ics",
    ]


def test_normalize_url_turns_webcal_into_https():
    assert normalize_url("webcal://www.ahpd.org/events/?ical=1") == "https://www.ahpd.org/events/?ical=1"
    assert normalize_url("https://x.org/") == "https://x.org/"


def test_probe_records_status_and_uses_the_builds_honest_headers_once():
    session = _Session(_Resp(b"<html><title>Cal</title></html>", status=403))
    result = probe({"url": "https://example.org/events", "item": 192, "purpose": "p"}, session=session, now=NOW)
    assert result["status"] == 403
    assert result["title"] == "Cal"
    assert result["item"] == 192
    assert result["probed_at"] == "2026-09-29T14:00:00+00:00"
    assert len(session.calls) == 1
    assert session.calls[0][1]["headers"] == REQUEST_HEADERS


def test_probe_decodes_utf8_when_the_server_names_no_charset():
    resp = _Resp("<html><title>Within Ten — Events</title></html>".encode("utf-8"), content_type="text/html")
    resp.encoding = "ISO-8859-1"  # what requests assumes for text/* without a charset
    result = probe({"url": "https://example.org/"}, session=_Session(resp), now=NOW)
    assert result["title"] == "Within Ten — Events"


def test_probe_counts_events_in_an_ics_response():
    body = b"BEGIN:VCALENDAR\nBEGIN:VEVENT\nEND:VEVENT\nBEGIN:VEVENT\nEND:VEVENT\nEND:VCALENDAR\n"
    result = probe({"url": "webcal://example.org/cal.ics"}, session=_Session(_Resp(body, content_type="text/calendar")), now=NOW)
    assert result["ics_event_count"] == 2
    assert "feed_links" not in result


def test_probe_records_transport_errors_instead_of_raising():
    result = probe({"url": "https://example.org/"}, session=_Session(exc=requests.ConnectTimeout()), now=NOW)
    assert result["error"] == "ConnectTimeout"
    assert "status" not in result


def test_committed_probe_list_is_well_formed():
    probes = load_probes(PROBES_PATH)
    assert probes, "config/url_probes.yaml should list at least one open question"
    urls = [p["url"] for p in probes]
    assert len(urls) == len(set(urls)), "duplicate probe URLs"
    for p in probes:
        assert p["url"].startswith(("https://", "webcal://")), p["url"]
        assert isinstance(p.get("item"), int) and p.get("purpose"), p


def test_load_probes_skips_entries_without_a_url(tmp_path):
    path = tmp_path / "probes.yaml"
    path.write_text(yaml.safe_dump({"probes": [{"url": "https://a.org/", "item": 1, "purpose": "x"}, {"item": 2}]}))
    assert [p["url"] for p in load_probes(path)] == ["https://a.org/"]


def test_pattern_matches_find_ids_inside_scripts_with_context_and_dedupe():
    html = '<script>var cal = {"url": "/calendar?cid=14131&t=d"}; load("/calendar?cid=14131");</script>'
    found = find_pattern_matches(html, [r"cid=\d+", r"nothing_here"])
    assert [h["match"] for h in found[r"cid=\d+"]] == ["cid=14131"]
    assert '"/calendar?cid=14131&t=d"' in found[r"cid=\d+"][0]["context"]
    assert found["nothing_here"] == []


def test_pattern_matches_are_capped_per_pattern():
    text = " ".join(f"MIID={n}" for n in range(MAX_MATCHES_PER_PATTERN + 5))
    assert len(find_pattern_matches(text, [r"MIID=\d+"])[r"MIID=\d+"]) == MAX_MATCHES_PER_PATTERN


def test_follow_url_resolves_relative_links_and_skips_the_page_itself():
    html = """<a href="#calendar">skip</a><a href="https://x.org/">Calendar home</a>
    <a href="/Page/2#calendar-top">District Calendar</a>"""
    assert find_follow_url(html, "https://x.org/", r"(?i)calendar") == "https://x.org/Page/2"
    assert find_follow_url(html, "https://x.org/", r"nomatch") is None


def test_probe_follows_one_level_with_the_same_patterns_and_stops():
    home = _Resp(b'<html><a href="/cal">Calendar</a></html>', url="https://d.org/")
    cal = _Resp(b'<html><a href="/cal2">Calendar 2</a><script>feed("icalfeed.ashx?MIID=569")</script></html>', url="https://d.org/cal")
    session = _Session(by_url={"https://d.org/": home, "https://d.org/cal": cal})
    entry = {"url": "https://d.org/", "item": 198, "purpose": "p", "follow": "(?i)cal", "patterns": [r"MIID=\d+"]}
    result = probe(entry, session=session, now=NOW)
    assert result["pattern_matches"] == {r"MIID=\d+": []}
    assert result["followed"]["url"] == "https://d.org/cal"
    assert [h["match"] for h in result["followed"]["pattern_matches"][r"MIID=\d+"]] == ["MIID=569"]
    assert "followed" not in result["followed"]
    assert [c[0] for c in session.calls] == ["https://d.org/", "https://d.org/cal"]


def test_load_probes_rejects_a_bad_regex_before_any_request(tmp_path):
    path = tmp_path / "probes.yaml"
    path.write_text(yaml.safe_dump({"probes": [{"url": "https://a.org/", "item": 1, "purpose": "x", "patterns": ["cid=(\\d+"]}]}))
    try:
        load_probes(path)
    except Exception as exc:
        assert "unterminated" in str(exc) or "missing" in str(exc)
    else:
        raise AssertionError("a malformed pattern should fail load_probes")
