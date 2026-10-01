import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    bedrock_access_key_id: str
    bedrock_secret_access_key: str
    bedrock_region: str
    bedrock_model: str
    elevenlabs_api_key: str
    elevenlabs_voice_id: str
    render_quality: str
    elevenlabs_model: str = "eleven_multilingual_v2"
    # A voice per video language; empty falls back to elevenlabs_voice_id.
    elevenlabs_voice_id_el: str = ""
    elevenlabs_voice_id_en: str = ""
    # Optional voice_settings sent to ElevenLabs (e.g. speed 0.95 for teaching); empty = the voice's defaults.
    elevenlabs_voice_settings: tuple[tuple[str, float], ...] = ()
    render_timeout_s: int = 180
    max_concurrent_renders: int = 4
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name, "").strip()
    return value or default


VOICE_SETTINGS = {"ELEVENLABS_STABILITY": "stability", "ELEVENLABS_SIMILARITY": "similarity_boost",
                  "ELEVENLABS_STYLE": "style", "ELEVENLABS_SPEED": "speed"}


def _voice_settings() -> tuple[tuple[str, float], ...]:
    out = []
    for env, key in VOICE_SETTINGS.items():
        if value := _env(env):
            try:
                out.append((key, float(value)))
            except ValueError as exc:
                raise ValueError(f"{env} must be a number, got {value!r}") from exc
    return tuple(out)


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or REPO_ROOT / ".env", override=False)
    return Settings(
        data_dir=Path(_env("DATA_DIR", str(REPO_ROOT / "data"))),
        bedrock_access_key_id=_env("AWS_BEDROCK_ACCESS_KEY_ID"),
        bedrock_secret_access_key=_env("AWS_BEDROCK_SECRET_ACCESS_KEY"),
        bedrock_region=_env("AWS_BEDROCK_REGION", "us-east-1"),
        bedrock_model=_env("AWS_BEDROCK_MODEL", "zai.glm-5"),
        elevenlabs_api_key=_env("ELEVENLABS_API_KEY"),
        elevenlabs_voice_id=_env("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb"),
        elevenlabs_model=_env("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
        elevenlabs_voice_id_el=_env("ELEVENLABS_VOICE_ID_EL"),
        elevenlabs_voice_id_en=_env("ELEVENLABS_VOICE_ID_EN"),
        elevenlabs_voice_settings=_voice_settings(),
        render_quality=_env("RENDER_QUALITY", "m"),
        cors_origins=tuple(o.strip() for o in _env("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()),
    )
