import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import (  # noqa: E402
    fetch_html_events,
    fetch_ics,
    fetch_rss,
    fetch_weather,
    submit_indexnow,
)

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


def _mock_response(text: str = "", content: bytes | None = None, url: str = "https://example.org/"):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.text = text
    resp.content = content if content is not None else text.encode("utf-8")
    # .url is the URL actually served, after redirects - real requests.Response
    # behavior, used by fetchers.py to resolve relative hrefs against the
    # right host. Defaults to a generic domain since most tests don't care
    # about the exact resolved URL; pass url= explicitly for the ones that do.
    resp.url = url
    return resp


@patch("fetchers.requests.get")
def test_fetch_rss_parses_items(mock_get):
    mock_get.return_value = _mock_response(SAMPLE_RSS)
    items = fetch_rss("https://example.org/rss")
    assert len(items) == 2
    assert items[0]["title"] == "Board Meeting Tuesday"
    assert items[0]["url"] == "https://example.org/board"


@patch("fetchers.requests.get")
def test_fetch_rss_resolves_relative_link_to_absolute(mock_get):
    rss = (
        '<?xml version="1.0"?><rss><channel>'
        "<item><title>Board Meeting Tuesday</title><link>/board</link></item>"
        "</channel></rss>"
    )
    mock_get.return_value = _mock_response(rss)
    items = fetch_rss("https://example.org/rss")
    assert items[0]["url"] == "https://example.org/board"


@patch("fetchers.requests.get")
def test_fetch_rss_resolves_relative_link_against_the_post_redirect_url(mock_get):
    # A source that 301-redirects (moves domains, adds a trailing slash,
    # etc.) is followed transparently by requests - resp.url reflects the
    # final URL actually served, which is what a relative href on that
    # page must resolve against, not the pre-redirect URL passed in by
    # config.
    rss = (
        '<?xml version="1.0"?><rss><channel>'
        "<item><title>Board Meeting Tuesday</title><link>/board</link></item>"
        "</channel></rss>"
    )
    mock_get.return_value = _mock_response(rss, url="https://newsite.example.org/rss")
    items = fetch_rss("https://oldsite.example.org/rss")
    assert items[0]["url"] == "https://newsite.example.org/board"


@patch("fetchers.requests.get")
def test_fetch_rss_fails_soft_on_error(mock_get):
    # None (not []) signals a transport failure - ROADMAP.md Phase 11 #55,
    # distinct from a real [] (fetched fine, found nothing).
    mock_get.side_effect = RuntimeError("boom")
    assert fetch_rss("https://example.org/rss") is None


@patch("fetchers.requests.get")
def test_fetch_rss_fails_soft_on_bad_xml(mock_get):
    mock_get.return_value = _mock_response("<not valid xml")
    assert fetch_rss("https://example.org/rss") is None


@patch("fetchers.requests.get")
def test_fetch_rss_does_not_truncate_a_well_stocked_feed_to_six(mock_get):
    # ROADMAP.md item 178 (forty-second research pass): every live source
    # in data/source_health.json's real trailing history returned exactly
    # 6 items on every recorded build - MAX_ITEMS_PER_SOURCE was cutting
    # each feed off before build_digest.py's own date-window filtering
    # ever got a chance to select from it. A feed with 50 real entries
    # should come back with (comfortably) more than the old cap, per the
    # item's own suggested test.
    items_xml = "".join(
        f"<item><title>Event {i}</title><link>https://example.org/{i}</link></item>"
        for i in range(50)
    )
    rss = f'<?xml version="1.0"?><rss><channel>{items_xml}</channel></rss>'
    mock_get.return_value = _mock_response(rss)
    items = fetch_rss("https://example.org/rss")
    assert len(items) == 50


@patch("fetchers.requests.get")
def test_fetch_ics_filters_past_events(mock_get):
    mock_get.return_value = _mock_response(SAMPLE_ICS)
    items = fetch_ics("https://example.org/cal.ics")
    assert len(items) == 1
    assert items[0]["title"] == "Storytime at the Park"


