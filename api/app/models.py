from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field

Language = Literal["el", "en"]
RenderStatus = Literal["pending", "generating", "rendering", "repairing", "done", "failed"]
AudioStatus = Literal["none", "generating", "done", "failed"]
AudioSource = Literal["ai", "professor"]
CutStatus = Literal["none", "building", "done", "failed"]
CutKind = Literal["preview", "final"]
# Target length of the whole video: under 1 minute, 1–3 minutes, 3–5 minutes.
DurationRange = Literal["short", "medium", "long"]


class SceneDraft(BaseModel):
    id: str | None = None
    title: str = Field(min_length=1)
    visual: str = Field(min_length=1)
    narration: str = Field(min_length=1)


class NarrationUpdate(BaseModel):
    narration: str = Field(min_length=1)


class ReviseRequest(BaseModel):
    instruction: str = Field(min_length=1)


class ProjectReviseRequest(BaseModel):
    instruction: str = Field(min_length=1)
    # Where the professor's player was when they asked, and which video they were watching.
    at_seconds: float | None = Field(default=None, ge=0)
    cut: CutKind = "preview"


class StoryboardUpdate(BaseModel):
    scenes: list[SceneDraft]


class SceneNotFound(KeyError):
    pass


class Hold(BaseModel):
    """A pause the professor made while recording: the frame at `at` (seconds into the scene) is held."""
    at: float = Field(ge=0)
    duration: float = Field(gt=0)


class Scene(BaseModel):
    id: str
    title: str
    visual: str
    narration: str
    code_version: int = 0
    render_status: RenderStatus = "pending"
    attempts: int = 0
    last_error: str | None = None
    # Layout problems the quality gate could not fix (the best render was kept).
    layout_issues: list[str] = []
    audio_source: AudioSource | None = None
    audio_status: AudioStatus = "none"
    audio_version: int = 0
    holds: list[Hold] = []
    # The animation changed after the professor recorded over it.
    audio_stale: bool = False


class Segment(BaseModel):
    scene_id: str
    start: float
    end: float


class Cut(BaseModel):
    """A composed video of the whole project and where each scene sits in it."""
    status: CutStatus = "none"
    version: int = 0
    signature: str = ""
    duration: float = 0
    segments: list[Segment] = []
    error: str | None = None

    def scene_at(self, seconds: float) -> str | None:
        for seg in self.segments:
            if seg.start <= seconds < seg.end:
                return seg.scene_id
        return self.segments[-1].scene_id if self.segments and seconds >= self.segments[-1].end else None


class Project(BaseModel):
    id: str
    created_at: datetime
    title: str
    concept: str
    style: str
    duration: DurationRange = "medium"
    language: Language
    stage: Literal["storyboard", "scenes"] = "storyboard"
    scenes: list[Scene]
    preview: Cut = Cut()  # the animation alone: what the professor narrates over
    final: Cut = Cut()    # the animation with its narration
    narrating: bool = False
    captions: bool = False  # burn captions into the parts narrated by the AI voice

    def scene(self, scene_id: str) -> Scene:
        for s in self.scenes:
            if s.id == scene_id:
                return s
        raise SceneNotFound(scene_id)

    def rendered(self) -> bool:
        return bool(self.scenes) and all(s.render_status == "done" and s.code_version > 0 for s in self.scenes)

    def voiced(self) -> bool:
        return any(s.audio_status == "done" for s in self.scenes)

    def preview_signature(self) -> str:
        return "|".join(f"{s.id}:{s.code_version}" for s in self.scenes)

    def final_signature(self) -> str:
        parts = "|".join(f"{s.id}:{s.code_version}:{s.audio_version if s.audio_status == 'done' else 0}"
                         for s in self.scenes)
        return parts + ("|cc" if self.captions else "")

    @computed_field
    @property
    def preview_outdated(self) -> bool:
        return self.rendered() and self.preview.signature != self.preview_signature()

    @computed_field
    @property
    def final_outdated(self) -> bool:
        if not self.rendered():
            return False
        if not self.voiced():
            return self.final.version > 0
        return self.final.signature != self.final_signature()


class EditSummary(BaseModel):
    scene_id: str
    start: float | None = None
    end: float | None = None
    summary: str
    animation: bool
    narration: bool


class ProjectSettings(BaseModel):
    captions: bool | None = None


class ReviseResult(BaseModel):
    project: Project
    edits: list[EditSummary]
