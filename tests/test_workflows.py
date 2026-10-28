"""ROADMAP.md items 406 and 407: the workflow watchdog's decision, and no workflow
installing a named package instead of requirements.txt."""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import workflow_watchdog as ww  # noqa: E402


def run(conclusion, day, status="completed"):
    return {"status": status, "conclusion": conclusion, "created_at": f"2026-10-{day:02d}T05:00:00Z", "id": day}


def test_two_consecutive_failures_are_flagged_and_one_is_not():
    assert ww.failing_since([run("failure", 28), run("failure", 27), run("success", 26)]) == "2026-10-27"
    assert ww.failing_since([run("failure", 28), run("failure", 27), run("failure", 26), run("success", 25)]) == "2026-10-26"
    assert ww.failing_since([run("failure", 28), run("success", 27)]) is None
    assert ww.failing_since([run("success", 28), run("failure", 27), run("failure", 26)]) is None
    assert ww.failing_since([run("failure", 28)]) is None
    assert ww.failing_since([run(None, 29, "in_progress"), run("failure", 28), run("failure", 27)]) == "2026-10-27"


def test_decide_opens_once_and_closes_when_a_run_succeeds():
    flows = {"OSM prospects": [run("failure", 28), run("failure", 27)], "Tests": [run("success", 28), run("failure", 27)]}
    plan = ww.decide(flows, [])
    assert plan == {"open": [("OSM prospects", "2026-10-27")], "close": []}
    open_issues = [{"number": 7, "title": "Workflow failing: OSM prospects (since 2026-10-27)"}, {"number": 8, "title": "Workflow failing: Tests (since 2026-10-20)"}, {"number": 9, "title": "Something else"}]
    plan2 = ww.decide(flows, open_issues)
    assert plan2["close"] == [8] and plan2["open"] == [("OSM prospects", "2026-10-27")]


def test_no_workflow_installs_a_named_package_except_pytest():
    # Item 407: dependencies come from requirements.txt, so a new import cannot
    # fail one workflow only (item 405).
    bad = []
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in (data.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                for line in str(step.get("run") or "").splitlines():
                    m = re.search(r"pip install (.+)", line)
                    if m and not re.fullmatch(r"-r requirements\.txt|pytest", m.group(1).strip()):
                        bad.append(f"{path.name}: {line.strip()}")
    assert not bad, bad
