import asyncio

import pytest

from app.models import SceneDraft
from app.store import ProjectNotFound, ProjectStore, SceneNotFound


def draft(t="A"):
    return SceneDraft(title=t, visual="v", narration="n")


def new(store, scenes):
    return store.create(title="t", concept="c", style="", tone="", language="en",
                        material_text="m", scenes=scenes)


def test_create_and_get_roundtrip(tmp_path):
    store = ProjectStore(tmp_path)
    p = store.create(title="Κλίση", concept="gradient descent", style="", tone="", language="el",
                     material_text="notes", scenes=[draft()])
    assert store.get(p.id) == p
    assert p.scenes[0].render_status == "pending" and p.scenes[0].code_version == 0
    assert store.material(p.id) == "notes"
    assert "Κλίση" in (tmp_path / "projects" / p.id / "project.json").read_text(encoding="utf-8")


def test_get_missing_raises(tmp_path):
    with pytest.raises(ProjectNotFound):
        ProjectStore(tmp_path).get("nope")


def test_scene_lookup_missing_raises(tmp_path):
    p = new(ProjectStore(tmp_path), [draft()])
    with pytest.raises(SceneNotFound):
        p.scene("nope")


def test_list_newest_first(tmp_path):
    s = ProjectStore(tmp_path)
    a = new(s, [draft()])
    b = new(s, [draft()])
    assert [p.id for p in s.list()] == [b.id, a.id]


async def test_concurrent_update_scene_keeps_all_writes(tmp_path):
    s = ProjectStore(tmp_path)
    p = new(s, [draft("A"), draft("B")])
    a, b = p.scenes
    await asyncio.gather(*[s.update_scene(p.id, a.id, attempts=i) for i in range(10)],
                         s.update_scene(p.id, b.id, render_status="done"))
    got = s.get(p.id)
    assert got.scene(b.id).render_status == "done" and got.scene(a.id).attempts in range(10)


def test_recover_interrupted(tmp_path):
    s = ProjectStore(tmp_path)
    p = new(s, [draft("A"), draft("B")])
    asyncio.run(s.update_scene(p.id, p.scenes[0].id, render_status="rendering"))
    asyncio.run(s.update_scene(p.id, p.scenes[1].id, render_status="done", audio_status="generating"))
    assert s.recover_interrupted() == 2
    a, b = s.get(p.id).scenes
    assert a.render_status == "failed" and a.last_error == "Interrupted by server restart"
    assert b.render_status == "done" and b.audio_status == "failed"


def test_recover_interrupted_revision_keeps_previous_version(tmp_path):
    s = ProjectStore(tmp_path)
    p = new(s, [draft("A")])
    asyncio.run(s.update_scene(p.id, p.scenes[0].id, render_status="rendering", code_version=2))
    s.recover_interrupted()
    a = s.get(p.id).scenes[0]
    assert (a.render_status, a.code_version, a.last_error) == ("done", 2, "Interrupted by server restart")
