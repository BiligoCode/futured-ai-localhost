import json

import pytest

from app.deck_store import DeckNotFound, DeckStore, new_slide_id
from app.models import Slide


async def test_create_get_list(tmp_path):
    store = DeckStore(tmp_path)
    a = store.create(title="Α <β>", language="el", material_text="υλικό")
    b = store.create(title="B", language="en", material_text="")
    assert a.slides[0].html == "<h1>Α &lt;β&gt;</h1>" and a.version == 1 and a.chat == []
    assert len(a.id) == 10 and len(a.slides[0].id) == 8
    assert store.get(a.id).title == "Α <β>" and store.material(a.id) == "υλικό"
    assert [d.id for d in store.list()] == [b.id, a.id]
    assert (tmp_path / "decks" / a.id / "deck.json").is_file()
    assert json.loads((tmp_path / "decks" / a.id / "deck.json").read_text())["language"] == "el"


async def test_save_bumps_version_and_updated_at(tmp_path):
    store = DeckStore(tmp_path)
    d = store.create(title="t", language="el", material_text="")
    before = d.updated_at
    d2 = await store.mutate(d.id, lambda deck: deck.slides.append(Slide(id=new_slide_id(), html="<p>x</p>")))
    assert d2.version == 2 and d2.updated_at >= before and len(store.get(d.id).slides) == 2
    assert not (tmp_path / "decks" / d.id / "deck.json.tmp").exists()


async def test_get_rejects_bad_ids_and_delete(tmp_path):
    store = DeckStore(tmp_path)
    d = store.create(title="t", language="el", material_text="")
    for bad in ("", "../x", "nope"):
        with pytest.raises(DeckNotFound):
            store.get(bad)
    await store.delete(d.id)
    with pytest.raises(DeckNotFound):
        store.get(d.id)
    assert not (tmp_path / "decks" / d.id).exists()


def test_project_deck_id_defaults_to_none():
    from app.models import Project

    p = Project(id="p", created_at="2026-10-01T00:00:00Z", title="t", concept="c", style="", language="el", scenes=[])
    assert p.deck_id is None and "deck_id" in p.model_dump()
