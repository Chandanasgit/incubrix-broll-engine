from app.providers.base import Clip, ProviderError
from app.ranker import TagScorer, choose_clip, gather


def clip(cid, tags, dur=10.0, provider="mock"):
    return Clip(provider=provider, clip_id=cid, page_url="", download_url="", thumbnail_url="",
                width=1920, height=1080, duration=dur, tags=tags,
                licence="test", attribution="test")


class OkProvider:
    name = "ok"
    def search(self, q, limit=8):
        return [clip("a", ["bank"], provider="ok"), clip("b", ["river"], provider="ok")]


class DownProvider:
    name = "down"
    def search(self, q, limit=8):
        raise ProviderError("down")


def test_picks_best_match_by_score():
    cands = [clip("1", ["river", "water"]), clip("2", ["bank", "money"])]
    r = choose_clip("the bank holds money", cands, TagScorer(), used=set())
    assert r["clip"].clip_id == "2"


def test_never_reuses_a_clip():
    cands = [clip("1", ["bank"]), clip("2", ["bank"])]
    first = choose_clip("bank", cands, TagScorer(), used=set())
    used = {("mock", first["clip"].clip_id)}
    second = choose_clip("bank", cands, TagScorer(), used=used)
    assert second["clip"].clip_id != first["clip"].clip_id


def test_returns_none_when_everything_used():
    cands = [clip("1", ["bank"])]
    assert choose_clip("bank", cands, TagScorer(), used={("mock", "1")}) is None


def test_prefers_clips_long_enough():
    cands = [clip("short", ["bank", "money"], dur=2.0), clip("long", ["bank"], dur=9.0)]
    r = choose_clip("bank money", cands, TagScorer(), used=set(), min_duration=5.0)
    assert r["clip"].clip_id == "long"


def test_notes_when_nothing_long_enough():
    r = choose_clip("bank", [clip("s", ["bank"], dur=1.0)], TagScorer(), used=set(), min_duration=5.0)
    assert r is not None and r["notes"]


def test_gather_survives_a_failing_provider():
    clips, errors = gather([DownProvider(), OkProvider()], ["bank", "money"])
    assert len(clips) == 2
    assert errors and "down" in errors[0]
