import json
import os
import re
from pathlib import Path

from .errors import PipelineError
from .pipeline import run_pipeline


def prepare_text(script):
    cleaned = re.sub("[\ufeff\u200b-\u200d\u2060]", "", script or "")
    text = " ".join(cleaned.split())
    if not text:
        raise PipelineError("EMPTY_SCRIPT", "The script is empty.")
    limit = int(os.getenv("MAX_SCRIPT_CHARS", "12000"))
    if len(text) > limit:
        raise PipelineError("SCRIPT_TOO_LONG", "The script is longer than the allowed maximum.",
                            details={"max_chars": limit, "got_chars": len(text)})
    return text


def run_script(script, out_dir, *, tts, **kw):
    text = prepare_text(script)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    audio = tts.synthesize(text, out / "narration.wav")
    res = run_pipeline(audio, out, script_text=text, **kw)
    mpath = out / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    manifest["input"]["type"] = "script"
    manifest["models"]["tts"] = {"name": tts.name, "voice": getattr(tts, "voice", None),
                                 "ai_generated_audio": True}
    mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return res
