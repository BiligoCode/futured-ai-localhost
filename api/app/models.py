from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Language = Literal["el", "en"]
RenderStatus = Literal["pending", "generating", "rendering", "repairing", "done", "failed"]
AudioStatus = Literal["none", "generating", "done", "failed"]
AudioSource = Literal["ai", "professor"]


class SceneDraft(BaseModel):
    id: str | None = None
    title: str = Field(min_length=1)
    visual: str = Field(min_length=1)
    narration: str = Field(min_length=1)


class NarrationUpdate(BaseModel):
    narration: str = Field(min_length=1)


class ReviseRequest(BaseModel):
    instruction: str = Field(min_length=1)


class StoryboardUpdate(BaseModel):
    scenes: list[SceneDraft]


class SceneNotFound(KeyError):
    pass


class Scene(BaseModel):
    id: str
    title: str
    visual: str
    narration: str
    code_version: int = 0
    render_status: RenderStatus = "pending"
    attempts: int = 0
    last_error: str | None = None
    audio_source: AudioSource | None = None
    audio_status: AudioStatus = "none"


class Project(BaseModel):
    id: str
    created_at: datetime
    title: str
    concept: str
    style: str
    tone: str
    language: Language
    stage: Literal["storyboard", "scenes"] = "storyboard"
    scenes: list[Scene]

    def scene(self, scene_id: str) -> Scene:
        for s in self.scenes:
            if s.id == scene_id:
                return s
        raise SceneNotFound(scene_id)
