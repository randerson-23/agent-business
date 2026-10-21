"""Heuristic, best-effort tagging for events and evergreen items.

Same philosophy as fetchers.py: never fatal, never blocks the build. A
missing or wrong tag is a minor quality issue, not a bug - worst case an
event just doesn't show up under a filter it arguably belongs in.

Curated content (evergreen entries in config/regions/*.yaml) can set tags
explicitly; fetched events get tags inferred from their title+detail text.
"""
from __future__ import annotations

import re as _re
from datetime import date as _date

# Order matters only for readability; a piece of text can match many tags.
# Keep keywords lowercase - matching is done against lowercased text.
TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "kid_friendly": (
        # " kid " (not bare "kid"), same substring-false-positive fix as
        # "art"/"hall"/"pup" below - unpadded, "kid" is a literal prefix
        # of "kidney", so a real fetched title ("Kidney Foundation Walk")
        # was tagging as kid-friendly. "kids" (plural, below) already
        # covers the far more common phrasing ("Kids' Night", "Kids Fun
        # Run") without this risk, since no common word is "kids" + more
        # letters the way "kidney" extends "kid".
        " kid ", "kids", "child", "children", "family", "toddler", "preschool",
        "storytime", "story time", "youth", "playgroup", "craft",
    ),
    "dog_friendly": (
        # " pup " (not bare "pup") - unpadded, "pup" is a literal prefix
        # of "puppet"/"puppetry", so a library puppet show (a genuinely
        # common, non-dog kids' program) was tagging as dog-friendly.
        # "puppy" (below) already covers the common phrasing.
        "dog", "dogs", " pup ", "puppy", "canine", "pet friendly", "pet-friendly",
    ),
    "free": ("free admission", "free event", "no cost", "no charge", " free "),
    "indoor": (
        # " hall " (not bare "hall") - unpadded, "hall" is a literal
        # prefix of "Halloween", so any Halloween event (usually an
        # outdoor parade or trick-or-treat, the opposite of indoor) was
        # tagging as indoor purely from that substring.
        "library", "indoor", "museum", "theater", "theatre", "gym", " hall ",
    ),
    "outdoor": (
        "outdoor", "trail", "farmers market", "festival", "parade",
        "concert in the park", "5k", "fireworks",
    ),
    "food": ("food", "tasting", "restaurant", "brewery", "bakery", "farmers market"),
    "art_culture": (
        # " art" (leading space only, no trailing space needed) - unpadded,
        # "art" is a literal substring of "party"/"smart"/"start"/
        # "apartment"/"heart"/"chart"/"depart" (any word with "art"
        # preceded by a letter), so common event titles like "Block
        # Party" were tagging as arts & culture. Leading-space-only still
        # matches "arts", "artist", "artistic", "artwork" - only a word
        # that *starts* with "art" should match, and none of those false
        # positives do.
        " art", "museum", "gallery", "concert", "music", "theater", "theatre", "exhibit",
    ),
    # Age bands, orthogonal to kid_friendly (which stays the broad 0-17
    # umbrella) - ROADMAP.md Phase 11 #45. "Kid-friendly" spans a 17-year
    # range; Red Tricycle's flagship improvement on acquisition by
    # Tinybeans was personalizing by a child's actual age, not just a
    # blanket "family" flag. A single event can match more than one band
    # (rare but real, e.g. a mixed-age storytime) - not deduplicated,
    # same as every other tag here.
    "toddler": (
        # " baby " (not bare "baby") - unpadded, "baby" is a literal
        # prefix of "babysitting"/"babysitter"/"babysit", so a real,
        # common library/park district program ("Babysitting Basics
        # Certification Course", usually aimed at tweens/teens learning
        # to care for younger kids, not the toddlers themselves) was
        # tagging as a toddler event purely from that substring. "babies"
        # (plural, below) already covers the common phrasing without
        # this risk - no common word is "babies" + more letters.
        "toddler", " baby ", "babies", "infant", "little ones", "ages 0-2", "ages 1-3", "ages 2-3",
    ),
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


