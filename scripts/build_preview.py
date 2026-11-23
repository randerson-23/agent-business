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
        for src, name in files:
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(add_noindex(src.read_text(encoding="utf-8")), encoding="utf-8")
        print(f"Wrote {len(files)} preview file(s) to {dest.relative_to(ROOT)} (build exit {result.returncode}).")
        return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--as-of", help="delivery date, YYYY-MM-DD")
    group.add_argument("--next-special", action="store_true", help="the next moved delivery within 10 days")
    args = parser.parse_args(argv)
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
