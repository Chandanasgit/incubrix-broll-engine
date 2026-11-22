from app.align import align_script


def asr(spec):
    return [{"word": " " + w, "start": s, "end": e} for w, s, e in spec]


def texts(words):
    return [w["word"].strip() for w in words]


def test_exact_match_keeps_times():
    out = align_script("Hello big world.", asr([("Hello", 0, 1), ("big", 1, 2), ("world.", 2, 3)]), 3.0)
    assert texts(out) == ["Hello", "big", "world."]
    assert [(w["start"], w["end"]) for w in out] == [(0, 1), (1, 2), (2, 3)]


def test_misheard_word_uses_script_text_and_asr_time():
    heard = asr([("Sunny", 0, 1), ("Jews", 1, 2), ("a", 2, 2.5), ("spot", 2.5, 3)])
    out = align_script("Sunny choose a spot", heard, 3.0)
    assert texts(out) == ["Sunny", "choose", "a", "spot"]
    assert (out[1]["start"], out[1]["end"]) == (1, 2)


def test_missing_word_is_interpolated_in_order():
    heard = asr([("Plant", 0, 1), ("seeds", 2, 3)])
    out = align_script("Plant your seeds", heard, 3.0)
    assert texts(out) == ["Plant", "your", "seeds"]
    assert 1 <= out[1]["start"] <= out[1]["end"] <= 2


def test_extra_heard_words_are_ignored():
    heard = asr([("Um", 0, 0.5), ("Plant", 0.5, 1), ("seeds", 1, 2)])
    assert texts(align_script("Plant seeds", heard, 2.0)) == ["Plant", "seeds"]


def test_times_never_go_backwards():
    heard = asr([("a", 0, 2), ("b", 1, 1.5), ("c", 3, 4)])
    out = align_script("a b c", heard, 4.0)
    for x, y in zip(out, out[1:]):
        assert x["end"] <= y["start"] + 1e-9
    assert all(w["end"] >= w["start"] for w in out)


def test_nothing_heard_returns_empty():
    assert align_script("hello", [], 2.0) == []
