import os
from .base import Clip, ProviderError
from .pixabay import PixabayProvider
from .mock import MockProvider

REGISTRY = {"pixabay": PixabayProvider, "mock": MockProvider}


def build_providers(names=None):
    raw = names or os.getenv("FOOTAGE_PROVIDERS", "pixabay")
    return [REGISTRY[n.strip()]() for n in raw.split(",") if n.strip()]
