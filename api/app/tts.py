import base64
import hashlib
import json
from pathlib import Path
from typing import Protocol

import httpx

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
# Same voice, plus per-character timing ({"characters", "character_start_times_seconds", ...}) used for captions.
ELEVENLABS_TIMED_URL = ELEVENLABS_URL + "/with-timestamps"
DEFAULT_MODEL = "eleven_multilingual_v2"
# Models that reject `language_code` (they detect the language from the text).
NO_LANGUAGE_CODE = {"eleven_multilingual_v2", "eleven_multilingual_v1", "eleven_monolingual_v1"}


class TTSError(RuntimeError):
    pass


class TTSProvider(Protocol):
    def cache_key(self, text: str, language: str = "") -> str: ...

    def synthesize(self, text: str, language: str) -> bytes:
        """Return MP3 bytes for `text`."""
        ...


class ElevenLabsTTS:
    """`voices` maps a video language to its own voice (a native Greek voice reads Greek best); other languages use
    `voice_id`. `voice_settings` (stability, similarity_boost, style, speed) are sent only when given."""

    def __init__(self, api_key: str, voice_id: str, model_id: str = DEFAULT_MODEL,
                 transport: httpx.BaseTransport | None = None, *, voices: dict[str, str] | None = None,
                 voice_settings: dict[str, float] | None = None):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.transport = transport
        self.voices = {k: v for k, v in (voices or {}).items() if v}
        self.voice_settings = voice_settings or {}

    def voice_for(self, language: str) -> str:
        return self.voices.get(language, self.voice_id)

    def _body(self, text: str, language: str) -> dict:
        body: dict = {"text": text, "model_id": self.model_id}
        if language and self.model_id not in NO_LANGUAGE_CODE:
            body["language_code"] = language  # e.g. reads "3,5" and abbreviations the Greek way
        if self.voice_settings:
            body["voice_settings"] = self.voice_settings
        return body

    def cache_key(self, text: str, language: str = "") -> str:
        body = self._body(text, language)
        extra = {k: body[k] for k in ("language_code", "voice_settings") if k in body}
        raw = f"elevenlabs|{self.voice_for(language)}|{self.model_id}|{text}"
        if extra:
            raw += "|" + json.dumps(extra, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _post(self, url: str, text: str, language: str, accept: str) -> httpx.Response:
        if not self.api_key:
            raise TTSError("AI voice is not configured: set ELEVENLABS_API_KEY in .env")
        try:
            with httpx.Client(transport=self.transport, timeout=60) as client:
                resp = client.post(
                    url.format(voice_id=self.voice_for(language)),
                    headers={"xi-api-key": self.api_key, "Accept": accept},
                    json=self._body(text, language),
                )
        except httpx.HTTPError as exc:
            raise TTSError(f"ElevenLabs request failed: {exc}") from exc
        if resp.status_code != 200:
            raise TTSError(f"ElevenLabs request failed ({resp.status_code}): {resp.text[:300]}")
        return resp

    def synthesize(self, text: str, language: str) -> bytes:
        return self._post(ELEVENLABS_URL, text, language, "audio/mpeg").content

    def synthesize_timed(self, text: str, language: str) -> tuple[bytes, dict | None]:
        """MP3 bytes and the character alignment of the speech."""
        try:
            body = self._post(ELEVENLABS_TIMED_URL, text, language, "application/json").json()
            return base64.b64decode(body["audio_base64"]), body.get("alignment")
        except (ValueError, KeyError, TypeError) as exc:
            raise TTSError(f"ElevenLabs returned an unexpected response: {exc}") from exc


class CachedTTS:
    def __init__(self, inner: TTSProvider, cache_dir: Path):
        self.inner = inner
        self.cache_dir = Path(cache_dir)

    def cache_key(self, text: str, language: str = "") -> str:
        return self.inner.cache_key(text, language)

    def synthesize(self, text: str, language: str) -> bytes:
        path = self.cache_dir / f"{self.cache_key(text, language)}.mp3"
        if path.is_file():
            return path.read_bytes()
        audio = self.inner.synthesize(text, language)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
        return audio

    def synthesize_timed(self, text: str, language: str) -> tuple[bytes, dict | None]:
        path = self.cache_dir / f"{self.cache_key(text, language)}.mp3"
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
