import argparse
import json
from dotenv import load_dotenv
load_dotenv()
from app.errors import PipelineError
from app.pipeline import run_pipeline
from app.providers import build_providers
from app.ranker import ClipScorer, TagScorer
from app.text_input import run_script
from app.tts import build_tts

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--audio")
ap.add_argument("--script")
ap.add_argument("--script-file")
ap.add_argument("--providers", default=None)
ap.add_argument("--scorer", choices=["clip", "tag"], default="clip")
ap.add_argument("--tts", default=None)
ap.add_argument("--ratios", default="16:9")
ap.add_argument("--avoid", default="")
a = ap.parse_args()

scorer = ClipScorer() if a.scorer == "clip" else TagScorer()
common = dict(providers=build_providers(a.providers), scorer=scorer,
              ratios=[r for r in a.ratios.split(",") if r],
              avoid=[x for x in a.avoid.split(",") if x],
              progress=lambda p, m: print("[%3d%%] %s" % (p, m)))
try:
    if a.audio:
        res = run_pipeline(a.audio, a.out, **common)
    else:
        text = a.script
        if a.script_file:
            text = open(a.script_file, encoding="utf-8").read()
        res = run_script(text, a.out, tts=build_tts(a.tts), **common)
except PipelineError as exc:
    print(json.dumps(exc.to_dict(), indent=2))
    raise SystemExit(1)
print(json.dumps(res, indent=2))
