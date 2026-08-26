import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_digest  # noqa: E402


def test_resolve_sponsor_falls_back_to_house_ad():
    cfg = {
        "active": "none",
        "house_ad": {"title": "Sponsor this spot", "detail": "", "url": ""},
        "history": [],
    }
    sponsor = build_digest.resolve_sponsor(cfg)
    assert sponsor["title"] == "Sponsor this spot"


def test_resolve_sponsor_finds_active_entry():
    cfg = {
        "active": "acme-2026-09-01",
        "house_ad": {"title": "house", "detail": "", "url": ""},
        "history": [
            {"id": "acme-2026-09-01", "title": "Acme Dentistry", "detail": "", "url": ""},
        ],
    }
    sponsor = build_digest.resolve_sponsor(cfg)
    assert sponsor["title"] == "Acme Dentistry"


def test_render_produces_html_even_with_empty_sources():
    blocks = [{"section": "Village News", "events": []}]
    sponsor = {"title": "Sponsor this spot", "detail": "", "url": ""}
    evergreen = [{"title": "Library", "detail": "Books.", "url": "https://mppl.org/"}]
    html = build_digest.render(blocks, sponsor, evergreen)
    assert "60056 Weekly" in html
    assert "Village News" in html
    assert "No live updates fetched this week" in html
    assert "Library" in html


def test_render_lists_fetched_events():
    blocks = [
        {
            "section": "Village News",
            "events": [{"title": "Board Meeting", "detail": "7pm", "url": "https://x/1", "date": None}],
        }
    ]
    sponsor = {"title": "Sponsor this spot", "detail": "", "url": ""}
    html = build_digest.render(blocks, sponsor, [])
    assert "Board Meeting" in html
    assert "No live updates fetched this week" not in html
