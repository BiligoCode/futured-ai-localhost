import pytest

from app.main import create_app
from app.models import SceneDraft
from app.render import RenderResult
from tests.conftest import api_client, make_clip, make_settings, make_wav, probe
from tests.fakes import FakeRenderer, FakeTTS, ScriptedLLM


def make_app(tmp_path):
    app = create_app(make_settings(tmp_path), llm=ScriptedLLM([]), renderer=FakeRenderer([RenderResult(ok=True)]),
                     tts=FakeTTS(b""))
    p = app.state.store.create(title="t", concept="c", style="", language="el", material_text="m",
                               scenes=[SceneDraft(title=f"S{i}", visual="v", narration="n") for i in range(2)])
    return app, p.id, [s.id for s in p.scenes]


async def render_all(app, pid, sids):
    for sid in sids:
        make_clip(app.state.store.scene_dir(pid, sid) / "render_v1.mp4", 2)
        await app.state.store.update_scene(pid, sid, code_version=1, render_status="done")


@pytest.mark.slow
async def test_export_api(tmp_path):
    app, pid, sids = make_app(tmp_path)
    await render_all(app, pid, sids)
    make_wav(app.state.store.scene_dir(pid, sids[0]) / "audio.wav", 3)
    await app.state.store.update_scene(pid, sids[0], audio_source="professor", audio_status="done")
    async with api_client(app) as c:
        r = await c.post(f"/projects/{pid}/export")
        assert r.status_code == 200 and r.json() == {"url": f"/projects/{pid}/export.mp4"}
        video = await c.get(f"/projects/{pid}/export.mp4")
    assert video.status_code == 200 and video.headers["content-type"] == "video/mp4"
    assert abs(probe(app.state.store.project_dir(pid) / "export.mp4")["duration"] - 5.3) < 0.25


async def test_export_requires_all_done_409(tmp_path):
    app, pid, sids = make_app(tmp_path)
    async with api_client(app) as c:
        r = await c.post(f"/projects/{pid}/export")
    assert r.status_code == 409 and r.json()["detail"] == "The animation is not finished yet"


async def test_export_download_404_before_export(tmp_path):
    app, pid, _ = make_app(tmp_path)
    async with api_client(app) as c:
        assert (await c.get(f"/projects/{pid}/export.mp4")).status_code == 404
