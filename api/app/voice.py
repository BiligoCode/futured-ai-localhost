import asyncio
import os
import tempfile
from pathlib import Path

from app.media import normalize_audio
from app.models import Scene
from app.store import ProjectStore
from app.tts import TTSProvider

AUDIO_FILE = "audio.wav"
RECORDING_FILE = "voice.webm"


def _write_normalized(data: bytes, suffix: str, dst: Path) -> None:
    """Normalize `data` to a wav next to `dst`, then atomically replace `dst`."""
    with tempfile.TemporaryDirectory(dir=dst.parent) as tmp:
        src = Path(tmp) / f"input{suffix}"
        src.write_bytes(data)
        out = Path(tmp) / "audio.wav"
        normalize_audio(src, out)
        os.replace(out, dst)


async def generate_ai_voice(store: ProjectStore, tts: TTSProvider, project_id: str, scene_id: str) -> Scene:
    project = store.get(project_id)
    scene = project.scene(scene_id)
    await store.update_scene(project_id, scene_id, audio_status="generating")
    try:
        audio = await asyncio.to_thread(tts.synthesize, scene.narration, project.language)
        dst = store.scene_dir(project_id, scene_id) / AUDIO_FILE
        await asyncio.to_thread(_write_normalized, audio, ".mp3", dst)
    except Exception:
        # A failed attempt must not drop a voice that still exists and would otherwise be exported.
        restored = "done" if scene.audio_status == "done" else "failed"
        await store.update_scene(project_id, scene_id, audio_status=restored)
        raise
    return await store.update_scene(project_id, scene_id, audio_source="ai", audio_status="done")


async def attach_recording(store: ProjectStore, project_id: str, scene_id: str, data: bytes) -> Scene:
    """Store a professor recording. Raises MediaError (leaving existing audio untouched) if unreadable."""
    store.get(project_id).scene(scene_id)
    scene_dir = store.scene_dir(project_id, scene_id)
    await asyncio.to_thread(_write_normalized, data, ".webm", scene_dir / AUDIO_FILE)
    (scene_dir / RECORDING_FILE).write_bytes(data)
    return await store.update_scene(project_id, scene_id, audio_source="professor", audio_status="done")


async def clear_voice(store: ProjectStore, project_id: str, scene_id: str) -> Scene:
    store.get(project_id).scene(scene_id)
    scene_dir = store.scene_dir(project_id, scene_id)
    for name in (AUDIO_FILE, RECORDING_FILE):
        (scene_dir / name).unlink(missing_ok=True)
    return await store.update_scene(project_id, scene_id, audio_source=None, audio_status="none")
