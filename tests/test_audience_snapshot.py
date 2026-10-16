import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import audience_snapshot as snap  # noqa: E402


def test_summarize_hits_counts_outbound_per_publisher_and_sponsor_clicks():
    out = snap.summarize_hits([
        {"path": "/out/www.ahml.info", "count": 40, "event": True},
        {"path": "out/www.ahml.info", "count": 5},
        {"path": "/out/mppl.org", "count": 12},
        {"path": "/sponsor-click-mount-prospect-60056", "count": 3},
        {"path": "/sponsor-click-palatine-60067", "count": 2},
        {"path": "/", "count": 900},
    ])
    assert out == {"outbound": {"www.ahml.info": 45, "mppl.org": 12}, "sponsor_clicks": 5}


def test_ai_referrals_match_known_assistants_only():
    refs = [{"name": "https://chatgpt.com/", "count": 4}, {"name": "perplexity.ai", "count": 2}, {"name": "google.com", "count": 500}]
    assert snap.count_ai_referrals(refs) == 6


def test_latest_subscriber_count_prefers_measured_recipients(tmp_path):
    path = tmp_path / "h.json"
    path.write_text(json.dumps([
        {"pre_send_subscriber_count": 1, "metrics": {"recipients": 1}},
        {"pre_send_subscriber_count": 7},
    ]), encoding="utf-8")
    assert snap.latest_subscriber_count(path) == 7
    assert snap.latest_subscriber_count(tmp_path / "missing.json") is None


def test_build_snapshot_uses_the_api_and_never_stores_personal_data():
    calls = []

    def fake_api(code, token, path, params):
        calls.append(path)
        if path == "stats/total":
            return {"total": 100 if "2026-10-26" in params["start"] else 400}
        if path == "stats/toprefs":
            return {"stats": [{"name": "chatgpt.com", "count": 3}, {"name": "google.com", "count": 50}]}
        return {"hits": [{"path": "/out/ahpd.org", "count": 9}]}

    result = snap.build_snapshot("withinten", "tok", date(2026, 11, 2), api=fake_api)
    assert result["visits_7d"] == 100 and result["visits_30d"] == 400
    assert result["ai_referrals_30d"] == 3 and result["outbound_30d"] == {"ahpd.org": 9}
    assert [r["name"] for r in result["top_referrers"]] == ["chatgpt.com", "google.com"]
    assert "tok" not in json.dumps(result)
    assert calls == ["stats/total", "stats/total", "stats/toprefs", "stats/hits"]


def test_main_skips_quietly_without_a_token(monkeypatch, tmp_path):
    monkeypatch.delenv("GOATCOUNTER_TOKEN", raising=False)
    monkeypatch.setattr(snap, "AUDIENCE_PATH", tmp_path / "audience.json")
    assert snap.main() == 0 and not (tmp_path / "audience.json").exists()
