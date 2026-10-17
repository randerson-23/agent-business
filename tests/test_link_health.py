import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import link_health as lh  # noqa: E402


class Resp:
    def __init__(self, code): self.status_code = code
    def close(self): pass


def fake(codes, calls=None):
    def get(method, url, **kw):
        if calls is not None: calls.append((method, url))
        code = codes[url]
        if isinstance(code, Exception): raise code
        return Resp(code[method] if isinstance(code, dict) else code)
    return get


def test_404_needs_two_consecutive_checks():
    first = lh.run([{"url": "https://a/x"}], {}, get=fake({"https://a/x": 404}), sleep=lambda s: None, now="t1")
    assert first["https://a/x"]["strikes"] == 1
    second = lh.run([{"url": "https://a/x"}], first, get=fake({"https://a/x": 410}), sleep=lambda s: None, now="t2")
    assert second["https://a/x"]["strikes"] == 2
    healed = lh.run([{"url": "https://a/x"}], second, get=fake({"https://a/x": 200}), sleep=lambda s: None, now="t3")
    assert healed["https://a/x"]["strikes"] == 0


def test_403_and_timeouts_are_recorded_but_never_a_strike():
    codes = {"https://a/1": {"HEAD": 403, "GET": 403}, "https://a/2": requests.Timeout("slow")}
    health = lh.run([{"url": "https://a/1"}, {"url": "https://a/2"}], {}, get=fake(codes), sleep=lambda s: None, now="t")
    assert health["https://a/1"] == {"status": 403, "strikes": 0, "checked_at": "t"}
    assert health["https://a/2"]["status"] is None and health["https://a/2"]["strikes"] == 0


def test_head_refused_falls_back_to_get():
    calls = []
    health = lh.run([{"url": "https://a/x"}], {}, get=fake({"https://a/x": {"HEAD": 405, "GET": 404}}, calls), sleep=lambda s: None, now="t")
    assert [m for m, _ in calls] == ["HEAD", "GET"] and health["https://a/x"]["status"] == 404


def test_one_request_per_host_per_second():
    now = [0.0]
    slept = []

    def sleep(s):
        slept.append(s); now[0] += s

    codes = {"https://a/1": 200, "https://a/2": 200, "https://b/1": 200}
    lh.run([{"url": u} for u in codes], {}, get=fake(codes), sleep=sleep, clock=lambda: now[0], now="t")
    assert len(slept) == 1 and abs(slept[0] - 1.0) < 1e-9  # only the second request to host a waits
