"""Regression tests for the "bird" tag bug.

DETR's literal COCO "bird" class was firing on food-styling photography
(garnishes, textures, plating props) and was never excluded, and a comma-split
bug fanned single weak ImageNet predictions out into several bird-related
synonyms. These tests pin down both fixes so the bug can't silently come back.

No network calls — HuggingFaceService is exercised directly with mocked
Hugging Face API payload shapes.
"""

from __future__ import annotations

from services.huggingface import HuggingFaceService


def make_service() -> HuggingFaceService:
    return HuggingFaceService(api_token="test-token")


def test_clean_tag_filters_bird():
    service = make_service()
    assert service._clean_tag("bird") == ""
    assert service._clean_tag("Bird") == ""
    assert service._clean_tag("BIRD") == ""


def test_detection_never_returns_bird_above_threshold():
    service = make_service()
    payload = [{"label": "bird", "score": 0.35}, {"label": "plate", "score": 0.9}]
    tags = service._parse_detection_tags(payload)
    assert "bird" not in tags
    assert "plate" in tags


def test_detection_filters_bird_even_at_high_confidence():
    service = make_service()
    payload = [{"label": "bird", "score": 0.99}]
    tags = service._parse_detection_tags(payload)
    assert tags == []


def test_classification_fan_out_no_longer_multiplies_bird_synonyms():
    service = make_service()
    payload = [
        {
            "label": "indigo bunting, indigo finch, indigo bird, Passerina cyanea",
            "score": 0.42,
        }
    ]
    tags = service._parse_classification_tags(payload)
    # Before the fix, this single weak prediction fanned out into 4 tags
    # (one per comma-separated synonym). Only the first/canonical synonym
    # should ever be attempted now.
    assert len(tags) <= 1
    assert "indigo finch" not in tags
    assert "indigo bird" not in tags
    assert "passerina cyanea" not in tags


def test_classification_filters_literal_bird_as_first_synonym():
    service = make_service()
    payload = [{"label": "bird, flying animal, avian creature", "score": 0.5}]
    tags = service._parse_classification_tags(payload)
    assert tags == []


def test_classification_only_takes_first_synonym_for_non_filtered_labels():
    service = make_service()
    payload = [{"label": "cheeseburger, hamburger, beefburger", "score": 0.5}]
    tags = service._parse_classification_tags(payload)
    assert tags == ["cheeseburger"]
    assert "hamburger" not in tags
    assert "beefburger" not in tags


def test_legitimate_food_tags_survive_the_blocklist():
    service = make_service()
    for label in ("chicken", "poultry", "plate", "kitchen", "pizza"):
        assert service._clean_tag(label) == label


def test_translate_tag_drops_untranslated_words_instead_of_showing_english():
    service = make_service()
    assert service._translate_tag("chicken") == "poulet"
    assert service._translate_tag("some-made-up-word-not-in-the-dict") is None
