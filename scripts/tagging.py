"""Heuristic, best-effort tagging for events and evergreen items.

Same philosophy as fetchers.py: never fatal, never blocks the build. A
missing or wrong tag is a minor quality issue, not a bug - worst case an
event just doesn't show up under a filter it arguably belongs in.

Curated content (evergreen entries in config/regions/*.yaml) can set tags
explicitly; fetched events get tags inferred from their title+detail text.
"""
from __future__ import annotations

# Order matters only for readability; a piece of text can match many tags.
# Keep keywords lowercase - matching is done against lowercased text.
TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "kid_friendly": (
        "kid", "kids", "child", "children", "family", "toddler", "preschool",
        "storytime", "story time", "youth", "playgroup", "craft",
    ),
    "dog_friendly": ("dog", "dogs", "pup", "puppy", "canine", "pet friendly", "pet-friendly"),
    "free": ("free admission", "free event", "no cost", "no charge", " free "),
    "indoor": ("library", "indoor", "museum", "theater", "theatre", "gym", "hall"),
    "outdoor": (
        "park", "outdoor", "trail", "farmers market", "festival", "parade",
        "concert in the park", "5k", "fireworks",
    ),
    "food": ("food", "tasting", "restaurant", "brewery", "bakery", "farmers market"),
    "art_culture": ("art", "museum", "gallery", "concert", "music", "theater", "theatre", "exhibit"),
    # Age bands, orthogonal to kid_friendly (which stays the broad 0-17
    # umbrella) - ROADMAP.md Phase 11 #45. "Kid-friendly" spans a 17-year
    # range; Red Tricycle's flagship improvement on acquisition by
    # Tinybeans was personalizing by a child's actual age, not just a
    # blanket "family" flag. A single event can match more than one band
    # (rare but real, e.g. a mixed-age storytime) - not deduplicated,
    # same as every other tag here.
    "toddler": ("toddler", "baby", "babies", "infant", "little ones", "ages 0-2", "ages 1-3", "ages 2-3"),
    "elementary": (
        "elementary", "school age", "school-age", "kindergarten", "grade school",
        "ages 5-10", "ages 6-10", "grades k-5",
    ),
    "teen": (
        # Bare "teen"/"tween" are padded with spaces, same trick as
        # "free" above - unpadded they're substrings of number words
        # (thir-TEEN, four-TEEN, be-TWEEN), a real false-positive risk
        # any event description mentioning a headcount would hit. Their
        # plural/derived forms don't have this problem (no word ends in
        # "-teens" or "-tweens"), so those stay unpadded.
        " teen ", "teens", "teenager", " tween ", "tweens", "middle school",
        "high school", "young adult", "grades 6-12",
    ),
}

# Display metadata for rendering filter chips/badges - label, emoji, and a
# `hue` naming one of the badge color variants defined in the page CSS
# (--hue-<name> custom properties), kept separate from the matching
# keywords above so wording/styling can change freely without touching
# the inference logic.
TAG_DISPLAY: dict[str, dict[str, str]] = {
    "kid_friendly": {"label": "Kid-friendly", "emoji": "🧒", "hue": "pink"},
    "dog_friendly": {"label": "Dog-friendly", "emoji": "🐕", "hue": "amber"},
    "free": {"label": "Free", "emoji": "💵", "hue": "green"},
    "indoor": {"label": "Indoor", "emoji": "🏠", "hue": "blue"},
    "outdoor": {"label": "Outdoor", "emoji": "🌳", "hue": "teal"},
    "food": {"label": "Food & drink", "emoji": "🍽️", "hue": "orange"},
    "art_culture": {"label": "Arts & culture", "emoji": "🎨", "hue": "purple"},
    "toddler": {"label": "Toddler", "emoji": "👶", "hue": "lime"},
    "elementary": {"label": "Elementary age", "emoji": "🎒", "hue": "cyan"},
    "teen": {"label": "Teen", "emoji": "🧑", "hue": "indigo"},
}


def infer_tags(*text_parts: str) -> list[str]:
    """Infer tags from arbitrary text (title, detail, section name, ...).

    Returns a sorted list of tag ids for stable output/testing.
    """
    haystack = " " + " ".join(p for p in text_parts if p).lower() + " "
    if not haystack.strip():
        return []
    matched = {
        tag
        for tag, keywords in TAG_KEYWORDS.items()
        if any(keyword in haystack for keyword in keywords)
    }
    return sorted(matched)


def tag_display(tag_id: str) -> dict[str, str]:
    """Display metadata for a tag id, with a safe fallback for unknown tags
    (e.g. a manually curated tag in config that isn't in TAG_DISPLAY yet).
    """
    return TAG_DISPLAY.get(
        tag_id, {"label": tag_id.replace("_", " ").title(), "emoji": "🏷️", "hue": "gray"}
    )
