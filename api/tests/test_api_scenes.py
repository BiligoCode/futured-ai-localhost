import asyncio

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import SceneDraft
from app.render import RenderResult
from app.store import ProjectStore
from tests.conftest import api_client, make_settings
from tests.fakes import STORYBOARD_JSON, VALID_CODE, FakeRenderer, ScriptedLLM

OK, BAD = RenderResult(ok=True), RenderResult(ok=False, error="boom")


def make_app(tmp_path, renderer=None):
    llm = ScriptedLLM([STORYBOARD_JSON] + [VALID_CODE] * 40)
    return create_app(make_settings(tmp_path), llm=llm, renderer=renderer or FakeRenderer([OK]))


async def new_project(c):
    r = await c.post("/projects", data={"concept": "gd", "material_text": "notes"})
    return r.json()


class GatedRenderer(FakeRenderer):
    def __init__(self):
        super().__init__([OK])
        self.gate = asyncio.Event()

    async def __call__(self, code_path, output_path):
        await self.gate.wait()
        return await super().__call__(code_path, output_path)


async def test_render_all_scenes(tmp_path):
    app = make_app(tmp_path)
    async with api_client(app) as c:
        p = await new_project(c)
        r = await c.post(f"/projects/{p['id']}/render")
        assert r.json()["stage"] == "scenes"
        assert all(s["render_status"] == "generating" for s in r.json()["scenes"])
        await app.state.jobs.wait_all()
        scenes = (await c.get(f"/projects/{p['id']}")).json()["scenes"]
    assert all(s["render_status"] == "done" and s["code_version"] == 1 for s in scenes)


async def test_render_twice_does_not_duplicate(tmp_path):
    renderer = GatedRenderer()
    app = make_app(tmp_path, renderer)
    async with api_client(app) as c:
        p = await new_project(c)
        await c.post(f"/projects/{p['id']}/render")
        await asyncio.sleep(0.05)
        await c.post(f"/projects/{p['id']}/render")
        renderer.gate.set()
        await app.state.jobs.wait_all()
    assert len(renderer.calls) == 4


async def test_revise_creates_new_version(tmp_path):
    app = make_app(tmp_path)
    async with api_client(app) as c:
        p = await new_project(c)
        sid = p["scenes"][0]["id"]
        await c.post(f"/projects/{p['id']}/render")
        await app.state.jobs.wait_all()
        r = await c.post(f"/projects/{p['id']}/scenes/{sid}/revise", json={"instruction": "make it red"})
        assert r.status_code == 200
        await app.state.jobs.wait_all()
        scene = (await c.get(f"/projects/{p['id']}")).json()["scenes"][0]
        assert scene["code_version"] == 2
        assert "GeneratedScene" in (await c.get(f"/projects/{p['id']}/scenes/{sid}/code")).text


async def test_revise_while_running_409(tmp_path):
    renderer = GatedRenderer()
    app = make_app(tmp_path, renderer)
    async with api_client(app) as c:
        p = await new_project(c)
        sid = p["scenes"][0]["id"]
        await c.post(f"/projects/{p['id']}/render")
        r = await c.post(f"/projects/{p['id']}/scenes/{sid}/revise", json={"instruction": "x"})
        assert r.status_code == 409 and r.json()["detail"] == "Scene is already being processed"
        renderer.gate.set()
        await app.state.jobs.wait_all()


async def test_revise_before_first_render_409(tmp_path):
    app = make_app(tmp_path)
    async with api_client(app) as c:
        p = await new_project(c)
        sid = p["scenes"][0]["id"]
        r = await c.post(f"/projects/{p['id']}/scenes/{sid}/revise", json={"instruction": "x"})
    assert r.status_code == 409


async def test_revise_empty_instruction_422(tmp_path):
    app = make_app(tmp_path)
    async with api_client(app) as c:
        p = await new_project(c)
        sid = p["scenes"][0]["id"]
        r = await c.post(f"/projects/{p['id']}/scenes/{sid}/revise", json={"instruction": ""})
    assert r.status_code == 422


async def test_video_404_then_200(tmp_path):
    app = make_app(tmp_path)
    async with api_client(app) as c:
        p = await new_project(c)
        sid = p["scenes"][0]["id"]
        assert (await c.get(f"/projects/{p['id']}/scenes/{sid}/video")).status_code == 404
        await c.post(f"/projects/{p['id']}/render")
        await app.state.jobs.wait_all()
        r = await c.get(f"/projects/{p['id']}/scenes/{sid}/video")
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"


