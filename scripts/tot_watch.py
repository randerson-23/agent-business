#!/usr/bin/env python3
"""Watch each village's trick-or-treat page for late changes (ROADMAP.md item 317).

From Oct 24 to Nov 1 only, fetches each region's `trick_or_treat.url` once per
run, strips the markup, keeps the text around the words trick, treat and
Halloween, and hashes it into `data/tot_watch.json`. When a page's text changes
the script writes the before and after snippets to `tot_watch_report.md`, which
the workflow turns into one GitHub issue. It NEVER edits `hours`: a person or
the build loop confirms new hours from the snippet and edits the region YAML.
One polite request per town per run. Outside the window it does nothing.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
REGIONS_DIR = ROOT / "config" / "regions"
WATCH_PATH = ROOT / "data" / "tot_watch.json"
REPORT_PATH = ROOT / "tot_watch_report.md"
USER_AGENT = "WithinTenBot/1.0 (+https://withintenmiles.com/about/; hello@withintenmiles.com)"
CONTEXT = 160


def in_window(today: date) -> bool:
    return date(today.year, 10, 24) <= today <= date(today.year, 11, 1)


def relevant_text(raw_html: str) -> str:
    """The page's visible text near the trick-or-treat keywords, whitespace
    normalised, so unrelated page changes (a new banner, a date in the
    footer) do not trigger a report."""
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw_html)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", text))
    text = " ".join(text.split())
    spans = [(max(0, m.start() - CONTEXT), min(len(text), m.end() + CONTEXT)) for m in re.finditer(r"(?i)trick|treat|halloween", text)]
    merged: list[list[int]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return " … ".join(text[a:b] for a, b in merged)[:6000]


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def compare(previous: dict | None, text: str) -> dict | None:
    """A change record when the watched text differs from the stored one; None
    for a first sighting or no change."""
    if not previous or previous.get("hash") == digest(text):
        return None
    return {"before": previous.get("snippet", ""), "after": text[:1500]}


def load_watch(path: Path | None = None) -> dict:
    path = path or WATCH_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def region_urls(regions_dir: Path | None = None) -> dict[str, tuple[str, str]]:
    regions_dir = regions_dir or REGIONS_DIR
    found = {}
    for path in sorted(regions_dir.glob("[!_]*.yaml")):
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        url = (cfg.get("trick_or_treat") or {}).get("url")
        if url:
            found[(cfg.get("region") or {}).get("id") or path.stem] = ((cfg.get("region") or {}).get("name") or path.stem, url)
    return found


def main(today: date | None = None) -> int:
    today = today or datetime.now(timezone.utc).date()
    if not in_window(today) and os.environ.get("TOT_WATCH_FORCE") != "1":
        print("Outside Oct 24 - Nov 1; nothing to watch.")
        return 0
    watch = load_watch()
    changes = []
    for region_id, (name, url) in region_urls().items():
        try:
            resp = requests.get(url, timeout=25, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"{name}: could not fetch ({exc}); left as it was.")
            continue
        text = relevant_text(resp.text)
        change = compare(watch.get(region_id), text)
        if change:
            changes.append((name, url, change))
        watch[region_id] = {"hash": digest(text), "snippet": text[:1500], "checked_at": datetime.now(timezone.utc).isoformat(timespec="minutes"), "url": url}
    WATCH_PATH.write_text(json.dumps(watch, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    if changes:
        lines = ["The text around trick-or-treat changed on a village page. **Do not edit hours from this automatically**: read the page, confirm the new hours, then edit the region YAML.", ""]
        for name, url, ch in changes:
            lines += [f"### {name}", f"Page: {url}", "", "**Before**", "", f"> {ch['before'][:900]}", "", "**After**", "", f"> {ch['after'][:900]}", ""]
        REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"changed={len(changes)}\n")
    print(f"{len(changes)} page(s) changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