@patch("fetchers.requests.get")
def test_fetch_ics_does_not_truncate_a_well_stocked_feed_to_six(mock_get):
    # Same regression as the RSS version above (item 178) - fetch_ics
    # already filters to upcoming-only before this cap applies, so
    # raising it directly implements "gather across a date horizon and
    # let the window select" with no other logic change needed here.
    events = "".join(
        f"BEGIN:VEVENT\nSUMMARY:Event {i}\nDTSTART:20990901T{i % 24:02d}0000Z\nEND:VEVENT\n"
        for i in range(50)
    )
    ics = f"BEGIN:VCALENDAR\n{events}END:VCALENDAR\n"
    mock_get.return_value = _mock_response(ics)
    items = fetch_ics("https://example.org/cal.ics")
    assert len(items) == 50


@patch("fetchers.requests.get")
def test_fetch_ics_fails_soft(mock_get):
    mock_get.side_effect = RuntimeError("boom")
    assert fetch_ics("https://example.org/cal.ics") is None


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
def test_fetch_ics_resolves_a_relative_url_field_to_absolute(mock_get):
    # Unlike fetch_rss and fetch_html_events, this path had no coverage
    # for a page-relative URL: field - a municipal export with
    # "URL:/events/123" would go through this branch untested.
    ics = (
        "BEGIN:VCALENDAR\n"
        "BEGIN:VEVENT\n"
        "SUMMARY:Storytime\n"
        "DTSTART:20990901T100000Z\n"
        "URL:/events/123\n"
        "END:VEVENT\n"
        "END:VCALENDAR\n"
    )
    mock_get.return_value = _mock_response(ics, url="https://example.org/cal.ics")
    items = fetch_ics("https://example.org/cal.ics")
    assert items[0]["url"] == "https://example.org/events/123"


@patch("fetchers.requests.get")
def test_fetch_ics_never_captures_organizer_attendee_or_x_properties(mock_get):
    # ROADMAP.md Phase 11 #115: a subscribed calendar.ics republishes
    # this parser's output at a public, unauthenticated URL - a source
    # feed can carry ORGANIZER/ATTENDEE/LOCATION/X- properties beyond
    # what the site ever displays, and the only reason those can't leak
    # into calendar.ics is that this parser never puts them in the
    # event dict in the first place. Verifying that at the source,
    # rather than only at build_region_calendar_ics's output, since a
    # future field this parser starts capturing would need a matching
    # decision there, not an assumption it's already covered.
    ics = (
        "BEGIN:VCALENDAR\n"
        "BEGIN:VEVENT\n"
        "SUMMARY:Storytime\n"
        "DTSTART:20990901T100000Z\n"
        "ORGANIZER;CN=Jane Doe:mailto:jane@example.org\n"
        "ATTENDEE;CN=John Smith:mailto:john@example.org\n"
        "LOCATION:Room 204B, private staff entrance\n"
        "X-INTERNAL-NOTES:Confidential setup instructions\n"
        "END:VEVENT\n"
        "END:VCALENDAR\n"
    )
    mock_get.return_value = _mock_response(ics)
    items = fetch_ics("https://example.org/cal.ics")
    assert set(items[0].keys()) == {"title", "detail", "url", "date"}


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
    assert fetch_html_events("https://example.org/events") is None


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
def test_fetch_html_events_resolves_relative_hrefs_to_absolute(mock_get):
    # Real production bug (found 2026-09-16 via the RSS feed's generated
    # output): AHML's Drupal calendar links with a page-relative href
    # ("/scheduling/reservation/218675"), correct for a browser on
    # ahml.info itself, but wrong once copied verbatim into this site's
    # own pages/feed - a reader's browser resolves it against *this*
    # site's domain instead, silently sending them to the wrong host.
    html = (
        '<h4 class="event_title">'
        '<a class="use-ajax" href="/scheduling/reservation/218675">Baby Time</a>'
        "</h4>"
    )
    mock_get.return_value = _mock_response(html, url="https://www.ahml.info/attend/events")
    items = fetch_html_events(
        "https://www.ahml.info/attend/events", detail_link_pattern=r"scheduling/reservation/\d+"
    )
    assert items[0]["url"] == "https://www.ahml.info/scheduling/reservation/218675"


