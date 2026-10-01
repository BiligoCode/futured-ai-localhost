from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, load_settings
from app.i18n import request_language, translate
from app.jobs import JobRunner
from app.llm import LLM, BedrockLLM
from app.render import Renderer, make_renderer
from app.routes import export, projects, scenes, voice
from app.routes.common import schedule_refresh
from app.store import ProjectNotFound, ProjectStore, SceneNotFound
from app.tts import CachedTTS, ElevenLabsTTS, TTSProvider


def create_app(settings: Settings, *, llm: LLM | None = None, renderer: Renderer | None = None,
               tts: TTSProvider | None = None) -> FastAPI:
    store = ProjectStore(settings.data_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.recover_interrupted()
        # Projects made before videos were composed (or interrupted mid-compose) get their videos built now.
        for project in store.list():
            if project.preview_outdated or project.final_outdated:
                await schedule_refresh(app, project.id)
        yield

    app = FastAPI(title="Lara API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.store = store
    app.state.llm = llm or BedrockLLM(settings)
    app.state.renderer = renderer or make_renderer(settings)
    app.state.tts = tts or CachedTTS(
        ElevenLabsTTS(settings.elevenlabs_api_key, settings.elevenlabs_voice_id, settings.elevenlabs_model,
                      voices={"el": settings.elevenlabs_voice_id_el, "en": settings.elevenlabs_voice_id_en},
                      voice_settings=dict(settings.elevenlabs_voice_settings)),
        settings.data_dir / "tts_cache")
    app.state.jobs = JobRunner()

    def error(request: Request, status: int, detail: str, headers=None) -> JSONResponse:
        return JSONResponse({"detail": translate(detail, request_language(request))}, status_code=status,
                            headers=headers)

    @app.exception_handler(ProjectNotFound)
    async def project_not_found(request: Request, exc: ProjectNotFound) -> JSONResponse:
        return error(request, 404, "Project not found")

    @app.exception_handler(SceneNotFound)
    async def scene_not_found(request: Request, exc: SceneNotFound) -> JSONResponse:
        return error(request, 404, "Scene not found")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error(request, exc.status_code, exc.detail, getattr(exc, "headers", None))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(projects.router)
    app.include_router(scenes.router)
    app.include_router(voice.router)
    app.include_router(export.router)
    return app


def create_default_app() -> FastAPI:
    return create_app(load_settings())
