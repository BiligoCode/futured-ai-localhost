import json

import httpx
import pytest

from app.tts import CachedTTS, ElevenLabsTTS, TTSError
from tests.fakes import FakeTTS


def test_elevenlabs_request_shape():
    seen = {}

    def handler(req):
        seen.update(url=str(req.url), key=req.headers["xi-api-key"], body=json.loads(req.content))
        return httpx.Response(200, content=b"MP3")

    tts = ElevenLabsTTS("k", "voice1", transport=httpx.MockTransport(handler))
    assert tts.synthesize("Γεια σας", "el") == b"MP3"
    assert seen["url"].endswith("/v1/text-to-speech/voice1") and seen["key"] == "k"
    assert seen["body"] == {"text": "Γεια σας", "model_id": "eleven_multilingual_v2"}


def test_elevenlabs_error_raises():
    tts = ElevenLabsTTS("k", "v", transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"detail": "bad key"})))
    with pytest.raises(TTSError, match="401"):
        tts.synthesize("x", "el")


def test_elevenlabs_missing_key_raises():
    with pytest.raises(TTSError, match="ELEVENLABS_API_KEY"):
        ElevenLabsTTS("", "v").synthesize("x", "el")


def test_cache_hits(tmp_path):
    inner = FakeTTS(b"A")
    c = CachedTTS(inner, tmp_path)
    assert c.synthesize("x", "el") == b"A"
    c.synthesize("x", "el")
    c.synthesize("y", "el")
    assert len(inner.calls) == 2


def test_elevenlabs_cache_key_depends_on_voice():
    assert ElevenLabsTTS("k", "a").cache_key("t") != ElevenLabsTTS("k", "b").cache_key("t")
