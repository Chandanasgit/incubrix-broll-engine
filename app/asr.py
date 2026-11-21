import os
import subprocess
import numpy as np
from faster_whisper import WhisperModel

_model = None


def load_audio(path, sr=16000):
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", path,
           "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype=np.float32)


def transcribe(path):
    """Return {"duration": float, "words": [{"word","start","end"}]}."""
    global _model
    if _model is None:
        _model = WhisperModel(os.getenv("WHISPER_MODEL", "base"),
                              device="cpu", compute_type="int8")
    audio = load_audio(path)
    segments, info = _model.transcribe(audio, word_timestamps=True)
    words = []
    for seg in segments:
        for w in seg.words:
            words.append({"word": w.word, "start": w.start, "end": w.end})
    return {"duration": info.duration, "words": words}
