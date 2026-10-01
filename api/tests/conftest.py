import dataclasses
import io
from pathlib import Path

import httpx
from reportlab.pdfgen import canvas

from app.config import Settings


def api_client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def make_pdf(text: str | None) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    if text:
        c.drawString(72, 720, text)
    c.showPage()
    c.save()
    return buf.getvalue()


def make_settings(tmp_path: Path, **overrides) -> Settings:
    base = Settings(
        data_dir=tmp_path / "data",
        bedrock_access_key_id="test-key",
        bedrock_secret_access_key="test-secret",
        bedrock_region="eu-central-1",
        bedrock_model="test-model",
        elevenlabs_api_key="test-eleven",
        elevenlabs_voice_id="test-voice",
        render_quality="l",
    )
    return dataclasses.replace(base, **overrides)
