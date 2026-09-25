import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_build_freshness  # noqa: E402


def _write_signal(path: Path, *, hours_ago: float | None) -> None:
    if hours_ago is None:
        path.write_text("not json", encoding="utf-8")
        return
    generated_at = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    path.write_text(json.dumps({"generated_at": generated_at, "total": 5}), encoding="utf-8")


def test_main_fails_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(check_build_freshness, "WEEKEND_SIGNAL_PATH", tmp_path / "missing.json")
    assert check_build_freshness.main() == 1


def test_main_fails_when_file_is_unparseable(tmp_path, monkeypatch):
    path = tmp_path / "weekend_signal.json"
    _write_signal(path, hours_ago=None)
    monkeypatch.setattr(check_build_freshness, "WEEKEND_SIGNAL_PATH", path)
    assert check_build_freshness.main() == 1


def test_main_fails_when_generated_at_is_missing(tmp_path, monkeypatch):
    path = tmp_path / "weekend_signal.json"
    path.write_text(json.dumps({"total": 5}), encoding="utf-8")
    monkeypatch.setattr(check_build_freshness, "WEEKEND_SIGNAL_PATH", path)
    assert check_build_freshness.main() == 1


def test_main_fails_when_build_is_stale(tmp_path, monkeypatch):
    path = tmp_path / "weekend_signal.json"
    _write_signal(path, hours_ago=check_build_freshness.MAX_BUILD_GAP_HOURS + 1)
    monkeypatch.setattr(check_build_freshness, "WEEKEND_SIGNAL_PATH", path)
    assert check_build_freshness.main() == 1


def test_main_succeeds_when_build_is_recent(tmp_path, monkeypatch):
    path = tmp_path / "weekend_signal.json"
    _write_signal(path, hours_ago=2)
    monkeypatch.setattr(check_build_freshness, "WEEKEND_SIGNAL_PATH", path)
    assert check_build_freshness.main() == 0


def test_main_succeeds_right_at_the_boundary(tmp_path, monkeypatch):
    path = tmp_path / "weekend_signal.json"
    _write_signal(path, hours_ago=check_build_freshness.MAX_BUILD_GAP_HOURS - 0.01)
    monkeypatch.setattr(check_build_freshness, "WEEKEND_SIGNAL_PATH", path)
    assert check_build_freshness.main() == 0
