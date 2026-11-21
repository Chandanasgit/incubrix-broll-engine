import io
import os
import httpx
from .providers.base import ProviderError


class ClipScorer:
    """Scores (scene text, clip) pairs by meaning using CLIP on the clip thumbnail."""
    name = "open_clip"

    def __init__(self, model_name=None, pretrained=None):
        self.model_name = model_name or os.getenv("CLIP_MODEL", "ViT-B-32")
        self.pretrained = pretrained or os.getenv("CLIP_PRETRAINED", "laion2b_s34b_b79k")
        self._loaded = False

    def _load(self):
        import open_clip
        import torch
        self.torch = torch
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            self.model_name, pretrained=self.pretrained)
        self.tokenizer = open_clip.get_tokenizer(self.model_name)
        self.model.eval()
        self._loaded = True

    def score(self, text, clips):
        if not self._loaded:
            self._load()
        from PIL import Image
        torch = self.torch
        out = []
        with torch.no_grad():
            t = self.model.encode_text(self.tokenizer([text]))
            t = t / t.norm(dim=-1, keepdim=True)
            for c in clips:
                try:
                    r = httpx.get(c.thumbnail_url, timeout=10)
                    r.raise_for_status()
                    img = Image.open(io.BytesIO(r.content)).convert("RGB")
                    v = self.model.encode_image(self.preprocess(img).unsqueeze(0))
                    v = v / v.norm(dim=-1, keepdim=True)
                    out.append(float((t @ v.T).item()))
                except Exception:
                    out.append(None)
        return out


class TagScorer:
    """No-model fallback and test double: word overlap between the scene text and clip tags."""
    name = "tag_overlap"

    def score(self, text, clips):
        words = set(w.strip(".,!?").lower() for w in text.split())
        out = []
        for c in clips:
            tagwords = set(w.lower() for tag in c.tags for w in tag.split())
            out.append(len(words & tagwords) / max(1, len(words)))
        return out


def gather(providers, queries, per_query=8):
    """Search every provider with every query. A failing provider is skipped, not fatal."""
    seen, clips, errors = set(), [], []
    for p in providers:
        for q in queries:
            try:
                found = p.search(q, limit=per_query)
            except ProviderError as exc:
                errors.append("%s: %s" % (p.name, exc))
                break
            for c in found:
                key = (c.provider, c.clip_id)
                if key not in seen:
                    seen.add(key)
                    clips.append(c)
    return clips, errors


def choose_clip(scene_text, candidates, scorer, used, min_duration=0.0, max_candidates=10):
    pool = [c for c in candidates if (c.provider, c.clip_id) not in used]
    if not pool:
        return None
    notes = []
    long_enough = [c for c in pool if c.duration >= min_duration]
    if long_enough:
        pool = long_enough
    else:
        notes.append("no candidate long enough for the scene")
    pool = pool[:max_candidates]
    scores = scorer.score(scene_text, pool)
    ranked = sorted(zip(pool, scores),
                    key=lambda cs: cs[1] if cs[1] is not None else -1.0, reverse=True)
    best, score = ranked[0]
    if score is None:
        notes.append("scoring failed for all candidates; took the first result")
    return {
        "clip": best,
        "score": score,
        "scorer": scorer.name,
        "considered": len(pool),
        "notes": notes,
        "top3": [(c.clip_id, c.tags[:3], s) for c, s in ranked[:3]],
    }
