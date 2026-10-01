from app.models import SceneDraft
from app.pipeline import build_scene
from app.render import RenderResult
from app.store import ProjectStore
from tests.fakes import INVALID_SYNTAX_CODE, VALID_CODE, FakeRenderer, ScriptedLLM

OK, BAD = RenderResult(ok=True), RenderResult(ok=False, error="Traceback: boom")


def new_project(tmp_path):
    store = ProjectStore(tmp_path)
    p = store.create(title="t", concept="gd", style="", language="el", material_text="notes",
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
    # The previous good version stays current and exportable; the revision error is reported alongside it.
    assert (s.render_status, s.code_version, s.last_error) == ("done", 1, "Traceback: boom")
    assert (store.scene_dir(pid, sid) / "render_v1.mp4").exists()
    assert "red" in llm.calls[0][1][0]["content"]


async def test_failed_first_render_with_instruction_still_fails(tmp_path):
    store, pid, sid = new_project(tmp_path)
    await build_scene(store, ScriptedLLM([VALID_CODE] * 4), FakeRenderer([BAD]), pid, sid, instruction="red")
    assert store.get(pid).scene(sid).render_status == "failed"


async def test_successful_render_clears_revision_error(tmp_path):
    store, pid, sid = new_project(tmp_path)
    await build_scene(store, ScriptedLLM([VALID_CODE]), FakeRenderer([OK]), pid, sid)
    await build_scene(store, ScriptedLLM([VALID_CODE] * 4), FakeRenderer([BAD]), pid, sid, instruction="red")
    await build_scene(store, ScriptedLLM([VALID_CODE]), FakeRenderer([OK]), pid, sid, instruction="blue")
    assert store.get(pid).scene(sid).last_error is None


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


MESSY = RenderResult(ok=True, issues=['At 4.0s: 12 texts are drawn on top of each other: Text "2", Text "5".',
                                      'At 9.0s: Text "Βρέθηκε!" is cut off by the edge of the frame.'])
LESS_MESSY = RenderResult(ok=True, issues=["At 7.0s: 2 texts are drawn on top of each other."])


async def test_layout_issues_are_fixed_before_accepting(tmp_path):
    store, pid, sid = new_project(tmp_path)
    llm = ScriptedLLM([VALID_CODE] * 2)
    await build_scene(store, llm, FakeRenderer([MESSY, OK]), pid, sid)
    s = store.get(pid).scene(sid)
    assert (s.render_status, s.code_version, s.layout_issues, s.last_error) == ("done", 2, [], None)
    fix_prompt = llm.calls[1][1][0]["content"]
    assert "layout check" in fix_prompt and "12 texts are drawn on top of each other" in fix_prompt


async def test_unfixable_layout_keeps_best_render(tmp_path):
    store, pid, sid = new_project(tmp_path)
    renderer = FakeRenderer([MESSY, LESS_MESSY, MESSY])
    await build_scene(store, ScriptedLLM([VALID_CODE] * 3), renderer, pid, sid)
    s = store.get(pid).scene(sid)
    assert len(renderer.calls) == 3  # the first render + MAX_LAYOUT_FIXES
    assert (s.render_status, s.code_version, s.layout_issues) == ("done", 2, LESS_MESSY.issues)


async def test_layout_fix_that_breaks_code_falls_back_to_earlier_render(tmp_path):
    store, pid, sid = new_project(tmp_path)
    await build_scene(store, ScriptedLLM([VALID_CODE] * 6), FakeRenderer([MESSY, BAD]), pid, sid)
    s = store.get(pid).scene(sid)
    assert (s.render_status, s.code_version, s.layout_issues) == ("done", 1, MESSY.issues)


async def test_revising_animation_marks_professor_recording_stale(tmp_path):
    store, pid, sid = new_project(tmp_path)
    await build_scene(store, ScriptedLLM([VALID_CODE]), FakeRenderer([OK]), pid, sid)
    await store.update_scene(pid, sid, audio_source="professor", audio_status="done")
    await build_scene(store, ScriptedLLM([VALID_CODE]), FakeRenderer([OK]), pid, sid, instruction="slower")
    assert store.get(pid).scene(sid).audio_stale
