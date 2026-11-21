import os
import subprocess
import sys
from pathlib import Path

from .errors import PipelineError


class PiperTTS:
    """Calls the Piper CLI as a separate process (Piper is GPL; we never import it)."""
    name = "piper"

    def __init__(self, voice=None, data_dir=None):
        self.voice = voice or os.getenv("PIPER_VOICE", "en_US-ljspeech-medium")
        self.data_dir = data_dir or os.getenv("PIPER_DATA_DIR", "data/voices")

    def synthesize(self, text, out_path):
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, "-m", "piper", "-m", self.voice,
               "--data-dir", self.data_dir, "-f", str(out_path)]
        try:
            res = subprocess.run(cmd, input=text, capture_output=True, text=True, encoding="utf-8",
                                 timeout=int(os.getenv("TTS_TIMEOUT_SECONDS", "300")))
        except subprocess.TimeoutExpired:
            raise PipelineError("TTS_FAILED", "Speech synthesis timed out.", retryable=True)
        if res.returncode != 0 or not out_path.exists():
            raise PipelineError("TTS_FAILED", "Speech synthesis failed.", retryable=True,
                                details={"stderr": res.stderr[-300:]})
        return out_path


class MockTTS:
    """Keyless test double: a quiet tone whose length follows the word count."""
    name = "mock"
    voice = "mock"

    def synthesize(self, text, out_path):
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        seconds = max(1.0, len(text.split()) * 0.4)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                        "-i", "sine=frequency=220:duration=%.2f" % seconds, str(out_path)], check=True)
        return out_path


REGISTRY = {"piper": PiperTTS, "mock": MockTTS}


def build_tts(name=None):
    return REGISTRY[name or os.getenv("TTS_PROVIDER", "piper")]()
