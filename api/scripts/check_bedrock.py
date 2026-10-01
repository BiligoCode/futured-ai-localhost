"""Quick connectivity check: uv run python scripts/check_bedrock.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_settings  # noqa: E402
from app.llm import BedrockLLM  # noqa: E402


def main() -> None:
    settings = load_settings()
    print(f"region={settings.bedrock_region} model={settings.bedrock_model}")
    llm = BedrockLLM(settings)
    print(llm("You are terse.", [{"role": "user", "content": "Reply with the single word: ok"}]))


if __name__ == "__main__":
    main()
