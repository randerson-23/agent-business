import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import fetch_html_events, fetch_ics, fetch_rss, fetch_weather  # noqa: E402

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

# Mirrors the real structure observed on mppl.libnet.info/events (Communico):
# top nav links to section pages, plus real per-event detail links.
COMMUNICO_STYLE_HTML = """
<html><body>
<nav>
<a href="https://mppl.libnet.info/events">All Events</a>
<a href="/special-events">Special Events</a>
<a href="https://mppl.org/events/reading-programs/">Reading and Activity Programs</a>
</nav>
<main>
<a href="/event/9687452">Library Closed</a>
<a href="/event/13719077">Developmental Playgroup</a>
</main>
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
def test_fetch_ics_normalizes_webcal_scheme(mock_get):
    # requests has no adapter for webcal:// - it must be rewritten to
    # https:// before being handed to requests.get, or every subscribe-only
    # calendar export (the common case) silently fetches nothing forever.
    mock_get.return_value = _mock_response(SAMPLE_ICS)
    fetch_ics("webcal://example.org/cal.ics")
    called_url = mock_get.call_args[0][0]
    assert called_url == "https://example.org/cal.ics"


@patch("fetchers.requests.get")
def test_fetch_ics_unescapes_text(mock_get):
    # Regression test: a real production run showed literal "\n" and "\,"
    # characters leaking into rendered card text - RFC 5545 TEXT values
    # escape newlines/commas/semicolons, and the parser wasn't undoing it.
    ics = (
        "BEGIN:VCALENDAR\n"
        "BEGIN:VEVENT\n"
        "SUMMARY:Barks and Brews 2: Electric Boogaloo\n"
        "DTSTART:20990901T100000Z\n"
        "DESCRIPTION:Ages 18+\\, 21+ after 6pm.\\nBring your own leash.\n"
        "END:VEVENT\n"
        "END:VCALENDAR\n"
    )
    mock_get.return_value = _mock_response(ics)
    items = fetch_ics("https://example.org/cal.ics")
    assert items[0]["detail"] == "Ages 18+, 21+ after 6pm. Bring your own leash."


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


@patch("fetchers.requests.get")
def test_fetch_html_events_accepts_custom_keywords(mock_get):
    # Village news uses this scraper too, tuned with news-flavored keywords
    # instead of the events default - "Board Meeting Notice" wouldn't match
    # the default keyword set's "class"/"camp"/"concert" style terms.
    html = (
        '<a href="/news/board-meeting-notice">Board Meeting Notice</a>'
        '<a href="/about">About Us</a>'
    )
    mock_get.return_value = _mock_response(html)
    items = fetch_html_events(
        "https://example.org/news", keywords=["news", "board", "meeting", "notice"]
    )
    titles = {i["title"] for i in items}
    assert titles == {"Board Meeting Notice"}


@patch("fetchers.requests.get")
def test_fetch_html_events_uses_custom_detail_link_pattern(mock_get):
    # vah.com (Village of Arlington Heights) links each real news item to
    # news_detail_T<n>_R<n>.php - a per-source override so this doesn't
    # have to guess with keywords once the real link structure is known.
    html = (
        '<a href="/news_detail_T13_R565.php">Music with the Mayor</a>'
        '<a href="/newslist.php">News List</a>'
        '<a href="/about.php">About the Village</a>'
    )
    mock_get.return_value = _mock_response(html)
    items = fetch_html_events(
        "https://example.org/newslist.php", detail_link_pattern=r"news_detail_T\d+_R\d+\.php"
    )
    titles = {i["title"] for i in items}
    assert titles == {"Music with the Mayor"}


@patch("fetchers.requests.get")
def test_fetch_html_events_ahml_drupal_calendar_uses_reservation_link_pattern(mock_get):
    # AHML (ahml.info/attend/events) runs a Drupal calendar (Views +
    # Calendar module). Each real event's <h4 class="event_title"> links to
    # its modal detail view at /scheduling/reservation/<id> - confirmed
    # 2026-08-28 from real page source. Nav/filter links on the same page
    # don't match that pattern and must be excluded.
    html = (
        '<td class="single-day past"><div class="inner"><div class="item">'
        '<h4 class="event_title">'
        '<a class="use-ajax" href="/scheduling/reservation/218675">'
        "Senior Services &amp; the Senior Center at the Farmer's Market</a>"
        "</h4></div></div></td>"
        '<a href="/attend/events">All Events</a>'
        '<a href="/attend/events?type=story">Story Times</a>'
    )
    mock_get.return_value = _mock_response(html)
    items = fetch_html_events(
        "https://www.ahml.info/attend/events", detail_link_pattern=r"scheduling/reservation/\d+"
    )
    titles = {i["title"] for i in items}
    assert titles == {"Senior Services & the Senior Center at the Farmer's Market"}
    assert "All Events" not in titles
    assert "Story Times" not in titles


@patch("fetchers.requests.get")
def test_fetch_html_events_extracts_nearby_data_date_attribute(mock_get):
    # AHML's Drupal calendar stamps each day's <td> with
    # data-date="YYYY-MM-DD" (confirmed 2026-08-28 from real page source),
    # a real per-event date signal the link extractor otherwise has no way
    # to see (it's a flat parser with no DOM/ancestor context). Mirrors the
    # real markup shape: data-date on the enclosing day cell, several
    # nested divs, then the event link deep inside.
    html = (
        '<td id="calendar-2026-08-15-0" data-date="2026-08-15" '
        'data-day-of-month="15" headers="Saturday" class="single-day past">'
        '<div class="inner"><div class="item"><div class="view-item">'
        '<div class="calendar monthview">'
        '<div class="calendar.218675.field_start_time.0.0 contents">'
        '<span class="mobile-day-of-month">15</span>'
        '<h4 class="event_title">'
        '<time datetime="2026-08-15T14:00:00Z">09:00:00</time>'
        '<a class="use-ajax" href="/scheduling/reservation/218675">'
        "Senior Services &amp; the Senior Center at the Farmer's Market</a>"
        "</h4></div></div></div></div></div></td>"
        # A different day's cell shouldn't leak its date onto this event.
        '<td data-date="2026-08-16"><a href="/scheduling/reservation/218900">'
        "Sunday Storytime</a></td>"
    )
    mock_get.return_value = _mock_response(html)
    items = fetch_html_events(
        "https://www.ahml.info/attend/events", detail_link_pattern=r"scheduling/reservation/\d+"
    )
    by_title = {i["title"]: i["date"] for i in items}
    assert by_title["Senior Services & the Senior Center at the Farmer's Market"] == "2026-08-15"
    assert by_title["Sunday Storytime"] == "2026-08-16"


@patch("fetchers.requests.get")
def test_fetch_html_events_mount_prospect_calendar_uses_event_link_pattern(mock_get):
    # mountprospect.org (Village of Mount Prospect) runs a Vision
    # Internet-style CMS calendar; each real event links to
    # /Home/Components/Calendar/Event/<event id>/<section navid> - e.g.
    # /Home/Components/Calendar/Event/27357/1044 - confirmed 2026-08-28
    # from a real event link and page source the site owner supplied. The
    # site's main nav links (unrelated /Home/... paths) must not match.
    html = (
        '<td class="calendar_weekendday calendar_day_with_items">'
        '<div class="calendar_items"><div class="calendar_item">'
        '<span class="calendar_eventtime">9:00 AM</span>'
        '<a class="calendar_eventlink" '
        'href="/Home/Components/Calendar/Event/27357/1044?curm=9&amp;cury=2026" '
        'title="Coffee with Council">Coffee with Council</a>'
        "</div></div></td>"
        '<a href="/services/calendar">Village Calendar</a>'
        '<a href="/home">Village Home Page</a>'
    )
    mock_get.return_value = _mock_response(html)
    items = fetch_html_events(
        "https://www.mountprospect.org/services/calendar",
        detail_link_pattern=r"Home/Components/Calendar/Event/\d+/\d+",
    )
    titles = {i["title"] for i in items}
    assert titles == {"Coffee with Council"}
    assert "Village Calendar" not in titles
    assert "Village Home Page" not in titles


@patch("fetchers.requests.get")
def test_fetch_html_events_falls_back_to_default_keywords_when_none_given(mock_get):
    mock_get.return_value = _mock_response(SAMPLE_HTML)
    items = fetch_html_events("https://example.org/events", keywords=None)
    titles = {i["title"] for i in items}
    assert "Summer Concert Series" in titles


@patch("fetchers.requests.get")
def test_fetch_html_events_prefers_event_detail_links_over_nav(mock_get):
    # Regression test: the first production run of this scraper against
    # mppl.org/events/ returned only nav labels like "All Events" and
    # "Special Events" because they matched the keyword filter - never any
    # real events. Communico's /event/<id> links are the reliable signal.
    mock_get.return_value = _mock_response(COMMUNICO_STYLE_HTML)
    items = fetch_html_events("https://mppl.libnet.info/events")
    titles = {i["title"] for i in items}
    assert titles == {"Library Closed", "Developmental Playgroup"}
    assert "All Events" not in titles
    assert "Special Events" not in titles
    assert "Reading and Activity Programs" not in titles


@patch("fetchers.requests.get")
def test_fetch_html_events_denylists_known_nav_labels_in_fallback(mock_get):
    # When no /event/<id> links exist at all, the keyword fallback must
    # still not resurrect known nav boilerplate.
    html = '<a href="/special-events">Special Events</a><a href="/x">Craft Camp Signup</a>'
    mock_get.return_value = _mock_response(html)
    items = fetch_html_events("https://example.org/events")
    titles = {i["title"] for i in items}
    assert titles == {"Craft Camp Signup"}


def _mock_weather_response(daily: dict):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json = Mock(return_value={"daily": daily})
    return resp


@patch("fetchers.requests.get")
def test_fetch_weather_parses_daily_forecast(mock_get):
    mock_get.return_value = _mock_weather_response(
        {
            "time": ["2026-08-29", "2026-08-30"],
            "temperature_2m_max": [81.4, 76.2],
            "temperature_2m_min": [64.9, 61.1],
            "precipitation_probability_max": [10, 70],
            "weathercode": [1, 61],
        }
    )
    days = fetch_weather(42.0666, -87.9373)
    assert len(days) == 2
    assert days[0] == {
        "date": "2026-08-29",
        "high_f": 81,
        "low_f": 65,
        "precip_percent": 10,
        "label": "Mostly clear",
        "emoji": "\U0001f324️",
        "is_precip": False,
    }
    assert days[1]["label"] == "Light rain"
    assert days[1]["is_precip"] is True


@patch("fetchers.requests.get")
def test_fetch_weather_fails_soft_on_error(mock_get):
    mock_get.side_effect = RuntimeError("boom")
    assert fetch_weather(42.0666, -87.9373) == []


@patch("fetchers.requests.get")
def test_fetch_weather_unknown_code_gets_empty_label_not_a_crash(mock_get):
    mock_get.return_value = _mock_weather_response(
        {
            "time": ["2026-08-29"],
            "temperature_2m_max": [81.4],
            "temperature_2m_min": [64.9],
            "precipitation_probability_max": [10],
            "weathercode": [999],
        }
    )
    days = fetch_weather(42.0666, -87.9373)
    assert days[0]["label"] == ""
    assert days[0]["is_precip"] is False
