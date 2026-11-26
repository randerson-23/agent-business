import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_send_history  # noqa: E402
import send_newsletter  # noqa: E402
import unschedule_email  # noqa: E402


class Resp:
    def __init__(self, data, ok=True, status=200):
        self._data, self.ok, self.status_code, self.text = data, ok, status, str(data)

    def json(self):
        return self._data

    def raise_for_status(self):
        if not self.ok:
            import requests
            raise requests.HTTPError(str(self.status_code))


def test_unschedule_takes_a_scheduled_email_back_to_draft_and_refuses_a_sent_one():
    # ROADMAP.md item 571.
    state = {"status": "scheduled"}
    calls = []

    def get(url, **kw):
        return Resp(dict(state, id="em_1"))

    def patch(url, json=None, **kw):
        calls.append(json)
        state["status"] = json["status"]
        return Resp(dict(state))
    out = unschedule_email.unschedule("em_1", "k", get=get, patch=patch)
    assert out["status"] == "draft" and calls == [{"status": "draft", "publish_date": None}]
    sent = lambda url, **kw: Resp({"status": "sent"})
    try:
        unschedule_email.unschedule("em_2", "k", get=sent, patch=patch)
        raise AssertionError("a sent email must be refused")
    except unschedule_email.UnscheduleError as exc:
        assert "can't be taken back" in str(exc)
    history = [{"buttondown_id": "em_1", "mode": "schedule", "timestamp": "2026-11-26T04:22:43+00:00"}]
    assert unschedule_email.mark_cancelled(history, "em_1", datetime(2026, 11, 26, 6, tzinfo=timezone.utc))
    assert send_newsletter.recent_delivery(history, datetime(2026, 11, 27, tzinfo=timezone.utc)) is None


def test_the_repeat_guard_asks_buttondown():
    # ROADMAP.md item 572.
    delivery = datetime(2026, 11, 26, 13, 0, tzinfo=timezone.utc)
    scheduled = {"results": [{"id": "em_x", "subject": "Thanksgiving", "status": "scheduled", "publish_date": "2026-11-25T13:00:00Z"}]}
    get = lambda url, params=None, **kw: Resp(scheduled if params["status"] == "scheduled" else {"results": []})
    assert send_newsletter.buttondown_conflict("k", delivery, get=get)["id"] == "em_x"
    empty = lambda url, params=None, **kw: Resp({"results": []})
    assert send_newsletter.buttondown_conflict("k", delivery, get=empty) is None
    far = {"results": [{"id": "em_y", "status": "scheduled", "publish_date": "2026-12-03T13:00:00Z"}]}
    assert send_newsletter.buttondown_conflict("k", delivery, get=lambda url, params=None, **kw: Resp(far if params["status"] == "scheduled" else {"results": []})) is None
    import requests
    try:
        send_newsletter.buttondown_conflict("k", delivery, get=lambda url, **kw: Resp({}, ok=False, status=500))
        raise AssertionError("an API error must surface so the caller falls back to history")
    except requests.RequestException:
        pass


def test_duplicate_deliveries_fail_the_watchdog_until_cancelled():
    # ROADMAP.md item 573.
    history = [{"timestamp": "2026-11-25T05:06:59+00:00", "mode": "schedule", "buttondown_id": "em_a", "subject": "T"},
               {"timestamp": "2026-11-26T04:22:43+00:00", "mode": "schedule", "buttondown_id": "em_b", "subject": "T"}]
    now = datetime(2026, 11, 26, 9, tzinfo=timezone.utc)
    pairs = check_send_history.find_duplicate_deliveries(history, now=now)
    assert [(a["buttondown_id"], b["buttondown_id"]) for a, b in pairs] == [("em_a", "em_b")]
    assert check_send_history.find_duplicate_deliveries([history[0], dict(history[1], cancelled="2026-11-26T06:00:00+00:00")], now=now) == []
    assert check_send_history.find_duplicate_deliveries(history, now=now + timedelta(days=5)) == []  # an old pair stops alarming
