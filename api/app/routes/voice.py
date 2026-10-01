import json

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import TypeAdapter, ValidationError

from app.media import MediaError
from app.models import Hold, NarrationUpdate, Project
from app.routes.common import schedule_refresh
from app.tts import TTSError
from app.voice import (AUDIO_FILE, TakeError, attach_recording, attach_take, clear_voice, generate_ai_narration,
                       generate_ai_voice)

router = APIRouter()

_HOLDS = TypeAdapter(list[Hold])


async def _ai_voice(request: Request, project_id: str, scene_id: str) -> None:
    try:
        await generate_ai_voice(request.app.state.store, request.app.state.tts, project_id, scene_id)
    except (TTSError, MediaError) as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/projects/{project_id}/scenes/{scene_id}/voice/ai")
async def ai_voice(project_id: str, scene_id: str, request: Request) -> Project:
    await _ai_voice(request, project_id, scene_id)
    await schedule_refresh(request.app, project_id)
    return request.app.state.store.get(project_id)


@router.post("/projects/{project_id}/voice/ai-all")
async def ai_voice_all(project_id: str, request: Request) -> Project:
    try:
        for scene in request.app.state.store.get(project_id).scenes:
            if scene.audio_status in ("none", "failed"):
                await _ai_voice(request, project_id, scene.id)
    finally:
        await schedule_refresh(request.app, project_id)
    return request.app.state.store.get(project_id)


@router.post("/projects/{project_id}/narration/ai")
async def ai_narration(project_id: str, request: Request) -> Project:
    """Narrate the whole video with the AI voice, in the background."""
    app = request.app
    store = app.state.store
    if not store.get(project_id).rendered():
        raise HTTPException(409, "Wait until the video is ready before adding narration")
    if store.get(project_id).narrating:
        raise HTTPException(409, "Narration is already being generated")
    await store.mutate(project_id, lambda p: setattr(p, "narrating", True))

    async def job() -> None:
        try:
            await generate_ai_narration(store, app.state.tts, project_id)
        finally:
            await schedule_refresh(app, project_id)

    app.state.jobs.submit(f"narration:{project_id}", job)
    return store.get(project_id)


@router.post("/projects/{project_id}/narration/recording")
async def upload_take(project_id: str, request: Request, file: UploadFile = File(),
                      from_scene: str = Form(), holds: str = Form("[]")) -> Project:
    """A recording made over the whole animation (or from one scene on), with the pauses the professor made."""
    try:
        parsed = _HOLDS.validate_python(json.loads(holds))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, "Invalid pauses in the recording") from exc
    try:
        project = await attach_take(request.app.state.store, project_id, await file.read(), from_scene=from_scene,
                                    holds=parsed)
    except TakeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except MediaError as exc:
        raise HTTPException(422, "Could not read the recording") from exc
    await schedule_refresh(request.app, project_id)
    return request.app.state.store.get(project.id)


@router.post("/projects/{project_id}/scenes/{scene_id}/voice/recording")
async def upload_recording(project_id: str, scene_id: str, request: Request, file: UploadFile = File()) -> Project:
    try:
        await attach_recording(request.app.state.store, project_id, scene_id, await file.read())
    except MediaError as exc:
        raise HTTPException(422, "Could not read the recording") from exc
    await schedule_refresh(request.app, project_id)
    return request.app.state.store.get(project_id)


@router.delete("/projects/{project_id}/scenes/{scene_id}/voice")
async def delete_voice(project_id: str, scene_id: str, request: Request) -> Project:
    await clear_voice(request.app.state.store, project_id, scene_id)
    await schedule_refresh(request.app, project_id)
    return request.app.state.store.get(project_id)


@router.delete("/projects/{project_id}/narration")
async def delete_narration(project_id: str, request: Request) -> Project:
    store = request.app.state.store
    for scene in store.get(project_id).scenes:
        await clear_voice(store, project_id, scene.id)
    await schedule_refresh(request.app, project_id)
    return store.get(project_id)


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

    project = await store.mutate(project_id, apply)
    await schedule_refresh(request.app, project_id)
    return store.get(project.id)
