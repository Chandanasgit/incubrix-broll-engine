import os
import httpx
from .base import Clip, ProviderError


class PixabayProvider:
    name = "pixabay"

    def __init__(self, api_key=None, base_url=None, transport=None, timeout=15):
        self.api_key = api_key if api_key is not None else os.getenv("PIXABAY_API_KEY", "")
        self.base_url = base_url or os.getenv("PIXABAY_BASE_URL", "https://pixabay.com/api/videos/")
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def _clean(self, text):
        return text.replace(self.api_key, "***") if self.api_key else text

    def search(self, query, limit=15):
        if not self.api_key:
            raise ProviderError("PIXABAY_API_KEY is not set")
        params = {"key": self.api_key, "q": query,
                  "per_page": max(3, min(limit, 50)), "safesearch": "true"}
        try:
            resp = self._client.get(self.base_url, params=params)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(self._clean("pixabay request failed: " + str(exc))) from exc

        clips = []
        for hit in data.get("hits", []):
            vids = hit.get("videos", {})
            best = None
            for size in ("large", "medium", "small"):
                if vids.get(size, {}).get("url"):
                    best = vids[size]
                    break
            if best is None:
                continue
            clips.append(Clip(
                provider=self.name,
                clip_id=str(hit.get("id")),
                page_url=hit.get("pageURL", ""),
                download_url=best["url"],
                thumbnail_url=best.get("thumbnail", ""),
                width=int(best.get("width", 0)),
                height=int(best.get("height", 0)),
                duration=float(hit.get("duration", 0)),
                tags=[t.strip() for t in hit.get("tags", "").split(",") if t.strip()],
                licence="Pixabay Content Licence",
                attribution="Video by " + str(hit.get("user", "unknown")) + " on Pixabay",
            ))
        return clips
