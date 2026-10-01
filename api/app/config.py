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
    render_timeout_s: int = 180
    max_concurrent_renders: int = 4
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or REPO_ROOT / ".env", override=False)
    return Settings(
        data_dir=Path(_env("DATA_DIR", str(REPO_ROOT / "data"))),
        bedrock_access_key_id=_env("AWS_BEDROCK_ACCESS_KEY_ID"),
        bedrock_secret_access_key=_env("AWS_BEDROCK_SECRET_ACCESS_KEY"),
        bedrock_region=_env("AWS_BEDROCK_REGION", "eu-central-1"),
        bedrock_model=_env("AWS_BEDROCK_MODEL", "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"),
        elevenlabs_api_key=_env("ELEVENLABS_API_KEY"),
        elevenlabs_voice_id=_env("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb"),
        render_quality=_env("RENDER_QUALITY", "m"),
    )
