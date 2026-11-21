from pathlib import Path
from app.asr import transcribe
from app.scenes import split_scenes
from app.providers.mock import MockProvider
from app.render import (concat, describe, download_clip, finalize, make_srt, normalise_scene, RATIOS)

AUDIO = "samples/test1.wav"
work = Path("outputs/smoke")
work.mkdir(parents=True, exist_ok=True)

r = transcribe(AUDIO)
scenes = split_scenes(r["words"], r["duration"], min_len=1.0)
clips = MockProvider().search("smoke")
(work / "captions.srt").write_text(make_srt(r["words"]), encoding="utf-8")

for ratio in RATIOS:
    parts = []
    for sc, clip in zip(scenes, clips):
        src = download_clip(clip.download_url, work / ("src_%d.mp4" % sc["index"]))
        part = work / ("scene_%d_%s.mp4" % (sc["index"], ratio.replace(":", "x")))
        normalise_scene(src, float(sc["end"]) - float(sc["start"]), ratio, part)
        parts.append(part)
    joined = concat(parts, work / ("joined_%s.mp4" % ratio.replace(":", "x")))
    final = finalize(joined, AUDIO, work / ("video_%s.mp4" % ratio.replace(":", "x")),
                     srt=work / "captions.srt", burn_in=True, ratio=ratio)
    print(ratio, describe(final))
print("narration seconds:", round(r["duration"], 2))
