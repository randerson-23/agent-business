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
