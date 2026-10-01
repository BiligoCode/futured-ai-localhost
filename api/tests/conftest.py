import dataclasses
import io
import json
import subprocess
from pathlib import Path

import httpx
import pytest
from reportlab.pdfgen import canvas

from app.config import Settings


def ffmpeg_bytes(*args: str) -> bytes:
    return subprocess.run(["ffmpeg", "-v", "error", *args], capture_output=True, check=True).stdout


@pytest.fixture(scope="session")
def mp3_bytes() -> bytes:
    return ffmpeg_bytes("-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-f", "mp3", "pipe:1")


@pytest.fixture(scope="session")
def webm_no_duration() -> bytes:
    # Writing to a pipe makes ffmpeg omit duration/cues, like Chrome's MediaRecorder output.
    return ffmpeg_bytes("-f", "lavfi", "-i", "sine=frequency=300:duration=1.5", "-c:a", "libopus",
                        "-f", "webm", "pipe:1")


def make_clip(path: Path, seconds: float, size: str = "854x480", fps: int = 15) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate={fps}:duration={seconds}",
                    "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def make_wav(path: Path, seconds: float) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=500:duration={seconds}",
                    "-ar", "44100", "-ac", "1", str(path)], check=True)
    return path


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration:stream=codec_type,width,height,r_frame_rate", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    info = json.loads(out)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    num, den = video["r_frame_rate"].split("/")
    return {"duration": float(info["format"]["duration"]), "width": video["width"], "height": video["height"],
            "fps": round(int(num) / int(den)), "has_audio": any(s["codec_type"] == "audio" for s in info["streams"])}


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
