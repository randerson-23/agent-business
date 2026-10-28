"""OUTREACH_BATCH.md: ready-to-send emails for warm prospects (ROADMAP.md item 401).

One block per organisation, at most MAX_BLOCKS, built from the warm list
(`data/warm_hosts.json`, item 387) and `config/outreach_contacts.yaml`. The
body is OUTREACH_TEMPLATES.md section 14a filled in. This file is committed to
a public repository: no individual's address, no send status.
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import warm_prospects  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "OUTREACH_BATCH.md"
CONTACTS_PATH = ROOT / "config" / "outreach_contacts.yaml"
MAX_BLOCKS = 8
SITE = "https://withintenmiles.com"
# firstname.lastname@ and initial-plus-surname addresses are personal; the file must never hold one.
PERSONAL_ADDRESS = re.compile(r"\b[a-z]+\.[a-z]+@|\b[a-z]\.?[a-z]{3,}@", re.IGNORECASE)
ROLE_LOCALPARTS = {"info", "news", "hello", "contact", "events", "marketing", "office", "admin", "press", "media", "sales"}


def load_contacts(path: Path = CONTACTS_PATH) -> list[dict]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    return [c for c in data.get("contacts") or [] if isinstance(c, dict) and c.get("match") and c.get("org") and c.get("site")]


def is_role_address(value: str) -> bool:
    m = re.fullmatch(r"([A-Za-z0-9._-]+)@[A-Za-z0-9.-]+\.[a-z]{2,}", value.strip())
    return bool(m) and m.group(1).lower() in ROLE_LOCALPARTS


def where_to_send(contact: dict) -> str:
    target = str(contact.get("contact") or "").strip()
    if target and "@" in target:
        if is_role_address(target) and contact.get("source"):
            return f"{target} (role address; source: {contact['source']})"
    elif target.startswith("https://") and contact.get("source"):
        return f"{target} (contact page; source: {contact['source']})"
    return f"look up on {contact['site']} (its Contact page; no address is stored here)"


def _day(iso: str) -> str:
    d = datetime.fromisoformat(iso)
    return f"{d.strftime('%a %b')} {d.day}"


def build_blocks(registry: dict, contacts: list[dict], limit: int = MAX_BLOCKS, today: date | None = None) -> list[dict]:
    """One block per organisation with a warm event: warm (non-venue) hosts first."""
    venue_keys = warm_prospects.venue_source_keys()
    orgs: dict[str, dict] = {}
    for key, host in sorted(registry.items()):
        contact = next((c for c in contacts if c["match"].lower() in key), None)
        if not contact:
            continue
        org = orgs.setdefault(contact["org"], {"contact": contact, "town": host["town"], "events": [], "venue": key in venue_keys})
        for e in host["events"]:
            org["events"].append({"title": e["title"], "date": e["date"], "host": host["name"]})
    ordered = sorted(orgs.items(), key=lambda kv: (kv[1]["venue"], kv[0]))
    blocks = []
    for name, org in ordered[:limit]:
        events = sorted(org["events"], key=lambda e: (bool(re.search(r"rescheduled|cancel", e["title"], re.IGNORECASE)), e["date"]))
        ev = events[0]
        shown = _day(ev["date"] + "T00:00:00")
        subject = f"Your {warm_prospects.short_title(ev['title'])} on {shown} was on our {org['town'] or 'local'} page"
        body = (
            f"Hi,\n\nYour {warm_prospects.short_title(ev['title'])} on {shown} was on Within Ten's {org['town'] or 'local'} page, "
            f"the free local guide. Next time, for $20, it goes first on the town page and in the weekly email, "
            f"labelled \"Presented by {name}\", with its own event page. You can see exactly what that looks like at {SITE}/sponsor/.\n\n"
            f"While the founding offer lasts (see {SITE}/sponsor/ for how many spots are left), your first Event Promo is free.\n\n"
            f"If you'd like one, reply with the event, date and the link you want it to open, and I'll set it up.\n\n"
            f"Thanks,\n[Your name]\nWithin Ten — {SITE}/"
        )
        blocks.append({"org": name, "where": where_to_send(org["contact"]), "subject": subject, "body": body, "event": f"{ev['title']} ({ev['date']})"})
    return blocks


def render(blocks: list[dict], now: datetime) -> str:
    lines = [
        "# Outreach batch (ROADMAP.md item 401)",
        "",
        f"Generated {now.strftime('%Y-%m-%d')} by `scripts/outreach_batch.py`. At most {MAX_BLOCKS} messages, warm prospects first.",
        "Each block is ready to paste: where to send, subject, body (OUTREACH_TEMPLATES.md section 14a).",
        "This repository is public: keep your own send notes elsewhere, and never add an individual's address here.",
        "",
    ]
    if not blocks:
        lines += ["No warm prospects with a known site right now.", ""]
    for i, b in enumerate(blocks, 1):
        lines += [f"## {i}. {b['org']}", "", f"- [ ] Sent (tick in your own copy)", f"- **Why it is warm:** {b['event']}", f"- **Where to send:** {b['where']}", f"- **Subject:** {b['subject']}", "", "```text", b["body"], "```", ""]
    return "\n".join(lines)


def main() -> int:
    now = datetime.now()
    blocks = build_blocks(warm_prospects.load_registry(), load_contacts())
    OUTPUT_PATH.write_text(render(blocks, now), encoding="utf-8")
    print("Wrote", OUTPUT_PATH, len(blocks), "blocks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
