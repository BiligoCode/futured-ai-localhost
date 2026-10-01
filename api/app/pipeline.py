import asyncio
import logging
import re
from pathlib import Path

from app.codegen import MAX_REPAIRS, generate_code, precheck, repair_code, revise_code
from app.llm import LLM
from app.render import Renderer
from app.store import ProjectStore

log = logging.getLogger(__name__)

_CODE_FILE = re.compile(r"code_v(\d+)\.py$")


def _next_version(scene_dir: Path) -> int:
    versions = [int(m.group(1)) for p in scene_dir.glob("code_v*.py") if (m := _CODE_FILE.search(p.name))]
    return max(versions, default=0) + 1


async def build_scene(store: ProjectStore, llm: LLM, renderer: Renderer, project_id: str, scene_id: str,
                      *, instruction: str | None = None) -> None:
    """Generate (or revise) a scene's Manim code, render it, and self-repair on failure. Never raises."""
    try:
        await store.update_scene(project_id, scene_id, render_status="generating", attempts=0, last_error=None)
        project = store.get(project_id)
        scene = project.scene(scene_id)
        scene_dir = store.scene_dir(project_id, scene_id)
        language = project.language

        if instruction and scene.code_version > 0:
            current = (scene_dir / f"code_v{scene.code_version}.py").read_text(encoding="utf-8")
            code = await asyncio.to_thread(revise_code, llm, current, scene, instruction, language=language)
        else:
            code = await asyncio.to_thread(generate_code, llm, scene, concept=project.concept,
                                           style=project.style, material=store.material(project_id),
                                           language=language)

        error = ""
        for attempt in range(1, MAX_REPAIRS + 2):
            version = _next_version(scene_dir)
            code_path = scene_dir / f"code_v{version}.py"
            code_path.write_text(code, encoding="utf-8")
            await store.update_scene(project_id, scene_id, attempts=attempt)

            error = precheck(code) or ""
            if not error:
                await store.update_scene(project_id, scene_id, render_status="rendering")
                result = await renderer(code_path, scene_dir / f"render_v{version}.mp4")
                if result.ok:
                    await store.update_scene(project_id, scene_id, render_status="done",
                                             code_version=version, last_error=None)
                    return
                error = result.error

            if attempt <= MAX_REPAIRS:
                await store.update_scene(project_id, scene_id, render_status="repairing", last_error=error)
                code = await asyncio.to_thread(repair_code, llm, code, error, language=language)

        await store.update_scene(project_id, scene_id, render_status="failed", last_error=error)
    except Exception as exc:  # noqa: BLE001 - every failure must surface on the scene
        log.exception("build_scene failed for %s/%s", project_id, scene_id)
        try:
            await store.update_scene(project_id, scene_id, render_status="failed", last_error=str(exc) or repr(exc))
        except Exception:  # noqa: BLE001
            log.exception("could not record failure for %s/%s", project_id, scene_id)
