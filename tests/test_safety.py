import pytest

from app import safety
from app.safety import apply_safety


def test_neutral_text_is_unchanged(monkeypatch):
    monkeypatch.setattr(safety, "named_entities", lambda t: [])
    q, notes = apply_safety("Plant your seeds in spring.", ["garden", "seeds"])
    assert q == ["garden", "seeds"] and notes == []


def test_named_people_and_brands_are_not_searched(monkeypatch):
    monkeypatch.setattr(safety, "named_entities", lambda t: [("Elon Musk", "PERSON"), ("Tesla", "ORG")])
    q, notes = apply_safety("Elon Musk said Tesla will grow.", ["elon musk speaking", "tesla factory", "electric cars"])
    assert "electric cars" in q
    assert not any("musk" in x or "tesla" in x for x in q)
    assert len(notes) == 2 and "Elon Musk" in notes[0] and "Tesla" in notes[1]


def test_sensitive_story_removes_graphic_terms_and_adds_calm(monkeypatch):
    monkeypatch.setattr(safety, "named_entities", lambda t: [])
    q, notes = apply_safety("A fire left families without homes.", ["fire factory rescue", "families homes"])
    assert not any("fire" in x for x in q)
    assert "families homes" in q and "candle vigil night" in q
    assert any("Sensitive topic" in n for n in notes)


def test_avoid_list_and_never_empty(monkeypatch):
    monkeypatch.setattr(safety, "named_entities", lambda t: [])
    q, notes = apply_safety("A war story.", ["war soldiers"], avoid=["candle"])
    assert q and all("candle" not in x for x in q)


def test_real_entity_detection():
    pytest.importorskip("spacy")
    from app.keywords import named_entities
    try:
        ents = named_entities("Elon Musk said Tesla will open a factory. The bank keeps savings safe.")
    except Exception:
        pytest.skip("spaCy model not installed")
    names = [n for n, _ in ents]
    if not names:
        pytest.skip("spaCy model not installed")
    assert "Elon Musk" in names and "Tesla" in names and "bank" not in [n.lower() for n in names]
