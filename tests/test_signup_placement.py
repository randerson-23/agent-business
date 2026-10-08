"""ROADMAP.md items 251 and 252: a newsletter signup on every page a first
visit lands on, one inline block each (no popup), and every signup
attributed to a town and a page."""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_digest  # noqa: E402

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
NEWSLETTER = {"configured": True, "headline": "Get it in your inbox", "detail": "Thursday mornings.", "buttondown_username": "planner"}
OFF = {"configured": False, "headline": "", "detail": "", "buttondown_username": ""}
ROOT = Path(__file__).resolve().parents[1]


def region_cfg():
    return next(r for r in build_digest.load_regions() if r["region"]["id"] == "mount-prospect-60056")


def event(i):
    return {"title": f"Event {i}", "url": f"https://src/{i}", "date": "Oct 10", "date_iso": "2026-10-10T10:00:00", "tags": [], "tag_badges": [], "detail": ""}


def region_page(nav_current="all", newsletter=NEWSLETTER, blocks=None):
    blocks = blocks if blocks is not None else [{"section": "Library", "events": [event(1), event(2)]}, {"section": "Parks", "events": [event(3)]}]
    return build_digest.render_region_page(
        region_cfg(), blocks, {"title": "", "detail": "", "url": ""}, [], NOW, newsletter=newsletter, nav_current=nav_current,
    )


def hub_page(slug, headline):
    sections = [{"region_name": "Mount Prospect", "region_url": "https://x/mp/", "events": [event(1)]}]
    return build_digest.render_merged_hub_page(
        sections, NOW, None, slug=slug, heading="H", subheading="s", meta_description="m", empty_message="none",
        newsletter=NEWSLETTER, signup_headline=headline,
    )


def tot_page(newsletter=NEWSLETTER):
    entries = [{"region_id": "mp", "region_name": "Mount Prospect", "region_url": "https://x/mp/", "url": "https://v", "hours": None, "note": None}]
    return build_digest.render_trick_or_treat_page(entries, NOW, None, newsletter)


def assert_one_runtime(html):
    assert html.count('name="bd-hidden-frame"') == 1
    assert html.count('document.querySelectorAll(".newsletter-form")') == 1


def all_ids(html):
    return re.findall(r'\bid="([^"]+)"', html)


def test_each_landing_page_has_exactly_one_inline_form():
    pages = {
        "this-weekend": hub_page("this-weekend", "Get this list every Thursday."),
        "today": hub_page("today", "Get the weekend's events by email on Thursday."),
        "free": hub_page("free", "Free things to do, every Thursday."),
        "trick-or-treat": tot_page(),
    }
    for name, html in pages.items():
        assert html.count("embed-subscribe") == 1, name
        assert html.count('id="newsletter-signup"') == 1, name
        assert html.count('id="bd-email"') == 1, name
        assert_one_runtime(html)
        ids = all_ids(html)
        assert ids.count("newsletter-signup") == 1 and ids.count("bd-email") == 1


def test_each_page_headline_matches_what_the_visitor_came_for():
    assert "Get this list every Thursday." in hub_page("this-weekend", "Get this list every Thursday.")
    assert "Free things to do, every Thursday." in hub_page("free", "Free things to do, every Thursday.")
    assert "Halloween falls on a Saturday this year. Get the weekend&#39;s events by email on Thursday." in tot_page()
    # The weekday is computed, not typed: it follows the year.
    assert "a Sunday" in build_digest.build_halloween_signup_headline(datetime(2027, 10, 8))


def test_region_main_page_has_two_blocks_with_distinct_ids():
    html = region_page()
    assert html.count("embed-subscribe") == 2
    for element_id in ("newsletter-signup", "newsletter-signup-end", "bd-email", "bd-email-end"):
        assert html.count(f'id="{element_id}"') == 1, element_id
    assert_one_runtime(html)
    # The mid-list block comes just before the first block of events, well before the end.
    assert html.index('id="newsletter-signup"') < html.index("Event 1")
    assert html.index("<h2>Library</h2>") > html.index('id="newsletter-signup"')
    assert html.index('id="newsletter-signup"') < html.index('id="newsletter-signup-end"')
    # The above-the-fold link jumps to it.
    assert '<a href="#newsletter-signup">' in html


def test_other_region_views_keep_a_single_bottom_form():
    for nav in ("weekend", "today", "free", "guides", "directory", "things-to-do"):
        html = region_page(nav_current=nav)
        assert html.count("embed-subscribe") == 1, nav
        assert html.count('id="newsletter-signup"') == 1, nav
        assert 'id="newsletter-signup-end"' not in html, nav


def test_a_main_page_with_no_events_still_has_one_form():
    html = region_page(blocks=[{"section": "Library", "events": []}])
    assert html.count("embed-subscribe") == 1
    assert html.count('id="newsletter-signup"') == 1


def test_every_signup_names_its_town_and_page():
    def hidden(html):
        return re.findall(r'<input type="hidden" name="(tag|utm_source|utm_campaign)" value="([^"]*)">', html)

    main = hidden(region_page())
    assert ("tag", "town:mount-prospect-60056") in main
    assert ("utm_source", "site") in main
    assert [v for k, v in main if k == "utm_campaign"] == ["region-midlist", "region"]
    assert [v for k, v in hidden(region_page(nav_current="free")) if k == "utm_campaign"] == ["free"]
    assert [v for k, v in hidden(region_page(nav_current="weekend")) if k == "utm_campaign"] == ["this-weekend"]
    assert [v for k, v in hidden(region_page(nav_current="guides")) if k == "utm_campaign"] == ["guide"]
    assert hidden(hub_page("today", "x")) == [("tag", "town:all"), ("utm_source", "site"), ("utm_campaign", "today")]
    assert ("utm_campaign", "trick-or-treat") in hidden(tot_page())


def test_nothing_renders_when_signup_is_not_configured():
    for html in (region_page(newsletter=OFF), tot_page(OFF)):
        assert "embed-subscribe" not in html
        assert 'name="bd-hidden-frame"' not in html
        assert "newsletter-pending" not in html.split("</style>")[-1]


def test_there_is_no_popup_modal_or_scroll_overlay():
    source = (ROOT / "templates" / "_signup.html.j2").read_text(encoding="utf-8")
    code = re.sub(r"\{#.*?#\}", "", source, flags=re.S).lower()  # comments may explain what is NOT done
    for banned in ("scroll", "modal", "popup", "window.open", "settimeout", "exitintent", "mouseleave", "position: fixed"):
        assert banned not in code, banned


def test_the_forward_link_in_emails_is_tracked():
    for name in ("email_digest.html.j2", "combined_email_digest.html.j2"):
        source = (ROOT / "templates" / name).read_text(encoding="utf-8")
        assert "?utm_source=email&utm_campaign=forward" in source, name
