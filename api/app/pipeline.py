import asyncio
import logging
import re
from pathlib import Path

from app.codegen import MAX_REPAIRS, fix_layout, generate_code, outline, precheck, repair_code, revise_code
from app.llm import LLM
from app.models import Project
from app.render import Renderer
from app.store import ProjectStore

log = logging.getLogger(__name__)

_CODE_FILE = re.compile(r"code_v(\d+)\.py$")
MAX_LAYOUT_FIXES = 2


def _next_version(scene_dir: Path) -> int:
    versions = [int(m.group(1)) for p in scene_dir.glob("code_v*.py") if (m := _CODE_FILE.search(p.name))]
    return max(versions, default=0) + 1


async def build_scene(store: ProjectStore, llm: LLM, renderer: Renderer, project_id: str, scene_id: str,
                      *, instruction: str | None = None) -> None:
    """Generate (or revise) a scene's Manim code, render it, and repair it until it renders with a clean layout.

    Crashes and layout problems (overlapping or cut-off text, reported by the renderer) are both sent back to the
    model. If the layout cannot be fixed within budget, the render with the fewest problems is kept. Never raises.
    """
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
                                           language=language, video_outline=outline(project.scenes, scene_id))

        error = ""
        repairs = layout_fixes = attempt = 0
        best: tuple[int, int, list[str]] | None = None  # (issue count, version, issues) of the best render so far
        while True:
            attempt += 1
            version = _next_version(scene_dir)
            code_path = scene_dir / f"code_v{version}.py"
            code_path.write_text(code, encoding="utf-8")
            await store.update_scene(project_id, scene_id, attempts=attempt)

            error = precheck(code) or ""
            if not error:
                await store.update_scene(project_id, scene_id, render_status="rendering")
                result = await renderer(code_path, scene_dir / f"render_v{version}.mp4")
                if result.ok:
                    if best is None or len(result.issues) < best[0]:
                        best = (len(result.issues), version, result.issues)
                    if not result.issues or layout_fixes >= MAX_LAYOUT_FIXES:
                        await _accept(store, project_id, scene_id, best[1], best[2])
                        return
                    layout_fixes += 1
                    await store.update_scene(project_id, scene_id, render_status="repairing",
                                             last_error="Layout: " + " ".join(result.issues))
                    code = await asyncio.to_thread(fix_layout, llm, code, result.issues, language=language)
                    continue
                error = result.error

            if repairs < MAX_REPAIRS:
                repairs += 1
                await store.update_scene(project_id, scene_id, render_status="repairing", last_error=error)
                code = await asyncio.to_thread(repair_code, llm, code, error, language=language)
                continue
            if best is not None:  # a layout fix broke the code; the earlier render still stands
                await _accept(store, project_id, scene_id, best[1], best[2])
                return
            break

        await _record_failure(store, project_id, scene_id, error)
    except Exception as exc:  # noqa: BLE001 - every failure must surface on the scene
        log.exception("build_scene failed for %s/%s", project_id, scene_id)
        try:
            await _record_failure(store, project_id, scene_id, str(exc) or repr(exc))
        except Exception:  # noqa: BLE001
            log.exception("could not record failure for %s/%s", project_id, scene_id)


async def _accept(store: ProjectStore, project_id: str, scene_id: str, version: int, issues: list[str]) -> None:
    def apply(project: Project) -> None:
        scene = project.scene(scene_id)
        if scene.audio_source == "professor" and scene.audio_status == "done" and scene.code_version > 0:
            scene.audio_stale = True  # the recording was made over the previous animation
        scene.render_status, scene.code_version = "done", version
        scene.last_error, scene.layout_issues = None, issues

    await store.mutate(project_id, apply)


async def _record_failure(store: ProjectStore, project_id: str, scene_id: str, error: str) -> None:
    # A scene with an earlier good render keeps it (still exportable); the error is reported alongside it.
    has_previous = store.get(project_id).scene(scene_id).code_version > 0
    await store.update_scene(project_id, scene_id, render_status="done" if has_previous else "failed",
                             last_error=error)
