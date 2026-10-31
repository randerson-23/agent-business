"""OUTREACH_BATCH.md: ready-to-send emails for warm prospects (ROADMAP.md item 401).

One block per organisation, at most MAX_BLOCKS, built from the warm list
(`data/warm_hosts.json`, item 387) and `config/outreach_contacts.yaml`. The
body is OUTREACH_TEMPLATES.md section 14a filled in. This file is committed to
a public repository: no individual's address, no send status.
"""

from __future__ import annotations

import calendar
import re
import sys
from urllib.parse import quote_plus
from datetime import date, datetime, timedelta
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
PERSONAL_ADDRESS = re.compile(r"\b[a-z]+\.[a-z]+@|\b[a-z]\.?[a-z]{3,}@", re.IGNORECASE)  # applies to addresses not configured as an organisation mailbox
ROLE_LOCALPARTS = {"info", "news", "hello", "contact", "events", "marketing", "office", "admin", "press", "media", "sales"}


def personal_addresses(text: str, contacts: list[dict]) -> list[str]:
    """Addresses in `text` that look personal, ignoring the organisation mailboxes
    the config explicitly marks (a craft fair's own mailbox, published on its page)."""
    allowed = {str(c["contact"]).lower() for c in contacts if c.get("organisation_mailbox") and c.get("contact") and c.get("source")}
    return [m.group(0) for m in PERSONAL_ADDRESS.finditer(text) if not any(a.startswith(m.group(0).lower()) for a in allowed)]


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
        # an organisation's own mailbox (the fair's, not a person's) is marked `organisation_mailbox: true`
        dotted_name = re.match(r"[A-Za-z]+\.[A-Za-z]+@", target)  # firstname.lastname@ is never stored
        if (is_role_address(target) or (contact.get("organisation_mailbox") and not dotted_name)) and contact.get("source"):
            return f"{target} (organisation mailbox; source: {contact['source']})"
    elif target.startswith("https://") and contact.get("source"):
        return f"{target} (contact page; source: {contact['source']})"
    return f"look up on {contact['site']} (its Contact page; no address is stored here)"


def _day(iso: str) -> str:
    d = datetime.fromisoformat(iso)
    return f"{d.strftime('%a %b')} {d.day}"


try:  # the send weekday comes from the sender itself, so the copy cannot drift from it (item 415)
    from send_newsletter import SEND_WEEKDAY
except Exception:  # noqa: BLE001
    SEND_WEEKDAY = 3
SEND_DAY = calendar.day_name[SEND_WEEKDAY]
VENUE_MIN_DAYS_AHEAD = 3
SUBJECT_MAX = 60
FAIR_SOON_DAYS = 21


DISPLAY_TITLE = None  # build_digest.py sets this when it calls the generator in-process


def _display(title: str) -> str:
    display = DISPLAY_TITLE
    if display is None:
        from build_digest import display_title as display  # item 334's display case (not the shouting source text)
    return display(warm_prospects.short_title(title))


def subject_for(kind: str, ev: dict, town: str) -> str:
    """Item 408: short and readable, at most SUBJECT_MAX characters."""
    town = town or "local"
    when = _day(ev["date"] + "T00:00:00")
    title = _display(ev["title"])
    if kind == "venue":
        options = [f"Your {title} on {when} is on our {town} page", f"Your {when} show is on our {town} page"]
    elif kind == "fair":
        options = [f"Your {title} on {when} is on our {town} page", f"Your {when} fair is on our {town} page"]
    else:
        options = [f"Your {title} on {when} was on our {town} page", f"Your {datetime.fromisoformat(ev['date']).strftime('%b')} {datetime.fromisoformat(ev['date']).day} event was on our {town} page"]
    return next((o for o in options if len(o) <= SUBJECT_MAX), options[-1][:SUBJECT_MAX])


def _clock(hhmm: str) -> str:
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    return f"{h % 12 or 12}{':%02d' % m if m else ''} {'AM' if h < 12 else 'PM'}"


def details_for(ev: dict) -> str | None:
    """"Sat Nov 7, 9 AM, Palatine High School" when the site holds the date, the start time and the place."""
    if not (ev.get("time") and ev.get("venue")):
        return None
    return f"{_day(ev['date'] + 'T00:00:00')}, {_clock(ev['time'])}, {ev['venue']}"


