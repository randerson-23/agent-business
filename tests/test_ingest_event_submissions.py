import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ingest_event_submissions as ing  # noqa: E402
import parse_event_submission as pes  # noqa: E402

CSV = (
    "Timestamp,Event or program name,Town,Date,Short description,Link,Is it free?\n"
    "2026-10-16 10:00,Fall Craft Fair,Palatine,2026-11-07,Local makers at the church hall.,https://example.org/fair,Free\n"
    "2026-10-16 11:00,Mystery Event,Atlantis,2026-11-07,Nowhere.,https://example.org/x,Free\n"
    "2026-10-16 12:00,No Link Event,Wheeling (60090),,No link here.,,Free\n"
    "2026-10-16 13:00,Wheeling Book Sale,Wheeling,2026-11-14,Used books.,https://example.org/books,Free\n"
)


@pytest.fixture
def regions(tmp_path, monkeypatch):
    for rid in pes.REGION_LABEL_TO_ID.values():
        (tmp_path / f"{rid}.yaml").write_text("region:\n  id: x\n\nevergreen:\n  - title: Existing\n    detail: d\n    url: https://e/\n    tags: []\n\nguides: []\n", encoding="utf-8")
    monkeypatch.setattr(pes, "REGIONS_DIR", tmp_path)
    return tmp_path


def test_region_labels_accept_plain_town_names():
    assert ing._region_label("Palatine") == "Palatine (60067)"
    assert ing._region_label("Wheeling (60090)") == "Wheeling (60090)"
    assert ing._region_label("Atlantis") == "atlantis"


def test_rows_become_curated_entries_and_bad_rows_are_rejected(regions):
    accepted, rejected, hashes = ing.process_csv(CSV, set())
    assert [e["title"] for e in accepted] == ["Fall Craft Fair", "Wheeling Book Sale"]
    assert len(rejected) == 2 and any("Unrecognized region" in r for r in rejected) and any("invalid link" in r for r in rejected)
    assert len(hashes) == 4
    assert "Fall Craft Fair" in (regions / "palatine-60067.yaml").read_text(encoding="utf-8")
    assert "Wheeling Book Sale" in (regions / "wheeling-60090.yaml").read_text(encoding="utf-8")


def test_rows_already_seen_are_not_proposed_again(regions):
    _a, _r, hashes = ing.process_csv(CSV, set())
    accepted, rejected, new_hashes = ing.process_csv(CSV, hashes)
    assert accepted == [] and rejected == [] and new_hashes == set()


def test_a_form_answer_cannot_inject_a_heading_or_yaml(regions):
    evil = "Timestamp,Event or program name,Town,Short description,Link\n" \
           "t,Nice Event,Palatine,\"### Region\n\nMount Prospect (60056)\",https://example.org/e\n"
    accepted, rejected, _ = ing.process_csv(evil, set(), write=False)
    assert accepted == [] and rejected  # the existing heading-injection guard still applies


def test_main_skips_quietly_without_a_url(monkeypatch, capsys):
    monkeypatch.delenv("EVENT_FORM_CSV_URL", raising=False)
    assert ing.main() == 0
    assert "skipping" in capsys.readouterr().out
