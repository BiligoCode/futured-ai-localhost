import asyncio

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.ingest import EmptyMaterialError, build_material
from app.models import Language, Project, Scene, StoryboardUpdate
from app.store import new_scene_id
from app.storyboard import StoryboardError, generate_storyboard

router = APIRouter()


@router.post("/projects")
async def create_project(
    request: Request,
    concept: str = Form(min_length=1),
    style: str = Form(""),
    tone: str = Form(""),
    language: Language = Form("el"),
    material_text: str = Form(""),
    file: UploadFile | None = File(None),
) -> Project:
    pdf_bytes = await file.read() if file is not None else None
    try:
        material = await asyncio.to_thread(build_material, pdf_bytes, material_text)
    except EmptyMaterialError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        title, drafts = await asyncio.to_thread(
            generate_storyboard, request.app.state.llm, material=material, concept=concept,
            style=style, tone=tone, language=language)
    except StoryboardError as exc:
        raise HTTPException(502, str(exc)) from exc
    return request.app.state.store.create(title=title, concept=concept, style=style, tone=tone,
                                          language=language, material_text=material, scenes=drafts)


@router.get("/projects")
def list_projects(request: Request) -> list[Project]:
    return request.app.state.store.list()


@router.get("/projects/{project_id}")
def get_project(project_id: str, request: Request) -> Project:
    return request.app.state.store.get(project_id)


@router.put("/projects/{project_id}/storyboard")
async def update_storyboard(project_id: str, body: StoryboardUpdate, request: Request) -> Project:
    store = request.app.state.store
    if store.get(project_id).stage != "storyboard":
        raise HTTPException(409, "Storyboard can only be edited before rendering starts")

    def apply(project: Project) -> None:
        existing = {s.id: s for s in project.scenes}
        scenes = []
        for d in body.scenes:
            if d.id in existing:
                scene = existing[d.id]
                scene.title, scene.visual, scene.narration = d.title, d.visual, d.narration
            else:
                scene = Scene(id=new_scene_id(), title=d.title, visual=d.visual, narration=d.narration)
            scenes.append(scene)
        project.scenes = scenes

    return await store.mutate(project_id, apply)
