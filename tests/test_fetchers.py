import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import fetch_html_events, fetch_ics, fetch_rss  # noqa: E402

SAMPLE_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>Village News</title>
<item>
  <title>Board Meeting Tuesday</title>
  <link>https://example.org/board</link>
  <description>Village board meets at 7pm.</description>
  <pubDate>Mon, 24 Aug 2026 12:00:00 GMT</pubDate>
</item>
<item>
  <title>Road Closure on Main St</title>
  <link>https://example.org/road</link>
  <description>Main St closed for repaving.</description>
  <pubDate>Tue, 25 Aug 2026 12:00:00 GMT</pubDate>
</item>
</channel></rss>
"""

SAMPLE_ICS = """BEGIN:VCALENDAR
BEGIN:VEVENT
SUMMARY:Storytime at the Park
DTSTART:20990901T100000Z
DESCRIPTION:Family storytime.
URL:https://example.org/storytime
END:VEVENT
BEGIN:VEVENT
SUMMARY:Past Event Should Be Filtered
DTSTART:20200101T100000Z
END:VEVENT
END:VCALENDAR
"""

SAMPLE_HTML = """
<html><body>
<a href="/events/summer-concert-series">Summer Concert Series</a>
<a href="/about">About Us</a>
<a href="/events/kids-craft-class">Kids Craft Class</a>
</body></html>
"""


def _mock_response(text: str = "", content: bytes | None = None):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.text = text
    resp.content = content if content is not None else text.encode("utf-8")
    return resp


@patch("fetchers.requests.get")
def test_fetch_rss_parses_items(mock_get):
    mock_get.return_value = _mock_response(SAMPLE_RSS)
    items = fetch_rss("https://example.org/rss")
    assert len(items) == 2
    assert items[0]["title"] == "Board Meeting Tuesday"
    assert items[0]["url"] == "https://example.org/board"


@patch("fetchers.requests.get")
def test_fetch_rss_fails_soft_on_error(mock_get):
    mock_get.side_effect = RuntimeError("boom")
    assert fetch_rss("https://example.org/rss") == []


@patch("fetchers.requests.get")
def test_fetch_rss_fails_soft_on_bad_xml(mock_get):
    mock_get.return_value = _mock_response("<not valid xml")
    assert fetch_rss("https://example.org/rss") == []


@patch("fetchers.requests.get")
def test_fetch_ics_filters_past_events(mock_get):
    mock_get.return_value = _mock_response(SAMPLE_ICS)
    items = fetch_ics("https://example.org/cal.ics")
    assert len(items) == 1
    assert items[0]["title"] == "Storytime at the Park"


@patch("fetchers.requests.get")
def test_fetch_ics_fails_soft(mock_get):
    mock_get.side_effect = RuntimeError("boom")
    assert fetch_ics("https://example.org/cal.ics") == []


@patch("fetchers.requests.get")
def test_fetch_html_events_filters_relevant_links(mock_get):
    mock_get.return_value = _mock_response(SAMPLE_HTML)
    items = fetch_html_events("https://example.org/events")
    titles = {i["title"] for i in items}
    assert "Summer Concert Series" in titles
    assert "Kids Craft Class" in titles
    assert "About Us" not in titles


@patch("fetchers.requests.get")
def test_fetch_html_events_fails_soft(mock_get):
    mock_get.side_effect = RuntimeError("boom")
    assert fetch_html_events("https://example.org/events") == []
