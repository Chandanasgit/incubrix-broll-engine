import httpx
import pytest
from app.providers.base import ProviderError
from app.providers.pixabay import PixabayProvider
from app.providers.mock import MockProvider

SAMPLE = {"hits": [
    {"id": 123, "pageURL": "https://pixabay.com/videos/x-123/", "tags": "piggy bank, coins",
     "duration": 12, "user": "alice",
     "videos": {"large": {"url": "https://cdn.test/v.mp4", "width": 1920, "height": 1080,
                          "thumbnail": "https://cdn.test/t.jpg"}}},
    {"id": 124, "videos": {"large": {"url": ""}, "medium": {"url": ""}}},
]}


def make(handler, key="SECRETKEY"):
    return PixabayProvider(api_key=key, transport=httpx.MockTransport(handler))


def test_parses_clips_with_licence():
    clips = make(lambda req: httpx.Response(200, json=SAMPLE)).search("piggy bank")
    assert len(clips) == 1
    c = clips[0]
    assert c.provider == "pixabay" and c.clip_id == "123"
    assert c.licence == "Pixabay Content Licence"
    assert c.ai_generated is False
    assert c.tags == ["piggy bank", "coins"]


def test_http_error_hides_key():
    with pytest.raises(ProviderError) as exc:
        make(lambda req: httpx.Response(500)).search("x")
    assert "SECRETKEY" not in str(exc.value)


def test_missing_key_raises():
    with pytest.raises(ProviderError):
        PixabayProvider(api_key="").search("x")


def test_mock_is_deterministic_and_licensed():
    a = MockProvider().search("bank")
    b = MockProvider().search("bank")
    assert [c.clip_id for c in a] == [c.clip_id for c in b]
    assert all(c.licence and c.ai_generated is False for c in a)
