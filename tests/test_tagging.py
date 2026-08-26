import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tagging import infer_tags, tag_display  # noqa: E402


def test_infer_tags_kid_and_indoor():
    tags = infer_tags("Toddler Storytime", "Join us at the library for songs and stories.")
    assert "kid_friendly" in tags
    assert "indoor" in tags


def test_infer_tags_dog_and_outdoor():
    tags = infer_tags("Dogs in the Park Meetup", "Bring your pup to the off-leash trail.")
    assert "dog_friendly" in tags
    assert "outdoor" in tags


def test_infer_tags_free():
    tags = infer_tags("Summer Concert Series", "Free admission, bring a lawn chair.")
    assert "free" in tags


def test_infer_tags_no_match_returns_empty_list():
    assert infer_tags("Board Meeting Notice", "Village board meets Tuesday.") == []


def test_infer_tags_handles_empty_and_none_text():
    assert infer_tags("", "") == []
    assert infer_tags() == []


def test_infer_tags_is_case_insensitive_and_sorted():
    tags = infer_tags("KIDS CRAFT CAMP")
    assert tags == sorted(tags)
    assert "kid_friendly" in tags


def test_tag_display_known_tag():
    display = tag_display("dog_friendly")
    assert display["label"] == "Dog-friendly"
    assert display["emoji"]
    assert display["hue"] == "amber"


def test_tag_display_unknown_tag_has_safe_fallback():
    display = tag_display("wheelchair_accessible")
    assert display["label"] == "Wheelchair Accessible"
    assert display["emoji"]
    assert display["hue"] == "gray"
