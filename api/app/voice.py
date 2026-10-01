import asyncio
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.captions import cues_from_alignment, cues_to_json
from app.media import cut_audio, normalize_audio, probe_duration
from app.models import Hold, Project, Scene, Segment
from app.store import ProjectStore
from app.tts import TTSProvider, synthesize_timed

AUDIO_FILE = "audio.wav"
CAPTIONS_FILE = "captions.json"  # timed caption cues of the AI voice
RECORDING_FILE = "voice.webm"
TAKES_DIR = "takes"
EPS = 0.02
MIN_AUDIO_S = 0.1


class TakeError(ValueError):
    pass


def _write_normalized(data: bytes, suffix: str, dst: Path) -> None:
    """Normalize `data` to a wav next to `dst`, then atomically replace `dst`."""
    with tempfile.TemporaryDirectory(dir=dst.parent) as tmp:
        src = Path(tmp) / f"input{suffix}"
        src.write_bytes(data)
        out = Path(tmp) / "audio.wav"
        normalize_audio(src, out)
        os.replace(out, dst)


def _set_audio(project: Project, scene_id: str, source: str, holds: list[Hold] | None = None) -> None:
    scene = project.scene(scene_id)
    scene.audio_source, scene.audio_status = source, "done"
    scene.audio_version += 1
    scene.holds = holds or []
    scene.audio_stale = False


async def generate_ai_voice(store: ProjectStore, tts: TTSProvider, project_id: str, scene_id: str) -> Scene:
    project = store.get(project_id)
    scene = project.scene(scene_id)
    await store.update_scene(project_id, scene_id, audio_status="generating")
    try:
        audio, alignment = await asyncio.to_thread(synthesize_timed, tts, scene.narration, project.language)
        scene_dir = store.scene_dir(project_id, scene_id)
        await asyncio.to_thread(_write_normalized, audio, ".mp3", scene_dir / AUDIO_FILE)
        captions = scene_dir / CAPTIONS_FILE
        if alignment:
            captions.write_text(json.dumps(cues_to_json(cues_from_alignment(alignment)), ensure_ascii=False),
                                encoding="utf-8")
        else:
            captions.unlink(missing_ok=True)  # captions are then timed from the text
    except Exception:
        # A failed attempt must not drop a voice that still exists and would otherwise be exported.
        restored = "done" if scene.audio_status == "done" else "failed"
        await store.update_scene(project_id, scene_id, audio_status=restored)
        raise
    project = await store.mutate(project_id, lambda p: _set_audio(p, scene_id, "ai"))
    return project.scene(scene_id)


async def generate_ai_narration(store: ProjectStore, tts: TTSProvider, project_id: str) -> None:
    """Give every scene an AI voice (replacing recordings). Stops at the first failure, keeping what was done."""
    await store.mutate(project_id, lambda p: setattr(p, "narrating", True))
    try:
        for scene in store.get(project_id).scenes:
            if not (scene.audio_source == "ai" and scene.audio_status == "done"):
                await generate_ai_voice(store, tts, project_id, scene.id)
    finally:
        await store.mutate(project_id, lambda p: setattr(p, "narrating", False))


async def attach_recording(store: ProjectStore, project_id: str, scene_id: str, data: bytes) -> Scene:
    """Store a professor recording. Raises MediaError (leaving existing audio untouched) if unreadable."""
    store.get(project_id).scene(scene_id)
    scene_dir = store.scene_dir(project_id, scene_id)
    await asyncio.to_thread(_write_normalized, data, ".webm", scene_dir / AUDIO_FILE)
    (scene_dir / RECORDING_FILE).write_bytes(data)
    (scene_dir / CAPTIONS_FILE).unlink(missing_ok=True)
    project = await store.mutate(project_id, lambda p: _set_audio(p, scene_id, "professor"))
    return project.scene(scene_id)


