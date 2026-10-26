"""Build OUTREACH_PROSPECTS.md from OpenStreetMap (ROADMAP.md item 306).

Run by .github/workflows/osm-prospects.yml on a GitHub runner (this sandbox
has no web access). One Overpass query per town for shops and eateries inside
the town's own `admin_level=8` boundary, written as one table per town:
name, category and website. No emails and no phone numbers, even when OSM
has them. A row with no website is marked "visit in person". Ordered by how
likely the category is to buy a holiday listing. Data (c) OpenStreetMap
contributors, ODbL; for outreach use only, never republished.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

import warm_prospects

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "OUTREACH_PROSPECTS.md"
LAST_GOOD_DIR = ROOT / "data" / "osm_last_good"
RETRY_DELAYS = (30, 120)  # seconds before the 2nd and 3rd attempt
TOWN_SPACING = 10  # seconds between town queries: Overpass rate-limits bursts
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "WithinTenBot/1.0 (+https://withintenmiles.com; outreach prospect list)"
TOWNS = ["Arlington Heights", "Des Plaines", "Mount Prospect", "Palatine", "Wheeling"]
STATE = "Illinois"  # Wheeling, WV and Palatine, TX exist too
MAX_ROWS_PER_TOWN = 80

# Highest holiday-buying first.
SHOP_ORDER = ["gift", "toys", "books", "florist", "jewelry", "boutique", "clothes", "chocolate", "confectionery", "bakery"]
AMENITY_ORDER = ["ice_cream", "cafe", "restaurant"]
CATEGORY_LABEL = {
    "gift": "Gift shop", "toys": "Toy shop", "books": "Bookshop", "florist": "Florist", "jewelry": "Jeweller",
    "boutique": "Boutique", "clothes": "Clothes", "chocolate": "Chocolate", "confectionery": "Sweets",
    "bakery": "Bakery", "ice_cream": "Ice cream", "cafe": "Cafe", "restaurant": "Restaurant",
}
RANK = {key: i for i, key in enumerate(SHOP_ORDER + AMENITY_ORDER)}


def build_query(town: str) -> str:
    shops = "|".join(SHOP_ORDER)
    amenities = "|".join(AMENITY_ORDER)
    return (
        "[out:json][timeout:60];\n"
        f'area["name"="{STATE}"]["admin_level"="4"]->.state;\n'
        f'area["name"="{town}"]["admin_level"="8"](area.state)->.town;\n'
        "(\n"
        f'  nwr["shop"~"^({shops})$"]["name"](area.town);\n'
        f'  nwr["amenity"~"^({amenities})$"]["name"](area.town);\n'
        ");\nout tags center;"
    )


def row_from_element(el: dict) -> dict | None:
    """One prospect row from an Overpass element; None when it has no name or
    a category we do not list. Website only: contact details are dropped."""
    tags = el.get("tags") or {}
    name = (tags.get("name") or "").strip()
    category = tags.get("shop") if tags.get("shop") in RANK else tags.get("amenity") if tags.get("amenity") in RANK else None
    if not name or category is None:
        return None
    website = (tags.get("website") or tags.get("contact:website") or "").strip()
    if website and not website.startswith(("http://", "https://")):
        website = "https://" + website
    return {"name": name, "category": category, "website": website}


def rows_for_town(elements: list[dict]) -> list[dict]:
    seen, rows = set(), []
    for el in elements:
        row = row_from_element(el)
        key = (row["name"].lower(), row["category"]) if row else None
        if row and key not in seen:
            seen.add(key)
            rows.append(row)
    rows.sort(key=lambda r: (RANK[r["category"]], not r["website"], r["name"].lower()))
    return rows


def render_markdown(towns: dict[str, list[dict] | None], now: datetime, warm: dict | None = None, stale: dict[str, str] | None = None) -> str:
    lines = [
        "# Outreach prospects (OpenStreetMap)",
        "",
        f"Generated {now.strftime('%Y-%m-%d')} by `scripts/osm_prospects.py` (ROADMAP.md item 306).",
        "",
        "> Data (c) OpenStreetMap contributors, available under the Open Database Licence (ODbL). "
        "**For outreach use only; never share or republish this file.** Names and websites only: "
        "no emails or phone numbers are kept, even where OSM has them. Order is the likelihood of "
        "buying a holiday listing (gifts, toys and books first, restaurants last). OSM coverage is "
        "volunteer-made: treat a missing shop as unknown, not as closed, and check the business's own "
        "site or a visit before writing to it.",
        "",
    ]
    if warm is not None:  # item 387: hosts already running public events lead the file
        lines += warm_prospects.render_section(warm, warm_prospects.venue_source_keys())
    for town, rows in towns.items():
        if warm and rows is not None:  # a business already listed as warm is not repeated below
            rows = [r for r in rows if warm_prospects.host_key(r["name"]) not in warm]
        lines += [f"## {town}", ""]
        if stale and town in stale:
            lines += [f"(from the {stale[town]} run; today's refresh failed)", ""]
        if rows is None:
            lines += ["The OpenStreetMap query for this town failed; re-run the workflow.", ""]
            continue
        if not rows:
            lines += ["Nothing came back for this town: OSM coverage is thin here. Use the downtown group's own member list instead.", ""]
            continue
        if len(rows) < 10:
            lines += [f"Only {len(rows)} named shops and eateries came back, so OSM coverage is thin. Do not treat this as the full list.", ""]
        shown = rows[:MAX_ROWS_PER_TOWN]
        lines += ["| Name | Category | Website |", "|---|---|---|"]
        for r in shown:
            site = f"<{r['website']}>" if r["website"] else "visit in person"
            lines.append(f"| {r['name'].replace('|', '/')} | {CATEGORY_LABEL[r['category']]} | {site} |")
        if len(rows) > len(shown):
            lines += ["", f"{len(rows) - len(shown)} more not shown (lower-priority categories)."]
        lines.append("")
    lines += [
        "## Cross-check (not yet done)",
        "",
        "Item 306 asks for five names per town to be checked against the downtown groups' own pages. "
        "That needs live pages the build cannot read; do it by hand before relying on a town's list.",
        "",
    ]
    return "\n".join(lines)


def fetch_town(town: str, post=requests.post) -> list[dict] | None:
    try:
        resp = post(OVERPASS_URL, data={"data": build_query(town)}, headers={"User-Agent": USER_AGENT}, timeout=90)
        resp.raise_for_status()
        return rows_for_town(resp.json().get("elements") or [])
    except Exception as exc:  # noqa: BLE001 - a failed town is stated in the file, not hidden
        print(f"{town}: Overpass failed ({exc})")
        return None


def fetch_town_with_retry(town: str, post=requests.post, sleep=time.sleep) -> list[dict] | None:
    """Item 392: up to three attempts, waiting 30 s then 120 s between them."""
    rows = fetch_town(town, post)
    for delay in RETRY_DELAYS:
        if rows is not None:
            break
        sleep(delay)
        rows = fetch_town(town, post)
    return rows


def load_last_good(town: str, directory: Path = LAST_GOOD_DIR) -> dict | None:
    try:
        data = json.loads((directory / f"{town.lower().replace(' ', '-')}.json").read_text(encoding="utf-8"))
        return data if isinstance(data.get("rows"), list) and data.get("date") else None
    except (OSError, ValueError, AttributeError):
        return None


def save_last_good(town: str, rows: list[dict], today: str, directory: Path = LAST_GOOD_DIR) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{town.lower().replace(' ', '-')}.json").write_text(json.dumps({"date": today, "rows": rows}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def gather_towns(now: datetime, fetch=None, sleep=None, directory: Path | None = None) -> tuple[dict, dict]:
    """Each town's rows, a failed query falling back to that town's last good
    result (item 392). Returns (towns, stale), `stale` mapping a town shown from
    an earlier run to that run's date ("Oct 23")."""
    fetch = fetch or (lambda t: fetch_town_with_retry(t, sleep=sleep or time.sleep))
    sleep = sleep or time.sleep
    directory = directory or LAST_GOOD_DIR
    towns, stale = {}, {}
    for i, town in enumerate(TOWNS):
        if i:
            sleep(TOWN_SPACING)
        rows = fetch(town)
        if rows is not None:
            save_last_good(town, rows, now.strftime("%Y-%m-%d"), directory)
        else:
            previous = load_last_good(town, directory)
            if previous:
                rows = previous["rows"]
                day = datetime.fromisoformat(previous["date"])
                stale[town] = f"{day.strftime('%b')} {day.day}"
        towns[town] = rows
    return towns, stale


def main() -> int:
    now = datetime.now(timezone.utc)
    towns, stale = gather_towns(now)
    if all(rows is None for rows in towns.values()):
        print("Every Overpass query failed; leaving OUTREACH_PROSPECTS.md as it was.")
        return 1
    OUTPUT_PATH.write_text(render_markdown(towns, now, warm_prospects.load_registry(), stale), encoding="utf-8")
    print("Wrote", OUTPUT_PATH, {t: (len(r) if r is not None else None) for t, r in towns.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
