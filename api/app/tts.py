import hashlib
from pathlib import Path
from typing import Protocol

import httpx

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


class TTSError(RuntimeError):
    pass


class TTSProvider(Protocol):
    def cache_key(self, text: str) -> str: ...

    def synthesize(self, text: str, language: str) -> bytes:
        """Return MP3 bytes for `text`."""
        ...


class ElevenLabsTTS:
    def __init__(self, api_key: str, voice_id: str, model_id: str = "eleven_multilingual_v2",
                 transport: httpx.BaseTransport | None = None):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.transport = transport

    def cache_key(self, text: str) -> str:
        raw = f"elevenlabs|{self.voice_id}|{self.model_id}|{text}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def synthesize(self, text: str, language: str) -> bytes:
        # eleven_multilingual_v2 detects the language from the text itself.
        if not self.api_key:
            raise TTSError("AI voice is not configured: set ELEVENLABS_API_KEY in .env")
        try:
            with httpx.Client(transport=self.transport, timeout=60) as client:
                resp = client.post(
                    ELEVENLABS_URL.format(voice_id=self.voice_id),
                    headers={"xi-api-key": self.api_key, "Accept": "audio/mpeg"},
                    json={"text": text, "model_id": self.model_id},
                )
        except httpx.HTTPError as exc:
            raise TTSError(f"ElevenLabs request failed: {exc}") from exc
        if resp.status_code != 200:
            raise TTSError(f"ElevenLabs request failed ({resp.status_code}): {resp.text[:300]}")
        return resp.content


class CachedTTS:
    def __init__(self, inner: TTSProvider, cache_dir: Path):
        self.inner = inner
        self.cache_dir = Path(cache_dir)

    def cache_key(self, text: str) -> str:
        return self.inner.cache_key(text)

    def synthesize(self, text: str, language: str) -> bytes:
        path = self.cache_dir / f"{self.cache_key(text)}.mp3"
        if path.is_file():
            return path.read_bytes()
        audio = self.inner.synthesize(text, language)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
        return audio
