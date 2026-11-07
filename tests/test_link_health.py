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
    first = lh.run([{"url": "https://a.org/x"}], {}, get=fake({"https://a.org/x": 404}), sleep=lambda s: None, now="t1")
    assert first["https://a.org/x"]["strikes"] == 1
    second = lh.run([{"url": "https://a.org/x"}], first, get=fake({"https://a.org/x": 410}), sleep=lambda s: None, now="t2")
    assert second["https://a.org/x"]["strikes"] == 2
    healed = lh.run([{"url": "https://a.org/x"}], second, get=fake({"https://a.org/x": 200}), sleep=lambda s: None, now="t3")
    assert healed["https://a.org/x"]["strikes"] == 0


def test_403_and_timeouts_are_recorded_but_never_a_strike():
    codes = {"https://a.org/1": {"HEAD": 403, "GET": 403}, "https://a.org/2": requests.Timeout("slow")}
    health = lh.run([{"url": "https://a.org/1"}, {"url": "https://a.org/2"}], {}, get=fake(codes), sleep=lambda s: None, now="t")
    assert health["https://a.org/1"] == {"status": 403, "strikes": 0, "checked_at": "t"}
    assert health["https://a.org/2"]["status"] is None and health["https://a.org/2"]["strikes"] == 0


def test_head_refused_falls_back_to_get():
    calls = []
    health = lh.run([{"url": "https://a.org/x"}], {}, get=fake({"https://a.org/x": {"HEAD": 405, "GET": 404}}, calls), sleep=lambda s: None, now="t")
    assert [m for m, _ in calls] == ["HEAD", "GET"] and health["https://a.org/x"]["status"] == 404


def test_one_request_per_host_per_second():
    now = [0.0]
    slept = []

    def sleep(s):
        slept.append(s); now[0] += s

    codes = {"https://a.org/1": 200, "https://a.org/2": 200, "https://b.org/1": 200}
    lh.run([{"url": u} for u in codes], {}, get=fake(codes), sleep=sleep, clock=lambda: now[0], now="t")
    assert len(slept) == 1 and abs(slept[0] - 1.0) < 1e-9  # only the second request to host a waits


def test_only_public_http_urls_are_requested():
    ok = ["https://example.org/a", "http://www.mountprospect.org/x?y=1"]
    bad = ["javascript:alert(1)", "file:///etc/passwd", "ftp://example.org/", "http://localhost/admin", "http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/",
           "http://10.0.0.5/", "http://192.168.1.1/", "http://[::1]/", "http://printer.local/", "http://db.internal/", "https:///nohost", "http://intranet/"]
    assert all(lh.is_public_http_url(u) for u in ok) and not any(lh.is_public_http_url(u) for u in bad)
    calls = []

    def fake(method, url, **kw):
        calls.append(url)
        return Resp(200)

    health = lh.run([{"url": u} for u in ok + bad], {}, get=fake, sleep=lambda s: None, now="t")
    assert sorted(calls) == sorted(ok) and set(health) == set(ok)


def test_calendar_audit_counts_dated_entries_without_google_and_midnight_links(tmp_path):
    # ROADMAP.md items 462/464.
    import link_health
    page = tmp_path / "x" / "index.html"
    page.parent.mkdir()
    page.write_text(
        '<ul><li><time datetime="2026-11-07">Sat</time> <a href="https://a">A</a></li>'
        '<li><time datetime="2026-11-07T10:00:00">Sat</time> <a href="https://calendar.google.com/calendar/render?action=TEMPLATE&dates=20261107T100000/20261107T110000">G</a></li>'
        '<li>No date here</li></ul>'
        '<article><time>Sun</time><a href="https://calendar.google.com/calendar/render?action=TEMPLATE&dates=20261108T000000/20261108T010000">G</a></article>',
        encoding="utf-8",
    )
    (tmp_path / "issues" / "2026-10-29").mkdir(parents=True)
    (tmp_path / "issues" / "2026-10-29" / "index.html").write_text("<li><time>x</time></li>", encoding="utf-8")  # frozen archive: skipped
    assert link_health.calendar_link_audit(tmp_path) == {"missing": 1, "midnight": 1}
