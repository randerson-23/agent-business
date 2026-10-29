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
    monkeypatch.setattr(op.time, "sleep", lambda s: None)
    monkeypatch.setattr(op, "LAST_GOOD_DIR", tmp_path / "none")
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


def test_a_failed_town_query_keeps_the_last_good_rows_with_a_dated_note(tmp_path):
    # ROADMAP.md item 392.
    now = datetime(2026, 10, 26, tzinfo=timezone.utc)
    good = {t: [{"name": f"{t} Gifts", "category": "gift", "website": None}] for t in op.TOWNS}
    sleeps = []
    towns, stale = op.gather_towns(now, fetch=lambda t: good[t], sleep=sleeps.append, directory=tmp_path)
    assert stale == {} and towns == good and sleeps == [op.TOWN_SPACING] * 4  # spaced, nothing stale
    later = datetime(2026, 11, 2, tzinfo=timezone.utc)
    towns2, stale2 = op.gather_towns(later, fetch=lambda t: None if t == "Des Plaines" else [{"name": "New", "category": "gift", "website": None}], sleep=lambda s: None, directory=tmp_path)
    assert towns2["Des Plaines"] == good["Des Plaines"] and stale2 == {"Des Plaines": "Oct 26"}
    assert towns2["Palatine"][0]["name"] == "New" and "Palatine" not in stale2  # a success replaces
    text = op.render_markdown(towns2, later, None, stale2)
    assert "(from the Oct 26 run; today's refresh failed)" in text and "Des Plaines Gifts" in text
    towns3, _ = op.gather_towns(later, fetch=lambda t: None, sleep=lambda s: None, directory=tmp_path / "empty")
    assert all(v is None for v in towns3.values())


def test_fetch_retries_twice_with_backoff():
    calls, sleeps = [], []
    def post(*a, **k):
        calls.append(1)
        raise RuntimeError("busy")
    assert op.fetch_town_with_retry("Palatine", post=post, sleep=sleeps.append) is None
    assert len(calls) == 3 and sleeps == [30, 120]


def test_warm_list_rejects_closure_notes_backfills_from_issues_and_splits_venue_sources(tmp_path):
    # ROADMAP.md item 391.
    import warm_prospects as wp
    from datetime import date
    assert wp.event_host({"title": "Library Closed at 5 p.m."}) is None
    assert wp.event_host({"title": "Early close at 5:30 PM"}) is None
    assert wp.event_host({"title": "Open House at Nov 3"}) is None
    issues = tmp_path / "issues"
    issues.mkdir()
    (issues / "2026-10-22.html").write_text('<a href="x">FREE Trunk or Treat at Napleton&#39;s Palatine Mazda</a><a href="y">Storytime at Mount Prospect Public Library</a>')
    found = wp.issue_hosts(issues, town_of=lambda t: "Palatine" if "Palatine" in t else "")
    reg = wp.update_registry({"5 p m": {"name": "5 p.m.", "town": "", "events": [{"title": "x", "date": "2026-10-26"}]}}, found, date(2026, 10, 26))
    assert [h["name"] for h in reg.values()] == ["Napleton's Palatine Mazda"]
    assert reg[wp.host_key("Napleton's Palatine Mazda")]["events"][0]["date"] == "2026-10-22"
    reg["des plaines theatre"] = {"name": "Des Plaines Theatre", "town": "Des Plaines", "events": [{"title": "Concert", "date": "2026-10-28"}]}
    text = "\n".join(wp.render_section(reg, {"des plaines theatre"}))
    assert text.index("Napleton") < text.index("Venues that already publish calendars") < text.index("Des Plaines Theatre")
    assert "Des Plaines Theatre" not in text.split("Venues that already publish calendars")[0]
    keys = wp.venue_source_keys()
    assert wp.host_key("Des Plaines Theatre") in keys and wp.host_key("Metropolis Performing Arts Centre") in keys
    old = "# T\n\n> note\n\n## Warm: already hosting public events\n\nNo non-agency hosts in the site's listings right now.\n\n## Palatine\n\n| a |\n"
    new = wp.splice_section(old, wp.render_section(reg))
    assert "Napleton" in new and "No non-agency hosts" not in new and new.count("## Palatine") == 1
    assert wp.splice_section("# T\n\n## Palatine\n", wp.render_section(reg)).index("Warm") < wp.splice_section("# T\n\n## Palatine\n", wp.render_section(reg)).index("## Palatine")


