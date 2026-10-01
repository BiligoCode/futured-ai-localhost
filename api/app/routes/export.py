from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.export import EXPORT_FILE, ExportNotReady, export_project
from app.media import MediaError

router = APIRouter()


@router.post("/projects/{project_id}/export")
async def export(project_id: str, request: Request) -> dict[str, str]:
    try:
        await export_project(request.app.state.store, project_id)
    except ExportNotReady as exc:
        raise HTTPException(409, str(exc)) from exc
    except MediaError as exc:
        raise HTTPException(500, f"Export failed: {exc}") from exc
    return {"url": f"/projects/{project_id}/export.mp4"}


@router.get("/projects/{project_id}/export.mp4")
def download(project_id: str, request: Request) -> FileResponse:
    store = request.app.state.store
    path = store.project_dir(project_id) / EXPORT_FILE
    store.get(project_id)
    if not path.is_file():
        raise HTTPException(404, "This project has not been exported yet")
    return FileResponse(path, media_type="video/mp4", filename=f"{project_id}.mp4")