async def test_retry_failed_scene(tmp_path):
    app = make_app(tmp_path, FakeRenderer([BAD]))
    async with api_client(app) as c:
        p = await new_project(c)
        sid = p["scenes"][0]["id"]
        await c.post(f"/projects/{p['id']}/render")
        await app.state.jobs.wait_all()
        assert (await c.get(f"/projects/{p['id']}")).json()["scenes"][0]["render_status"] == "failed"
        app.state.renderer = FakeRenderer([OK])
        assert (await c.post(f"/projects/{p['id']}/scenes/{sid}/retry")).status_code == 200
        await app.state.jobs.wait_all()
        assert (await c.get(f"/projects/{p['id']}")).json()["scenes"][0]["render_status"] == "done"


def test_startup_recovers_interrupted(tmp_path):
    settings = make_settings(tmp_path)
    store = ProjectStore(settings.data_dir)
    p = store.create(title="t", concept="c", style="", language="en", material_text="m",
                     scenes=[SceneDraft(title="A", visual="v", narration="n")])
    asyncio.run(store.update_scene(p.id, p.scenes[0].id, render_status="rendering"))
    with TestClient(create_app(settings, llm=ScriptedLLM([]), renderer=FakeRenderer([OK]))):
        pass
    assert store.get(p.id).scenes[0].render_status == "failed"


async def test_cancel_stops_rendering_and_keeps_nothing_half_done(tmp_path):
    renderer = GatedRenderer()  # never opened: every render hangs until cancelled
    app = make_app(tmp_path, renderer)
    async with api_client(app) as c:
        p = await new_project(c)
        await c.post(f"/projects/{p['id']}/render")
        await asyncio.sleep(0.05)
        r = await c.post(f"/projects/{p['id']}/cancel")
        assert r.status_code == 200
        assert all(s["render_status"] == "failed" and s["last_error"] == "Cancelled" for s in r.json()["scenes"])
        assert not app.state.jobs.keys(f"{p['id']}:")
        # Continuing renders the stopped parts again.
        renderer.gate.set()
        await c.post(f"/projects/{p['id']}/render")
        await app.state.jobs.wait_all()
        scenes = (await c.get(f"/projects/{p['id']}")).json()["scenes"]
    assert all(s["render_status"] == "done" for s in scenes)


async def test_delete_project_while_rendering(tmp_path):
    app = make_app(tmp_path, GatedRenderer())
    async with api_client(app) as c:
        p = await new_project(c)
        await c.post(f"/projects/{p['id']}/render")
        await asyncio.sleep(0.05)
        r = await c.delete(f"/projects/{p['id']}")
        assert r.status_code == 204 and r.content == b""
        assert "json" not in r.headers.get("content-type", "")
        assert (await c.get(f"/projects/{p['id']}")).status_code == 404
        assert (await c.get("/projects")).json() == []
        assert (await c.delete(f"/projects/{p['id']}")).status_code == 404
    assert not app.state.store.project_dir(p["id"]).joinpath("project.json").exists()


async def test_back_to_script_rerenders_only_changed_parts(tmp_path):
    renderer = FakeRenderer([OK])
    app = make_app(tmp_path, renderer)
    async with api_client(app) as c:
        p = await new_project(c)
        await c.post(f"/projects/{p['id']}/render")
        await app.state.jobs.wait_all()
        assert len(renderer.calls) == 4

        r = await c.post(f"/projects/{p['id']}/reopen")
        assert r.json()["stage"] == "storyboard"
        scenes = r.json()["scenes"]
        drafts = [{k: s[k] for k in ("id", "title", "visual", "narration")} for s in scenes]
        drafts[0]["visual"] = "A different picture"
        drafts[1]["narration"] = "Only the words change"
        drafts[2], drafts[3] = drafts[3], drafts[2]
        r = await c.put(f"/projects/{p['id']}/storyboard", json={"scenes": drafts})
        by_id = {s["id"]: s for s in r.json()["scenes"]}
        assert by_id[drafts[0]["id"]]["render_status"] == "pending"
        assert by_id[drafts[1]["id"]]["render_status"] == "done"
        assert [s["id"] for s in r.json()["scenes"]] == [d["id"] for d in drafts]

        await c.post(f"/projects/{p['id']}/render")
        await app.state.jobs.wait_all()
        scenes = (await c.get(f"/projects/{p['id']}")).json()["scenes"]
    assert len(renderer.calls) == 5
    assert all(s["render_status"] == "done" for s in scenes)


async def test_back_to_script_stops_running_work(tmp_path):
    app = make_app(tmp_path, GatedRenderer())
    async with api_client(app) as c:
        p = await new_project(c)
        await c.post(f"/projects/{p['id']}/render")
        await asyncio.sleep(0.05)
        r = await c.post(f"/projects/{p['id']}/reopen")
        assert r.json()["stage"] == "storyboard"
        assert all(s["render_status"] == "failed" for s in r.json()["scenes"])
        assert not app.state.jobs.keys(f"{p['id']}:")