@patch("fetchers.requests.get")
def test_fetch_html_events_leaves_already_absolute_hrefs_unchanged(mock_get):
    html = '<a href="https://example.org/event/12345">Real Event Here Today</a>'
    mock_get.return_value = _mock_response(html)
    items = fetch_html_events("https://example.org/events")
    assert items[0]["url"] == "https://example.org/event/12345"


@patch("fetchers.requests.get")
def test_fetch_html_events_resolves_relative_href_against_the_post_redirect_url(mock_get):
    # Same redirect-base fix as fetch_rss: a source's configured URL can
    # 301 to a new host, and a relative href on the final page must
    # resolve against that final URL (resp.url), not the pre-redirect one.
    html = '<a href="/event/12345">Real Event Here Today</a>'
    mock_get.return_value = _mock_response(html, url="https://newsite.example.org/events")
    items = fetch_html_events("https://oldsite.example.org/events")
    assert items[0]["url"] == "https://newsite.example.org/event/12345"


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
def test_fetch_html_events_mount_prospect_calendar_extracts_aria_label_date(mock_get):
    # mountprospect.org's Calendar has no data-date attribute (unlike
    # AHML's Drupal calendar) - its only date signal is the day cell's
    # accessible aria-label, e.g.
    # aria-label="Scheduled events, Saturday, September 12, 2026" -
    # confirmed 2026-08-28 from real page source.
    html = (
        '<td class="calendar_weekendday calendar_day_with_items" style="width: 14%;" '
        'aria-label="Scheduled events, Saturday, September 12, 2026" aria-expanded="false">'
        '<span class="calendar_day_value" aria-hidden="true">12</span>'
        '<div class="calendar_items"><div class="calendar_item">'
        '<span class="calendar_eventtime">9:00 AM</span>'
        '<a class="calendar_eventlink" '
        'href="/Home/Components/Calendar/Event/27357/1044?curm=9&amp;cury=2026" '
        'title="Coffee with Council">Coffee with Council</a>'
        "</div></div></td>"
    )
    mock_get.return_value = _mock_response(html)
    items = fetch_html_events(
        "https://www.mountprospect.org/services/calendar",
        detail_link_pattern=r"Home/Components/Calendar/Event/\d+/\d+",
    )
    assert items[0]["date"] == "September 12, 2026"


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


@patch("fetchers.requests.get")
def test_fetch_html_events_denylists_libcal_and_civicplus_chrome(mock_get):
    # ROADMAP.md item 175 (forty-first research pass): found in real
    # production output, not crafted first - Des Plaines, Palatine, and
    # Wheeling's Library/Village/Park District sources (none with a
    # confirmed detail_link_pattern) were all falling into this exact
    # fallback branch and returning generic nav/account/legal chrome as
    # "events" purely because a keyword substring matched ("my EVENTS",
    # "news & EVENTS", "PROGRAM guide"). "Copyright Notices" confirmed on
    # two unrelated civicplus-template domains (palatine.il.us,
    # wheelingil.gov), "My events" confirmed on calendar.dppl.org (a
    # LibCal system, same false-positive shape item 9 first found on a
    # different LibCal URL) - a real recurring platform pattern, not a
    # one-off typo to patch and forget.
    html = (
        '<a href="https://calendar.dppl.org/myevents">My events</a>'
        '<a href="https://www.dpparks.org/events/">Programs / Event Tickets</a>'
        '<a href="https://www.wheelingil.gov/civicalerts.aspx">News &amp; Events</a>'
        '<a href="https://www.palatine.il.us/site/copyright">Copyright Notices</a>'
        '<a href="/x">Fall Festival Craft Fair</a>'
    )
    mock_get.return_value = _mock_response(html)
    # "notice" isn't in DEFAULT_KEYWORDS - real production configs for the
    # two civicplus sources above (Palatine's Village News, Wheeling's
    # Village Calendar) both add it, which is exactly how "Copyright
    # Notices" reached the denylist check in the wild rather than being
    # excluded by the keyword filter before ever getting there.
    items = fetch_html_events(
        "https://example.org/events",
        keywords=["event", "program", "notice", "festival"],
    )
    titles = {i["title"] for i in items}
    assert titles == {"Fall Festival Craft Fair"}


