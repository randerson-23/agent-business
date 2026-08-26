#!/usr/bin/env python3
"""Build the weekly 60056 digest: fetch sources, render docs/index.html.

Usage:
    python3 scripts/build_digest.py

Designed to run unattended from a scheduled GitHub Actions workflow. Every
network call is fail-soft (see fetchers.py) so a single broken source never
blocks publication — the section just falls back to an "no live updates"
message, and the evergreen block always renders.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).parent))
from fetchers import FETCHERS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("build_digest")

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
TEMPLATES_DIR = ROOT / "templates"
OUTPUT_DIR = ROOT / "docs"
ARCHIVE_DIR = OUTPUT_DIR / "archive"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def fetch_all_sources(sources_cfg: dict) -> list[dict]:
    blocks = []
    for source in sources_cfg.get("sources", []):
        if not source.get("enabled", True):
            continue
        fetcher = FETCHERS.get(source["type"])
        if fetcher is None:
            logger.warning("Unknown source type %r for %s", source["type"], source["name"])
            items = []
        else:
            logger.info("Fetching %s (%s)", source["name"], source["type"])
            items = fetcher(source["url"], keywords=source.get("keywords"))
            logger.info("  -> %d item(s)", len(items))
        blocks.append({"section": source["section"], "events": items})
    return blocks


def resolve_sponsor(sponsors_cfg: dict) -> dict:
    active_id = sponsors_cfg.get("active")
    if active_id and active_id != "none":
        for entry in sponsors_cfg.get("history", []):
            if entry.get("id") == active_id:
                return entry
    return sponsors_cfg.get("house_ad", {"title": "Sponsor this spot", "detail": "", "url": ""})


def render(blocks: list[dict], sponsor: dict, evergreen: list[dict]) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("digest.html.j2")
    now = datetime.now(timezone.utc)
    return template.render(
        issue_date=now.strftime("%B %d, %Y"),
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        sponsor=sponsor,
        blocks=blocks,
        evergreen=evergreen,
    )


def main() -> None:
    sources_cfg = load_yaml(CONFIG_DIR / "sources.yaml")
    sponsors_cfg = load_yaml(CONFIG_DIR / "sponsors.yaml")

    blocks = fetch_all_sources(sources_cfg)
    sponsor = resolve_sponsor(sponsors_cfg)
    evergreen = sources_cfg.get("evergreen", [])

    html = render(blocks, sponsor, evergreen)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    index_path = OUTPUT_DIR / "index.html"
    index_path.write_text(html, encoding="utf-8")
    logger.info("Wrote %s", index_path)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive_path = ARCHIVE_DIR / f"{stamp}.html"
    archive_path.write_text(html, encoding="utf-8")
    logger.info("Wrote %s", archive_path)

    nojekyll = OUTPUT_DIR / ".nojekyll"
    nojekyll.touch()


if __name__ == "__main__":
    main()
