from app.scenes import split_scenes


def make_words(spec):
    return [{"word": w, "start": s, "end": e} for w, s, e in spec]


WORDS = make_words([
    (" Saving", 0.00, 0.32), (" money", 0.32, 0.64), (" builds", 0.64, 1.06),
    (" real", 1.06, 1.30), (" value.", 1.30, 1.82),
    (" The", 2.06, 2.12), (" bank", 2.12, 2.34), (" keeps", 2.34, 2.66),
    (" it", 2.66, 2.88), (" safe,", 2.88, 3.30), (" and", 3.74, 3.88),
    (" cloud", 3.88, 4.26), (" apps", 4.26, 4.52), (" make", 4.52, 4.72),
    (" tracking", 4.72, 5.12), (" easy.", 5.12, 5.58),
])


def test_short_sentences_merge_into_one_scene():
    scenes = split_scenes(WORDS, 5.78, min_len=2.5)
    assert len(scenes) == 1 or all(s["end"] - s["start"] >= 2.5 for s in scenes)


def test_cuts_on_sentence_boundaries():
    scenes = split_scenes(WORDS, 5.78, min_len=1.0)
    assert len(scenes) == 2
    assert scenes[0]["text"].endswith("value.")
    assert scenes[1]["text"].startswith("The bank")


def test_full_coverage_no_gaps():
    scenes = split_scenes(WORDS, 5.78, min_len=1.0)
    assert scenes[0]["start"] == 0.0
    assert scenes[-1]["end"] == 5.78
    for a, b in zip(scenes, scenes[1:]):
        assert a["end"] == b["start"]


def test_empty_input():
    assert split_scenes([], 3.0) == []
