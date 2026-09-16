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


# A real thing worth knowing about, but not something to plan an outing
# around - a school half-day, a holiday trash-pickup shift, an office
# closure (ROADMAP.md Phase 11 #90, found from a real send: the subject
# line advertised "Half-Day Student Attendance" as if it were an event).
# Deliberately specific phrases, not a bare "holiday" or "closing" -
# either would misclassify a real event like a "Holiday Craft Fair" or a
# seasonal exhibit's "closing weekend".
INFORMATIONAL_KEYWORDS: tuple[str, ...] = (
    "no school", "half day", "half-day", "early dismissal", "institute day",
    "e-learning day", "remote learning day", "no refuse collection",
    "trash pickup", "recycling pickup", "office closed", "village hall closed",
    "closed for the holiday", "school closed", "schools closed",
)


def is_informational(*text_parts: str) -> bool:
    """True for a school-closure/office-closure/no-collection notice - real
    content the D57-style school-calendar feed is deliberately not
    filtered out for (ROADMAP.md Phase 11's config comments call it "a
    real gap no local competitor covers"), but which must never headline
    a subject line or a weekend highlight the way an actual event does.
    """
    haystack = " " + " ".join(p for p in text_parts if p).lower() + " "
    return any(kw in haystack for kw in INFORMATIONAL_KEYWORDS)


def merge_default_tags(default_tags, inferred: list[str]) -> list[str]:
    """Merge a source-level `default_tags` list into the per-item inferred
    tags.

    Some venues' programming is uniformly one way - a shopping centre's
    community events are free, a library's are indoor - and a per-source
    default is more reliable than hoping each listing's wording happens to
    contain a matching keyword. Defaults only ever *add*: they never
    remove a tag the heuristic inferred, and the heuristic can still add
    others on top.

    Same fail-soft philosophy as the rest of this module: a non-list or
    empty value is simply ignored rather than raising.
    """
    if not default_tags or not isinstance(default_tags, (list, tuple)):
        return inferred
    merged = list(inferred)
    for tag in default_tags:
        if isinstance(tag, str) and tag and tag not in merged:
            merged.append(tag)
    return merged


def tag_display(tag_id: str) -> dict[str, str]:
    """Display metadata for a tag id, with a safe fallback for unknown tags
    (e.g. a manually curated tag in config that isn't in TAG_DISPLAY yet).
    """
    return TAG_DISPLAY.get(
        tag_id, {"label": tag_id.replace("_", " ").title(), "emoji": "🏷️", "hue": "gray"}
    )
