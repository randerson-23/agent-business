"""Fail the build if a sitemap page is more than two clicks from the homepage.

ROADMAP.md item 338. Runs against the freshly-built docs/ directory, after
build_digest.py: a breadth-first walk of plain `href`s from docs/index.html,
then a check that every URL in sitemap.xml was reached at depth 2 or less.
"""
import re
import sys
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
BASE = "https://withintenmiles.com/"
MAX_DEPTH = 2


def _page_file(docs_dir: Path, base: str, url: str) -> Path | None:
    path = urlparse(url).path.lstrip("/")
    file = docs_dir / path / "index.html" if not path or path.endswith("/") else docs_dir / path
    if file.is_dir():
        file = file / "index.html"
    return file if file.exists() else None


def link_depths(docs_dir: Path, base: str = BASE) -> dict[str, int]:
    depth = {base: 0}
    queue = [base]
    while queue:
        url = queue.pop(0)
        page = _page_file(docs_dir, base, url)
        if page is None:
            continue
        for href in re.findall(r'href="([^"#][^"]*)"', page.read_text(encoding="utf-8", errors="ignore")):
            target = urldefrag(urljoin(url, href))[0].split("?")[0]
            if target.startswith(base) and target not in depth:
                depth[target] = depth[url] + 1
                queue.append(target)
    return depth


def too_deep(docs_dir: Path, base: str = BASE, max_depth: int = MAX_DEPTH) -> list[tuple[str, int | None]]:
    sitemap = (docs_dir / "sitemap.xml").read_text(encoding="utf-8")
    depth = link_depths(docs_dir, base)
    return [(u, depth.get(u)) for u in re.findall(r"<loc>([^<]+)</loc>", sitemap) if depth.get(u, max_depth + 1) > max_depth]


def main() -> int:
    bad = too_deep(DOCS_DIR)
    if bad:
        print(f"{len(bad)} sitemap page(s) are more than {MAX_DEPTH} clicks from the homepage:")
        for url, d in bad:
            print(f"  {url} (depth {d if d is not None else 'unreachable'})")
        return 1
    print(f"Every sitemap page is within {MAX_DEPTH} clicks of the homepage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
