from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.compose import ExportNotReady, cut_path, export_project
from app.models import CutKind, Project
from app.routes.common import schedule_refresh

router = APIRouter()


@router.post("/projects/{project_id}/export")
async def export(project_id: str, request: Request) -> dict[str, str]:
    try:
        kind, _ = await export_project(request.app.state.store, project_id)
    except ExportNotReady as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"url": f"/projects/{project_id}/{'export' if kind == 'final' else 'preview'}.mp4"}


@router.post("/projects/{project_id}/compose")
async def compose(project_id: str, request: Request) -> Project:
    """Retry putting the video together (e.g. after a failure)."""
    await schedule_refresh(request.app, project_id)
    return request.app.state.store.get(project_id)


def _serve(request: Request, project_id: str, kind: CutKind, missing: str) -> FileResponse:
    store = request.app.state.store
    project = store.get(project_id)
    path = cut_path(store, project_id, kind)
    if not path.is_file():
        raise HTTPException(404, missing)
    return FileResponse(path, media_type="video/mp4", filename=f"{project.title or project_id}.mp4")


@router.get("/projects/{project_id}/export.mp4")
def download(project_id: str, request: Request) -> FileResponse:
    return _serve(request, project_id, "final", "This project has no narrated video yet")


@router.get("/projects/{project_id}/preview.mp4")
def preview(project_id: str, request: Request) -> FileResponse:
    return _serve(request, project_id, "preview", "The video is not ready yet")
