import json
import subprocess
from pathlib import Path

import httpx

RATIOS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
FPS = 30
CAPTION_SIZE = {"16:9": 14, "1:1": 13, "9:16": 10}


class RenderError(Exception):
    """A media step failed (download, probe, encode)."""


def _run(cmd, cwd=None):
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if res.returncode != 0:
        raise RenderError("command failed: " + " ".join(cmd[:2]) + " :: " + res.stderr[-400:])
    return res


def probe(path):
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True)
    if res.returncode != 0:
        raise RenderError("not a readable media file: " + str(path))
    return json.loads(res.stdout)


def validate_video(path):
    info = probe(path)
    if not any(s.get("codec_type") == "video" for s in info.get("streams", [])):
        raise RenderError("no video stream in " + str(path))
    return info


def describe(path):
    info = probe(path)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    num, den = v["r_frame_rate"].split("/")
    return {
        "width": v["width"], "height": v["height"],
        "fps": round(int(num) / int(den), 2), "pix_fmt": v["pix_fmt"],
        "duration": float(info["format"]["duration"]),
        "has_audio": any(s["codec_type"] == "audio" for s in info["streams"]),
    }


def download_clip(url, dest):
    """Download (or, for mock:// URLs, generate) a clip and check that it is a real video."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if url.startswith("mock://"):
        n = int(url.rsplit("/", 1)[1])
        _run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
              "-i", "testsrc2=size=1280x720:rate=30:duration=10",
              "-vf", "hue=h=%d" % (n * 60), "-c:v", "libx264", "-preset", "ultrafast",
              "-pix_fmt", "yuv420p", str(dest)])
    else:
        try:
            with httpx.stream("GET", url, timeout=30, follow_redirects=True) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in resp.iter_bytes(65536):
                        f.write(chunk)
        except httpx.HTTPError as exc:
            dest.unlink(missing_ok=True)
            raise RenderError("download failed: " + str(exc)) from exc
    try:
        validate_video(dest)
    except RenderError:
        dest.unlink(missing_ok=True)
        raise
    return dest


def normalise_scene(src, duration, ratio, out):
    """Cut or loop a clip to exactly `duration` seconds at the target size, 30 fps, yuv420p, no audio."""
    w, h = RATIOS[ratio]
    vf = ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,fps=%d,format=yuv420p"
          % (w, h, w, h, FPS))
    _run(["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", str(src),
          "-t", "%.3f" % float(duration), "-vf", vf, "-an",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
          "-r", str(FPS), "-pix_fmt", "yuv420p", "-g", str(FPS), str(out)])
    return Path(out)


def concat(parts, out):
    out = Path(out)
    lst = out.with_suffix(".txt")
    lst.write_text("".join("file '%s'\n" % Path(p).resolve().as_posix() for p in parts), encoding="utf-8")
    _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
          "-c", "copy", str(out)])
    return out


def _ts(t):
    ms = int(round(float(t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def make_srt(words, max_words=7, max_dur=3.5):
    """Group word timings into short caption cues."""
    cues, cur = [], []

    def flush():
        if cur:
            start = float(cur[0]["start"])
            end = max(float(cur[-1]["end"]), start + 0.2)
            cues.append((start, end, "".join(w["word"] for w in cur).strip()))
            cur.clear()

    for w in words:
        cur.append(w)
        text = w["word"].strip()
        too_long = float(cur[-1]["end"]) - float(cur[0]["start"]) >= max_dur
        punct = text.endswith((".", "!", "?", ",", ";", ":")) and len(cur) >= 3
        if len(cur) >= max_words or too_long or punct:
            flush()
    flush()
    lines = []
    for i, (s, e, t) in enumerate(cues, 1):
        lines.append("%d\n%s --> %s\n%s\n" % (i, _ts(s), _ts(e), t))
    return "\n".join(lines)


def finalize(video, audio, out, srt=None, burn_in=False, ratio="16:9"):
    """Add the narration (and optionally burned-in captions) to the joined video."""
    video, audio, out = Path(video).resolve(), Path(audio).resolve(), Path(out).resolve()
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio),
           "-map", "0:v:0", "-map", "1:a:0"]
    cwd = None
    if burn_in and srt:
        srt = Path(srt).resolve()
        cwd = str(srt.parent)
        style = "FontSize=%d,Outline=2,Shadow=0,MarginV=30" % CAPTION_SIZE.get(ratio, 14)
        cmd += ["-vf", "subtitles=%s:force_style='%s'" % (srt.name, style),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
    else:
        cmd += ["-c:v", "copy"]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-shortest",
            "-movflags", "+faststart", str(out)]
    _run(cmd, cwd=cwd)
    return out
