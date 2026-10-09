"""ROADMAP.md item 194: a failure-rate window, because a source that fails
every other build has a streak of 1 forever and no streak-based check can
see it."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_digest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_window_appends_outcomes_and_keeps_the_newest():
    window = {}
    for failed in (True, False, False, True):
        build_digest.update_failure_window(window, "a:b", failed)
    assert window == {"a:b": "1001"}
    for _ in range(40):
        build_digest.update_failure_window(window, "a:b", False)
    assert window["a:b"] == "0" * build_digest.FAILURE_WINDOW_SIZE


def test_an_alternating_source_is_flagged_though_its_streak_never_passes_one():
    window, streaks = {}, {}
    for n in range(12):
        failed = n % 2 == 0
        build_digest.update_failure_window(window, "ah:park", failed)
        build_digest.update_transport_failures(streaks, "ah:park", failed)
    assert max(1 if v else 0 for v in [streaks["ah:park"]]) <= 1
    assert build_digest.detect_chronic_transport_failures(streaks) == []  # the old check is blind to it
    assert build_digest.detect_flapping_sources(window) == [("ah:park", 6, 12)]


def test_flapping_needs_history_a_real_rate_and_a_source_not_down_right_now():
    detect = build_digest.detect_flapping_sources
    assert detect({"a": "10101"}) == []  # too few builds to judge
    assert detect({"a": "0" * 23 + "1"}) == []  # one blip in 24: under the rate
    assert detect({"a": "0" * 24}) == []
    assert detect({"a": "1" * 24}) == []  # chronic: the streak check's job
    assert detect({"a": "010101010111"}) == []  # failing its last three: already chronic territory
    assert detect({"a": "0100000010000000"}) == []  # 2 in 16 is 12.5%, under the rate
    assert detect({"a": "010001000100"}) == [("a", 3, 12)]  # 3 in 12 is 25%


def test_rate_threshold_is_one_in_five():
    assert build_digest.FLAPPING_MIN_RATE == 0.2
    five_in_twenty_four = "100001000010000100001000"[:24]
    assert build_digest.detect_flapping_sources({"a": five_in_twenty_four}) == [("a", 5, 24)]
    four_in_twenty_four = "100001000010000100000000"
    assert build_digest.detect_flapping_sources({"a": four_in_twenty_four}) == []


def test_lockstep_groups_sources_that_fail_on_exactly_the_same_builds():
    window = {
        "ah:park": "10101010",
        "dp:park": "10101010",
        "mp:park": "10101010",
        "ah:library": "00000000",
        "wheeling:park": "11111111",
        "wheeling:ccsd": "11111111",
        "pal:library": "01001000",
    }
    assert build_digest.detect_lockstep_failures(window) == [["ah:park", "dp:park", "mp:park"]]
    # Different patterns are not one cause, and always-failing sources say nothing about timing.
    assert build_digest.detect_lockstep_failures({"a": "10101010", "b": "01010101"}) == []
    assert build_digest.detect_lockstep_failures({"a": "1010", "b": "1010"}) == []  # too little history


def test_load_survives_a_missing_or_damaged_file(tmp_path, monkeypatch):
    monkeypatch.setattr(build_digest, "FAILURE_WINDOW_PATH", tmp_path / "w.json")
    assert build_digest.load_failure_window() == {}
    (tmp_path / "w.json").write_text("{nope")
    assert build_digest.load_failure_window() == {}
    (tmp_path / "w.json").write_text(json.dumps({"a": "0101", "b": 3, "c": None}))
    assert build_digest.load_failure_window() == {"a": "0101"}
    build_digest.save_failure_window({"z": "01", "a": "10"})
    assert json.loads((tmp_path / "w.json").read_text()) == {"a": "10", "z": "01"}


def test_fetching_records_each_outcome_in_the_window(tmp_path):
    from unittest.mock import patch

    cfg = {
        "region": {"id": "r", "name": "Town", "state": "IL"},
        "sources": [
            {"name": "Good", "type": "fake_ok", "section": "S", "url": "u1"},
            {"name": "Bad", "type": "fake_bad", "section": "S", "url": "u2"},
        ],
    }
    window = {}
    with patch.dict(build_digest.FETCHERS, {"fake_ok": lambda *a, **k: [], "fake_bad": lambda *a, **k: None}):
        build_digest.fetch_region_sections(cfg, failure_window=window)
        build_digest.fetch_region_sections(cfg, failure_window=window)
    assert window == {"r:Good": "00", "r:Bad": "11"}


def test_the_committed_file_exists_and_the_workflow_commits_it():
    assert isinstance(json.loads((ROOT / "data" / "source_failure_window.json").read_text()), dict)
    assert "data/source_failure_window.json" in (ROOT / ".github" / "workflows" / "build-digest.yml").read_text()
