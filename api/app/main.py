from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, load_settings
from app.jobs import JobRunner
from app.llm import LLM, BedrockLLM
from app.render import Renderer, make_renderer
from app.routes import export, projects, scenes, voice
from app.store import ProjectNotFound, ProjectStore, SceneNotFound
from app.tts import CachedTTS, ElevenLabsTTS, TTSProvider


def create_app(settings: Settings, *, llm: LLM | None = None, renderer: Renderer | None = None,
               tts: TTSProvider | None = None) -> FastAPI:
    store = ProjectStore(settings.data_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.recover_interrupted()
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
    app.state.tts = tts or CachedTTS(ElevenLabsTTS(settings.elevenlabs_api_key, settings.elevenlabs_voice_id),
                                     settings.data_dir / "tts_cache")
    app.state.jobs = JobRunner()

    @app.exception_handler(ProjectNotFound)
    async def project_not_found(_: Request, exc: ProjectNotFound) -> JSONResponse:
        return JSONResponse({"detail": "Project not found"}, status_code=404)

    @app.exception_handler(SceneNotFound)
    async def scene_not_found(_: Request, exc: SceneNotFound) -> JSONResponse:
        return JSONResponse({"detail": "Scene not found"}, status_code=404)

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
