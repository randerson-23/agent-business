"""Warm prospects: businesses that already host public events (ROADMAP.md item 387).

Read from the events the site already lists: the venue or an "at <Name>" in
a title, when the host is not a library, park district, village, school or
church. The build keeps a rolling registry in `data/warm_hosts.json` (events
from the last 60 days and the next 30), and `osm_prospects.py` renders it as
the top section of OUTREACH_PROSPECTS.md. Names, events, dates and towns only:
this repository is public, so no contact notes belong here.
"""
import json
import re
from html import unescape
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WARM_HOSTS_PATH = ROOT / "data" / "warm_hosts.json"
LOOKBACK_DAYS = 60
LOOKAHEAD_DAYS = 30

# A host that is an agency, school, church or a town itself is not a prospect.
_AGENCY = re.compile(
    r"\b(library|park district|parks?\b|village|city of|town of|township|school|district|church|parish|synagogue|"
    r"temple|college|university|forest preserve|police|fire (?:department|dept)|department|"
    r"chamber|rotary|kiwanis|lions club|scouts?|ymca|ywca|council|committee|association|pta|pto|"
    r"county|state of|library's|the library|community|open house|senior center|district \d+)\b",
    re.IGNORECASE,
)
_PLACEHOLDER = re.compile(r"^(?:[A-Za-z .'-]+,\s*[A-Z]{2}|the|a|an|our|your|home|tbd|tba|online|virtual|various.*|multiple.*)$", re.IGNORECASE)
# Item 391: times, dates and closure notes are not business names ("Library
# Closed at 5 p.m." must yield no host).
_NOT_A_NAME = re.compile(
    r"\d{1,2}(?::\d\d)?\s*[ap]\.?\s?m\b|\b\d{1,2}[/-]\d{1,2}\b|"
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b|"
    r"\b(?:closed|closes|closing|rescheduled|cancel+ed|postponed|noon|midnight)\b",
    re.IGNORECASE,
)
# Item 396: a craft fair's organiser ("<Boosters> Present: Fall Craft Fair") is a prospect of its own.
FAIR_TITLE = re.compile(r"\b(?:craft fair|holiday market|makers[\u2019' ]*s? market|bazaar|vendor fair|holiday boutique)\b", re.IGNORECASE)
_PRESENTS = re.compile(r"^(.{3,70}?)\s+Presents?:\s+", re.IGNORECASE)
_TITLE_HOST = re.compile(r"\b(?:at|@)\s+([A-Z0-9][^,;:()|–—]{2,60})$")


def short_title(title: str) -> str:
    """An event title for a sentence: "FREE Trunk or Treat at Napleton's Mazda"
    becomes "Trunk or Treat" (the host is named separately); a leading "The"
    is dropped so "Your The Rock..." cannot happen."""
    t = re.sub(r"^.{3,70}?\s+Presents?:\s+", "", title.strip(), flags=re.IGNORECASE)  # "<Organiser> Present: Fall Craft Fair"
    t = re.sub(r"\s+(?:at|@)\s+.*$", "", t.strip())
    t = re.sub(r"^(?:free|rescheduled[^:]*:)\s+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^(?:the|a|an)\s+", "", t.strip(), flags=re.IGNORECASE)
    return t.strip() or title.strip()


def host_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower().replace("'s", "")).strip()


_BOOSTER = re.compile(r"\b(?:boosters?|pto|pta|parent teacher)\b", re.IGNORECASE)


def _clean(name: str | None) -> str | None:
    name = re.sub(r"\s+", " ", (name or "")).strip(" .-–—")
    if len(name) < 3 or (_AGENCY.search(name) and not _BOOSTER.search(name)) or _PLACEHOLDER.match(name) or _NOT_A_NAME.search(name):
        return None
    return name


def event_host(event: dict) -> str | None:
    """The business hosting an event, from its title ("... at Napleton's
    Palatine Mazda") or its venue, or None."""
    title = (event.get("title") or "").strip()
    pm = _PRESENTS.match(title)
    if pm and FAIR_TITLE.search(title):
        name = _clean(pm.group(1))
        if name:
            return name
    m = _TITLE_HOST.search(title)
    if m:
        name = _clean(m.group(1))
        if name:
            return name
    return _clean(event.get("venue"))


def collect_hosts(events: list[dict], town: str) -> list[dict]:
    found = []
    for e in events:
        if not (e.get("date_iso") and e.get("title")):
            continue
        hosts = [event_host(e)]
        # Item 398: a collapsed "Also at: A, B" line is the same event at more hosts.
        hosts += [_clean(a.get("label")) for a in e.get("also_at") or [] if isinstance(a, dict)]
        for host in dict.fromkeys(h for h in hosts if h):
            found.append({"host": host, "town": town, "title": e["title"].strip(), "date": e["date_iso"][:10]})
    return found


_CHIP = re.compile(r">\s*([A-Z]{3})\s*</td>.{0,900}?>\s*(\d{1,2})\s*</td>", re.DOTALL)


