from app.main import create_app
from tests.conftest import api_client, make_pdf, make_settings
from tests.fakes import STORYBOARD_JSON, ScriptedLLM


def make_app(tmp_path, responses=None):
    llm = ScriptedLLM(responses if responses is not None else [STORYBOARD_JSON])
    return create_app(make_settings(tmp_path), llm=llm), llm


async def create(c, **data):
    return await c.post("/projects", data={"concept": "gradient descent", "material_text": "notes",
                                           "language": "el", **data})


async def test_create_with_text(tmp_path):
    app, _ = make_app(tmp_path)
    async with api_client(app) as c:
        r = await create(c)
    assert r.status_code == 200
    p = r.json()
    assert p["stage"] == "storyboard" and len(p["scenes"]) == 4 and p["title"] == "Κάθοδος κλίσης"
    assert app.state.store.material(p["id"]) == "notes"


async def test_create_with_pdf(tmp_path):
    app, llm = make_app(tmp_path)
    async with api_client(app) as c:
        r = await c.post("/projects", data={"concept": "gd"},
                         files={"file": ("notes.pdf", make_pdf("Loss surface"), "application/pdf")})
    assert r.status_code == 200
    assert "Loss surface" in llm.calls[0][1][0]["content"]


async def test_create_without_material_422(tmp_path):
    app, _ = make_app(tmp_path)
    async with api_client(app) as c:
        r = await c.post("/projects", data={"concept": "x"})
        assert r.status_code == 422
        assert r.json()["detail"] == "No readable text found in the uploaded material"
        assert (await c.get("/projects")).json() == []


async def test_create_without_concept_422(tmp_path):
    app, _ = make_app(tmp_path)
    async with api_client(app) as c:
        r = await c.post("/projects", data={"concept": "", "material_text": "notes"})
    assert r.status_code == 422


async def test_storyboard_failure_502(tmp_path):
    app, _ = make_app(tmp_path, ["bad", "bad"])
    async with api_client(app) as c:
        r = await create(c)
    assert r.status_code == 502


async def test_list_and_get(tmp_path):
    app, _ = make_app(tmp_path)
    async with api_client(app) as c:
        pid = (await create(c)).json()["id"]
        assert [p["id"] for p in (await c.get("/projects")).json()] == [pid]
        assert (await c.get(f"/projects/{pid}")).json()["id"] == pid


async def test_get_unknown_404(tmp_path):
    app, _ = make_app(tmp_path)
    async with api_client(app) as c:
        assert (await c.get("/projects/nope")).status_code == 404


async def test_put_storyboard_edit_reorder_add_delete(tmp_path):
    app, _ = make_app(tmp_path)
    async with api_client(app) as c:
        p = (await create(c)).json()
        s0, _, s2, _ = p["scenes"]
        body = {"scenes": [
            {**s2, "title": "New"},
            {"title": "Added", "visual": "v", "narration": "n"},
            s0,
        ]}
        r = await c.put(f"/projects/{p['id']}/storyboard", json=body)
    assert r.status_code == 200
    scenes = r.json()["scenes"]
    assert len(scenes) == 3
    assert scenes[0]["id"] == s2["id"] and scenes[0]["title"] == "New"
    assert scenes[1]["id"] not in (s0["id"], s2["id"]) and scenes[1]["title"] == "Added"
    assert scenes[2]["id"] == s0["id"]


async def test_put_storyboard_after_render_409(tmp_path):
    app, _ = make_app(tmp_path)
    async with api_client(app) as c:
        p = (await create(c)).json()
        await app.state.store.mutate(p["id"], lambda proj: setattr(proj, "stage", "scenes"))
        r = await c.put(f"/projects/{p['id']}/storyboard", json={"scenes": p["scenes"]})
    assert r.status_code == 409
    assert r.json()["detail"] == "Storyboard can only be edited before rendering starts"
