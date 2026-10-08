"""Fail the build if a generated page's inline JS grows past its budget.

Standalone script (not pytest) so it can run as its own CI step against the
freshly-built docs/ directory, after build_digest.py has run. Only inline
<script> blocks count — JSON-LD structured data is stated content, not code,
so it's excluded from the budget it's meant to police.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"

# The heaviest page is a region's main view (tray widget, filter chips,
# distance sort and the signup runtime all inline). It was ~7.1KB when this
# budget was first set and had grown to 12,115 bytes by 2026-10-08, close
# enough to the old 12,288 cap that the post-signup "open your inbox" button
# (ROADMAP.md item 254, a P1 conversion step) could not fit. Raised to 13,312
# (13KB) for that one feature; the next increase should come out of what is
# already here, not out of this number.
MAX_INLINE_JS_BYTES = 13_312

_SCRIPT_BLOCK = re.compile(
    r'<script(?![^>]*type="application/ld\+json")[^>]*>(.*?)</script>',
    re.S,
)


def inline_js_bytes(html: str) -> int:
    return sum(len(block.encode("utf-8")) for block in _SCRIPT_BLOCK.findall(html))


def main() -> int:
    pages = sorted(DOCS_DIR.glob("**/index.html"))
    if not pages:
        print(f"No pages found under {DOCS_DIR} — run build_digest.py first.")
        return 1

    failures = []
    for page in pages:
        size = inline_js_bytes(page.read_text(encoding="utf-8"))
        if size > MAX_INLINE_JS_BYTES:
            failures.append((page.relative_to(REPO_ROOT), size))

    for page, size in failures:
        print(f"FAIL  {page}: {size} bytes inline JS > {MAX_INLINE_JS_BYTES} budget")

    if failures:
        return 1

    largest = max(inline_js_bytes(p.read_text(encoding="utf-8")) for p in pages)
    print(
        f"OK — {len(pages)} pages checked, largest inline JS payload "
        f"{largest} bytes (budget {MAX_INLINE_JS_BYTES})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