def _chip_date(html_before: str, issue_day: date) -> str | None:
    """The event date from the last day chip ("SAT" / "24") before a link in a
    stored issue; the month is the issue's, rolling to the next when the day
    is earlier than the send date."""
    chips = _CHIP.findall(html_before)
    if not chips:
        return None
    day = int(chips[-1][1])
    month, year = issue_day.month, issue_day.year
    if day < issue_day.day - 3:
        month, year = (1, year + 1) if month == 12 else (month + 1, year)
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def issue_hosts(directory: Path | None = None, town_of=None) -> list[dict]:
    """Item 391: run the host extraction over the link text of the stored
    sends (`data/issues/<date>.html`, kept byte-for-byte), so hosts that
    appeared since the first send are recovered. The date is the issue's
    send date. `town_of` maps a title to a town name; default is blank."""
    directory = directory or ROOT / "data" / "issues"
    found = []
    for path in sorted(directory.glob("*.html")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        try:
            issue_day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        for m in re.finditer(r"<a\b[^>]*>([^<]{5,120})</a>", text):
            title = unescape(m.group(1)).strip()
            host = event_host({"title": title})
            if host:
                # item 398: the event's own date from its card's day chip, else the send date
                day = _chip_date(text[max(0, m.start() - 1500):m.start()], issue_day) or path.stem
                found.append({"host": host, "town": (town_of(title) if town_of else "") or "", "title": title, "date": day})
    return found


def venue_source_keys(config_dir: Path | None = None) -> set[str]:
    """host_keys of venues that are configured sources themselves (a theatre
    that publishes its own calendar): a different pitch from a business that
    merely hosts an event."""
    import yaml

    keys = set()
    for path in (config_dir or ROOT / "config" / "regions").glob("*.yaml"):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        for source in data.get("sources") or []:
            if isinstance(source, dict) and source.get("venue_name"):
                keys.add(host_key(str(source["venue_name"])))
    return keys


def update_registry(registry: dict, found: list[dict], today: date) -> dict:
    """Merge this build's hosts into the stored registry and drop events
    outside the window, and hosts left with none."""
    registry = {k: dict(v, events=list(v.get("events") or [])) for k, v in registry.items()}
    for f in found:
        entry = registry.setdefault(host_key(f["host"]), {"name": f["host"], "town": f["town"], "events": []})
        row = {"title": f["title"], "date": f["date"]}
        # Item 408: an older row for the same title dated a few days earlier is a send-date
        # placeholder from before event dates were read from the cards; the real date replaces it.
        entry["events"] = [
            e for e in entry["events"]
            if not (e["title"] == row["title"] and e["date"] < row["date"] and (date.fromisoformat(row["date"]) - date.fromisoformat(e["date"])).days <= 6)
        ]
        if row not in entry["events"]:
            entry["events"].append(row)
    start, end = today - timedelta(days=LOOKBACK_DAYS), today + timedelta(days=LOOKAHEAD_DAYS)
    out = {}
    for key, entry in registry.items():
        if not _clean(entry.get("name")):
            continue  # a name an earlier version accepted ("5 p.m.") is dropped on the next build
        events = sorted((e for e in entry["events"] if start.isoformat() <= e["date"] <= end.isoformat()), key=lambda e: e["date"])
        if events:
            out[key] = {"name": entry["name"], "town": entry["town"], "events": events}
    return out


def load_registry(path: Path = WARM_HOSTS_PATH) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_registry(registry: dict, path: Path = WARM_HOSTS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _table(hosts: list[dict]) -> list[str]:
    lines = ["| Host | Town | Events |", "|---|---|---|"]
    for h in hosts:
        shown = "; ".join(f"{e['title'].replace('|', '/')} ({e['date']})" for e in h["events"][:3])
        more = f"; +{len(h['events']) - 3} more" if len(h["events"]) > 3 else ""
        lines.append(f"| {h['name'].replace('|', '/')} | {h['town']} | {shown}{more} |")
    return lines + [""]


def _is_fair_organiser(host: dict) -> bool:
    return any(FAIR_TITLE.search(e["title"]) for e in host["events"])


def render_section(registry: dict, venue_keys: set[str] | None = None) -> list[str]:
    """Markdown lines for the "Warm" section (item 387), with hosts that are
    configured calendar sources in a separate short list (item 391)."""
    venue_keys = venue_keys or set()
    lines = ["## Warm: already hosting public events", ""]
    hosts = sorted(registry.items(), key=lambda kv: (kv[1]["town"], kv[1]["name"].lower()))
    organisers = [h for k, h in hosts if k not in venue_keys and _is_fair_organiser(h)]
    warm = [h for k, h in hosts if k not in venue_keys and not _is_fair_organiser(h)]
    venues = [h for k, h in hosts if k in venue_keys]
    if not warm:
        lines += ["No non-agency hosts in the site's listings right now.", ""]
    else:
        lines += [
            "Businesses whose own events appeared on a town page in the last 60 days or the next 30. "
            "Names, events and dates only. Start here: they already hold public events.",
            "",
        ] + _table(warm)
    if organisers:
        lines += ["### Fair organisers", "", "Booster clubs, PTOs and programmes running a craft fair or holiday market. Send OUTREACH_TEMPLATES.md section 14b two weeks before the fair.", ""] + _table(organisers)
    if venues:
        lines += ["### Venues that already publish calendars", "", "They may still buy a promo, but the pitch differs: they already reach their own audience.", ""] + _table(venues)
    return lines


WARM_HEADING = "## Warm: already hosting public events"


def splice_section(text: str, section_lines: list[str]) -> str:
    """Replace the Warm section of OUTREACH_PROSPECTS.md in place (so every
    build can refresh it without touching the OpenStreetMap tables), or add it
    after the header block when the file has none yet."""
    section = "\n".join(section_lines).rstrip() + "\n\n"
    if WARM_HEADING in text:
        start = text.index(WARM_HEADING)
        rest = text[start + len(WARM_HEADING):]
        nxt = re.search(r"^## (?!#)", rest, re.MULTILINE)
        end = start + len(WARM_HEADING) + (nxt.start() if nxt else len(rest))
        return text[:start] + section + text[end:]
    first = re.search(r"^## ", text, re.MULTILINE)
    cut = first.start() if first else len(text)
    return text[:cut] + section + text[cut:]
