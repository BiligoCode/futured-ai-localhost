from typing import Callable

import boto3
from botocore.config import Config

from app.config import Settings

# (system prompt, messages [{"role": "user"|"assistant", "content": str}]) -> reply text
LLM = Callable[[str, list[dict[str, str]]], str]
# (system prompt, user prompt, JPEG images shown before the prompt) -> reply text
VisionLLM = Callable[[str, str, list[bytes]], str]


def _client(settings: Settings, *, adaptive: bool):
    # Adaptive retries slow a busy queue down on Bedrock throttling instead of failing it (the grading pipeline
    # sends many calls at once); interactive features keep the quick standard retries.
    retries = {"max_attempts": 10, "mode": "adaptive"} if adaptive else {"max_attempts": 3}
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.bedrock_region,
        aws_access_key_id=settings.bedrock_access_key_id or None,
        aws_secret_access_key=settings.bedrock_secret_access_key or None,
        config=Config(read_timeout=300, retries=retries),
    )


def _text(resp: dict) -> str:
    return "".join(b.get("text", "") for b in resp["output"]["message"]["content"])


class BedrockLLM:
    def __init__(self, settings: Settings, *, model: str | None = None, temperature: float = 0.4,
                 max_tokens: int = 8000, adaptive: bool = False):
        self.model = model or settings.bedrock_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = _client(settings, adaptive=adaptive)

    def __call__(self, system: str, messages: list[dict[str, str]]) -> str:
        resp = self.client.converse(
            modelId=self.model,
            system=[{"text": system}],
            messages=[{"role": m["role"], "content": [{"text": m["content"]}]} for m in messages],
            inferenceConfig={"maxTokens": self.max_tokens, "temperature": self.temperature},
        )
        return _text(resp)


class BedrockVision:
    """A vision model on Bedrock Converse: page images first, then the instructions."""

    def __init__(self, settings: Settings, model: str, *, max_tokens: int = 6000):
        self.model = model
        self.max_tokens = max_tokens
        self.client = _client(settings, adaptive=True)

    def __call__(self, system: str, prompt: str, images: list[bytes]) -> str:
        content: list[dict] = [{"image": {"format": "jpeg", "source": {"bytes": data}}} for data in images]
        content.append({"text": prompt})
        resp = self.client.converse(
            modelId=self.model,
            system=[{"text": system}],
            messages=[{"role": "user", "content": content}],
            inferenceConfig={"maxTokens": self.max_tokens, "temperature": 0},
        )
        return _text(resp)
