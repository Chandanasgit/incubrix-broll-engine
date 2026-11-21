from dataclasses import dataclass, asdict


class ProviderError(Exception):
    """A footage provider failed (network, bad response, missing key)."""


@dataclass
class Clip:
    provider: str
    clip_id: str
    page_url: str
    download_url: str
    thumbnail_url: str
    width: int
    height: int
    duration: float
    tags: list
    licence: str
    attribution: str
    ai_generated: bool = False

    def to_dict(self):
        return asdict(self)
