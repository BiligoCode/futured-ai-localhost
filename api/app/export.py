import asyncio
from pathlib import Path

from app.media import assemble
from app.store import ProjectStore
from app.voice import AUDIO_FILE

EXPORT_FILE = "export.mp4"


class ExportNotReady(RuntimeError):
    pass


async def export_project(store: ProjectStore, project_id: str) -> Path:
    project = store.get(project_id)
    if not project.scenes or any(s.render_status != "done" or s.code_version == 0 for s in project.scenes):
        raise ExportNotReady("All scenes must be rendered before export")
    segments = []
    for scene in project.scenes:
        scene_dir = store.scene_dir(project_id, scene.id)
        audio = scene_dir / AUDIO_FILE if scene.audio_status == "done" else None
        segments.append((scene_dir / f"render_v{scene.code_version}.mp4", audio))
    out = store.project_dir(project_id) / EXPORT_FILE
    await asyncio.to_thread(assemble, segments, out)
    return out
