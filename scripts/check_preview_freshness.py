#!/usr/bin/env python3
"""ROADMAP.md item 569: fail when a future special delivery has no preview, or
its preview is older than MAX_AGE (judged by the build date the preview carries,
so "older than 36 hours" means built before yesterday). Run by send-watchdog.yml;
a failed run emails the owner."""
from __future__ import annotations

import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PREVIEWS_DIR = ROOT / "docs" / "previews"
MAX_AGE = timedelta(hours=36)


def stale_previews(today: date, overrides: dict, previews_dir: Path = PREVIEWS_DIR, max_age: timedelta = MAX_AGE) -> list[str]:
    problems = []
    oldest_ok = today - timedelta(days=max(1, max_age.days + (1 if max_age.seconds else 0)) - 1)
    for moved in (overrides or {}).values():
        try:
            delivery = datetime.fromisoformat(str(moved)).date()
        except ValueError:
            continue
        if delivery < today:
            continue
        page = previews_dir / delivery.isoformat() / "combined-email-preview.html"
        if not page.exists():
            problems.append(f"{delivery}: no preview")
            continue
        m = re.search(r'name="preview-built" content="([0-9-]+)"', page.read_text(encoding="utf-8"))
        built = date.fromisoformat(m.group(1)) if m else None
        if built is None or built < oldest_ok:
            problems.append(f"{delivery}: preview built {built or 'unknown'}, older than {max_age.total_seconds() / 3600:.0f} hours")
    return problems


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config" / "newsletter.yaml").read_text(encoding="utf-8")) or {}
    problems = stale_previews(datetime.now(timezone.utc).date(), cfg.get("delivery_overrides") or {})
    for p in problems:
        print(f"::error::Issue preview stale: {p}. Check preview-issue.yml's recent runs.")
    if not problems:
        print("OK: every future special delivery has a fresh preview.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
