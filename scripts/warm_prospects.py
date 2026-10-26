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
    r"county|state of|library's|the library|community center|senior center|district \d+)\b",
    re.IGNORECASE,
)
_PLACEHOLDER = re.compile(r"^(?:[A-Za-z .'-]+,\s*[A-Z]{2}|the|a|an|our|your|home|tbd|tba|online|virtual|various.*|multiple.*)$", re.IGNORECASE)
_TITLE_HOST = re.compile(r"\b(?:at|@)\s+([A-Z0-9][^,;:()|–—]{2,60})$")


def host_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower().replace("'s", "")).strip()


def _clean(name: str | None) -> str | None:
    name = re.sub(r"\s+", " ", (name or "")).strip(" .-–—")
    if len(name) < 3 or _AGENCY.search(name) or _PLACEHOLDER.match(name):
        return None
    return name


def event_host(event: dict) -> str | None:
    """The business hosting an event, from its title ("... at Napleton's
    Palatine Mazda") or its venue, or None."""
    m = _TITLE_HOST.search((event.get("title") or "").strip())
    if m:
        name = _clean(m.group(1))
        if name:
            return name
    return _clean(event.get("venue"))


def collect_hosts(events: list[dict], town: str) -> list[dict]:
    found = []
    for e in events:
        host = event_host(e)
        if host and e.get("date_iso") and e.get("title"):
            found.append({"host": host, "town": town, "title": e["title"].strip(), "date": e["date_iso"][:10]})
    return found


def update_registry(registry: dict, found: list[dict], today: date) -> dict:
    """Merge this build's hosts into the stored registry and drop events
    outside the window, and hosts left with none."""
    registry = {k: dict(v, events=list(v.get("events") or [])) for k, v in registry.items()}
    for f in found:
        entry = registry.setdefault(host_key(f["host"]), {"name": f["host"], "town": f["town"], "events": []})
        row = {"title": f["title"], "date": f["date"]}
        if row not in entry["events"]:
            entry["events"].append(row)
    start, end = today - timedelta(days=LOOKBACK_DAYS), today + timedelta(days=LOOKAHEAD_DAYS)
    out = {}
    for key, entry in registry.items():
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


def render_section(registry: dict, osm_names: set[str] | None = None) -> list[str]:
    """Markdown lines for the "Warm" section; hosts already in the OSM list
    (`osm_names`, compared by host_key) are not repeated there."""
    lines = ["## Warm: already hosting public events", ""]
    hosts = sorted(registry.values(), key=lambda h: (h["town"], h["name"].lower()))
    if not hosts:
        return lines + ["No non-agency hosts in the site's listings right now.", ""]
    lines += [
        "Businesses and venues whose own events appeared on a town page in the last 60 days or the next 30. "
        "Names, events and dates only. Start here: they already hold public events.",
        "",
        "| Host | Town | Events |",
        "|---|---|---|",
    ]
    for h in hosts:
        shown = "; ".join(f"{e['title'].replace('|', '/')} ({e['date']})" for e in h["events"][:3])
        more = f"; +{len(h['events']) - 3} more" if len(h["events"]) > 3 else ""
        lines.append(f"| {h['name'].replace('|', '/')} | {h['town']} | {shown}{more} |")
    lines.append("")
    return lines
