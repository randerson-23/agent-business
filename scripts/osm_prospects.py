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

import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "OUTREACH_PROSPECTS.md"
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


def render_markdown(towns: dict[str, list[dict] | None], now: datetime) -> str:
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
    for town, rows in towns.items():
        lines += [f"## {town}", ""]
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


def main() -> int:
    towns = {town: fetch_town(town) for town in TOWNS}
    if all(rows is None for rows in towns.values()):
        print("Every Overpass query failed; leaving OUTREACH_PROSPECTS.md as it was.")
        return 1
    OUTPUT_PATH.write_text(render_markdown(towns, datetime.now(timezone.utc)), encoding="utf-8")
    print("Wrote", OUTPUT_PATH, {t: (len(r) if r is not None else None) for t, r in towns.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
