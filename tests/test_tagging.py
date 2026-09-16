import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tagging import infer_tags, is_informational, merge_default_tags, tag_display  # noqa: E402


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


def test_infer_tags_toddler_age_band():
    tags = infer_tags("Baby & Me Playgroup", "For infants and toddlers ages 0-2.")
    assert "toddler" in tags


def test_infer_tags_elementary_age_band():
    tags = infer_tags("Elementary STEM Club", "For school age kids in kindergarten through grade 5.")
    assert "elementary" in tags


def test_infer_tags_teen_age_band():
    tags = infer_tags("Teen Game Night", "Open to middle school and high school students.")
    assert "teen" in tags


def test_infer_tags_teen_does_not_false_positive_on_number_words():
    # "teen"/"tween" are substrings of number words (thirTEEN, fourTEEN,
    # beTWEEN) - a headcount in a description shouldn't tag an event as
    # teen-oriented.
    tags = infer_tags("Volunteer Cleanup Day", "Thirteen volunteers showed up between 9 and 11am.")
    assert "teen" not in tags


def test_tag_display_known_tag():
    display = tag_display("dog_friendly")
    assert display["label"] == "Dog-friendly"
    assert display["emoji"]
    assert display["hue"] == "amber"


def test_tag_display_age_band_tags():
    assert tag_display("toddler")["hue"] == "lime"
    assert tag_display("elementary")["hue"] == "cyan"
    assert tag_display("teen")["hue"] == "indigo"


def test_tag_display_unknown_tag_has_safe_fallback():
    display = tag_display("wheelchair_accessible")
    assert display["label"] == "Wheelchair Accessible"
    assert display["emoji"]
    assert display["hue"] == "gray"


def test_merge_default_tags_adds_without_removing():
    inferred = ["kid_friendly", "outdoor"]
    merged = merge_default_tags(["free"], inferred)
    assert merged == ["kid_friendly", "outdoor", "free"]


def test_merge_default_tags_does_not_duplicate():
    merged = merge_default_tags(["free"], ["free", "outdoor"])
    assert merged == ["free", "outdoor"]


def test_is_informational_detects_school_half_day():
    # ROADMAP.md Phase 11 #90: the real title that shipped as a subject-
    # line headline before this fix - a synthetic phrase would pass a
    # broken implementation, so this uses the actual D57 title.
    assert is_informational("Half-Day Student Attendance (Grades 1-8)", "")


def test_is_informational_detects_office_and_collection_closures():
    assert is_informational("Village Hall Closed for the Holiday", "")
    assert is_informational("", "No refuse collection Monday - trash pickup delayed one day.")


def test_is_informational_does_not_false_positive_on_a_real_event():
    # The keywords are deliberately specific phrases, not bare "holiday"
    # or "closing" - either would misclassify real events like these.
    assert not is_informational("Holiday Craft Fair", "Make ornaments and cards for the season.")
    assert not is_informational("Fall Exhibit Closing Weekend", "Last chance to see the exhibit.")


def test_is_informational_handles_empty_and_none_text():
    assert not is_informational("", "")
    assert not is_informational()


def test_merge_default_tags_ignores_empty_and_bad_values():
    # Fail-soft: a missing, empty, or wrongly-typed config value is ignored
    # rather than raising, same as the rest of the tagging module.
    assert merge_default_tags(None, ["outdoor"]) == ["outdoor"]
    assert merge_default_tags([], ["outdoor"]) == ["outdoor"]
    assert merge_default_tags("free", ["outdoor"]) == ["outdoor"]
    assert merge_default_tags([None, "", "free"], ["outdoor"]) == ["outdoor", "free"]
