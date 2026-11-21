import sys
import time
from dotenv import load_dotenv
load_dotenv()
from app.queries import build_queries
from app.providers.pixabay import PixabayProvider
from app.ranker import ClipScorer, choose_clip, gather

text = sys.argv[1] if len(sys.argv) > 1 else "The bank keeps it safe, and cloud apps make tracking easy."
res = build_queries(text)
print("queries:", res["queries"])
cands, errors = gather([PixabayProvider()], res["queries"])
print("candidates:", len(cands), "errors:", errors)
t0 = time.time()
out = choose_clip(text, cands, ClipScorer(), used=set(), min_duration=3.0)
print("seconds:", round(time.time() - t0, 1))
if out:
    print("chosen:", out["clip"].clip_id, out["clip"].tags[:5], "score:", out["score"])
    print("top3:", out["top3"])
    print("notes:", out["notes"])
