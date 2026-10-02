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
    # Assessments: the model that reads scanned pages, the one that reads definitive answers a second time
    # (empty disables the second reading), and the one that grades (empty = bedrock_model).
    vision_model: str = "qwen.qwen3-vl-235b-a22b"
    verify_model: str = "moonshotai.kimi-k2.5"
    grading_model: str = ""
    grading_concurrency: int = 6


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def _env_set(name: str, default: str) -> str:
    """Like _env, but a variable that is set to an empty value stays empty (it switches something off)."""
    value = os.environ.get(name)
    return default if value is None else value.strip()


def _env_int(name: str, default: int, low: int, high: int) -> int:
    value = _env(name)
    if not value:
        return default
    try:
        number = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a whole number, got {value!r}") from exc
    if not low <= number <= high:
        raise ValueError(f"{name} must be between {low} and {high}, got {number}")
    return number


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
        vision_model=_env("AWS_BEDROCK_VISION_MODEL", "qwen.qwen3-vl-235b-a22b"),
        verify_model=_env_set("AWS_BEDROCK_VERIFY_MODEL", "moonshotai.kimi-k2.5"),
        grading_model=_env("AWS_BEDROCK_GRADING_MODEL"),
        grading_concurrency=_env_int("GRADING_CONCURRENCY", 6, 1, 32),
    )
