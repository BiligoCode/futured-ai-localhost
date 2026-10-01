from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse

from app.models import Project, ReviseRequest
from app.pipeline import build_scene

router = APIRouter()

BUSY = "Scene is already being processed"


def job_key(project_id: str, scene_id: str) -> str:
    return f"{project_id}:{scene_id}"


async def _start(request: Request, project_id: str, scene_id: str, instruction: str | None = None) -> bool:
    app = request.app
    key = job_key(project_id, scene_id)
    if app.state.jobs.is_running(key):
        return False
    await app.state.store.update_scene(project_id, scene_id, render_status="generating", last_error=None)

    async def job() -> None:
        await build_scene(app.state.store, app.state.llm, app.state.renderer, project_id, scene_id,
                          instruction=instruction)

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
