import asyncio

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse

from app.ingest import EmptyMaterialError, build_material
from app.models import DurationRange, Language, Project, ProjectSettings, Scene, StoryboardUpdate
from app.routes.common import schedule_refresh
from app.store import new_scene_id
from app.storyboard import StoryboardError, generate_storyboard
from app.voice import clear_voice

router = APIRouter()


@router.post("/projects")
async def create_project(
    request: Request,
    concept: str = Form(min_length=1),
    style: str = Form(""),
    duration: DurationRange = Form("medium"),
    language: Language = Form("el"),
    material_text: str = Form(""),
    files: list[UploadFile] | None = File(None),
    replaces: str = Form(""),
) -> Project:
    """Draft a script. With `replaces` (back to setup from an existing video), that project is deleted once the
    new script exists, so a failed or cancelled redraft leaves it untouched."""
    store = request.app.state.store
    if replaces:
        store.get(replaces)
    pdfs = [await f.read() for f in files or []]
    try:
        material = await asyncio.to_thread(build_material, pdfs, material_text)
    except EmptyMaterialError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        title, drafts = await asyncio.to_thread(
            generate_storyboard, request.app.state.llm, material=material, concept=concept,
            style=style, duration=duration, language=language)
    except StoryboardError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - Bedrock/network errors must reach the UI as a readable 502
        raise HTTPException(502, f"The AI model request failed: {exc}") from exc
    if await request.is_disconnected():
        raise HTTPException(499, "Cancelled")  # the professor cancelled while the script was being drafted
    project = store.create(title=title, concept=concept, style=style, duration=duration, language=language,
                           material_text=material, scenes=drafts)
    if replaces:
        await _delete(request.app, replaces)
    return project


@router.get("/projects")
def list_projects(request: Request) -> list[Project]:
    return request.app.state.store.list()


@router.get("/projects/{project_id}")
def get_project(project_id: str, request: Request) -> Project:
    return request.app.state.store.get(project_id)


@router.get("/projects/{project_id}/material")
def get_material(project_id: str, request: Request) -> PlainTextResponse:
    """The course material as text (what was extracted from the PDFs plus pasted text), to edit in setup."""
    return PlainTextResponse(request.app.state.store.material(project_id))


async def _cancel_jobs(app, project_id: str) -> None:
    jobs = app.state.jobs
    await jobs.cancel(jobs.keys(f"{project_id}:") + [f"narration:{project_id}"])


@router.post("/projects/{project_id}/cancel")
async def cancel_project(project_id: str, request: Request) -> Project:
    """Stop everything being generated for this video. Finished scenes and voices are kept."""
    store = request.app.state.store
    store.get(project_id)
    await _cancel_jobs(request.app, project_id)
    await store.stop_busy(project_id)
    await schedule_refresh(request.app, project_id)
    return store.get(project_id)


async def _delete(app, project_id: str) -> None:
    await _cancel_jobs(app, project_id)
    # Cancelled jobs may have queued a rebuild of the videos on their way out: stop that last.
    await app.state.jobs.cancel([f"cuts:{project_id}"])
    await app.state.store.delete(project_id)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: str, request: Request) -> None:
    request.app.state.store.get(project_id)
    await _delete(request.app, project_id)


@router.post("/projects/{project_id}/reopen")
async def reopen_script(project_id: str, request: Request) -> Project:
    """Back from the video to the script. Running work stops; renders and voices are kept, and on approval only
    the parts whose script changed are made again."""
    store = request.app.state.store
    store.get(project_id)
    await _cancel_jobs(request.app, project_id)
    await store.stop_busy(project_id)
    project = await store.mutate(project_id, lambda p: setattr(p, "stage", "storyboard"))
    await schedule_refresh(request.app, project_id)
    return project


@router.put("/projects/{project_id}/storyboard")
async def update_storyboard(project_id: str, body: StoryboardUpdate, request: Request) -> Project:
    store = request.app.state.store
    if store.get(project_id).stage != "storyboard":
        raise HTTPException(409, "Storyboard can only be edited before rendering starts")

    revoice: list[str] = []

    def apply(project: Project) -> None:
        existing = {s.id: s for s in project.scenes}
        scenes = []
        for d in body.scenes:
            if d.id in existing:
                scene = existing[d.id]
                if (scene.title, scene.visual) != (d.title, d.visual) and scene.code_version > 0:
                    scene.render_status, scene.last_error = "pending", None  # made again on approval
                if scene.narration != d.narration and scene.audio_status == "done":
                    if scene.audio_source == "ai":
                        revoice.append(scene.id)  # the AI voice reads the old text
                    else:
                        scene.audio_stale = True  # the professor said the old text; they may re-record
                scene.title, scene.visual, scene.narration = d.title, d.visual, d.narration
            else:
                scene = Scene(id=new_scene_id(), title=d.title, visual=d.visual, narration=d.narration)
            scenes.append(scene)
        project.scenes = scenes

    await store.mutate(project_id, apply)
    for scene_id in revoice:
        await clear_voice(store, project_id, scene_id)
    return store.get(project_id)


@router.patch("/projects/{project_id}/settings")
async def update_settings(project_id: str, body: ProjectSettings, request: Request) -> Project:
    """Project options that change the finished video, e.g. burned-in captions."""
    store = request.app.state.store

    def apply(project: Project) -> None:
        if body.captions is not None:
            project.captions = body.captions

    await store.mutate(project_id, apply)
    await schedule_refresh(request.app, project_id)
    return store.get(project_id)
