"""ROADMAP.md item 247: /sponsor/ sells the Event Promo that item 245 built."""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_digest  # noqa: E402

NOW = datetime(2026, 10, 7, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def sponsor_html(**kw):
    return build_digest.render_sponsor_page([], NOW, **kw)


def test_the_event_promo_card_shows_an_example_featured_event():
    html = sponsor_html()
    card = re.search(r'<div class="sample-card".*?</div>\s*</div>', html, re.S).group(0)
    assert '<span class="sample-tag">Example</span>' in card
    assert 'class="featured-label">Featured · Presented by Your Business Name</div>' in card
    assert "Fall Open House &amp; Pumpkin Painting" in card
    # It sits inside the Event Promo tier, not another.
    event_promo = re.search(r'<div class="tier">\s*<h3>Event Promo</h3>.*?(?=<div class="tier|</section>)', html, re.S).group(0)
    assert "sample-card" in event_promo
    assert html.count("sample-card\" role") == 1


def test_the_example_uses_the_same_partial_as_a_real_promotion():
    # The label comes from one macro; no template writes it out by hand.
    for name in ("region.html.j2", "merged_hub.html.j2", "sponsor.html.j2"):
        source = (ROOT / "templates" / name).read_text(encoding="utf-8")
        assert 'import featured_label' in source, name
        assert "featured_label(" in source, name
        assert "Featured · Presented by" not in source, f"{name} hand-writes the label"
    assert "Featured · Presented by" in (ROOT / "templates" / "_featured.html.j2").read_text(encoding="utf-8")


def test_the_example_event_never_reaches_real_data():
    sample = build_digest.SAMPLE_PROMOTION_EVENT
    region_cfg = next(iter(build_digest.load_regions()))
    page = build_digest.render_region_page(
        region_cfg, [{"section": "News", "events": []}],
        {"title": "Sponsor this spot", "detail": "", "url": "", "is_active_sponsor": False}, [], NOW,
    )
    assert sample["title"] not in page and "Your Business Name" not in page
    listing = build_digest.build_events_json([("Town", "https://x/", [])], "n", NOW)
    assert sample["title"] not in listing
    assert sample["title"] not in build_digest.build_llms_full_txt([("Town", "https://x/", [])], "Oct 10-11")
    source = (ROOT / "scripts" / "build_digest.py").read_text(encoding="utf-8")
    # Referenced in exactly two places: its definition and render_sponsor_page's
    # template context. Any third use is a new route for it into real data.
    assert source.count("SAMPLE_PROMOTION_EVENT") == 2


def test_the_event_promo_card_says_what_it_delivers_and_stays_honest():
    html = sponsor_html()
    assert "Your event goes first on your town&#39;s page" in html
    assert "labelled &#34;Presented by [you]&#34;" in html
    assert "marked as sponsored in the event data AI assistants read" in html
    assert "Runs until the event day" in html
    assert "We guarantee the placement, not any assistant&#39;s mention." in html
    assert "boosted to the top" not in html


def test_value_grows_with_replaces_gated_by_everywhere():
    assert "Gated by" not in sponsor_html()
    assert "Gated by" not in (ROOT / "SPONSOR_KIT.md").read_text(encoding="utf-8")
    assert "| Value grows with |" in (ROOT / "SPONSOR_KIT.md").read_text(encoding="utf-8")


def test_payment_line_without_stripe_links():
    html = sponsor_html(payment_links={"event_promo": None, "weekly_spot": None})
    assert "Payment: Venmo/Zelle/check. Annual and month-to-month options" in html
    assert "Card (Stripe)" not in html


def test_payment_line_names_exactly_the_tiers_that_take_a_card():
    both = sponsor_html(payment_links={"event_promo": "https://buy.stripe.com/a", "weekly_spot": "https://buy.stripe.com/b"})
    assert "Card (Stripe) on Event Promo and Weekly Spot; Venmo, Zelle or check for anything else." in both
    assert both.count("Buy now") == 2
    one = sponsor_html(payment_links={"event_promo": "https://buy.stripe.com/a", "weekly_spot": None})
    assert "Card (Stripe) on Event Promo; Venmo, Zelle or check for anything else." in one
    assert "Weekly Spot;" not in one.split("Card (Stripe)")[1].split("</p>")[0]
