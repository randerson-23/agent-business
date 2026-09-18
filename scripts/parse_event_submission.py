#!/usr/bin/env python3
"""Turn a community event submission (see
.github/ISSUE_TEMPLATE/event-submission.yml) into a new evergreen entry in
the right region's config/regions/*.yaml file.

Run by .github/workflows/event-submission.yml when an Issue Form
submission is opened: the workflow reads the rendered issue body, this
script parses it and writes the region file, then a separate workflow
step opens a PR for a human to review - nothing here merges anything, or
is allowed to; a public-facing submission form is spam/abuse-prone, so a
person always reviews before it goes live (see ROADMAP.md Phase 11 #13).

Two things kept deliberately separate and independently testable:
  - parse_issue_body(): pure text parsing of the rendered Issue Form body
  - insert_evergreen_entry(): pure text surgery on a region file's
    contents

insert_evergreen_entry() is a targeted splice, not a yaml.safe_load +
yaml.safe_dump round trip - config/regions/*.yaml files carry extensive
human-written comments a round trip would silently discard. The
submitted text itself still goes through yaml.safe_dump (never
hand-spliced as a raw string), so a title/detail/url containing a quote,
colon, or newline can't corrupt the file or escape into a different key.
"""
from __future__ import annotations

import os
import re
import secrets
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGIONS_DIR = ROOT / "config" / "regions"

# Issue Form dropdown label -> region id + config filename. Kept as an
# explicit mapping (not inferred from config/regions/*.yaml at parse time)
# since the dropdown's options are static text baked into the .yml form -
# add a region here whenever a new one is added to config/regions/.
REGION_LABEL_TO_ID = {
    "Mount Prospect (60056)": "mount-prospect-60056",
    "Arlington Heights (60005)": "arlington-heights-60005",
    "Des Plaines (60016)": "des-plaines-60016",
    "Palatine (60067)": "palatine-60067",
}

_FIELD_LABELS = {
    "region": "Region",
    "title": "Event or program name",
    "detail": "Short description",
    "url": "Link",
    "date": "Date (optional)",
}


class SubmissionError(ValueError):
    """A submission is missing a required field, names an unknown region,
    or otherwise can't safely become a curated entry - raised so the
    workflow can post a clear comment back on the issue instead of the
    job just failing with a traceback.
    """


