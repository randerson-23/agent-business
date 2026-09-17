import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_send_history import latest_delivery, main  # noqa: E402


def _record(*, days_ago: float, mode: str, subject: str = "Subj") -> dict:
    timestamp = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {"timestamp": timestamp, "subject": subject, "buttondown_id": "x", "region": "combined", "mode": mode}


def test_latest_delivery_ignores_drafts():
    # ROADMAP.md item 114: a draft sitting unsent in Buttondown isn't
    # evidence the newsletter went out.
    history = [_record(days_ago=1, mode="draft"), _record(days_ago=10, mode="send")]
    result = latest_delivery(history)
    assert result["mode"] == "send"


def test_latest_delivery_picks_the_most_recent_of_several():
    history = [
        _record(days_ago=20, mode="send"),
        _record(days_ago=2, mode="schedule", subject="Newest"),
        _record(days_ago=9, mode="send"),
    ]
    result = latest_delivery(history)
    assert result["subject"] == "Newest"


def test_latest_delivery_returns_none_when_nothing_qualifies():
    assert latest_delivery([]) is None
    assert latest_delivery([_record(days_ago=1, mode="draft")]) is None


def test_main_fails_when_no_delivery_recorded(monkeypatch, capsys):
    import check_send_history

    monkeypatch.setattr(check_send_history, "load_send_history", lambda: [])
    assert main() == 1


def test_main_fails_when_latest_delivery_is_stale(monkeypatch):
    import check_send_history

    monkeypatch.setattr(
        check_send_history, "load_send_history", lambda: [_record(days_ago=10, mode="schedule")]
    )
    assert main() == 1


def test_main_succeeds_when_latest_delivery_is_recent(monkeypatch):
    import check_send_history

    monkeypatch.setattr(
        check_send_history, "load_send_history", lambda: [_record(days_ago=3, mode="send")]
    )
    assert main() == 0


def test_main_succeeds_right_at_the_boundary(monkeypatch):
    import check_send_history

    monkeypatch.setattr(
        check_send_history,
        "load_send_history",
        lambda: [_record(days_ago=check_send_history.MAX_SEND_GAP_DAYS - 0.01, mode="send")],
    )
    assert main() == 0
