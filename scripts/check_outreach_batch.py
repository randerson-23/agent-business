"""Check the GENERATED OUTREACH_BATCH.md, not only the generator (ROADMAP.md item 413).

Run by osm-prospects.yml right after outreach_batch.py. It fails (exit 1) when:
- a block's subject date differs from the registry's date for that event,
- a block has no /sponsor/preview/?name= link,
- a subject is longer than 60 characters,
- a fair within 21 days is in the registry but the first block is not a fair.
A failing step fails the workflow, and the workflow watchdog (item 406) opens its issue.
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import outreach_batch  # noqa: E402
import warm_prospects  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
_BLOCK = re.compile(r"^## \d+\. (?P<org>.+?)\n(?P<body>.*?)(?=^## \d+\. |\Z)", re.MULTILINE | re.DOTALL)


def check(text: str, registry: dict, today: date | None = None) -> list[str]:
    today = today or date.today()
    problems = []
    blocks = list(_BLOCK.finditer(text))
    for m in blocks:
        org, body = m.group("org"), m.group("body")
        why = re.search(r"\*\*Why it is warm:\*\* (?P<title>.+) \((?P<date>\d{4}-\d{2}-\d{2})\) \(template (?P<tpl>14[abc])\)", body)
        subject = re.search(r"\*\*Subject:\*\* (.+)", body)
        if not why or not subject:
            problems.append(f"{org}: block is missing its reason or subject")
            continue
        subject = subject.group(1).strip()
        if len(subject) > outreach_batch.SUBJECT_MAX:
            problems.append(f"{org}: subject is {len(subject)} characters: {subject}")
        if "/sponsor/preview/?name=" not in body:
            problems.append(f"{org}: no personalised preview link")
        day = datetime.fromisoformat(why.group("date"))
        label = f"{day.strftime('%b')} {day.day}"  # "Sat Oct 24" and the "Oct 24 event" fallback both contain it
        if label not in subject:
            problems.append(f"{org}: subject date does not match the event date {why.group('date')}: {subject}")
        known = [e["date"] for h in registry.values() for e in h["events"] if e["title"] == why.group("title")]
        if known and why.group("date") not in known:
            problems.append(f"{org}: {why.group('date')} is not a registry date for {why.group('title')!r}")
        if known and why.group("date") < max(known) and any(
            0 < (date.fromisoformat(k) - date.fromisoformat(why.group("date"))).days <= 6 for k in known
        ):
            problems.append(f"{org}: stale send-date placeholder {why.group('date')} (registry has a later real date)")
    fairs_soon = [
        e for h in registry.values() for e in h["events"]
        if warm_prospects.FAIR_TITLE.search(e["title"]) and 0 <= (date.fromisoformat(e["date"]) - today).days <= outreach_batch.FAIR_SOON_DAYS
    ]
    contacts = outreach_batch.load_contacts()
    fair_has_contact = any(
        any(c["match"].lower() in k for c in contacts) and any(warm_prospects.FAIR_TITLE.search(e["title"]) for e in h["events"])
        for k, h in registry.items()
    )
    if fairs_soon and fair_has_contact and blocks and "(template 14b)" not in blocks[0].group("body"):
        problems.append("a fair within 21 days is not the first block")
    return problems


def main() -> int:
    path = ROOT / "OUTREACH_BATCH.md"
    problems = check(path.read_text(encoding="utf-8"), warm_prospects.load_registry())
    for p in problems:
        print("OUTREACH_BATCH.md:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
