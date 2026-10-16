import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import search_console_snapshot as gsc  # noqa: E402


def test_shape_rows_keeps_aggregates_only():
    rows = gsc.shape_rows([{"keys": ["trick or treat hours mount prospect"], "clicks": 3, "impressions": 120, "ctr": 0.025, "position": 7.123}])
    assert rows == [{"key": "trick or treat hours mount prospect", "clicks": 3, "impressions": 120, "ctr": 0.025, "position": 7.1}]


def test_build_snapshot_falls_back_to_the_url_prefix_property_and_uses_a_28_day_window():
    seen = []

    def fake_query(token, site, body):
        seen.append((site, body["dimensions"][0], body["startDate"], body["endDate"]))
        if site.startswith("sc-domain:"):
            raise RuntimeError("403 not a user of this property")
        return [{"keys": [f"k-{body['dimensions'][0]}"], "clicks": 1, "impressions": 10, "ctr": 0.1, "position": 3.0}]

    snap = gsc.build_snapshot("tok", date(2026, 11, 2), query=fake_query)
    assert snap["property"] == "https://withintenmiles.com/"
    assert (snap["start"], snap["end"]) == ("2026-10-04", "2026-10-31")  # ends two days back, 28 days inclusive
    assert snap["queries"][0]["key"] == "k-query" and snap["pages"][0]["key"] == "k-page"
    assert "tok" not in str(snap)


def test_build_snapshot_raises_when_no_property_answers():
    def always_fail(token, site, body):
        raise RuntimeError("nope")

    try:
        gsc.build_snapshot("tok", date(2026, 11, 2), query=always_fail)
    except RuntimeError as exc:
        assert "no Search Console property answered" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_main_skips_quietly_without_the_secret(monkeypatch, tmp_path):
    monkeypatch.delenv("GSC_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setattr(gsc, "SNAPSHOT_PATH", tmp_path / "search_console.json")
    assert gsc.main() == 0 and not (tmp_path / "search_console.json").exists()