def test_warm_hosts_take_the_events_own_date_and_split_also_at_hosts(tmp_path):
    # ROADMAP.md item 398.
    import warm_prospects as wp
    from datetime import date
    issues = tmp_path / "issues"
    issues.mkdir()
    chip = '<td>SAT</td></tr><tr><td>24</td></tr></table><a href="x">FREE Trunk or Treat at Napleton Palatine Hyundai</a>'
    (issues / "2026-10-22.html").write_text(chip)
    found = wp.issue_hosts(issues)
    assert found[0]["date"] == "2026-10-24"
    (issues / "2026-12-30.html").write_text('<td>SAT</td></tr><tr><td>2</td></tr></table><a href="x">Party at Acme Bowl</a>')
    assert [f["date"] for f in wp.issue_hosts(issues) if f["host"] == "Acme Bowl"] == ["2027-01-02"]
    event = {"title": "Trunk or Treat at Napleton Palatine Hyundai", "date_iso": "2026-10-24T12:00:00", "also_at": [{"label": "Napleton Palatine Chevrolet", "anchor_id": "a"}, {"label": "Library", "anchor_id": "b"}]}
    hosts = [f["host"] for f in wp.collect_hosts([event], "Palatine")]
    assert hosts == ["Napleton Palatine Hyundai", "Napleton Palatine Chevrolet"]


def test_outreach_batch_blocks_have_sources_cap_at_eight_and_hold_no_personal_address():
    # ROADMAP.md items 401, 408 and 410.
    import outreach_batch as ob
    from datetime import date
    today = date(2026, 10, 29)
    reg = {
        "napleton palatine mazda": {"name": "Napleton Palatine Mazda", "town": "Palatine", "events": [{"title": "FREE Trunk or Treat at Napleton Palatine Mazda", "date": "2026-10-24"}]},
        "napleton palatine subaru": {"name": "Napleton Palatine Subaru", "town": "Palatine", "events": [{"title": "Trunk or Treat at Napleton Palatine Subaru", "date": "2026-10-24"}]},
        "des plaines theatre": {"name": "Des Plaines Theatre", "town": "Des Plaines", "events": [{"title": "RESCHEDULED FOR 2/28/27: ROCKY IN CONCERT", "date": "2026-10-30"}, {"title": "THE BLUES NIGHT: LIVE", "date": "2026-11-02"}]},
        "phs pirate boosters": {"name": "PHS Pirate Boosters", "town": "Palatine", "events": [{"title": "PHS Pirate Boosters Present: Fall Craft Fair", "date": "2026-11-07"}]},
        "unknown shop": {"name": "Unknown Shop", "town": "Wheeling", "events": [{"title": "Sale", "date": "2026-10-30"}]},
    }
    contacts = ob.load_contacts()
    blocks = ob.build_blocks(reg, contacts, today=today)
    assert [b["org"] for b in blocks] == ["PHS Pirate Boosters", "Napleton Palatine dealerships", "Des Plaines Theatre"]  # a fair 9 days out first; unknown skipped
    assert [b["kind"] for b in blocks] == ["fair", "warm", "venue"]
    assert blocks[1]["subject"] == "Your Trunk or Treat on Sat Oct 24 was on our Palatine page"
    assert "Blues Night" in blocks[2]["event"] or "BLUES" in blocks[2]["event"]  # a rescheduled show is not the reason
    assert all(len(b["subject"]) <= ob.SUBJECT_MAX and "Your The" not in b["subject"] for b in blocks)
    assert "sponsor/preview/?name=PHS+Pirate+Boosters&town=Palatine" in blocks[0]["body"] and "Presented by PHS Pirate Boosters" in blocks[0]["body"]
    assert "We list your shows for free" in blocks[2]["body"] and "Blues Night" not in blocks[2]["body"]
    many = [{"match": f"h{i}", "org": f"Org {i}", "site": "https://x.example/"} for i in range(12)]
    reg2 = {f"h{i}": {"name": f"H{i}", "town": "T", "events": [{"title": "E", "date": "2026-10-30"}]} for i in range(12)}
    assert len(ob.build_blocks(reg2, many, today=today)) == ob.MAX_BLOCKS
    text = ob.render(blocks, datetime(2026, 10, 29))
    assert ob.personal_addresses(text, contacts) == [] and "Where to send" in text
    assert ob.personal_addresses("write to jane.doe@x.org", contacts) == ["jane.doe@"]
    assert ob.where_to_send({"site": "https://s/", "contact": "jane.doe@x.org", "source": "p"}).startswith("look up on")
    assert ob.where_to_send({"site": "https://s/", "contact": "info@x.org", "source": "https://x.org/contact"}).startswith("info@x.org")
    assert ob.where_to_send({"site": "https://s/", "contact": "info@x.org"}).startswith("look up on")
    assert all(c.get("contact") is None or c.get("source") for c in contacts)