_NOT_A_KIDS_CRAFT = _re.compile(r"hand-?craft(?:ed)?|craft (?:beer|cocktail|brew|spirit|distill)\w*")
ADULT_SIGNALS: tuple[str, ...] = (
    "21+", "ages 21", "speakeasy", "bourbon", "cocktail", "wine tasting", "beer tasting",
    "brewery", "happy hour", "bar crawl", "adults only",
)


# ROADMAP.md item 354: "park" means a place outdoors only as a word of its own,
# never "Park District", "Park Ridge", "parking", "parker" or "parkway".
_OUTDOOR_PARK = _re.compile(r"(?<![a-z])park(?![a-z])(?!\s+(?:district|ridge|avenue|ave\b|street|st\b|road|rd\b|place|plaza))")


def infer_tags(*text_parts: str, section: str = "") -> list[str]:
    """Infer tags from the title and description (`text_parts`), plus the
    source's section name (`section`) for every tag except "outdoor": a
    section called "Park District Events" says where the listing came from,
    not that the event is outdoors (item 354).

    Returns a sorted list of tag ids for stable output/testing.
    """
    text = " " + " ".join(p for p in text_parts if p).lower() + " "
    haystack = " " + " ".join(p for p in (*text_parts, section) if p).lower() + " "
    if not haystack.strip():
        return []
    # ROADMAP.md item 333: "craft" in a drinks sense is not a kids' craft.
    kid_haystack = _NOT_A_KIDS_CRAFT.sub(" ", haystack)
    matched = set()
    for tag, keywords in TAG_KEYWORDS.items():
        hay = kid_haystack if tag == "kid_friendly" else text if tag == "outdoor" else haystack
        if any(keyword in hay for keyword in keywords) or (tag == "outdoor" and _OUTDOOR_PARK.search(text)):
            matched.add(tag)
    # An adult signal only ever removes the kid-friendly tag.
    if "kid_friendly" in matched and any(signal in haystack for signal in ADULT_SIGNALS):
        matched.discard("kid_friendly")
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


# ROADMAP.md item 327: a registration-opens date, only from explicit phrases.
_MONTHS = {m: i for i, m in enumerate(
    ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"), 1)}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True)) + "|" + "|".join(m[:3] for m in _MONTHS if m != "may") + "|sept"
_DATE_RE = rf"(?:(?:mon|tues?|wed(?:nes)?|thu(?:rs?)?|fri|sat(?:ur)?|sun)[a-z]*\.?,?\s+)?({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?"
_REGISTRATION_PHRASES = (
    r"registration\s*(?:is\s+)?(?:required\s*[,;:.-]?\s*)?(?:begin|begins|beginning|opens|open|starts|start|starting)\s+(?:on\s+)?",
    r"sign[- ]?ups?\s+(?:begin|begins|beginning|opens|open|starts|start|starting)\s+(?:on\s+)?",
    r"register(?:ing)?\s+(?:begins|beginning|opens|starts|starting)\s+(?:on\s+)?",
)
_REGISTRATION_RE = _re.compile("(?:" + "|".join(_REGISTRATION_PHRASES) + ")" + _DATE_RE, _re.IGNORECASE)


def parse_registration_opens(text: str | None, event_date: _date | None) -> _date | None:
    """The date registration opens, from phrases like "registration begins
    October 21", "registration required, beginning Oct. 21st" or "sign up
    starting Oct 21". The year is the event's (or the year written). Only a
    date strictly earlier than the event is accepted; anything ambiguous or
    later is dropped, never guessed."""
    if not text or event_date is None:
        return None
    found = set()
    for m in _REGISTRATION_RE.finditer(text):
        month = _MONTHS.get(m.group(1).lower()) or next((n for name, n in _MONTHS.items() if name.startswith(m.group(1).lower()[:3])), None)
        try:
            found.add(_date(int(m.group(3)) if m.group(3) else event_date.year, month, int(m.group(2))))
        except (ValueError, TypeError):
            continue
    if len(found) != 1:
        return None
    opens = found.pop()
    return opens if opens < event_date else None
