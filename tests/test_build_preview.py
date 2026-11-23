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
