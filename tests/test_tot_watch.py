import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import tot_watch as tw  # noqa: E402

PAGE = """<html><head><style>.x{}</style><script>var trick = 1;</script></head><body>
<nav>Home About Contact</nav><h1>Halloween</h1>
<p>Trick-or-treating is 3:00 to 7:00 PM on Saturday, October 31.</p><footer>Updated 12/1/2026</footer></body></html>"""


def test_window_is_oct_24_to_nov_1_only():
    assert not tw.in_window(date(2026, 10, 23)) and tw.in_window(date(2026, 10, 24)) and tw.in_window(date(2026, 11, 1)) and not tw.in_window(date(2026, 11, 2))


def test_relevant_text_keeps_the_keyword_neighbourhood_and_drops_scripts_and_styles():
    text = tw.relevant_text(PAGE)
    assert "3:00 to 7:00 PM" in text and "var trick" not in text and ".x{}" not in text


def test_an_unrelated_change_does_not_trigger_but_a_changed_time_does():
    page = PAGE.replace("</body>", " filler" * 80 + "</body>")
    before = tw.relevant_text(page)
    previous = {"hash": tw.digest(before), "snippet": before}
    unrelated = tw.relevant_text(page.replace("</body>", " Jobs Bids</body>"))
    assert tw.compare(previous, unrelated) is None
    moved = tw.relevant_text(PAGE.replace("3:00 to 7:00 PM on Saturday, October 31", "2:00 to 5:00 PM on Sunday, November 1 (weather)"))
    change = tw.compare(previous, moved)
    assert change and "November 1" in change["after"] and "October 31" in change["before"]
    assert tw.compare(None, moved) is None  # a first sighting is not a change


def test_main_never_touches_hours_and_is_silent_outside_the_window(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(tw, "WATCH_PATH", tmp_path / "w.json")
    monkeypatch.setattr(tw, "REPORT_PATH", tmp_path / "r.md")
    assert tw.main(date(2026, 10, 10)) == 0
    assert "nothing to watch" in capsys.readouterr().out and not (tmp_path / "w.json").exists()


def test_main_reports_a_change_in_the_report_file_only(monkeypatch, tmp_path):
    region_dir = tmp_path / "regions"
    region_dir.mkdir()
    cfg = region_dir / "p.yaml"
    cfg.write_text("region:\n  id: p-1\n  name: Palatine\ntrick_or_treat:\n  url: https://v/p\n  hours: '3:00-7:00 PM, Saturday, October 31'\n", encoding="utf-8")
    monkeypatch.setattr(tw, "REGIONS_DIR", region_dir)
    monkeypatch.setattr(tw, "WATCH_PATH", tmp_path / "w.json")
    monkeypatch.setattr(tw, "REPORT_PATH", tmp_path / "r.md")
    pages = iter([PAGE, PAGE.replace("3:00 to 7:00 PM", "1:00 to 4:00 PM")])

    class R:
        def __init__(self, text): self.text = text
        def raise_for_status(self): pass

    monkeypatch.setattr(tw.requests, "get", lambda *a, **k: R(next(pages)))
    assert tw.main(date(2026, 10, 25)) == 0 and not (tmp_path / "r.md").exists()  # first sighting
    before_yaml = cfg.read_text(encoding="utf-8")
    assert tw.main(date(2026, 10, 26)) == 0
    report = (tmp_path / "r.md").read_text(encoding="utf-8")
    assert "Palatine" in report and "1:00 to 4:00 PM" in report and "Do not edit hours" in report
    assert cfg.read_text(encoding="utf-8") == before_yaml  # the configured hours are never edited
    assert json.loads((tmp_path / "w.json").read_text())["p-1"]["checked_at"]
