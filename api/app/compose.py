"""Compose the project's scenes into the single videos the professor sees: the preview (animation only) and the
final video (animation with narration and the professor's pauses), each with a timeline of where every scene sits."""
import asyncio
import json
import logging
import os
from collections import defaultdict
from pathlib import Path

from app.captions import cues_from_json, cues_from_text, to_ass
from app.media import concat, encode_segment, probe_duration
from app.models import Cut, CutKind, Project, Scene, Segment
from app.store import ProjectStore
from app.voice import AUDIO_FILE, CAPTIONS_FILE

log = logging.getLogger(__name__)

FILES: dict[CutKind, str] = {"preview": "preview.mp4", "final": "export.mp4"}
SEGMENTS_DIR = "segments"

_locks: defaultdict[Path, asyncio.Lock] = defaultdict(asyncio.Lock)


class ExportNotReady(RuntimeError):
    pass


def cut_path(store: ProjectStore, project_id: str, kind: CutKind) -> Path:
    return store.project_dir(project_id) / FILES[kind]


def _wanted(project: Project, kind: CutKind) -> str | None:
    """The signature the cut should have, or None when it should not exist yet."""
    if not project.rendered():
        return None
    if kind == "preview":
        return project.preview_signature()
    return project.final_signature() if project.voiced() else None


def _captions(scene_dir: Path, scene: Scene, out: Path) -> Path:
    """Write the scene's caption file: timed from the AI voice when available, else spread over the audio."""
    timed = scene_dir / CAPTIONS_FILE
    if timed.is_file():
        cues = cues_from_json(json.loads(timed.read_text(encoding="utf-8")))
    else:
        cues = cues_from_text(scene.narration, probe_duration(scene_dir / AUDIO_FILE))
    out.write_text(to_ass(cues), encoding="utf-8")
    return out


def _segment(store: ProjectStore, project_id: str, scene: Scene, kind: CutKind,
             captions: bool = False) -> tuple[Path, float]:
    """Encode (or reuse) one scene's part of a cut. Unchanged scenes are not re-encoded."""
    scene_dir = store.scene_dir(project_id, scene.id)
    voiced = kind == "final" and scene.audio_status == "done"
    # Captions follow the script, so only the AI voice (which reads it word for word) gets them.
    captioned = captions and voiced and scene.audio_source == "ai"
    name = f"{kind}-{scene.code_version}-{scene.audio_version if voiced else 0}{'-cc' if captioned else ''}.mp4"
    out = scene_dir / SEGMENTS_DIR / name
    if not out.is_file():
        tmp = out.with_suffix(".tmp.mp4")
        out.parent.mkdir(parents=True, exist_ok=True)
        ass = _captions(scene_dir, scene, out.with_suffix(".ass")) if captioned else None
        encode_segment(scene_dir / f"render_v{scene.code_version}.mp4", scene_dir / AUDIO_FILE if voiced else None,
                       tmp, [(h.at, h.duration) for h in scene.holds] if voiced else [], captions=ass)
        os.replace(tmp, out)
        for old in out.parent.glob(f"{kind}-*"):
            if old not in (out, out.with_suffix(".ass")):
                old.unlink(missing_ok=True)
    return out, probe_duration(out)


def _compose(store: ProjectStore, project: Project, kind: CutKind) -> tuple[float, list[Segment]]:
    parts, segments, t = [], [], 0.0
    for scene in project.scenes:
        part, duration = _segment(store, project.id, scene, kind, captions=project.captions)
        parts.append(part)
        segments.append(Segment(scene_id=scene.id, start=round(t, 3), end=round(t + duration, 3)))
        t += duration
    concat(parts, cut_path(store, project.id, kind))
    return round(t, 3), segments


async def mark_pending(store: ProjectStore, project_id: str) -> None:
    """Flag cuts that are about to be rebuilt, so the dashboard keeps polling until they are."""
    def apply(project: Project) -> None:
        for kind in ("preview", "final"):
            cut: Cut = getattr(project, kind)
            wanted = _wanted(project, kind)
            if wanted is not None and wanted != cut.signature:
                cut.status = "building"

    await store.mutate(project_id, apply)


async def refresh_cuts(store: ProjectStore, project_id: str) -> None:
    """Bring the preview and final video up to date with the scenes. Safe to call often: it only redoes what
    changed, and calls for one project run one at a time."""
    async with _locks[store.project_dir(project_id)]:
        for kind in ("preview", "final"):
            await _refresh(store, project_id, kind)


async def _refresh(store: ProjectStore, project_id: str, kind: CutKind) -> None:
    project = store.get(project_id)
    cut: Cut = getattr(project, kind)
    wanted = _wanted(project, kind)
    if wanted is None:
        if kind == "final" and project.rendered() and cut.version > 0:
            # Every voice was removed: the narrated video no longer exists.
            await store.mutate(project_id, lambda p: setattr(p, "final", Cut()))
            cut_path(store, project_id, "final").unlink(missing_ok=True)
        return
    if wanted == cut.signature and cut.status == "done":
        return

    await store.mutate(project_id, lambda p: setattr(getattr(p, kind), "status", "building"))
    try:
        duration, segments = await asyncio.to_thread(_compose, store, project, kind)
    except Exception as exc:  # noqa: BLE001 - shown on the dashboard, which offers a retry
        log.exception("composing %s for %s failed", kind, project_id)

        def failed(p: Project) -> None:
            c: Cut = getattr(p, kind)
            c.status, c.error = "failed", str(exc) or repr(exc)

        await store.mutate(project_id, failed)
        return

    def done(p: Project) -> None:
        setattr(p, kind, Cut(status="done", version=cut.version + 1, signature=wanted, duration=duration,
                             segments=segments))

    await store.mutate(project_id, done)


async def export_project(store: ProjectStore, project_id: str) -> tuple[CutKind, Path]:
    """Make sure the downloadable video is current and return it: the narrated one if any narration exists."""
    project = store.get(project_id)
    if not project.rendered():
        raise ExportNotReady("The animation is not finished yet")
    await refresh_cuts(store, project_id)
    project = store.get(project_id)
    kind: CutKind = "final" if project.voiced() else "preview"
    cut: Cut = getattr(project, kind)
    if cut.status != "done":
        raise ExportNotReady(cut.error or "The video could not be put together")
    return kind, cut_path(store, project_id, kind)
