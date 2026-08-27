import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from parse_event_submission import (  # noqa: E402
    SubmissionError,
    build_evergreen_yaml_block,
    insert_evergreen_entry,
    parse_issue_body,
)

SAMPLE_BODY = """### Region

Mount Prospect (60056)

### Event or program name

Fall Craft Fair

### Short description

Handmade crafts and local vendors at Melas Park. Free admission.

### Link

https://example.org/fall-craft-fair

### Date (optional)

Sept 20, 2026
"""

SAMPLE_BODY_NO_DATE = SAMPLE_BODY.replace("Sept 20, 2026", "_No response_")


def test_parse_issue_body_extracts_all_fields():
    event = parse_issue_body(SAMPLE_BODY)
    assert event == {
        "region_id": "mount-prospect-60056",
        "title": "Fall Craft Fair",
        "detail": "Handmade crafts and local vendors at Melas Park. Free admission.",
        "url": "https://example.org/fall-craft-fair",
        "date": "Sept 20, 2026",
    }


def test_parse_issue_body_treats_no_response_as_none():
    event = parse_issue_body(SAMPLE_BODY_NO_DATE)
    assert event["date"] is None


def test_parse_issue_body_rejects_unrecognized_region():
    body = SAMPLE_BODY.replace("Mount Prospect (60056)", "Chicago (60601)")
    with pytest.raises(SubmissionError, match="Unrecognized region"):
        parse_issue_body(body)


def test_parse_issue_body_rejects_missing_title():
    body = SAMPLE_BODY.replace("Fall Craft Fair", "_No response_")
    with pytest.raises(SubmissionError, match="Missing event title"):
        parse_issue_body(body)


def test_parse_issue_body_rejects_missing_url():
    body = SAMPLE_BODY.replace("https://example.org/fall-craft-fair", "_No response_")
    with pytest.raises(SubmissionError, match="Missing or invalid link"):
        parse_issue_body(body)


def test_parse_issue_body_rejects_non_url_link():
    body = SAMPLE_BODY.replace("https://example.org/fall-craft-fair", "call the village hall")
    with pytest.raises(SubmissionError, match="Missing or invalid link"):
        parse_issue_body(body)


def test_build_evergreen_yaml_block_matches_existing_style():
    block = build_evergreen_yaml_block(
        {"title": "Fall Craft Fair", "detail": "Handmade crafts. Free.", "url": "https://example.org/x"}
    )
    assert block == (
        "  - title: Fall Craft Fair\n"
        "    detail: Handmade crafts. Free.\n"
        "    url: https://example.org/x\n"
    )


def test_build_evergreen_yaml_block_safely_escapes_tricky_text():
    # A colon or quote in submitted text must not break the YAML
    # structure or let it escape into a sibling key - going through
    # yaml.safe_dump (not string interpolation) is what guarantees this.
    block = build_evergreen_yaml_block(
        {"title": 'Say "Hi": A Sale', "detail": "Starts at 5: come early", "url": "https://example.org/x"}
    )
    import yaml

    reparsed = yaml.safe_load("evergreen:\n" + block)
    assert reparsed["evergreen"][0]["title"] == 'Say "Hi": A Sale'
    assert reparsed["evergreen"][0]["detail"] == "Starts at 5: come early"


def test_build_evergreen_yaml_block_omits_tags_and_date():
    block = build_evergreen_yaml_block(
        {"title": "X", "detail": "Y", "url": "https://example.org/x", "date": "Sept 20, 2026"}
    )
    assert "tags" not in block
    assert "date" not in block
    assert "Sept 20" not in block


FIXTURE_FILE = """region:
  id: "test-region"

evergreen:
  - title: "Existing Thing"
    detail: "Already here."
    url: "https://example.org/existing"
    tags: ["free"]

# Seasonal/evergreen guides - explanatory comment.
guides:
  - slug: "fall-guide"
    title: "Fall Guide"
"""

FIXTURE_FILE_NO_TRAILING_SECTION = """region:
  id: "test-region"

evergreen:
  - title: "Existing Thing"
    detail: "Already here."
    url: "https://example.org/existing"
    tags: ["free"]
"""


def test_insert_evergreen_entry_inserts_before_trailing_comment_and_next_key():
    block = "  - title: New Thing\n    detail: New detail.\n    url: https://example.org/new\n"
    result = insert_evergreen_entry(FIXTURE_FILE, block)
    # New entry lands inside evergreen:, before the guides: comment/section.
    evergreen_section, _, rest = result.partition("# Seasonal/evergreen guides")
    assert "Existing Thing" in evergreen_section
    assert "New Thing" in evergreen_section
    assert "guides:" not in evergreen_section
    assert "guides:" in "# Seasonal/evergreen guides" + rest


def test_insert_evergreen_entry_appends_at_eof_when_no_trailing_section():
    block = "  - title: New Thing\n    detail: New detail.\n    url: https://example.org/new\n"
    result = insert_evergreen_entry(FIXTURE_FILE_NO_TRAILING_SECTION, block)
    assert result.rstrip("\n").endswith("url: https://example.org/new")


def test_insert_evergreen_entry_result_is_valid_yaml():
    import yaml

    block = build_evergreen_yaml_block(
        {"title": "New Thing", "detail": "New detail.", "url": "https://example.org/new"}
    )
    result = insert_evergreen_entry(FIXTURE_FILE, block)
    parsed = yaml.safe_load(result)
    titles = [e["title"] for e in parsed["evergreen"]]
    assert titles == ["Existing Thing", "New Thing"]
    assert parsed["guides"][0]["slug"] == "fall-guide"


def test_insert_evergreen_entry_raises_without_evergreen_key():
    with pytest.raises(SubmissionError, match="no top-level `evergreen:` key"):
        insert_evergreen_entry("region:\n  id: x\n", "  - title: New Thing\n")
