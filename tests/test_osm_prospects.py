import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import osm_prospects as op  # noqa: E402


def el(name, **tags):
    return {"type": "node", "tags": {"name": name, **tags}}


def test_query_is_scoped_to_the_town_boundary_in_illinois_and_to_named_places():
    q = op.build_query("Wheeling")
    assert '["name"="Illinois"]["admin_level"="4"]' in q and '["name"="Wheeling"]["admin_level"="8"]' in q
    assert 'nwr["shop"~"^(gift|toys|books|florist|jewelry|boutique|clothes|chocolate|confectionery|bakery)$"]["name"]' in q
    assert 'nwr["amenity"~"^(ice_cream|cafe|restaurant)$"]["name"]' in q and "out tags center" in q


def test_rows_keep_names_categories_and_websites_only_never_emails_or_phones():
    row = op.row_from_element(el("Book Nook", shop="books", website="booknook.example", email="owner@booknook.example", phone="+1 555"))
    assert row == {"name": "Book Nook", "category": "books", "website": "https://booknook.example"}
    assert "email" not in str(row) and "555" not in str(row)
    assert op.row_from_element({"tags": {"shop": "books"}}) is None  # no name
    assert op.row_from_element(el("Hardware", shop="hardware")) is None  # not a category we list


def test_rows_are_ordered_by_holiday_buying_category_then_website_then_name_and_deduplicated():
    elements = [el("Diner", amenity="restaurant", website="d.example"), el("Zed Gifts", shop="gift"), el("Alpha Gifts", shop="gift", website="a.example"),
                el("Kids Toys", shop="toys"), el("Zed Gifts", shop="gift")]
    rows = op.rows_for_town(elements)
    assert [r["name"] for r in rows] == ["Alpha Gifts", "Zed Gifts", "Kids Toys", "Diner"]


def test_markdown_has_attribution_visit_in_person_thin_coverage_and_failed_town_notes():
    now = datetime(2026, 10, 24, tzinfo=timezone.utc)
    rows = op.rows_for_town([el("Zed Gifts", shop="gift"), el("Alpha Gifts", shop="gift", website="a.example")])
    md = op.render_markdown({"Palatine": rows, "Wheeling": [], "Des Plaines": None}, now)
    assert "OpenStreetMap contributors" in md and "ODbL" in md.replace("Open Database Licence (ODbL)", "ODbL") and "never share or republish" in md
    assert "| Alpha Gifts | Gift shop | <https://a.example> |" in md and "| Zed Gifts | Gift shop | visit in person |" in md
    assert "OSM coverage is thin" in md and "query for this town failed" in md and "Cross-check (not yet done)" in md


def test_fetch_town_fails_soft_and_main_keeps_the_old_file_when_everything_fails(tmp_path, monkeypatch):
    def boom(*a, **k): raise RuntimeError("blocked")
    assert op.fetch_town("Palatine", post=boom) is None
    monkeypatch.setattr(op, "OUTPUT_PATH", tmp_path / "p.md")
    monkeypatch.setattr(op, "fetch_town", lambda town, post=None: None)
    assert op.main() == 1 and not (tmp_path / "p.md").exists()
