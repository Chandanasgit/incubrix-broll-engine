import json
import shutil
import subprocess
import pytest
from app.errors import PipelineError
from app.pipeline import run_pipeline
from app.providers.base import ProviderError
from app.providers.mock import MockProvider
from app.ranker import TagScorer

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

WORDS = [
    {"word": " Money", "start": 0.0, "end": 1.0}, {"word": " matters", "start": 1.0, "end": 2.0},
    {"word": " today.", "start": 2.0, "end": 3.0},
    {"word": " Banks", "start": 3.2, "end": 4.0}, {"word": " keep", "start": 4.0, "end": 5.0},
    {"word": " cash", "start": 5.0, "end": 5.5}, {"word": " safe.", "start": 5.5, "end": 6.0},
]


def fake_asr(path):
    return {"duration": 6.0, "words": WORDS}


def make_audio(path, seconds=6):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=%d" % seconds, str(path)], check=True)
    return path


class DownProvider:
    name = "down"

    def search(self, q, limit=8):
        raise ProviderError("down")


def run(tmp_path, **kw):
    audio = make_audio(tmp_path / "a.wav")
    args = dict(providers=[MockProvider()], scorer=TagScorer(), ratios=["16:9"],
                captions={"burn_in": False, "srt": True}, transcribe_fn=fake_asr)
    args.update(kw)
    return run_pipeline(audio, tmp_path / "out", **args)


def test_full_run_with_mock(tmp_path):
    run(tmp_path, ratios=["16:9", "9:16"])
    out = tmp_path / "out"
    for f in ["video_16x9.mp4", "video_9x16.mp4", "timeline.json", "manifest.json", "captions.srt"]:
        assert (out / f).exists(), f
    scenes = json.loads((out / "timeline.json").read_text())["scenes"]
    assert len(scenes) == 2
    ids = [(s["clip"]["provider"], s["clip"]["clip_id"]) for s in scenes]
    assert len(set(ids)) == len(ids)
    assert all(s["clip"]["licence"] and "ai_generated" in s["clip"] and s["reason"] for s in scenes)
    assert scenes[0]["start"] == 0.0 and scenes[-1]["end"] == 6.0
    manifest = json.loads((out / "manifest.json").read_text())
    assert all(c["ok"] for c in manifest["checks"].values())


def test_provider_down_uses_fallback(tmp_path):
    run(tmp_path, providers=[DownProvider()])
    out = tmp_path / "out"
    scenes = json.loads((out / "timeline.json").read_text())["scenes"]
    assert all(s["clip"]["provider"] == "fallback" for s in scenes)
    assert json.loads((out / "manifest.json").read_text())["warnings"]
    assert (out / "video_16x9.mp4").exists()


def test_silent_audio_gives_clear_error(tmp_path):
    with pytest.raises(PipelineError) as exc:
        run(tmp_path, transcribe_fn=lambda p: {"duration": 6.0, "words": []})
    assert exc.value.code == "NO_SPEECH_DETECTED"


def test_wrong_file_type(tmp_path):
    bad = tmp_path / "x.mp3"
    bad.write_text("not audio at all")
    with pytest.raises(PipelineError) as exc:
        run_pipeline(bad, tmp_path / "out", providers=[MockProvider()], scorer=TagScorer(),
                     transcribe_fn=fake_asr)
    assert exc.value.code == "UNSUPPORTED_MEDIA"


def test_invalid_ratio(tmp_path):
    with pytest.raises(PipelineError) as exc:
        run(tmp_path, ratios=["4:3"])
    assert exc.value.code == "INVALID_ASPECT_RATIO"
