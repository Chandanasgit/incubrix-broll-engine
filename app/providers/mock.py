import hashlib
from .base import Clip


class MockProvider:
    name = "mock"

    def search(self, query, limit=15):
        seed = int(hashlib.md5(query.encode()).hexdigest(), 16) % 1000
        return [Clip(
            provider=self.name,
            clip_id="mock-%d-%d" % (seed, i),
            page_url="https://example.test/mock/%d" % i,
            download_url="mock://color/%d" % ((seed + i) % 6),
            thumbnail_url="",
            width=1920, height=1080, duration=10.0,
            tags=query.split(),
            licence="Test only (generated locally)",
            attribution="Generated test clip",
        ) for i in range(min(limit, 8))]
