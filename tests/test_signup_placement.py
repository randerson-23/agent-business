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


# ---- ROADMAP.md item 254: the "open your inbox" step after Subscribe --------


def test_webmail_provider_maps_the_address_domain():
    wp = build_digest.webmail_provider
    assert wp("ann@gmail.com") == ("Open Gmail", "https://mail.google.com/mail/u/0/#search/from%3Abuttondown")
    assert wp("ann@googlemail.com")[0] == "Open Gmail"
    assert wp("ann@yahoo.com") == ("Open Yahoo Mail", "https://mail.yahoo.com/")
    assert wp("ann@ymail.com")[0] == "Open Yahoo Mail"
    assert wp("ann@aol.com") == ("Open AOL Mail", "https://mail.aol.com/")
    for domain in ("outlook.com", "hotmail.com", "live.com", "msn.com"):
        assert wp(f"ann@{domain}") == ("Open Outlook", "https://outlook.live.com/mail/0/")
    for domain in ("icloud.com", "me.com", "mac.com"):
        assert wp(f"ann@{domain}") == ("Open iCloud Mail", "https://www.icloud.com/mail/")


def test_webmail_provider_ignores_case_and_only_reads_after_the_at_sign():
    wp = build_digest.webmail_provider
    assert wp("Ann@GMAIL.COM")[0] == "Open Gmail"
    assert wp("  ann@gmail.com ")[0] == "Open Gmail"
    assert wp("gmail.com@school.org") is None  # the part before "@" is not a domain
    assert wp("ann@mail.yahoo.com") is None  # a subdomain is not an address domain
    assert wp("ann@mygmail.com") is None  # suffix match would be wrong
    assert wp("ann@example.org") is None
    assert wp("not an address") is None
    assert wp("") is None


def test_the_page_script_uses_the_same_table_as_python():
    html = region_page()
    import json
    table = json.loads(re.search(r"var WM = (\[.*?\]);", html, re.S).group(1))
    assert table == [[label, url, list(domains)] for label, url, domains in build_digest.WEBMAIL_PROVIDERS]


def test_the_pending_step_has_one_hidden_button_and_the_spam_hint():
    html = tot_page()
    done = re.search(r'<div class="newsletter-done" hidden>.*?</div>', html, re.S).group(0)
    assert "Almost there — check your email and click the confirmation link." in done
    assert 'class="newsletter-open" href="#" target="_blank" rel="noopener" hidden' in done
    assert "Not there in two minutes? Check Spam or Promotions for a message from Within Ten via Buttondown." in done
    # Hidden until the script fills it in for a known provider; no-JS readers see the form's own note.
    assert "We'll send one email to confirm." in html


def test_the_inline_js_budget_is_the_deliberate_one():
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_perf_budget
    assert check_perf_budget.MAX_INLINE_JS_BYTES == 13_312


# ---- ROADMAP.md item 255: preferred source on Google -------------------------


def test_preferred_source_link_is_built_from_the_one_domain_constant():
    assert build_digest.PREFERRED_SOURCE_URL == f"https://google.com/preferences/source?q={build_digest.CUSTOM_DOMAIN}"
    # No template hard-codes the domain into the link.
    for path in (ROOT / "templates").glob("*.j2"):
        assert "google.com/preferences/source" not in path.read_text(encoding="utf-8"), path.name


def test_every_page_footer_links_the_preferred_source_once():
    url = build_digest.PREFERRED_SOURCE_URL
    pages = {
        "region": region_page(),
        "region-free": region_page(nav_current="free"),
        "this-weekend": hub_page("this-weekend", "x"),
        "trick-or-treat": tot_page(),
        "sponsor": build_digest.render_sponsor_page([], NOW),
    }
    for name, html in pages.items():
        assert html.count(f'href="{url}"') == 1, name
        assert "Add us as a preferred source on Google" in html.split("<footer>")[-1], name
    about = build_digest.render_about_page(NOW, None)
    assert about.count(f'href="{url}"') == 2  # the explanatory section and the footer
    assert "See us first on Google" in about


def test_both_emails_link_the_preferred_source_once_after_the_forward_line():
    url = build_digest.PREFERRED_SOURCE_URL
    for name in ("email_digest.html.j2", "combined_email_digest.html.j2"):
        source = (ROOT / "templates" / name).read_text(encoding="utf-8")
        assert source.count("{{ preferred_source_url }}") == 1, name
        assert source.index("utm_campaign=forward") < source.index("{{ preferred_source_url }}"), name
    region = {"id": "r", "name": "Mount Prospect"}
    single = build_digest.render_email_digest(region, [], [], "https://x/r/", "Oct 10-11", None, NEWSLETTER)
    assert single.count(f'href="{url}"') == 1
    combined = build_digest.render_combined_email_digest([], "Oct 10-11", NOW, NEWSLETTER)
    assert combined.count(f'href="{url}"') == 1
