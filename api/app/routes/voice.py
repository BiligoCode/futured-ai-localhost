from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.media import MediaError
from app.models import NarrationUpdate, Project
from app.tts import TTSError
from app.voice import AUDIO_FILE, generate_ai_voice

router = APIRouter()


async def _ai_voice(request: Request, project_id: str, scene_id: str) -> None:
    try:
        await generate_ai_voice(request.app.state.store, request.app.state.tts, project_id, scene_id)
    except (TTSError, MediaError) as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/projects/{project_id}/scenes/{scene_id}/voice/ai")
async def ai_voice(project_id: str, scene_id: str, request: Request) -> Project:
    await _ai_voice(request, project_id, scene_id)
    return request.app.state.store.get(project_id)


@router.post("/projects/{project_id}/voice/ai-all")
async def ai_voice_all(project_id: str, request: Request) -> Project:
    for scene in request.app.state.store.get(project_id).scenes:
        if scene.audio_status in ("none", "failed"):
            await _ai_voice(request, project_id, scene.id)
    return request.app.state.store.get(project_id)


@router.get("/projects/{project_id}/scenes/{scene_id}/audio")
def scene_audio(project_id: str, scene_id: str, request: Request) -> FileResponse:
    store = request.app.state.store
    scene = store.get(project_id).scene(scene_id)
    path = store.scene_dir(project_id, scene_id) / AUDIO_FILE
    if scene.audio_status != "done" or not path.is_file():
        raise HTTPException(404, "This scene has no narration audio yet")
    return FileResponse(path, media_type="audio/wav")


@router.patch("/projects/{project_id}/scenes/{scene_id}")
async def update_narration(project_id: str, scene_id: str, body: NarrationUpdate, request: Request) -> Project:
    store = request.app.state.store
    audio = store.scene_dir(project_id, scene_id) / AUDIO_FILE

    def apply(project: Project) -> None:
        scene = project.scene(scene_id)
        scene.narration = body.narration
        if scene.audio_source == "ai":
            audio.unlink(missing_ok=True)
            scene.audio_source = None
            scene.audio_status = "none"

    return await store.mutate(project_id, apply)
