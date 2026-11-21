import pytest

pytest.importorskip("spacy")

from app.keywords import visual_phrases


def test_drops_time_filler_and_keeps_subject():
    p = visual_phrases("Within weeks, small green shoots will appear.")
    assert p is not None
    assert any("shoots" in x for x in p)
    assert not any("weeks" in x for x in p)


def test_keeps_concrete_nouns():
    p = visual_phrases("First, choose a sunny spot and prepare the soil.")
    assert any("soil" in x for x in p)
    assert not any("first" in x for x in p)
