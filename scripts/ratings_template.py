import csv
import json
import sys
from pathlib import Path

run = sys.argv[1]
rating = sys.argv[2] if len(sys.argv) > 2 else ""
tl = json.loads(Path("outputs/%s/timeline.json" % run).read_text(encoding="utf-8"))
out = Path("evidence/ratings.csv")
out.parent.mkdir(exist_ok=True)
new = not out.exists()
with open(out, "a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    if new:
        w.writerow(["run", "scene", "text", "rating", "notes"])
    for s in tl["scenes"]:
        w.writerow([run, s["index"], s["text"], rating, ""])
print("added", len(tl["scenes"]), "scenes from", run)
