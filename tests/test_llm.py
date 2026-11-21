import json
import shutil
import subprocess
import httpx
import pytest
from app.llm import GeminiQueryWriter, LLMError, parse_queries
from app.pipeline import run_pipeline
from app.providers.mock import MockProvider
from app.ranker import TagScorer

OK = {"candidates": [{"content": {"parts": [{"text": "- seedling sprouting soil\n2. \"green plant growing\"\n"}]}}]}


def writer(handler, key="SECRETKEY"):
    return GeminiQueryWriter(api_key=key, model="m", transport=httpx.MockTransport(handler))


def test_parse_cleans_bullets_and_respects_avoid():
    q = parse_queries("- Seedling sprouting soil\n2. \"alcohol bottles\"\n3) green plant", avoid=["alcohol"])
    assert q == ["seedling sprouting soil", "green plant"]


def test_gemini_success():
    out = writer(lambda r: httpx.Response(200, json=OK)).write("Green shoots appear.")
    assert out["queries"] == ["seedling sprouting soil", "green plant growing"]


def test_rate_limit_error_hides_key():
    with pytest.raises(LLMError) as exc:
        writer(lambda r: httpx.Response(429)).write("x")
    assert "SECRETKEY" not in str(exc.value)


def test_missing_key_or_model():
    with pytest.raises(LLMError):
        GeminiQueryWriter(api_key="", model="m").write("x")


def test_bad_format_is_llm_error():
    with pytest.raises(LLMError):
        writer(lambda r: httpx.Response(200, json={"candidates": []})).write("x")


pytestmark_ff = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


class GoodLLM:
    name = "good"
    model = "good"

    def write(self, text, avoid=None):
        return {"queries": ["green seedling soil"], "model": "good", "prompt_version": "q1", "raw": ""}


class BadLLM:
    name = "bad"
    model = "bad"

    def write(self, text, avoid=None):
        raise LLMError("down")


def fake_asr(path):
    words = [{"word": " Money", "start": 0.0, "end": 1.0}, {"word": " matters", "start": 1.0, "end": 2.0},
             {"word": " today.", "start": 2.0, "end": 3.0}]
    return {"duration": 3.0, "words": words}


def go(tmp_path, llm):
    audio = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                    str(audio)], check=True)
    run_pipeline(audio, tmp_path / "out", providers=[MockProvider()], scorer=TagScorer(), ratios=["16:9"],
                 captions={"burn_in": False, "srt": False}, transcribe_fn=fake_asr, query_writer=llm)
    return json.loads((tmp_path / "out" / "timeline.json").read_text())["scenes"]


@pytestmark_ff
def test_pipeline_uses_llm_queries_and_records_them(tmp_path):
    s = go(tmp_path, GoodLLM())[0]
    assert s["queries"][0] == "green seedling soil"
    assert s["llm"]["model"] == "good"


@pytestmark_ff
def test_pipeline_falls_back_when_llm_fails(tmp_path):
    s = go(tmp_path, BadLLM())[0]
    assert s["llm"] is None and s["queries"]
    assert any("query LLM failed" in w for w in s["warnings"])
