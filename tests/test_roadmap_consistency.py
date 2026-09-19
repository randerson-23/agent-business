"""ROADMAP.md item 142: the backlog overstated itself by ~35 items because
a shipped item's ✅ DONE verification note lived a few paragraphs into its
body while the numbered heading kept its original, unmarked wording -
invisible to anyone (or anything) scanning headings to see what's left.

This is a cheap, static guard against that exact drift recurring: an item
whose own body already states it's done must say so on the heading line
too, not just somewhere inside it.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

ROADMAP_PATH = Path(__file__).resolve().parents[1] / "ROADMAP.md"

_ITEM_HEADING = re.compile(r"^(\d+)\.\s")
_BODY_DONE_MARKER = re.compile(r"✅\s*\*{0,2}DONE", re.IGNORECASE)
_HEADING_RESOLVED = re.compile(r"^\d+\.\s*(✅|⚠️)")

# Items whose body legitimately mentions "✅ DONE" without claiming the
# item itself is done - e.g. describing the fix this test itself enforces,
# or quoting another item's marker in passing. Extend this set (with a
# comment naming the item) rather than loosening the regex, which is what
# let the original drift go undetected for 30+ items.
_KNOWN_PROSE_MENTIONS = {142}


def _numbered_items(text: str) -> list[tuple[int, str, str]]:
    """(item number, heading line, body text) for every top-level `N. ` item."""
    lines = text.split("\n")
    starts = [(i, int(m.group(1))) for i, line in enumerate(lines) if (m := _ITEM_HEADING.match(line))]
    items = []
    for idx, (start, num) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        heading = lines[start]
        body = "\n".join(lines[start + 1 : end])
        items.append((num, heading, body))
    return items


def test_no_roadmap_item_reads_open_while_its_own_body_says_done():
    text = ROADMAP_PATH.read_text(encoding="utf-8")
    drifted = [
        num
        for num, heading, body in _numbered_items(text)
        if num not in _KNOWN_PROSE_MENTIONS
        and _BODY_DONE_MARKER.search(body)
        and not _HEADING_RESOLVED.match(heading)
    ]
    assert not drifted, (
        f"Item(s) {drifted} have a '✅ DONE' marker in their body but not on "
        "their own numbered heading - move/add the marker to the heading line "
        "(ROADMAP.md item 142) so the backlog count stays accurate at a glance."
    )
