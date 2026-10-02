import re

from app.main import create_app
from app.models import Cut, SceneDraft
from tests.conftest import api_client, make_pdf, make_settings
from tests.fakes import ScriptedLLM


def make_app(tmp_path, responses=()):
    return create_app(make_settings(tmp_path), llm=ScriptedLLM(list(responses)))


async def create_deck(c, **data):
    r = await c.post("/decks", data={"title": "Αλγόριθμοι", "language": "el", **data})
    assert r.status_code == 200, r.text
    return r.json()


def make_project(app, deck_id=None, **cuts):
    store = app.state.store
    p = store.create(title="Φυσαλίδα", concept="bubble sort", style="", language="el", material_text="",
                     scenes=[SceneDraft(title="t", visual="v", narration="n")])
    if deck_id or cuts:
        def apply(project):
            project.deck_id = deck_id
            for k, v in cuts.items():
                setattr(project, k, v)
        p = store.get(p.id)
        apply(p)
        store.save(p)
    return store.get(p.id)


async def test_create_deck_with_pdf_and_text(tmp_path):
    app = make_app(tmp_path)
    async with api_client(app) as c:
        r = await c.post("/decks", data={"title": "Αλγόριθμοι", "language": "el", "material_text": "σημειώσεις"},
                         files=[("files", ("a.pdf", make_pdf("pdf text"), "application/pdf"))])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["slides"][0]["html"] == "<h1>Αλγόριθμοι</h1>" and d["animations"] == [] and d["version"] == 1
        assert d["language"] == "el" and d["chat"] == []
        assert (await c.get(f"/decks/{d['id']}/material")).text == "pdf text\n\nσημειώσεις"


async def test_create_deck_without_material_ok_but_unreadable_pdf_422(tmp_path):
    app = make_app(tmp_path)
    async with api_client(app) as c:
        d = await create_deck(c)
        assert (await c.get(f"/decks/{d['id']}/material")).text == ""
        r = await c.post("/decks", data={"title": "x", "language": "en"},
                         files=[("files", ("a.pdf", make_pdf(None), "application/pdf"))])
        assert r.status_code == 422
        assert r.json()["detail"] == "No readable text found in the uploaded material"


async def test_list_summaries(tmp_path):
    app = make_app(tmp_path)
    async with api_client(app) as c:
        a = await create_deck(c, title="Πρώτο")
        b = await create_deck(c, title="Δεύτερο")
        make_project(app, deck_id=a["id"])
        r = await c.get("/decks")
        assert r.status_code == 200
        summaries = r.json()
        assert [s["title"] for s in summaries] == ["Δεύτερο", "Πρώτο"]
        assert summaries[1] == {**summaries[1], "slide_count": 1, "animation_count": 1,
                                "first_slide_html": "<h1>Πρώτο</h1>", "language": "el"}
        assert summaries[0]["animation_count"] == 0 and b["id"] == summaries[0]["id"]


async def test_put_sanitises_assigns_ids_and_checks_version(tmp_path):
    app = make_app(tmp_path)
    async with api_client(app) as c:
        d = await create_deck(c)
        body = {"title": "Νέος", "version": 1, "slides": [
            {"id": d["slides"][0]["id"], "html": "<h1>A</h1><div><p onclick='x'>b</p></div>", "video": None},
            {"id": None, "html": "<p>new</p>", "video": None},
            {"id": "zzz", "html": "<p>bad id</p>", "video": None}]}
        r = await c.put(f"/decks/{d['id']}", json=body)
        assert r.status_code == 200, r.text
        v = r.json()
        assert [s["html"] for s in v["slides"]] == ["<h1>A</h1><p>b</p>", "<p>new</p>", "<p>bad id</p>"]
        assert v["slides"][0]["id"] == d["slides"][0]["id"]
        assert re.fullmatch(r"[0-9a-f]{8}", v["slides"][1]["id"]) and re.fullmatch(r"[0-9a-f]{8}", v["slides"][2]["id"])
        assert v["version"] == 2 and v["title"] == "Νέος"
        stale = await c.put(f"/decks/{d['id']}", json=body)
        assert stale.status_code == 409 and stale.json()["detail"] == "The slides were changed elsewhere"


async def test_put_too_long_slide_422(tmp_path):
    app = make_app(tmp_path)
    async with api_client(app) as c:
        d = await create_deck(c)
        body = {"title": "t", "version": 1, "slides": [{"id": None, "html": "<p>" + "x" * 20_001 + "</p>"}]}
        r = await c.put(f"/decks/{d['id']}", json=body)
        assert r.status_code == 422 and r.json()["detail"] == "Slide is too long"