def _extract_field(body: str, label: str) -> str | None:
    """Pull the value under a `### <label>` heading from a rendered Issue
    Form body. Returns None for an unanswered optional field (GitHub
    renders these as the literal text `_No response_`) or a missing
    section.
    """
    pattern = re.compile(
        r"^###\s+" + re.escape(label) + r"\s*\n+(.*?)(?=\n###\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(body)
    if not match:
        return None
    value = match.group(1).strip()
    if not value or value == "_No response_":
        return None
    return value


def _assert_no_injected_headings(body: str) -> None:
    """Guard against a field-boundary injection: GitHub always renders
    exactly one `### <Label>` heading per form field (even an unanswered
    optional one, as `_No response_`), so a real submission has exactly
    `len(_FIELD_LABELS)` of them. `title`/`url`/`date` are single-line
    `input` fields and can't contain a newline at all, but `detail` is a
    multi-line `textarea` - a submitter can type a line starting with
    "### " into it, and `_extract_field()` searches for a label's heading
    from the *start* of the body, so an earlier, attacker-controlled fake
    "### Link" (or "### Date (optional)") embedded inside their own
    `detail` answer would be found instead of the real one that GitHub
    renders later in the body - silently substituting a URL (or a date)
    the submitter typed somewhere a human reviewer glancing at the
    rendered issue wouldn't necessarily connect to the field it actually
    populated (markdown renders a heading typed inside a textarea
    identically to a real one). A miscount here is that attack's one
    unavoidable side effect, so reject rather than parse ambiguously -
    the human-review gate this whole file depends on only works if what
    it shows a reviewer is what actually gets written.
    """
    actual = len(re.findall(r"^###\s+", body, re.MULTILINE))
    expected = len(_FIELD_LABELS)
    if actual != expected:
        raise SubmissionError(
            f"Expected {expected} form-field headings in the issue body, found {actual} - "
            "a field's answer may contain a line starting with '###', which this parser "
            "can't safely tell apart from a real field boundary. Remove any line starting "
            "with '###' from your answers and resubmit."
        )


def parse_issue_body(body: str) -> dict:
    """Parse a rendered event-submission Issue Form body into
    {"region_id", "title", "detail", "url", "date"} ("date" is informational
    only - see build_evergreen_yaml_block's docstring for why it isn't
    written into the region file). Raises SubmissionError on anything
    that can't safely become a curated entry.
    """
    _assert_no_injected_headings(body)

    region_label = _extract_field(body, _FIELD_LABELS["region"])
    region_id = REGION_LABEL_TO_ID.get(region_label or "")
    if not region_id:
        raise SubmissionError(f"Unrecognized region: {region_label!r}")

    title = _extract_field(body, _FIELD_LABELS["title"])
    if not title:
        raise SubmissionError("Missing event title")

    detail = _extract_field(body, _FIELD_LABELS["detail"]) or ""

    url = _extract_field(body, _FIELD_LABELS["url"])
    if not url or not re.match(r"^https?://\S+$", url):
        raise SubmissionError(f"Missing or invalid link: {url!r}")

    date = _extract_field(body, _FIELD_LABELS["date"])

    return {"region_id": region_id, "title": title, "detail": detail, "url": url, "date": date}


def build_evergreen_yaml_block(event: dict) -> str:
    """Render one evergreen list item as YAML text, matching the existing
    hand-written style in config/regions/*.yaml (2-space list indent).

    `tags` is deliberately omitted: prepare_evergreen() in build_digest.py
    already infers tags at build time from title+detail when a curated
    entry doesn't set them explicitly, so a submitted entry gets the same
    auto-tagging a fetched event would - no new code needed there.

    The submitter's optional "date" isn't written here either: evergreen
    entries have no date field in this schema (they're framed as ongoing/
    curated resources, not one-time dated events - see
    ROADMAP.md Phase 11 #4's note that only fetched RSS/ICS/HTML sources
    carry `date`). A submitted date is surfaced in the PR description
    instead, for the human reviewer to act on if they want to.
    """
    entry = {"title": event["title"], "detail": event["detail"], "url": event["url"]}
    dumped = yaml.safe_dump(entry, default_flow_style=False, sort_keys=False, allow_unicode=True)
    lines = dumped.rstrip("\n").splitlines()
    block_lines = [f"  - {lines[0]}"] + [f"    {line}" for line in lines[1:]]
    return "\n".join(block_lines) + "\n"


# Marks the end of the evergreen list: either the next top-level YAML key
# (e.g. `guides:`) or a column-0 comment introducing one (every region
# file's `guides:` section is preceded by a comment block explaining it -
# stopping only at `guides:` itself would insert the new entry between
# that comment and the key it describes).
_BLOCK_BOUNDARY = re.compile(r"^(?:[A-Za-z_][\w-]*:|#)", re.MULTILINE)


def insert_evergreen_entry(text: str, yaml_block: str) -> str:
    """Insert a new list item at the end of a region file's `evergreen:`
    block, returning the full updated file text with every other line
    (including comments) preserved verbatim.
    """
    evergreen_match = re.search(r"^evergreen:\s*$", text, re.MULTILINE)
    if not evergreen_match:
        raise SubmissionError("Region file has no top-level `evergreen:` key")
    boundary_match = _BLOCK_BOUNDARY.search(text, evergreen_match.end())
    insert_at = boundary_match.start() if boundary_match else len(text)
    before = text[:insert_at].rstrip("\n") + "\n"
    after = text[insert_at:]
    separator = "\n" if after else ""
    return before + yaml_block + separator + after


def region_file_path(region_id: str) -> Path:
    path = REGIONS_DIR / f"{region_id}.yaml"
    if not path.exists():
        raise SubmissionError(f"No config file for region {region_id!r} (looked for {path})")
    return path


def format_github_output(name: str, value: str) -> str:
    """One $GITHUB_OUTPUT entry, in the delimiter form GitHub documents
    for multiline values - never the bare `name=value` form, because
    every value passed through here (a submitter's title/url/date, or a
    SubmissionError message quoting them) originates from a public
    Issue Form body an attacker fully controls. A literal newline in
    `value` would otherwise start a new line in $GITHUB_OUTPUT that
    could itself parse as `SOME_KEY=malicious`, letting a crafted
    submission inject or overwrite outputs the workflow trusts. A
    randomized delimiter (unguessable, so it can't be forged from
    inside `value`) closes that off regardless of what `value` contains.
    """
    delimiter = f"ghadelim_{secrets.token_hex(16)}"
    return f"{name}<<{delimiter}\n{value}\n{delimiter}"


def main() -> int:
    body = os.environ.get("ISSUE_BODY")
    if body is None:
        print("ISSUE_BODY environment variable not set", file=sys.stderr)
        return 1
    try:
        event = parse_issue_body(body)
        path = region_file_path(event["region_id"])
        block = build_evergreen_yaml_block(event)
        updated = insert_evergreen_entry(path.read_text(encoding="utf-8"), block)
    except SubmissionError as exc:
        print(format_github_output("SUBMISSION_ERROR", str(exc)))
        return 1
    path.write_text(updated, encoding="utf-8")
    print(format_github_output("REGION_FILE", str(path.relative_to(ROOT))))
    print(format_github_output("EVENT_TITLE", event["title"]))
    if event["date"]:
        print(format_github_output("EVENT_DATE", event["date"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
