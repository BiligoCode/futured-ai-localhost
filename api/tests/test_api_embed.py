import pytest

from app.main import create_app
from app.models import Cut
from tests.conftest import api_client, make_settings
from tests.fakes import ScriptedLLM
from tests.test_api_decks import make_project


class FakePoster:
    def __init__(self):
        self.calls = []

    def __call__(self, video, out, at):
        self.calls.append((video, out, at))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"jpg")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    app = create_app(make_settings(tmp_path), llm=ScriptedLLM([]))
    poster = FakePoster()
    monkeypatch.setattr("app.routes.decks.make_poster", poster)
    deck = app.state.decks.create(title="Δέντρα", language="el", material_text="")
    ready = make_project(app, deck_id=deck.id, stage="scenes", preview=Cut(status="done", version=1, duration=20.0))
    (app.state.store.project_dir(ready.id) / "preview.mp4").write_bytes(b"mp4")
    return app, poster, deck, ready


async def test_embed_append_new_after_new_end(setup):
    app, poster, deck, ready = setup
    first = deck.slides[0].id
    async with api_client(app) as c:
        r = await c.post(f"/decks/{deck.id}/embed", json={"project_id": ready.id, "slide_id": first, "mode": "append"})
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["slides"][0]["video"] == ready.id and v["slides"][0]["html"] == "<h1>Δέντρα</h1>" and v["version"] == 2
        assert poster.calls[0][0].name == "preview.mp4" and poster.calls[0][2] == 6.0
        assert poster.calls[0][1] == app.state.decks.deck_dir(deck.id) / "posters" / f"{ready.id}.jpg"
        ref = next(a for a in v["animations"] if a["project_id"] == ready.id)
        assert ref == {"project_id": ready.id, "title": "Φυσαλίδα", "status": "ready", "cut": "preview", "version": 1,
                       "duration": 20.0, "embedded": True}

        r = await c.post(f"/decks/{deck.id}/embed", json={"project_id": ready.id, "slide_id": first, "mode": "new_after"})
        v = r.json()
        assert [s["html"] for s in v["slides"]] == ["<h1>Δέντρα</h1>", "<h2>Φυσαλίδα</h2>"] and v["slides"][1]["video"] == ready.id

        r = await c.post(f"/decks/{deck.id}/embed", json={"project_id": ready.id, "mode": "new_end"})
        v = r.json()
        assert len(v["slides"]) == 3 and v["slides"][2]["video"] == ready.id and v["slides"][2]["html"] == "<h2>Φυσαλίδα</h2>"


async def test_embed_replaces_existing_video_on_slide(setup):
    app, poster, deck, ready = setup
    other = make_project(app, deck_id=deck.id, stage="scenes", preview=Cut(status="done", version=1, duration=4.0),
                         final=Cut(status="done", version=3, duration=5.0))
    (app.state.store.project_dir(other.id) / "export.mp4").write_bytes(b"mp4")
    first = deck.slides[0].id
    async with api_client(app) as c:
        await c.post(f"/decks/{deck.id}/embed", json={"project_id": ready.id, "slide_id": first, "mode": "append"})
        r = await c.post(f"/decks/{deck.id}/embed", json={"project_id": other.id, "slide_id": first, "mode": "append"})
        v = r.json()
        assert v["slides"][0]["video"] == other.id and len(v["slides"]) == 1
        assert poster.calls[-1][0].name == "export.mp4" and poster.calls[-1][2] == 1.5
        ref = next(a for a in v["animations"] if a["project_id"] == other.id)
        assert ref["cut"] == "final" and ref["version"] == 3 and ref["embedded"] is True
        assert next(a for a in v["animations"] if a["project_id"] == ready.id)["embedded"] is False


async def test_embed_not_ready_409_unknown_project_404_bad_slide_422(setup):
    app, poster, deck, ready = setup
    draft = make_project(app, deck_id=deck.id)
    async with api_client(app) as c:
        r = await c.post(f"/decks/{deck.id}/embed", json={"project_id": draft.id, "mode": "new_end"})
        assert r.status_code == 409 and r.json()["detail"] == "The animation is not ready yet"
        r = await c.post(f"/decks/{deck.id}/embed", json={"project_id": "nope", "mode": "new_end"})
        assert r.status_code == 404 and r.json()["detail"] == "Project not found"
        r = await c.post(f"/decks/{deck.id}/embed", json={"project_id": ready.id, "slide_id": "nope", "mode": "append"})
        assert r.status_code == 422 and r.json()["detail"] == "This slide does not exist"
        r = await c.post(f"/decks/{deck.id}/embed", json={"project_id": ready.id, "mode": "append"})
        assert r.status_code == 422 and r.json()["detail"] == "This slide does not exist"
        assert poster.calls == []


async def test_poster_served(setup):
    app, poster, deck, ready = setup
    async with api_client(app) as c:
        assert (await c.get(f"/decks/{deck.id}/posters/{ready.id}.jpg")).status_code == 404
        await c.post(f"/decks/{deck.id}/embed", json={"project_id": ready.id, "mode": "new_end"})
        r = await c.get(f"/decks/{deck.id}/posters/{ready.id}.jpg")
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content == b"jpg"


async def test_embed_poster_failure_is_a_readable_502(setup, monkeypatch):
    from app.media import MediaError

    app, poster, deck, ready = setup

    def broken(video, out, at):
        raise MediaError("ffmpeg exploded")

    monkeypatch.setattr("app.routes.decks.make_poster", broken)
    async with api_client(app) as c:
        r = await c.post(f"/decks/{deck.id}/embed", json={"project_id": ready.id, "mode": "new_end"})
        assert r.status_code == 502 and r.json()["detail"] == "Could not take a still from the animation: ffmpeg exploded"
        r = await c.post(f"/decks/{deck.id}/embed", json={"project_id": ready.id, "mode": "new_end"},
                         headers={"X-Lara-Lang": "el"})
        assert r.json()["detail"].startswith("Δεν ήταν δυνατή η λήψη καρέ από την κινούμενη εικόνα: ")
