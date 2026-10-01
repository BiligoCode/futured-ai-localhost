from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, load_settings
from app.llm import LLM, BedrockLLM
from app.routes import projects
from app.store import ProjectNotFound, ProjectStore, SceneNotFound


def create_app(settings: Settings, *, llm: LLM | None = None) -> FastAPI:
    app = FastAPI(title="Educator Visual Explanations API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.store = ProjectStore(settings.data_dir)
    app.state.llm = llm or BedrockLLM(settings)

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
    return app


def create_default_app() -> FastAPI:
    return create_app(load_settings())