async def test_delete_deck_clears_deck_id_on_projects(tmp_path):
    app = make_app(tmp_path)
    async with api_client(app) as c:
        d = await create_deck(c)
        p = make_project(app, deck_id=d["id"])
        assert app.state.store.get(p.id).deck_id == d["id"]
        r = await c.delete(f"/decks/{d['id']}")
        assert r.status_code == 204 and r.content == b""
        assert "json" not in r.headers.get("content-type", "")
        assert app.state.store.get(p.id).deck_id is None
        assert (await c.get(f"/decks/{d['id']}")).status_code == 404


async def test_view_marks_missing_and_linked_animations(tmp_path):
    app = make_app(tmp_path)
    async with api_client(app) as c:
        d = await create_deck(c)
        ready = make_project(app, deck_id=d["id"], stage="scenes",
                             preview=Cut(status="done", version=2, duration=20.0))
        draft = make_project(app, deck_id=d["id"])
        await app.state.decks.mutate(d["id"], lambda deck: setattr(deck.slides[0], "video", "ghost"))
        r = await c.get(f"/decks/{d['id']}")
        assert r.status_code == 200
        refs = {a["project_id"]: a for a in r.json()["animations"]}
        assert refs["ghost"] == {"project_id": "ghost", "title": "", "status": "missing", "cut": None,
                                 "version": 0, "signature": "", "duration": 0, "embedded": True}
        assert refs[ready.id] == {"project_id": ready.id, "title": "Φυσαλίδα", "status": "ready", "cut": "preview",
                                  "version": 2, "signature": "", "duration": 20.0, "embedded": False}
        assert refs[draft.id]["status"] == "draft" and refs[draft.id]["cut"] is None


async def test_404_in_greek(tmp_path):
    app = make_app(tmp_path)
    async with api_client(app) as c:
        r = await c.get("/decks/nope", headers={"X-Lara-Lang": "el"})
        assert r.status_code == 404 and r.json()["detail"] == "Οι διαφάνειες δεν βρέθηκαν"
        assert (await c.get("/decks/nope")).json()["detail"] == "Slides not found"


async def test_export_route_and_download(tmp_path):
    app = make_app(tmp_path)
    async with api_client(app) as c:
        d = await create_deck(c, title="Δέντρα")
        r = await c.post(f"/decks/{d['id']}/export", json={"format": "docx"})
        assert r.status_code == 200, r.text
        assert r.json() == {"url": f"/decks/{d['id']}/export/deck.docx", "filename": "Δέντρα.docx"}
        f = await c.get(r.json()["url"])
        assert f.status_code == 200
        assert f.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        assert "filename*=utf-8''%CE%94%CE%AD%CE%BD%CF%84%CF%81%CE%B1.docx" in f.headers["content-disposition"]
        assert f.content[:2] == b"PK"
        assert (await c.get(f"/decks/{d['id']}/export/nope.pdf")).status_code == 404
        r = await c.post(f"/decks/{d['id']}/export", json={"format": "pdf"})
        assert r.json()["filename"] == "Δέντρα.pdf" and (await c.get(r.json()["url"])).content[:5] == b"%PDF-"


async def test_put_duplicate_and_sloppy_ids_get_fresh_ids(tmp_path):
    app = make_app(tmp_path)
    async with api_client(app) as c:
        d = await create_deck(c)
        first = d["slides"][0]["id"]
        body = {"title": "t", "version": 1, "slides": [
            {"id": first, "html": "<p>a</p>", "video": None}, {"id": first, "html": "<p>b</p>", "video": None},
            {"id": "abcdef12\n", "html": "<p>c</p>", "video": None}]}
        ids = [s["id"] for s in (await c.put(f"/decks/{d['id']}", json=body)).json()["slides"]]
        assert ids[0] == first and len(set(ids)) == 3 and all(re.fullmatch(r"[0-9a-f]{8}", i) for i in ids)


async def test_blank_title_422(tmp_path):
    app = make_app(tmp_path)
    async with api_client(app) as c:
        r = await c.post("/decks", data={"title": "   ", "language": "el"})
        assert r.status_code == 422 and r.json()["detail"] == "Please give the slides a title"
        d = await create_deck(c)
        r = await c.put(f"/decks/{d['id']}", json={"title": " ", "version": 1, "slides": [{"id": None, "html": "<p>x</p>", "video": None}]})
        assert r.status_code == 422