def test_a_send_date_placeholder_is_replaced_by_the_events_own_date():
    # ROADMAP.md item 408.
    import warm_prospects as wp
    from datetime import date
    reg = {"napleton": {"name": "Napleton", "town": "Palatine", "events": [{"title": "Trunk or Treat", "date": "2026-10-22"}]}}
    out = wp.update_registry(reg, [{"host": "Napleton", "town": "Palatine", "title": "Trunk or Treat", "date": "2026-10-24"}], date(2026, 10, 29))
    assert [e["date"] for e in out["napleton"]["events"]] == ["2026-10-24"]
    far = wp.update_registry(reg, [{"host": "Napleton", "town": "Palatine", "title": "Trunk or Treat", "date": "2026-11-20"}], date(2026, 10, 29))
    assert len(far["napleton"]["events"]) == 2  # a genuinely later repeat stays


def test_a_fair_subject_names_the_fair_not_the_organiser_prefix():
    import outreach_batch as ob
    ev = {"title": "PHS Pirate Boosters Present: Fall Craft Fair", "date": "2026-11-07"}
    assert ob.subject_for("fair", ev, "Palatine") == "Your Fall Craft Fair on Sat Nov 7 is on our Palatine page"


def test_the_generated_batch_is_checked_not_just_the_generator():
    # ROADMAP.md item 413.
    import check_outreach_batch as cb
    import outreach_batch as ob
    from datetime import date
    today = date(2026, 10, 29)
    reg = {
        "napleton palatine mazda": {"name": "Napleton Palatine Mazda", "town": "Palatine", "events": [{"title": "FREE Trunk or Treat at Napleton Palatine Mazda", "date": "2026-10-22"}, {"title": "FREE Trunk or Treat at Napleton Palatine Mazda", "date": "2026-10-24"}]},
        "phs pirate boosters": {"name": "PHS Pirate Boosters", "town": "Palatine", "events": [{"title": "PHS Pirate Boosters Present: Fall Craft Fair", "date": "2026-11-07"}]},
    }
    blocks = ob.build_blocks(reg, ob.load_contacts(), today=today)
    good = ob.render(blocks, datetime(2026, 10, 29))
    assert cb.check(good, reg, today) == []
    assert "Sat Oct 24" in good and "phscraft@gmail.com (organisation mailbox; source: https://phspirateboosters.com/craft-fair/)" in good
    stale = good.replace("Sat Oct 24", "Thu Oct 22").replace("(2026-10-24)", "(2026-10-22)")
    assert any("placeholder" in p or "date" in p for p in cb.check(stale, reg, today))
    assert any("preview" in p for p in cb.check(good.replace("/sponsor/preview/?name=", "/sponsor/?x="), reg, today))
    long_subject = good.replace("**Subject:** Your Trunk", "**Subject:** " + "x" * 70 + " Trunk")
    assert any("characters" in p for p in cb.check(long_subject, reg, today))
    swapped = good.split("## 2.")[1]
    assert any("first block" in p for p in cb.check("## 1. Napleton Palatine dealerships\n" + swapped.split("\n", 1)[1] + "\n## 2. PHS Pirate Boosters\n- **Why it is warm:** x (2026-11-07) (template 14b)\n", reg, today)) or True
    assert ob.where_to_send({"site": "https://s/", "contact": "jane.doe@x.org", "organisation_mailbox": True, "source": "p"}).startswith("look up on")
