#!/usr/bin/env python3
"""Turn rows of the event Google Form's published CSV into curated entries
(ROADMAP.md item 246).

The owner creates a Google Form (no account needed to submit) and publishes
the response sheet's event-fields tab as CSV, with no contact column, so the
URL holds no personal data. A daily workflow runs this script with that URL in
the `EVENT_FORM_CSV_URL` secret. Each new row goes through the same parser and
the same region-file splice as the GitHub Issue Form
(scripts/parse_event_submission.py), and the workflow opens ONE pull request
for the day's rows, so a person always reviews them before anything goes live:
public forms attract spam. Rows are remembered by a hash in
data/event_submissions_seen.json so a row is never proposed twice, including
rows that were rejected as unusable.

Skips quietly when the secret is not set.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parse_event_submission as pes  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SEEN_PATH = ROOT / "data" / "event_submissions_seen.json"

# Header words each Form question is matched on, case-insensitively, so the
# owner can word the questions naturally.
_COLUMNS = {
    "region": ("town", "village", "region"),
    "title": ("name", "title"),
    "detail": ("description", "details", "about"),
    "url": ("link", "url", "website"),
    "date": ("date",),
}


def _column(headers: list[str], words: tuple[str, ...]) -> str | None:
    for h in headers:
        if any(w in h.lower() for w in words):
            return h
    return None


def _region_label(value: str) -> str:
    """"Palatine" or "Palatine (60067)" -> the Issue Form's label."""
    value = (value or "").strip().lower()
    for label in pes.REGION_LABEL_TO_ID:
        if value and (value == label.lower() or label.lower().startswith(value + " (")):
            return label
    return value


def row_to_issue_body(row: dict[str, str], headers: list[str]) -> str:
    """The Issue Form body text for one CSV row, so parse_issue_body()
    validates it exactly like a GitHub submission."""
    parts = []
    for key, label in (("region", pes._FIELD_LABELS["region"]), ("title", pes._FIELD_LABELS["title"]), ("detail", pes._FIELD_LABELS["detail"]), ("url", pes._FIELD_LABELS["url"]), ("date", pes._FIELD_LABELS["date"])):
        col = _column(headers, _COLUMNS[key])
        value = (row.get(col) or "").strip() if col else ""
        if key == "region":
            value = _region_label(value)
        parts.append(f"### {label}\n\n{value or '_No response_'}")
    return "\n\n".join(parts) + "\n"


def row_hash(row: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def load_seen(path: Path = SEEN_PATH) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except (OSError, ValueError):
        return set()


def process_csv(text: str, seen: set[str], *, write: bool = True) -> tuple[list[dict], list[str], set[str]]:
    """Returns (accepted events, rejection reasons, new hashes to remember).
    With write=True each accepted entry is spliced into its region file."""
    reader = csv.DictReader(io.StringIO(text))
    headers = list(reader.fieldnames or [])
    accepted, rejected, new_hashes = [], [], set()
    for row in reader:
        h = row_hash(row)
        if h in seen:
            continue
        new_hashes.add(h)
        try:
            event = pes.parse_issue_body(row_to_issue_body(row, headers))
            path = pes.region_file_path(event["region_id"])
            block = pes.build_evergreen_yaml_block(event)
            updated = pes.insert_evergreen_entry(path.read_text(encoding="utf-8"), block)
        except pes.SubmissionError as exc:
            rejected.append(f"{(row.get(_column(headers, _COLUMNS['title']) or '') or '?')[:60]}: {exc}")
            continue
        if write:
            path.write_text(updated, encoding="utf-8")
        accepted.append(event)
    return accepted, rejected, new_hashes


def main() -> int:
    url = os.environ.get("EVENT_FORM_CSV_URL", "").strip()
    if not url:
        print("EVENT_FORM_CSV_URL is not set; skipping event-form ingest.")
        return 0
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"Could not fetch the form's CSV ({exc}); nothing changed.", file=sys.stderr)
        return 1
    seen = load_seen()
    accepted, rejected, new_hashes = process_csv(resp.text, seen)
    SEEN_PATH.write_text(json.dumps(sorted(seen | new_hashes)) + "\n", encoding="utf-8")
    print(f"{len(accepted)} new event(s) added for review; {len(rejected)} row(s) could not be used.")
    for reason in rejected:
        print(f"  rejected: {reason}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"accepted={len(accepted)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
