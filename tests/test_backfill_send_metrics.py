import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backfill_send_metrics import (  # noqa: E402
    METRICS_BACKFILL_MIN_AGE,
    derive_metrics,
    fetch_email_analytics,
    load_send_history,
    main,
    needs_backfill,
    save_send_history,
)

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def _entry(**overrides):
    base = {
        "timestamp": (NOW - timedelta(days=5)).isoformat(),
        "subject": "This weekend across Arlington Heights and Mount Prospect",
        "buttondown_id": "em_abc123",
        "region": "combined",
        "mode": "send",
    }
    base.update(overrides)
    return base


def test_needs_backfill_true_for_an_old_unmetered_send():
    assert needs_backfill(_entry(), NOW) is True


def test_needs_backfill_false_when_too_recent():
    entry = _entry(timestamp=(NOW - timedelta(hours=1)).isoformat())
    assert needs_backfill(entry, NOW) is False


def test_needs_backfill_false_when_metrics_already_recorded():
    entry = _entry(metrics={"recipients": 1, "opens": 1, "clicks": 0})
    assert needs_backfill(entry, NOW) is False


def test_needs_backfill_false_without_a_buttondown_id():
    # A draft never sent, or a send whose POST somehow returned no id -
    # nothing to ask Buttondown about.
    entry = _entry(buttondown_id="")
    assert needs_backfill(entry, NOW) is False


def test_needs_backfill_false_at_exactly_the_minimum_age_boundary_minus_one_second():
    entry = _entry(timestamp=(NOW - METRICS_BACKFILL_MIN_AGE + timedelta(seconds=1)).isoformat())
    assert needs_backfill(entry, NOW) is False


def test_needs_backfill_true_at_exactly_the_minimum_age():
    entry = _entry(timestamp=(NOW - METRICS_BACKFILL_MIN_AGE).isoformat())
    assert needs_backfill(entry, NOW) is True


def test_derive_metrics_computes_open_and_click_rate():
    metrics = derive_metrics({"recipients": 100, "opens": 45, "clicks": 6})
    assert metrics == {"recipients": 100, "opens": 45, "clicks": 6, "open_rate": 0.45, "click_rate": 0.06}


def test_derive_metrics_omits_rates_when_recipients_is_zero():
    # Division by zero, and a rate over zero recipients is meaningless
    # anyway - not the same as a genuine 0% rate over a real audience.
    metrics = derive_metrics({"recipients": 0, "opens": 0, "clicks": 0})
    assert metrics == {"recipients": 0, "opens": 0, "clicks": 0}
    assert "open_rate" not in metrics


def test_derive_metrics_treats_missing_fields_as_zero_not_a_crash():
    # ROADMAP.md item 187: Buttondown's own docs say a request with
    # tracking disabled still succeeds but returns no data - this must
    # read as zeroes, not raise.
    metrics = derive_metrics({})
    assert metrics == {"recipients": 0, "opens": 0, "clicks": 0}


class _FakeAnalyticsResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._payload


def test_fetch_email_analytics_sends_the_documented_endpoint_and_auth(monkeypatch):
    import backfill_send_metrics

    seen = {}

    def fake_get(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return _FakeAnalyticsResponse({"recipients": 10, "opens": 5, "clicks": 1})

    monkeypatch.setattr(backfill_send_metrics.requests, "get", fake_get)
    result = fetch_email_analytics("em_abc123", "secret-key")
    assert seen["url"] == "https://api.buttondown.com/v1/emails/em_abc123/analytics"
    assert seen["headers"]["Authorization"] == "Token secret-key"
    assert result == {"recipients": 10, "opens": 5, "clicks": 1}


def test_fetch_email_analytics_raises_on_a_non_2xx_status(monkeypatch):
    import backfill_send_metrics

    monkeypatch.setattr(
        backfill_send_metrics.requests, "get",
        lambda url, **kwargs: _FakeAnalyticsResponse({}, status_code=404),
    )
    with pytest.raises(requests.HTTPError):
        fetch_email_analytics("em_missing", "secret-key")


def test_save_and_load_send_history_round_trip(tmp_path):
    path = tmp_path / "send_history.json"
    history = [_entry()]
    save_send_history(history, path=path)
    assert load_send_history(path=path) == history


def test_load_send_history_returns_empty_list_when_missing(tmp_path):
    assert load_send_history(path=tmp_path / "missing.json") == []


def test_main_returns_1_when_api_key_missing(monkeypatch, tmp_path):
    import backfill_send_metrics

    monkeypatch.delenv(backfill_send_metrics.API_KEY_ENV, raising=False)
    monkeypatch.setattr(backfill_send_metrics, "SEND_HISTORY_PATH", tmp_path / "send_history.json")
    assert main() == 1


def test_main_backfills_an_eligible_entry_and_persists_it(monkeypatch, tmp_path):
    import backfill_send_metrics

    history_path = tmp_path / "send_history.json"
    save_send_history([_entry()], path=history_path)
    monkeypatch.setattr(backfill_send_metrics, "SEND_HISTORY_PATH", history_path)
    monkeypatch.setenv(backfill_send_metrics.API_KEY_ENV, "secret-key")
    monkeypatch.setattr(
        backfill_send_metrics.requests, "get",
        lambda url, **kwargs: _FakeAnalyticsResponse({"recipients": 10, "opens": 5, "clicks": 1}),
    )

    assert main() == 0

    updated = load_send_history(path=history_path)
    assert updated[0]["metrics"] == {
        "recipients": 10, "opens": 5, "clicks": 1, "open_rate": 0.5, "click_rate": 0.1,
    }


def test_main_leaves_a_recent_send_unmetered(monkeypatch, tmp_path):
    # ROADMAP.md item 187: reading metrics too early would permanently
    # record a zero, since a given entry is only ever backfilled once.
    import backfill_send_metrics

    history_path = tmp_path / "send_history.json"
    recent = _entry(timestamp=datetime.now(timezone.utc).isoformat())
    save_send_history([recent], path=history_path)
    monkeypatch.setattr(backfill_send_metrics, "SEND_HISTORY_PATH", history_path)
    monkeypatch.setenv(backfill_send_metrics.API_KEY_ENV, "secret-key")

    def fail_if_called(url, **kwargs):
        raise AssertionError("should not fetch analytics for a too-recent send")

    monkeypatch.setattr(backfill_send_metrics.requests, "get", fail_if_called)

    assert main() == 0
    assert "metrics" not in load_send_history(path=history_path)[0]


def test_main_does_not_fail_the_job_when_one_fetch_errors(monkeypatch, tmp_path):
    # ROADMAP.md item 187: non-fatal by design - one send's metrics
    # failing to fetch must not block backfilling the others or fail
    # this job the way a real send failure would.
    import backfill_send_metrics

    history_path = tmp_path / "send_history.json"
    save_send_history([_entry(buttondown_id="em_broken")], path=history_path)
    monkeypatch.setattr(backfill_send_metrics, "SEND_HISTORY_PATH", history_path)
    monkeypatch.setenv(backfill_send_metrics.API_KEY_ENV, "secret-key")
    monkeypatch.setattr(
        backfill_send_metrics.requests, "get",
        lambda url, **kwargs: (_ for _ in ()).throw(requests.ConnectionError("boom")),
    )

    assert main() == 0
    assert "metrics" not in load_send_history(path=history_path)[0]
