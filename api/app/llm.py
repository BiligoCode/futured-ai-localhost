from typing import Callable

import boto3
from botocore.config import Config

from app.config import Settings

# (system prompt, messages [{"role": "user"|"assistant", "content": str}]) -> reply text
LLM = Callable[[str, list[dict[str, str]]], str]


class BedrockLLM:
    def __init__(self, settings: Settings):
        self.model = settings.bedrock_model
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=settings.bedrock_region,
            aws_access_key_id=settings.bedrock_access_key_id or None,
            aws_secret_access_key=settings.bedrock_secret_access_key or None,
            config=Config(read_timeout=300, retries={"max_attempts": 3}),
        )

    def __call__(self, system: str, messages: list[dict[str, str]]) -> str:
        resp = self.client.converse(
            modelId=self.model,
            system=[{"text": system}],
            messages=[{"role": m["role"], "content": [{"text": m["content"]}]} for m in messages],
            inferenceConfig={"maxTokens": 8000, "temperature": 0.4},
        )
        return "".join(b.get("text", "") for b in resp["output"]["message"]["content"])
