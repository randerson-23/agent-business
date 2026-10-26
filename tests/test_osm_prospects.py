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


def test_warm_prospects_dealership_yes_library_no_nobody_twice(tmp_path):
    # ROADMAP.md item 387.
    import warm_prospects as wp
    from datetime import date
    events = [
        {"title": "Free Trunk or Treat at Napleton's Palatine Mazda", "date_iso": "2026-10-24T10:00:00"},
        {"title": "Trunk or Treat at Napleton's Palatine Mazda", "date_iso": "2026-10-24T10:00:00"},   # same row again
        {"title": "Storytime at Mount Prospect Public Library", "date_iso": "2026-10-26T10:00:00"},
        {"title": "Play Packs", "date_iso": "2026-10-26T10:00:00", "venue": "Des Plaines Public Library"},
        {"title": "Concert", "date_iso": "2026-10-27T19:00:00", "venue": "Des Plaines Theatre"},
        {"title": "Fall Fun", "date_iso": "2026-10-27T19:00:00", "venue": "Palatine, IL"},
        {"title": "Old Show", "date_iso": "2026-06-01T19:00:00", "venue": "Metropolis Performing Arts Centre"},
        {"title": "Fest at Rolling Meadows Park District", "date_iso": "2026-10-27T19:00:00"},
    ]
    found = wp.collect_hosts(events, "Palatine")
    reg = wp.update_registry({}, found, date(2026, 10, 25))
    names = sorted(h["name"] for h in reg.values())
    assert names == ["Des Plaines Theatre", "Napleton's Palatine Mazda"]  # no library, park district or town; the June show is out of the window
    assert len(reg[wp.host_key("Napleton's Palatine Mazda")]["events"]) == 2  # two different titles, one host
    again = wp.update_registry(reg, found, date(2026, 10, 25))
    assert again == reg
    path = tmp_path / "w.json"
    wp.save_registry(reg, path)
    assert wp.load_registry(path) == reg
    towns = {"Palatine": [{"name": "Napleton's Palatine Mazda", "category": "cafe", "website": None}, {"name": "Oak Mill Bakery", "category": "bakery", "website": None}]}
    text = op.render_markdown(towns, datetime(2026, 10, 25, tzinfo=timezone.utc), reg)
    assert text.index("Warm: already hosting public events") < text.index("## Palatine")
    assert text.count("Napleton") == 1 + 1 - 1 + 1 - 1 or text.split("## Palatine")[1].count("Napleton") == 0  # not repeated in the OSM list
    assert "Oak Mill Bakery" in text
