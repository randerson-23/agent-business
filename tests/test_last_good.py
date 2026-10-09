"""ROADMAP.md item 262: a failed fetch falls back to the source's last good
copy (under 72 hours old), so an alternating source does not empty a town."""

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_digest  # noqa: E402

NOW = datetime(2026, 10, 9, 14, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 9)
REGION_CFG = {
    "region": {"id": "ah-60005", "name": "Arlington Heights", "state": "IL", "timezone": "America/Chicago"},
    "sources": [{"name": "AH Park District — Events", "type": "fake", "section": "Parks", "url": "https://x/parks"}],
}


def item(title, day):
    return {"title": title, "detail": "d", "url": f"https://x/{title}", "date": day.replace("-", "") + "T100000"}


def fetch(tmp_path, result, *, now=NOW, completeness=None, cfg=REGION_CFG):
    with patch.dict(build_digest.FETCHERS, {"fake": lambda *a, **k: result}):
        return build_digest.fetch_region_sections(
            cfg, completeness=completeness, last_good_dir=tmp_path, now=now
        )


def saved(tmp_path):
    return json.loads(next(tmp_path.glob("*.json")).read_text())


def test_a_successful_fetch_writes_the_copy(tmp_path):
    fetch(tmp_path, [item("Pumpkin Splash", "2026-10-18")])
    data = saved(tmp_path)
    assert data["source"] == "AH Park District — Events"
    assert data["fetched_at"] == "2026-10-09T14:00:00+00:00"
    assert [i["title"] for i in data["items"]] == ["Pumpkin Splash"]
    assert next(tmp_path.glob("*.json")).name == "ah-60005__ah-park-district-events.json"


def test_only_upcoming_items_are_kept_soonest_first_and_capped(tmp_path):
    items = [item("Old", "2026-10-01"), item("Later", "2026-10-30"), item("Soon", "2026-10-10"), item("Today", "2026-10-09")]
    kept = build_digest.select_last_good_items(items + [{"title": "News", "url": "u", "date": None}], TODAY)
    assert [i["title"] for i in kept] == ["Today", "Soon", "Later", "News"]
    many = [item(f"E{n}", "2026-11-01") for n in range(200)]
    assert len(build_digest.select_last_good_items(many, TODAY)) == build_digest.LAST_GOOD_MAX_ITEMS


def test_a_failure_under_72_hours_uses_the_copy_and_says_so(tmp_path):
    fetch(tmp_path, [item("Pumpkin Splash", "2026-10-18"), item("Carving Night", "2026-10-21")])
    later = NOW + timedelta(hours=14)
    completeness = {"expected": 0, "reporting": 0}
    blocks = fetch(tmp_path, None, now=later, completeness=completeness)
    assert [e["title"] for e in blocks[0]["events"]] == ["Pumpkin Splash", "Carving Night"]
    assert completeness["reporting"] == 0  # it did not report; it is not counted as if it had
    assert completeness["expected"] == 1
    (used,) = completeness["last_good"]
    assert used["source"] == "ah-60005:AH Park District — Events" and round(used["age_hours"]) == 14
    assert "1 source is shown from its last update, up to 14 hours ago." in build_digest.last_good_sentence(completeness)


def test_past_events_in_the_copy_drop_out_downstream(tmp_path):
    fetch(tmp_path, [item("Tomorrow", "2026-10-10"), item("Next week", "2026-10-17")])
    later = NOW + timedelta(days=2, hours=1)  # the copy is 49 hours old; "Tomorrow" has passed
    blocks = fetch(tmp_path, None, now=later)
    kept = build_digest.filter_past_events(blocks, date(2026, 10, 11))
    assert [e["title"] for e in kept[0]["events"]] == ["Next week"]


def test_a_copy_72_hours_old_or_more_is_not_used(tmp_path):
    fetch(tmp_path, [item("Pumpkin Splash", "2026-10-18")])
    assert fetch(tmp_path, None, now=NOW + timedelta(hours=71, minutes=59))[0]["events"]
    completeness = {"expected": 0, "reporting": 0}
    blocks = fetch(tmp_path, None, now=NOW + timedelta(hours=72), completeness=completeness)
    assert blocks[0]["events"] == []
    assert "last_good" not in completeness


def test_a_source_that_never_succeeded_is_unaffected(tmp_path):
    completeness = {"expected": 0, "reporting": 0}
    blocks = fetch(tmp_path, None, completeness=completeness)
    assert blocks[0]["events"] == [] and "last_good" not in completeness
    assert list(tmp_path.glob("*.json")) == []


def test_an_empty_success_does_not_overwrite_a_useful_copy(tmp_path):
    fetch(tmp_path, [item("Pumpkin Splash", "2026-10-18")])
    fetch(tmp_path, [], now=NOW + timedelta(hours=1))
    assert [i["title"] for i in saved(tmp_path)["items"]] == ["Pumpkin Splash"]


def test_an_unchanged_copy_is_refreshed_only_after_six_hours(tmp_path):
    items = [item("Pumpkin Splash", "2026-10-18")]
    fetch(tmp_path, items)
    fetch(tmp_path, items, now=NOW + timedelta(hours=5))
    assert saved(tmp_path)["fetched_at"] == "2026-10-09T14:00:00+00:00"  # no churn
    fetch(tmp_path, items, now=NOW + timedelta(hours=6))
    assert saved(tmp_path)["fetched_at"] == "2026-10-09T20:00:00+00:00"
    fetch(tmp_path, items + [item("New", "2026-10-19")], now=NOW + timedelta(hours=7))  # changed: rewritten at once
    assert [i["title"] for i in saved(tmp_path)["items"]] == ["Pumpkin Splash", "New"]


def test_a_damaged_copy_counts_as_no_copy(tmp_path):
    (tmp_path / "ah-60005__ah-park-district-events.json").write_text("{not json")
    assert fetch(tmp_path, None)[0]["events"] == []
    (tmp_path / "ah-60005__ah-park-district-events.json").write_text(json.dumps({"fetched_at": "2026-10-09T13:00:00+00:00", "items": "oops"}))
    assert fetch(tmp_path, None)[0]["events"] == []


def test_the_note_is_stated_where_completeness_is(tmp_path):
    completeness = {"expected": 5, "reporting": 4, "last_good": [{"source": "a:b", "age_hours": 14.2}, {"source": "c:d", "age_hours": 3.0}]}
    sentence = build_digest.last_good_sentence(completeness)
    assert sentence == " 2 sources are shown from their last update, up to 14 hours ago."
    assert build_digest.last_good_sentence({"expected": 5, "reporting": 5}) == ""
    assert build_digest.last_good_sentence(None) == ""
    assert sentence.strip() in build_digest.build_feed_xml([], NOW, completeness)
    assert sentence.strip() in build_digest.build_llms_txt([], completeness)
    about = build_digest.render_about_page(NOW, None, source_completeness=completeness)
    assert "2 sources are shown from their last update, up to 14 hours ago." in about


def test_the_build_workflow_commits_the_copies_and_the_directory_exists():
    root = Path(__file__).resolve().parents[1]
    assert "data/source_last_good/" in (root / ".github" / "workflows" / "build-digest.yml").read_text()
    assert (root / "data" / "source_last_good" / ".gitkeep").exists()
    assert build_digest.LAST_GOOD_DIR == root / "data" / "source_last_good"
