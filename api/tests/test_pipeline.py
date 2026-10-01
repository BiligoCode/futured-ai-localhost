from app.models import SceneDraft
from app.pipeline import build_scene
from app.render import RenderResult
from app.store import ProjectStore
from tests.fakes import INVALID_SYNTAX_CODE, VALID_CODE, FakeRenderer, ScriptedLLM

OK, BAD = RenderResult(ok=True), RenderResult(ok=False, error="Traceback: boom")


def new_project(tmp_path):
    store = ProjectStore(tmp_path)
    p = store.create(title="t", concept="gd", style="", tone="", language="el", material_text="notes",
                     scenes=[SceneDraft(title="A", visual="parabola", narration="hello there")])
    return store, p.id, p.scenes[0].id


async def test_success_first_try(tmp_path):
    store, pid, sid = new_project(tmp_path)
    await build_scene(store, ScriptedLLM([VALID_CODE]), FakeRenderer([OK]), pid, sid)
    s = store.get(pid).scene(sid)
    assert (s.render_status, s.code_version, s.attempts, s.last_error) == ("done", 1, 1, None)
    d = store.scene_dir(pid, sid)
    assert (d / "code_v1.py").exists() and (d / "render_v1.mp4").exists()


async def test_repairs_then_succeeds(tmp_path):
    store, pid, sid = new_project(tmp_path)
    llm = ScriptedLLM([VALID_CODE] * 3)
    await build_scene(store, llm, FakeRenderer([BAD, BAD, OK]), pid, sid)
    s = store.get(pid).scene(sid)
    assert (s.render_status, s.attempts, s.code_version) == ("done", 3, 3)
    assert len(llm.calls) == 3
    assert "Traceback: boom" in llm.calls[1][1][0]["content"]


async def test_fails_after_max_repairs(tmp_path):
    store, pid, sid = new_project(tmp_path)
    renderer = FakeRenderer([BAD])
    await build_scene(store, ScriptedLLM([VALID_CODE] * 4), renderer, pid, sid)
    s = store.get(pid).scene(sid)
    assert (s.render_status, s.attempts, s.code_version, s.last_error) == ("failed", 4, 0, "Traceback: boom")
    assert len(renderer.calls) == 4


async def test_precheck_failure_skips_render(tmp_path):
    store, pid, sid = new_project(tmp_path)
    renderer = FakeRenderer([OK])
    await build_scene(store, ScriptedLLM([INVALID_SYNTAX_CODE, VALID_CODE]), renderer, pid, sid)
    s = store.get(pid).scene(sid)
    assert s.render_status == "done" and s.attempts == 2 and len(renderer.calls) == 1


async def test_failed_revise_keeps_previous_video(tmp_path):
    store, pid, sid = new_project(tmp_path)
    await build_scene(store, ScriptedLLM([VALID_CODE]), FakeRenderer([OK]), pid, sid)
    llm = ScriptedLLM([VALID_CODE] * 4)
    await build_scene(store, llm, FakeRenderer([BAD]), pid, sid, instruction="red")
    s = store.get(pid).scene(sid)
    assert s.render_status == "failed" and s.code_version == 1
    assert (store.scene_dir(pid, sid) / "render_v1.mp4").exists()
    assert "red" in llm.calls[0][1][0]["content"]


async def test_successful_revise_bumps_version(tmp_path):
    store, pid, sid = new_project(tmp_path)
    await build_scene(store, ScriptedLLM([VALID_CODE]), FakeRenderer([OK]), pid, sid)
    await build_scene(store, ScriptedLLM([VALID_CODE]), FakeRenderer([OK]), pid, sid, instruction="red")
    assert store.get(pid).scene(sid).code_version == 2


async def test_llm_exception_marks_failed(tmp_path):
    store, pid, sid = new_project(tmp_path)
    await build_scene(store, ScriptedLLM([RuntimeError("throttled")]), FakeRenderer([OK]), pid, sid)
    s = store.get(pid).scene(sid)
    assert s.render_status == "failed" and "throttled" in s.last_error