@patch("fetchers.requests.get")
def test_fetch_html_events_dedupes_identical_title_and_url_in_fallback(mock_get):
    # ROADMAP.md item 140: found in a real production build, not crafted
    # first - Des Plaines' D62 calendar page (item 138) links the exact
    # same closure notice more than once (an "ICS:"/"All Schools:"-
    # prefixed add-to-calendar variant alongside the plain listing), and
    # every link in this fallback branch shares one generic listing-page
    # url (there's no per-event detail link here, unlike the branch
    # above that already dedupes) - so the live site rendered "No
    # School (Labor Day)" twice and "No School (Parent-Teacher
    # Conferences)" four times over for what's really one closure each.
    html = (
        '<a href="/calendars">All Schools: No School (Labor Day)</a>'
        '<a href="/calendars">All Schools: No School (Labor Day)</a>'
        '<a href="/calendars">ICS: No School (Parent-Teacher Conferences)</a>'
        '<a href="/calendars">ICS: No School (Parent-Teacher Conferences)</a>'
    )
    mock_get.return_value = _mock_response(html)
    items = fetch_html_events("https://example.org/calendars", keywords=["no school"])
    titles = [i["title"] for i in items]
    assert titles == [
        "All Schools: No School (Labor Day)",
        "ICS: No School (Parent-Teacher Conferences)",
    ]


@patch("fetchers.requests.get")
def test_fetch_html_events_keeps_distinct_titles_sharing_one_page_url(mock_get):
    # The fix above must not overcorrect: two genuinely different closures
    # that happen to share one generic listing-page url (the normal case
    # for every source in this fallback branch, which exists precisely
    # because it has no distinct per-event detail links) are not
    # duplicates of each other just because their url matches - only
    # (title, url) together identifies a real duplicate.
    html = (
        '<a href="/calendars">No School (Labor Day)</a>'
        '<a href="/calendars">No School (Parent-Teacher Conferences)</a>'
    )
    mock_get.return_value = _mock_response(html)
    items = fetch_html_events("https://example.org/calendars", keywords=["no school"])
    titles = {i["title"] for i in items}
    assert titles == {"No School (Labor Day)", "No School (Parent-Teacher Conferences)"}


@patch("fetchers.requests.get")
def test_fetch_html_events_returns_real_empty_list_when_nothing_matches(mock_get):
    # ROADMAP.md Phase 11 #55: a page that's reached successfully but has
    # no matching links returns a real [] - distinct from None (transport
    # failure). This is the "genuinely quiet week" case, not a broken
    # scraper, and must count as real health signal.
    html = '<a href="/about">About Us</a><a href="/staff">Our Staff</a>'
    mock_get.return_value = _mock_response(html)
    items = fetch_html_events("https://example.org/events")
    assert items == []
    assert items is not None


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


@patch("fetchers.requests.post")
def test_submit_indexnow_returns_true_on_success(mock_post):
    resp = Mock()
    resp.raise_for_status = Mock()
    mock_post.return_value = resp
    ok = submit_indexnow(
        host="withintenmiles.com",
        key="abc123",
        key_location="https://withintenmiles.com/abc123.txt",
        urls=["https://withintenmiles.com/"],
    )
    assert ok is True
    _, kwargs = mock_post.call_args
    assert kwargs["json"] == {
        "host": "withintenmiles.com",
        "key": "abc123",
        "keyLocation": "https://withintenmiles.com/abc123.txt",
        "urlList": ["https://withintenmiles.com/"],
    }


@patch("fetchers.requests.post")
def test_submit_indexnow_fails_soft_on_error(mock_post):
    mock_post.side_effect = RuntimeError("boom")
    ok = submit_indexnow(
        host="withintenmiles.com",
        key="abc123",
        key_location="https://withintenmiles.com/abc123.txt",
        urls=["https://withintenmiles.com/"],
    )
    assert ok is False
