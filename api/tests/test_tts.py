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


ALIGNMENT = {"characters": list("Γεια"), "character_start_times_seconds": [0, 0.1, 0.2, 0.3],
             "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4]}


def test_elevenlabs_timed_request_returns_audio_and_alignment():
    import base64
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        return httpx.Response(200, json={"audio_base64": base64.b64encode(b"MP3").decode(), "alignment": ALIGNMENT})

    audio, alignment = ElevenLabsTTS("k", "v1", transport=httpx.MockTransport(handler)).synthesize_timed("Γεια", "el")
    assert (audio, alignment) == (b"MP3", ALIGNMENT)
    assert seen["url"].endswith("/v1/text-to-speech/v1/with-timestamps")


def test_cached_timed_and_fallback_for_untimed_provider(tmp_path):
    from app.tts import synthesize_timed

    class Timed(FakeTTS):
        def synthesize_timed(self, text, language):
            self.calls.append((text, language))
            return b"A", ALIGNMENT

    inner = Timed(b"A")
    c = CachedTTS(inner, tmp_path)
    assert c.synthesize_timed("x", "el") == (b"A", ALIGNMENT)
    assert c.synthesize_timed("x", "el") == (b"A", ALIGNMENT) and len(inner.calls) == 1
    assert synthesize_timed(FakeTTS(b"B"), "y", "el") == (b"B", None)
