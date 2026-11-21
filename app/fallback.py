from pathlib import Path
from .render import _run

COLOURS = ["0x1e293b", "0x0f766e", "0x7c2d12", "0x4c1d95", "0x1e3a8a", "0x14532d"]


def make_fallback_clip(dest, index=0):
    """A plain generated background, used when no footage can be found. Contains no third-party media."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    colour = COLOURS[index % len(COLOURS)]
    _run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
          "-i", "color=c=%s:s=1280x720:r=30:d=10" % colour,
          "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(dest)])
    return dest
