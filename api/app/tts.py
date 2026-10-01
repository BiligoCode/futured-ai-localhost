import base64
import hashlib
import json
from pathlib import Path
from typing import Protocol

import httpx

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
# Same voice, plus per-character timing ({"characters", "character_start_times_seconds", ...}) used for captions.
ELEVENLABS_TIMED_URL = ELEVENLABS_URL + "/with-timestamps"


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

    def _post(self, url: str, text: str, accept: str) -> httpx.Response:
        # eleven_multilingual_v2 detects the language from the text itself.
        if not self.api_key:
            raise TTSError("AI voice is not configured: set ELEVENLABS_API_KEY in .env")
        try:
            with httpx.Client(transport=self.transport, timeout=60) as client:
                resp = client.post(
                    url.format(voice_id=self.voice_id),
                    headers={"xi-api-key": self.api_key, "Accept": accept},
                    json={"text": text, "model_id": self.model_id},
                )
        except httpx.HTTPError as exc:
            raise TTSError(f"ElevenLabs request failed: {exc}") from exc
        if resp.status_code != 200:
            raise TTSError(f"ElevenLabs request failed ({resp.status_code}): {resp.text[:300]}")
        return resp

    def synthesize(self, text: str, language: str) -> bytes:
        return self._post(ELEVENLABS_URL, text, "audio/mpeg").content

    def synthesize_timed(self, text: str, language: str) -> tuple[bytes, dict | None]:
        """MP3 bytes and the character alignment of the speech."""
        try:
            body = self._post(ELEVENLABS_TIMED_URL, text, "application/json").json()
            return base64.b64decode(body["audio_base64"]), body.get("alignment")
        except (ValueError, KeyError, TypeError) as exc:
            raise TTSError(f"ElevenLabs returned an unexpected response: {exc}") from exc


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

    def synthesize_timed(self, text: str, language: str) -> tuple[bytes, dict | None]:
        path = self.cache_dir / f"{self.cache_key(text)}.mp3"
        timing = path.with_suffix(".timing.json")
        if path.is_file() and timing.is_file():
            return path.read_bytes(), json.loads(timing.read_text(encoding="utf-8"))
        audio, alignment = synthesize_timed(self.inner, text, language)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
        if alignment is not None:
            timing.write_text(json.dumps(alignment, ensure_ascii=False), encoding="utf-8")
        return audio, alignment


def synthesize_timed(tts: TTSProvider, text: str, language: str) -> tuple[bytes, dict | None]:
    """Speech with character timing when the provider supports it, else (audio, None)."""
    timed = getattr(tts, "synthesize_timed", None)
    return timed(text, language) if timed else (tts.synthesize(text, language), None)
