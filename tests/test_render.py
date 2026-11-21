import shutil
import pytest
from app.render import (RenderError, concat, describe, download_clip, make_srt,
                        normalise_scene, validate_video)

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_srt_format_and_order():
    words = [{"word": " Hello", "start": 0.0, "end": 0.4},
             {"word": " big", "start": 0.4, "end": 0.7},
             {"word": " world.", "start": 0.7, "end": 1.2}]
    srt = make_srt(words)
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,200\nHello big world.")


def test_corrupt_file_is_rejected(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"this is not a video" * 50)
    with pytest.raises(RenderError):
        validate_video(bad)


def test_normalise_and_concat_to_vertical(tmp_path):
    src = download_clip("mock://color/1", tmp_path / "src.mp4")
    a = normalise_scene(src, 1.0, "9:16", tmp_path / "a.mp4")
    b = normalise_scene(src, 1.5, "9:16", tmp_path / "b.mp4")
    out = concat([a, b], tmp_path / "joined.mp4")
    d = describe(out)
    assert (d["width"], d["height"]) == (1080, 1920)
    assert d["fps"] == 30.0
    assert d["pix_fmt"] == "yuv420p"
    assert abs(d["duration"] - 2.5) < 0.15


def test_short_clip_is_looped_to_fill_scene(tmp_path):
    src = download_clip("mock://color/2", tmp_path / "src.mp4")
    out = normalise_scene(src, 12.0, "16:9", tmp_path / "long.mp4")
    assert abs(describe(out)["duration"] - 12.0) < 0.2