async def clear_voice(store: ProjectStore, project_id: str, scene_id: str) -> Scene:
    store.get(project_id).scene(scene_id)
    scene_dir = store.scene_dir(project_id, scene_id)
    for name in (AUDIO_FILE, RECORDING_FILE, CAPTIONS_FILE):
        (scene_dir / name).unlink(missing_ok=True)

    def apply(project: Project) -> None:
        scene = project.scene(scene_id)
        scene.audio_source, scene.audio_status, scene.holds, scene.audio_stale = None, "none", [], False

    project = await store.mutate(project_id, apply)
    return project.scene(scene_id)


@dataclass
class TakePart:
    scene_id: str
    start: float          # seconds into the recording
    end: float | None     # None: to the end of the recording
    holds: list[Hold]     # in seconds into the scene


def split_take(segments: list[Segment], start_index: int, holds: list[Hold], take_s: float) -> list[TakePart]:
    """Split one recording, made over the preview from scene `start_index` on, into per-scene parts.

    `holds` are the pauses the professor made, at preview times. A pause exactly at a scene boundary belongs to the
    scene that just ended (its last frame is what was on screen). Scenes the recording did not reach are left out.
    """
    start = segments[start_index].start
    holds = sorted((h for h in holds if h.at >= start - EPS), key=lambda h: h.at)

    def held_until(t: float) -> float:
        return sum(h.duration for h in holds if h.at <= t + EPS)

    parts = []
    for k, seg in enumerate(segments[start_index:]):
        first, last = k == 0, start_index + k == len(segments) - 1
        r0 = 0.0 if first else seg.start - start + held_until(seg.start)
        if r0 >= take_s - MIN_AUDIO_S:
            break
        r1 = None if last else seg.end - start + held_until(seg.end)
        if r1 is not None and r1 >= take_s - EPS:
            r1 = None
        length = seg.end - seg.start
        own = [Hold(at=round(min(max(h.at - seg.start, 0.0), length), 3), duration=round(h.duration, 3))
               for h in holds if (first or h.at > seg.start + EPS) and (last or h.at <= seg.end + EPS)]
        parts.append(TakePart(scene_id=seg.scene_id, start=round(r0, 3), end=None if r1 is None else round(r1, 3),
                              holds=own))
        if r1 is None:
            break
    return parts


async def attach_take(store: ProjectStore, project_id: str, data: bytes, *, from_scene: str,
                      holds: list[Hold]) -> Project:
    """Store a recording the professor made over the whole animation (or from one scene on)."""
    project = store.get(project_id)
    preview = project.preview
    if preview.status != "done" or preview.signature != project.preview_signature():
        raise TakeError("The video changed while you were recording. Please record again.")
    index = next((i for i, s in enumerate(preview.segments) if s.scene_id == from_scene), None)
    if index is None:
        raise TakeError("Unknown starting point for the recording")

    takes = store.project_dir(project_id) / TAKES_DIR
    takes.mkdir(exist_ok=True)
    number = len(list(takes.glob("take_*.webm"))) + 1
    (takes / f"take_{number}.webm").write_bytes(data)
    wav = takes / f"take_{number}.wav"
    await asyncio.to_thread(_write_normalized, data, ".webm", wav)
    parts = split_take(preview.segments, index, holds, await asyncio.to_thread(probe_duration, wav))
    if not parts:
        raise TakeError("The recording is empty")

    for part in parts:
        scene_dir = store.scene_dir(project_id, part.scene_id)
        tmp = scene_dir / "audio.tmp.wav"
        await asyncio.to_thread(cut_audio, wav, part.start, part.end, tmp)
        os.replace(tmp, scene_dir / AUDIO_FILE)
        for name in (RECORDING_FILE, CAPTIONS_FILE):
            (scene_dir / name).unlink(missing_ok=True)

    def apply(p: Project) -> None:
        for part in parts:
            _set_audio(p, part.scene_id, "professor", part.holds)

    return await store.mutate(project_id, apply)
