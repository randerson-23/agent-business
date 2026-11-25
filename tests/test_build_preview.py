from datetime import date, datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_digest  # noqa: E402
import build_preview  # noqa: E402


def test_as_of_clock_is_the_evening_before_and_drives_the_delivery(monkeypatch):
    # ROADMAP.md item 553.
    now = build_digest.as_of_clock("2026-11-25")
    assert now == datetime(2026, 11, 25, 2, 0, tzinfo=timezone.utc)  # Tue Nov 24, 8 PM Central
    monkeypatch.setattr(build_digest, "load_delivery_overrides", lambda: {date(2026, 11, 26): datetime(2026, 11, 25, 7, 0)})
    assert build_digest.email_delivery_time(now) == datetime(2026, 11, 25, 7, 0)
    assert build_digest.giving_tuesday_email_line(now) is not None
    assert build_digest.as_of_clock("2026-12-23").astimezone(build_digest.LOCAL_TZ).date() == date(2026, 12, 22)


def test_next_special_delivery_reads_the_overrides():
    overrides = {"2026-11-26": "2026-11-25T07:00", "2026-12-24": "2026-12-23T07:00", "2026-12-31": "2026-12-30T07:00"}
    assert build_preview.next_special_delivery(date(2026, 11, 23), overrides) == date(2026, 11, 25)
    assert build_preview.next_special_delivery(date(2026, 11, 26), overrides) is None  # Dec 23 is 27 days out
    assert build_preview.next_special_delivery(date(2026, 12, 14), overrides) == date(2026, 12, 23)
    assert build_preview.next_special_delivery(date(2026, 12, 24), overrides) == date(2026, 12, 30)


def test_previews_are_noindex_and_only_email_files_are_copied(tmp_path):
    assert build_preview.add_noindex("<html><head><title>x</title>").startswith("<html><head>" + build_preview.NOINDEX)
    once = build_preview.add_noindex("<head></head>")
    assert build_preview.add_noindex(once) == once
    docs = tmp_path / "docs"
    (docs / "email-preview").mkdir(parents=True)
    (docs / "combined-email-preview.html").write_text("a")
    (docs / "email-preview" / "palatine-60067.html").write_text("b")
    (docs / "index.html").write_text("live page")
    names = [n for _, n in build_preview.preview_files(docs)]
    assert names == ["combined-email-preview.html", "email-preview/palatine-60067.html"]


def test_all_specials_skips_past_overrides():
    # ROADMAP.md item 562.
    overrides = {"2026-11-26": "2026-11-25T07:00", "2026-12-24": "2026-12-23T07:00", "2026-12-31": "2026-12-30T07:00"}
    assert build_preview.future_specials(date(2026, 11, 26), overrides) == [date(2026, 12, 23), date(2026, 12, 30)]
    assert build_preview.future_specials(date(2027, 1, 1), overrides) == []


def test_preview_header_names_build_and_delivery_dates():
    html = build_preview.add_preview_header("<html><body><p>x</p></body></html>", date(2026, 11, 25), date(2026, 12, 23))
    assert "Preview built Nov 25; data may change before Wed Dec 23." in html
    assert 'name="preview-built" content="2026-11-25"' in html and html.index("<body>") < html.index("Preview built")


def test_previews_index_lists_each_folder_newest_delivery_first(tmp_path):
    # ROADMAP.md item 564.
    for day, built in (("2026-12-23", "2026-11-25"), ("2026-12-30", "2026-11-25")):
        d = tmp_path / day / "email-preview"
        d.mkdir(parents=True)
        (tmp_path / day / "combined-email-preview.html").write_text(build_preview.add_preview_header("<body></body>", date.fromisoformat(built), date.fromisoformat(day)))
        (d / "palatine-60067.html").write_text("x")
    out = build_preview.write_index(tmp_path).read_text()
    assert out.index("Wed Dec 30, 2026") < out.index("Wed Dec 23, 2026")
    assert build_preview.NOINDEX in out and "built 2026-11-25" in out and "2026-12-23/email-preview/palatine-60067.html" in out
