import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse

from app.models import EditSummary, Project, ProjectReviseRequest, ReviseRequest, ReviseResult
from app.pipeline import build_scene
from app.revise import Edit, RevisionError, plan_revision
from app.routes.common import schedule_refresh
from app.voice import generate_ai_voice

router = APIRouter()

BUSY = "Scene is already being processed"


def job_key(project_id: str, scene_id: str) -> str:
    return f"{project_id}:{scene_id}"


async def _start(request: Request, project_id: str, scene_id: str, instruction: str | None = None,
                 *, revoice: bool = False) -> bool:
    """Run a scene job: rebuild its animation (unless only `revoice`), regenerate its AI voice if asked, then
    rebuild the project's videos."""
    app = request.app
    key = job_key(project_id, scene_id)
    if app.state.jobs.is_running(key):
        return False
    rebuild = instruction is not None or not revoice
    if rebuild:
        await app.state.store.update_scene(project_id, scene_id, render_status="generating", last_error=None)

    async def job() -> None:
        store = app.state.store
        if rebuild:
            await build_scene(store, app.state.llm, app.state.renderer, project_id, scene_id,
                              instruction=instruction)
        if revoice:
            try:
                await generate_ai_voice(store, app.state.tts, project_id, scene_id)
            except Exception:  # noqa: BLE001 - the scene keeps its previous voice (or shows the voice as failed)
                pass
        await schedule_refresh(app, project_id)

    return app.state.jobs.submit(key, job)


@router.post("/projects/{project_id}/render")
async def render_project(project_id: str, request: Request) -> Project:
    store = request.app.state.store
    await store.mutate(project_id, lambda p: setattr(p, "stage", "scenes"))
    for scene in store.get(project_id).scenes:
        if scene.render_status in ("pending", "failed"):
            await _start(request, project_id, scene.id)
    return store.get(project_id)


@router.post("/projects/{project_id}/scenes/{scene_id}/retry")
async def retry_scene(project_id: str, scene_id: str, request: Request) -> Project:
    request.app.state.store.get(project_id).scene(scene_id)
    if not await _start(request, project_id, scene_id):
        raise HTTPException(409, BUSY)
    return request.app.state.store.get(project_id)


@router.post("/projects/{project_id}/scenes/{scene_id}/revise")
async def revise_scene(project_id: str, scene_id: str, body: ReviseRequest, request: Request) -> Project:
    store = request.app.state.store
    if request.app.state.jobs.is_running(job_key(project_id, scene_id)):
        raise HTTPException(409, BUSY)
    if store.get(project_id).scene(scene_id).code_version == 0:
        raise HTTPException(409, "Scene has not been rendered yet")
    if not await _start(request, project_id, scene_id, body.instruction):
        raise HTTPException(409, BUSY)
    return store.get(project_id)


@router.post("/projects/{project_id}/revise")
async def revise_video(project_id: str, body: ProjectReviseRequest, request: Request) -> ReviseResult:
    """A change request about the whole video: work out which scenes it concerns and change those."""
    app = request.app
    store = app.state.store
    project = store.get(project_id)
    if not project.rendered():
        raise HTTPException(409, "Wait until the video is ready before asking for changes")
    cut = project.final if body.cut == "final" and project.final.version > 0 else project.preview
    try:
        edits: list[Edit] = await asyncio.to_thread(plan_revision, app.state.llm, project, body.instruction,
                                                    cut=cut if cut.version > 0 else None, at_seconds=body.at_seconds)
    except RevisionError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - Bedrock/network errors must reach the UI as a readable 502
        raise HTTPException(502, f"The AI model request failed: {exc}") from exc
    if any(app.state.jobs.is_running(job_key(project_id, e.scene_id)) for e in edits):
        raise HTTPException(409, "That part of the video is still being changed. Try again when it is done.")

    def apply(p: Project) -> None:
        for e in edits:
            if e.narration is None:
                continue
            scene = p.scene(e.scene_id)
            scene.narration = e.narration
            if scene.audio_source == "professor" and scene.audio_status == "done":
                scene.audio_stale = True  # the professor said the old text; they may want to re-record it

    project = await store.mutate(project_id, apply)
    for e in edits:
        scene = project.scene(e.scene_id)
        revoice = e.narration is not None and scene.audio_source == "ai" and scene.audio_status == "done"
        if e.animation or revoice:
            await _start(request, project_id, e.scene_id, e.instruction if e.animation else None, revoice=revoice)

    times = {seg.scene_id: seg for seg in cut.segments}
    summaries = [EditSummary(scene_id=e.scene_id, start=times[e.scene_id].start if e.scene_id in times else None,
                             end=times[e.scene_id].end if e.scene_id in times else None, summary=e.summary,
                             animation=e.animation, narration=e.narration is not None) for e in edits]
    return ReviseResult(project=store.get(project_id), edits=summaries)


def _current_file(request: Request, project_id: str, scene_id: str, pattern: str):
    store = request.app.state.store
    version = store.get(project_id).scene(scene_id).code_version
    path = store.scene_dir(project_id, scene_id) / pattern.format(version)
    if version == 0 or not path.is_file():
        raise HTTPException(404, "Scene has not been rendered yet")
    return path


@router.get("/projects/{project_id}/scenes/{scene_id}/video")
def scene_video(project_id: str, scene_id: str, request: Request) -> FileResponse:
    return FileResponse(_current_file(request, project_id, scene_id, "render_v{}.mp4"), media_type="video/mp4")


@router.get("/projects/{project_id}/scenes/{scene_id}/code")
def scene_code(project_id: str, scene_id: str, request: Request) -> PlainTextResponse:
    path = _current_file(request, project_id, scene_id, "code_v{}.py")
    return PlainTextResponse(path.read_text(encoding="utf-8"))
