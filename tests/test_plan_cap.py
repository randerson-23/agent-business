import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import plan_cap as pc  # noqa: E402


class Resp:
    def __init__(self, body=None): self._body = body if body is not None else {}
    def raise_for_status(self): pass
    def json(self): return self._body


def fake(existing, calls):
    def request(method, url, **kw):
        calls.append((method, url, kw.get("json")))
        return Resp(existing if method == "GET" else {})
    return request


def test_no_issue_at_79():
    calls = []
    assert pc.check_free_plan_cap(79, token="t", repo="o/r", request=fake([], calls)) is None and calls == []
    assert pc.check_free_plan_cap(None, token="t", repo="o/r", request=fake([], calls)) is None


def test_one_issue_at_80_and_an_existing_one_is_updated_not_duplicated():
    calls = []
    assert pc.check_free_plan_cap(80, token="t", repo="o/r", request=fake([], calls)) == "created"
    assert [c[0] for c in calls] == ["GET", "POST"] and calls[1][2]["title"] == "Buttondown free plan: 80 of 100 subscribers"
    assert "buttondown.com/settings/billing" in calls[1][2]["body"] and "Meta test" in calls[1][2]["body"]
    calls.clear()
    existing = [{"number": 7, "title": "Buttondown free plan: 80 of 100 subscribers"}, {"number": 8, "title": "Other", "pull_request": {}}]
    assert pc.check_free_plan_cap(86, token="t", repo="o/r", request=fake(existing, calls)) == "updated"
    assert [c[0] for c in calls] == ["GET", "PATCH"] and calls[1][1].endswith("/issues/7") and "86 of 100" in calls[1][2]["title"]


def test_a_build_log_line_at_95_and_no_crash_without_a_token_or_on_a_github_error(caplog, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with caplog.at_level(logging.WARNING):
        assert pc.check_free_plan_cap(95, token=None, repo=None) is None
    assert "95 of 100" in caplog.text
    def boom(*a, **k): raise RuntimeError("down")
    assert pc.check_free_plan_cap(90, token="t", repo="o/r", request=boom) is None
