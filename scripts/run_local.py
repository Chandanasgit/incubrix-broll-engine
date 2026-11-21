import argparse
import json
from dotenv import load_dotenv
load_dotenv()
from app.errors import PipelineError
from app.pipeline import run_pipeline
from app.providers import build_providers
from app.ranker import ClipScorer, TagScorer

ap = argparse.ArgumentParser()
ap.add_argument("audio")
ap.add_argument("out")
ap.add_argument("--providers", default=None)
ap.add_argument("--scorer", choices=["clip", "tag"], default="clip")
ap.add_argument("--ratios", default="16:9")
ap.add_argument("--avoid", default="")
a = ap.parse_args()

scorer = ClipScorer() if a.scorer == "clip" else TagScorer()
try:
    res = run_pipeline(
        a.audio, a.out, providers=build_providers(a.providers), scorer=scorer,
        ratios=[r for r in a.ratios.split(",") if r],
        avoid=[x for x in a.avoid.split(",") if x],
        progress=lambda p, m: print("[%3d%%] %s" % (p, m)))
except PipelineError as exc:
    print(json.dumps(exc.to_dict(), indent=2))
    raise SystemExit(1)
print(json.dumps(res, indent=2))
