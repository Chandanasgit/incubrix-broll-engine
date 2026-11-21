import subprocess, sys, time
import numpy as np
from faster_whisper import WhisperModel

path = sys.argv[1] if len(sys.argv) > 1 else "samples/test1.wav"

def load_audio(p, sr=16000):
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", p,
           "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype=np.float32)

t0 = time.time()
audio = load_audio(path)
model = WhisperModel("base", device="cpu", compute_type="int8")
t1 = time.time()
segments, info = model.transcribe(audio, word_timestamps=True)
print("language:", info.language, "duration:", round(info.duration, 2))
for seg in segments:
    print(f"[{seg.start:.2f}-{seg.end:.2f}] {seg.text}")
    for w in seg.words:
        print(f"   {w.start:.2f}-{w.end:.2f} {w.word}")
print("load seconds:", round(t1 - t0, 1), "| transcribe seconds:", round(time.time() - t1, 1))
