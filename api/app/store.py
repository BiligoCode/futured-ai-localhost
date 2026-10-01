import asyncio
import os
import shutil
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.models import Project, Scene, SceneDraft, SceneNotFound

__all__ = ["ProjectNotFound", "ProjectStore", "SceneNotFound", "new_scene_id"]

INTERRUPTED = "Interrupted by server restart"
CANCELLED = "Cancelled"
BUSY_RENDER = {"generating", "rendering", "repairing"}


class ProjectNotFound(KeyError):
    pass


def new_scene_id() -> str:
    return uuid.uuid4().hex[:8]


class ProjectStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.projects_dir = self.root / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def project_dir(self, project_id: str) -> Path:
        return self.projects_dir / project_id

    def scene_dir(self, project_id: str, scene_id: str) -> Path:
        d = self.project_dir(project_id) / "scenes" / scene_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def create(self, *, title: str, concept: str, style: str, duration: str = "medium", language: str,
               material_text: str, scenes: list[SceneDraft], deck_id: str | None = None,
               deck_text: str = "") -> Project:
        project = Project(
            id=uuid.uuid4().hex[:10],
            created_at=datetime.now(timezone.utc),
            title=title,
            concept=concept,
            style=style,
            duration=duration,
            language=language,
            deck_id=deck_id,
            scenes=[Scene(id=new_scene_id(), title=d.title, visual=d.visual, narration=d.narration)
                    for d in scenes],
        )
        self.project_dir(project.id).mkdir(parents=True)
        (self.project_dir(project.id) / "material.txt").write_text(material_text, encoding="utf-8")
        if deck_text:
            (self.project_dir(project.id) / "deck.txt").write_text(deck_text, encoding="utf-8")
        self.save(project)
        return project

    def get(self, project_id: str) -> Project:
        path = self.project_dir(project_id) / "project.json"
        if not project_id or "/" in project_id or not path.is_file():
            raise ProjectNotFound(project_id)
        return Project.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self) -> list[Project]:
        projects = [self.get(p.name) for p in self.projects_dir.iterdir()
                    if (p / "project.json").is_file()]
        return sorted(projects, key=lambda p: p.created_at, reverse=True)

    def material(self, project_id: str) -> str:
        """The professor's own course material (what the setup form shows again)."""
        self.get(project_id)
        return (self.project_dir(project_id) / "material.txt").read_text(encoding="utf-8")

    def full_material(self, project_id: str) -> str:
        """What the model reads: the slides the animation was made from (if any), then the professor's material."""
        deck = self.project_dir(project_id) / "deck.txt"
        parts = [deck.read_text(encoding="utf-8") if deck.is_file() else "", self.material(project_id)]
        return "\n\n".join(p for p in parts if p)

    async def delete(self, project_id: str) -> None:
        self.get(project_id)
        async with self._locks[project_id]:
            # A worker thread of a cancelled job may still be writing a file here; leftovers have no project.json.
            shutil.rmtree(self.project_dir(project_id), ignore_errors=True)
        self._locks.pop(project_id, None)

    async def stop_busy(self, project_id: str) -> Project:
        """After its jobs were cancelled: nothing is in progress any more; finished work is kept."""
        def apply(project: Project) -> None:
            project.narrating = False
            for scene in project.scenes:
                if scene.render_status in BUSY_RENDER:
                    done = scene.code_version > 0
                    scene.render_status = "done" if done else "failed"
                    scene.last_error = None if done else CANCELLED  # a kept render is not an unapplied change
                if scene.audio_status == "generating":
                    scene.audio_status = "done" if scene.audio_version > 0 else "none"

        return await self.mutate(project_id, apply)

    def save(self, project: Project) -> None:
        path = self.project_dir(project.id) / "project.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(project.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, path)

    async def mutate(self, project_id: str, fn: Callable[[Project], None]) -> Project:
        async with self._locks[project_id]:
            project = self.get(project_id)
            fn(project)
            self.save(project)
            return project

    async def update_scene(self, project_id: str, scene_id: str, **fields) -> Scene:
        def apply(project: Project) -> None:
            scene = project.scene(scene_id)
            for key, value in fields.items():
                setattr(scene, key, value)

        project = await self.mutate(project_id, apply)
        return project.scene(scene_id)

    def recover_interrupted(self) -> int:
        changed = 0
        for project in self.list():
            dirty = False
            for cut in (project.preview, project.final):
                if cut.status == "building":
                    cut.status = "done" if cut.version > 0 else "none"
                    dirty = True
            if project.narrating:
                project.narrating = False
                dirty = True
            for scene in project.scenes:
                touched = False
                if scene.render_status in BUSY_RENDER:
                    scene.render_status = "done" if scene.code_version > 0 else "failed"
                    scene.last_error = INTERRUPTED
                    touched = True
                if scene.audio_status == "generating":
                    scene.audio_status = "failed"
                    touched = True
                if touched:
                    changed += 1
                    dirty = True
            if dirty:
                self.save(project)
        return changed
