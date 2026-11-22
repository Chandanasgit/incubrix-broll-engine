import json
import shutil
import subprocess

import pytest

from app.pipeline import run_pipeline
from app.providers.mock import MockProvider
from app.ranker import TagScorer

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def misheard_asr(path):
    words = [{"word": " Sunny", "start": 0.0, "end": 1.0}, {"word": " Jews", "start": 1.0, "end": 2.0},
             {"word": " a", "start": 2.0, "end": 3.0}, {"word": " spot.", "start": 3.0, "end": 4.0}]
    return {"duration": 4.0, "words": words}


def test_script_text_replaces_misheard_words(tmp_path):
    audio = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                    str(audio)], check=True)
    run_pipeline(audio, tmp_path / "out", providers=[MockProvider()], scorer=TagScorer(), ratios=["16:9"],
                 captions={"burn_in": False, "srt": True}, transcribe_fn=misheard_asr,
                 script_text="Sunny choose a spot.")
    scenes = json.loads((tmp_path / "out" / "timeline.json").read_text())["scenes"]
    assert scenes[0]["text"] == "Sunny choose a spot."
    assert "Jews" not in json.dumps(scenes)
    srt = (tmp_path / "out" / "captions.srt").read_text()
    assert "choose" in srt and "Jews" not in srt
