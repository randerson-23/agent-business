#!/usr/bin/env python3
"""Preview a future issue (ROADMAP.md item 553).

`python scripts/build_preview.py --as-of 2026-11-25` builds the whole site in a
throwaway copy of the repository with the build clock set to the evening before
that delivery (build_digest.as_of_clock), then copies only the email previews
into docs/previews/<date>/: the shared preview and one per town. The live pages,
data files, sitemap and the send are never touched, and a preview build never
submits anything to IndexNow or Bing.

`--next-special` picks the next moved delivery from config/newsletter.yaml's
`delivery_overrides` within the next 10 days (the Thanksgiving, winter-break and
New Year's issues); with none due it does nothing. preview-issue.yml runs it.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PREVIEWS_DIR = ROOT / "docs" / "previews"
COPY_IGNORE = shutil.ignore_patterns(".git", "docs", "__pycache__", ".pytest_cache", "node_modules")
NOINDEX = '<meta name="robots" content="noindex">'


def next_special_delivery(today: date, overrides: dict, days: int = 10) -> date | None:
    """The soonest moved delivery (an override's new date) from today to
    `days` ahead, or None."""
    found = []
    for _, moved in (overrides or {}).items():
        try:
            day = datetime.fromisoformat(str(moved)).date()
        except ValueError:
            continue
        if today <= day <= today + timedelta(days=days):
            found.append(day)
    return min(found) if found else None


def future_specials(today: date, overrides: dict) -> list[date]:
    """ROADMAP.md item 562: every moved delivery from today on, soonest first,
    whatever the distance; past ones are skipped."""
    days = set()
    for moved in (overrides or {}).values():
        try:
            day = datetime.fromisoformat(str(moved)).date()
        except ValueError:
            continue
        if day >= today:
            days.add(day)
    return sorted(days)


def add_preview_header(html: str, built: date, delivery: date) -> str:
    """Item 562: say when the preview was built and that the data can change."""
    note = (f'<meta name="preview-built" content="{built.isoformat()}">'
            f'<div style="font:14px sans-serif;background:#fff4c2;color:#3a2c00;padding:8px 12px;text-align:center;">'
            f'Preview built {built.strftime("%b")} {built.day}; data may change before {delivery.strftime("%a %b")} {delivery.day}.</div>')
    i = html.lower().find("<body")
    if i < 0:
        return note + html
    j = html.find(">", i) + 1
    return html[:j] + note + html[j:]


def write_index(previews_dir: Path = PREVIEWS_DIR) -> Path | None:
    """ROADMAP.md item 564: docs/previews/index.html (noindex, linked from
    nowhere public), one line per preview folder, newest delivery first."""
    import re

    rows = []
    for d in sorted((p for p in previews_dir.glob("*") if p.is_dir()), reverse=True):
        try:
            delivery = date.fromisoformat(d.name)
        except ValueError:
            continue
        shared = d / "combined-email-preview.html"
        if not shared.exists():
            continue
        m = re.search(r'name="preview-built" content="([0-9-]+)"', shared.read_text(encoding="utf-8"))
        built = m.group(1) if m else "unknown"
        towns = " · ".join(f'<a href="{d.name}/email-preview/{t.name}">{t.stem.rsplit("-", 1)[0].replace("-", " ").title()}</a>' for t in sorted((d / "email-preview").glob("*.html")))
        rows.append(f'<li><strong><a href="{d.name}/combined-email-preview.html">{delivery.strftime("%a %b")} {delivery.day}, {delivery.year}</a></strong> &middot; built {built}'
                    + (f'<br><small>{towns}</small>' if towns else "") + "</li>")
    if not rows:
        return None
    page = ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">" + NOINDEX +
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Issue previews</title>"
            "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:640px;margin:24px auto;padding:0 16px}li{margin:0 0 12px}</style></head>"
            "<body><h1>Upcoming issue previews</h1><p>Built as of each delivery date. Not linked from the site.</p><ul>" + "".join(rows) + "</ul></body></html>\n")
    out = previews_dir / "index.html"
    out.write_text(page, encoding="utf-8")
    return out


def add_noindex(html: str) -> str:
    """A preview is for reading, not search: noindex once, right after <head>."""
    if NOINDEX in html:
        return html
    i = html.lower().find("<head>")
    return html[: i + 6] + NOINDEX + html[i + 6 :] if i >= 0 else NOINDEX + html


def preview_files(built_docs: Path) -> list[tuple[Path, str]]:
    """(source, name under docs/previews/<date>/) for each preview the build wrote."""
    out = []
    shared = built_docs / "combined-email-preview.html"
    if shared.exists():
        out.append((shared, "combined-email-preview.html"))
    for town in sorted((built_docs / "email-preview").glob("*.html")):
        out.append((town, f"email-preview/{town.name}"))
    return out


def build_preview(delivery: date) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "repo"
        shutil.copytree(ROOT, work, ignore=COPY_IGNORE)
        (work / "docs").mkdir()
        env = {k: v for k, v in os.environ.items() if k not in ("BING_WEBMASTER_API_KEY",)}
        env["AS_OF"] = delivery.isoformat()
        result = subprocess.run([sys.executable, str(work / "scripts" / "build_digest.py")], cwd=work, env=env)
        files = preview_files(work / "docs")
        if not files:
            raise SystemExit(f"The preview build wrote no email preview (exit {result.returncode}).")
        dest = PREVIEWS_DIR / delivery.isoformat()
        shutil.rmtree(dest, ignore_errors=True)
        built = datetime.now(timezone.utc).date()
        for src, name in files:
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(add_preview_header(add_noindex(src.read_text(encoding="utf-8")), built, delivery), encoding="utf-8")
        write_index()
        print(f"Wrote {len(files)} preview file(s) to {dest.relative_to(ROOT)} (build exit {result.returncode}).")
        return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--as-of", help="delivery date, YYYY-MM-DD")
    group.add_argument("--next-special", action="store_true", help="the next moved delivery within 10 days")
    group.add_argument("--all-specials", action="store_true", help="every moved delivery from today on (item 562)")
    args = parser.parse_args(argv)
    if args.all_specials:
        cfg = yaml.safe_load((ROOT / "config" / "newsletter.yaml").read_text(encoding="utf-8")) or {}
        days = future_specials(datetime.now(timezone.utc).date(), cfg.get("delivery_overrides") or {})
        if not days:
            print("No future special delivery; nothing to preview.")
            return 0
        for day in days:
            build_preview(day)
        return 0
    if args.as_of:
        delivery = date.fromisoformat(args.as_of)
    else:
        cfg = yaml.safe_load((ROOT / "config" / "newsletter.yaml").read_text(encoding="utf-8")) or {}
        delivery = next_special_delivery(datetime.now(timezone.utc).date(), cfg.get("delivery_overrides") or {})
        if delivery is None:
            print("No special delivery in the next 10 days; nothing to preview.")
            return 0
    build_preview(delivery)
    return 0


if __name__ == "__main__":
    sys.exit(main())
