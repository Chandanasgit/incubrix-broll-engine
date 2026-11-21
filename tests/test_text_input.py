import json
import shutil
import pytest
from app.errors import PipelineError
from app.providers.mock import MockProvider
from app.ranker import TagScorer
from app.render import probe
from app.text_input import prepare_text, run_script
from app.tts import MockTTS

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

WORDS = ["Money", "matters", "today.", "Banks", "keep", "cash", "safe."]


def asr_from_audio(path):
    d = float(probe(path)["format"]["duration"])
    step = d / len(WORDS)
    return {"duration": d, "words": [{"word": " " + w, "start": i * step, "end": (i + 1) * step}
                                     for i, w in enumerate(WORDS)]}


def test_empty_script_rejected():
    with pytest.raises(PipelineError) as exc:
        prepare_text("   \n  ")
    assert exc.value.code == "EMPTY_SCRIPT"


def test_script_too_long(monkeypatch):
    monkeypatch.setenv("MAX_SCRIPT_CHARS", "20")
    with pytest.raises(PipelineError) as exc:
        prepare_text("x" * 50)
    assert exc.value.code == "SCRIPT_TOO_LONG"


def test_script_to_video_with_mock_tts(tmp_path):
    run_script("Money matters today. Banks keep cash safe.", tmp_path / "out",
               tts=MockTTS(), providers=[MockProvider()], scorer=TagScorer(),
               ratios=["16:9"], captions={"burn_in": False, "srt": True},
               transcribe_fn=asr_from_audio)
    out = tmp_path / "out"
    assert (out / "video_16x9.mp4").exists() and (out / "narration.wav").exists()
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["input"]["type"] == "script"
    assert manifest["models"]["tts"]["ai_generated_audio"] is True