def body_for(kind: str, name: str, ev: dict, town: str, preview: str) -> str:
    """The filled OUTREACH_TEMPLATES.md section: 14a (warm), 14b (fair), 14c (venue)."""
    town = town or "local"
    when = _day(ev["date"] + "T00:00:00")
    title = _display(ev["title"])
    sign = f"Thanks,\n[Your name]\nWithin Ten \u2014 {SITE}/"
    details = details_for(ev)
    if details:  # item 415: one word is enough when the site already holds the facts
        ask = f"Reply 'yes' and we'll feature it exactly as it's listed ({details}); tell us if anything has changed."
    elif kind == "venue":
        ask = "If you'd like that, reply with the show, date and the link you want it to open, and I'll set it up."
    else:
        ask = "If you'd like that, reply with the event, date, time, address and the link you want it to open, and I'll set it up."
    founding = f"(see {SITE}/sponsor/ for how many spots are left)"
    founding_plain = f"see {SITE}/sponsor/ for how many spots are left"
    if kind == "venue":
        return (
            f"Hi,\n\nWe list your shows for free on Within Ten's {town} page, the free local guide. "
            f"If you'd like one show a week featured first, it's $20, and the first is free while our founding offer lasts "
            f"{founding}. Your next one on our list is {title} on {when}.\n\nHere is how {name} would look: {preview}\n\n{ask}\n\n{sign}"
        )
    if kind == "fair":
        return (
            f"Hi,\n\nYour {title} on {when} is on Within Ten's {town} page, the free local guide. For $20 (or free under our "
            f"founding offer, {founding_plain}) it goes first on the town page and in {SEND_DAY} morning's "
            f"email, labelled \"Presented by {name}\", so families see it while they plan the weekend.\n\n"
            f"Here is how {name} would look: {preview}\n\n{ask}\n\n{sign}"
        )
    return (
        f"Hi,\n\nYour {title} on {when} was on Within Ten's {town} page, the free local guide. Next time, for $20, it goes first "
        f"on the town page and in {SEND_DAY} morning's email, labelled \"Presented by {name}\", with its own event page. "
        f"Here is how {name} would look: {preview}\n\n"
        f"While the founding offer lasts {founding}, your first Event Promo is free.\n\n{ask}\n\n{sign}"
    )


def preview_link(kind: str, name: str, town: str, ev: dict) -> str:
    """Item 419: the prospect's own event, date, place and kind in the preview link."""
    parts = [("name", name), ("town", town or ""), ("event", _display(ev["title"])), ("date", _day(ev["date"] + "T00:00:00")), ("d", ev["date"])]
    if ev.get("venue"):
        parts.append(("venue", ev["venue"]))
    parts.append(("kind", "fair" if kind == "fair" else "warm"))
    return f"{SITE}/sponsor/preview/?" + "&".join(f"{k}={quote_plus(v)}" for k, v in parts)


def build_blocks(registry: dict, contacts: list[dict], limit: int = MAX_BLOCKS, today: date | None = None) -> list[dict]:
    """One block per organisation. Order (item 410): fairs within 21 days first,
    then warm businesses, then other fairs, then venues that publish calendars."""
    today = today or date.today()
    venue_keys = warm_prospects.venue_source_keys()
    orgs: dict[str, dict] = {}
    for key, host in sorted(registry.items()):
        contact = next((c for c in contacts if c["match"].lower() in key), None)
        if not contact:
            continue
        org = orgs.setdefault(contact["org"], {"contact": contact, "town": host["town"], "events": [], "venue": key in venue_keys})
        for e in warm_prospects.drop_placeholder_dates(host["events"]):
            org["events"].append({**e, "host": host["name"]})
    ranked = []
    for name, org in orgs.items():
        if org["venue"]:  # item 415: a venue's next show must be at least three days out, else it sits this week out
            cutoff = (today + timedelta(days=VENUE_MIN_DAYS_AHEAD)).isoformat()
            upcoming = [e for e in org["events"] if e["date"] >= cutoff]
            if not upcoming:
                continue
        else:
            upcoming = [e for e in org["events"] if e["date"] >= today.isoformat()] or org["events"]
        fairs = [e for e in upcoming if warm_prospects.FAIR_TITLE.search(e["title"])]
        kind = "venue" if org["venue"] else "fair" if fairs else "warm"
        pool = fairs or upcoming
        pool = sorted(pool, key=lambda e: (bool(re.search(r"rescheduled|cancel", e["title"], re.IGNORECASE)), e["date"]))
        ev = pool[0]
        days = (date.fromisoformat(ev["date"]) - today).days
        rank = 0 if kind == "fair" and 0 <= days <= FAIR_SOON_DAYS else 1 if kind == "warm" else 2 if kind == "fair" else 3
        ranked.append((rank, ev["date"] if kind == "fair" else "", name, kind, org, ev))
    ranked.sort(key=lambda r: r[:3])
    blocks = []
    for _rank, _d, name, kind, org, ev in ranked[:limit]:
        preview = preview_link(kind, name, org["town"], ev)
        blocks.append({
            "org": name, "kind": kind, "where": where_to_send(org["contact"]),
            "subject": subject_for(kind, ev, org["town"]), "body": body_for(kind, name, ev, org["town"], preview),
            "event": f"{ev['title']} ({ev['date']})",
        })
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
        lines += [f"## {i}. {b['org']}", "", f"- [ ] Sent (tick in your own copy)", f"- **Why it is warm:** {b['event']} (template {dict(warm='14a', fair='14b', venue='14c')[b['kind']]})", f"- **Where to send:** {b['where']}", f"- **Subject:** {b['subject']}", "", "```text", b["body"], "```", ""]
    return "\n".join(lines)


def write_batch(registry: dict, now: datetime, path: Path | None = None) -> int:
    blocks = build_blocks(registry, load_contacts())
    (path or OUTPUT_PATH).write_text(render(blocks, now), encoding="utf-8")
    return len(blocks)


def main() -> int:
    now = datetime.now()
    blocks = build_blocks(warm_prospects.load_registry(), load_contacts())
    OUTPUT_PATH.write_text(render(blocks, now), encoding="utf-8")
    print("Wrote", OUTPUT_PATH, len(blocks), "blocks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
