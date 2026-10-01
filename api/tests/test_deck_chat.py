import json
from datetime import datetime, timezone

import pytest

from app.deck_chat import DeckChatError, _Edit, apply_edits, build_user_message, run_chat
from app.main import create_app
from app.models import ChatMessage, Deck, EditLog, Slide
from tests.conftest import api_client, make_settings
from tests.fakes import ScriptedLLM

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def deck_with(*htmls: str, language="el") -> Deck:
    slides = [Slide(id=f"aaaaaaa{i + 1}", html=h) for i, h in enumerate(htmls)]
    return Deck(id="deck000001", created_at=NOW, updated_at=NOW, title="Ταξινόμηση", language=language, slides=slides)


def reply(edits: list[dict], text="ok") -> str:
    return json.dumps({"reply": text, "edits": edits}, ensure_ascii=False)


def test_user_message_lists_slides_history_and_context():
    deck = deck_with("<h1>Α</h1>", "<p>Β</p>")
    a, b = deck.slides[0].id, deck.slides[1].id
    deck.chat = [ChatMessage(role="user", content="γεια", at=NOW),
                 ChatMessage(role="assistant", content="γεια σας", edits=[EditLog(op="replace", slide_id=a, title="Α")], at=NOW)]
    msg = build_user_message(deck, "υλικό" * 3000, "κάνε το έντονο", slide_id=b, selection="Β")
    assert f"[{a}] <h1>Α</h1>" in msg and f"[{b}] <p>Β</p>" in msg
    assert "Course material (excerpt)" in msg and len(msg) < 14_000
    assert "Professor: γεια\nLara: γεια σας (changed slides 1)" in msg
    assert f"looking at slide [{b}]" in msg and 'Selected text on that slide: "Β"' in msg
    assert msg.rstrip().endswith("Professor: κάνε το έντονο")


def test_user_message_without_material_or_history():
    msg = build_user_message(deck_with("<p>x</p>"), "", "ερώτηση", slide_id=None, selection=None)
    assert "Course material" not in msg and "Earlier in this conversation" not in msg and "looking at" not in msg


def test_apply_edits_each_op():
    slides = deck_with("<p>1</p>", "<p>2</p>", "<p>3</p>").slides
    a, b, c = (s.id for s in slides)
    out, log = apply_edits(slides, [
        _Edit(op="replace", slide=a, html="<h1>Uno</h1>"),
        _Edit(op="insert_after", slide=a, html="<p>x</p>"),
        _Edit(op="insert_after", slide=a, html="<p>y</p>"),
        _Edit(op="delete", slide=c),
        _Edit(op="move", slide=b, after=None),
    ])
    assert [s.html for s in out] == ["<p>2</p>", "<h1>Uno</h1>", "<p>x</p>", "<p>y</p>"]
    assert [(e.op, e.title) for e in log] == [("replace", "Uno"), ("insert_after", "x"), ("insert_after", "y"),
                                              ("delete", "3"), ("move", "2")]
    assert out[1].id == a and out[1].video is None and len(out[2].id) == 8
    assert [s.html for s in slides] == ["<p>1</p>", "<p>2</p>", "<p>3</p>"]  # input untouched


def test_apply_edits_keeps_video_and_sanitises():
    slides = deck_with("<p>1</p>").slides
    slides[0].video = "pid"
    out, _ = apply_edits(slides, [_Edit(op="replace", slide=slides[0].id, html="<div><p>new</p></div>")])
    assert out[0].video == "pid" and out[0].html == "<p>new</p>"


def test_apply_edits_errors():
    slides = deck_with("<p>1</p>").slides
    a = slides[0].id
    for bad in ([_Edit(op="replace", slide="nope", html="<p>x</p>")],
                [_Edit(op="replace", slide=a, html="<div></div>")],
                [_Edit(op="move", slide=a, after=a)],
                [_Edit(op="delete", slide=a)],
                [_Edit(op="insert_after", slide=a, html="<p>new</p>"), _Edit(op="insert_after", slide="ghost", html="<p>z</p>")]):
        with pytest.raises(ValueError):
            apply_edits(slides, bad)


def test_run_chat_question_only():
    deck = deck_with("<p>1</p>")
    llm = ScriptedLLM([reply([], "Ναι, μπορείτε.")])
    text, slides, log, edits = run_chat(llm, deck, "", "τι λες;", slide_id=None, selection=None)
    assert text == "Ναι, μπορείτε." and log == [] and slides == deck.slides and edits == []
    system = llm.calls[0][0]
    assert "Greek" in system and '"edits"' in system and "1280" in system


def test_run_chat_language_retry():
    deck = deck_with("<p>1</p>")
    a = deck.slides[0].id
    llm = ScriptedLLM([reply([{"op": "replace", "slide": a, "html": "<p>This is English text that is long enough to count</p>"}]),
                       reply([{"op": "replace", "slide": a, "html": "<p>Αυτό είναι ελληνικό κείμενο αρκετά μεγάλο για έλεγχο</p>"}])])
    _, slides, log, _ = run_chat(llm, deck, "", "γράψε", slide_id=None, selection=None)
    assert len(llm.calls) == 2
    retry = llm.calls[1][1]
    assert retry[-2]["role"] == "assistant" and "not valid" in retry[-1]["content"]
    assert slides[0].html.startswith("<p>Αυτό") and log[0].op == "replace"


def test_run_chat_short_text_skips_language_check():
    deck = deck_with("<p>1</p>")
    llm = ScriptedLLM([reply([{"op": "replace", "slide": deck.slides[0].id, "html": "<h1>O(n log n)</h1>"}])])
    _, slides, _, _ = run_chat(llm, deck, "", "τίτλος", slide_id=None, selection=None)
    assert slides[0].html == "<h1>O(n log n)</h1>" and len(llm.calls) == 1


def test_run_chat_gives_up_after_two_attempts():
    deck = deck_with("<p>1</p>")
    llm = ScriptedLLM(["not json at all", reply([{"op": "delete", "slide": "ghost"}])])
    with pytest.raises(DeckChatError):
        run_chat(llm, deck, "", "x", slide_id=None, selection=None)
    assert len(llm.calls) == 2


# --- route -------------------------------------------------------------------------------------------------------

def make_app(tmp_path, responses):
    return create_app(make_settings(tmp_path), llm=ScriptedLLM(list(responses)))


async def test_chat_route_applies_and_records(tmp_path):
    app = make_app(tmp_path, [])
    deck = app.state.decks.create(title="Ταξινόμηση", language="el", material_text="")
    a = deck.slides[0].id
    app.state.llm.responses = [reply([{"op": "replace", "slide": a, "html": "<h1>Ταξινόμηση</h1><p>Νέο κείμενο για τη διαφάνεια</p>"}],
                                     "Πρόσθεσα μια εισαγωγή.")]
    async with api_client(app) as c:
        r = await c.post(f"/decks/{deck.id}/chat", json={"message": "γράψε εισαγωγή", "slide_id": a, "selection": None})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["reply"] == "Πρόσθεσα μια εισαγωγή." and body["edits"] == [{"op": "replace", "slide_id": a, "title": "Ταξινόμηση"}]
        assert body["deck"]["version"] == 2 and body["deck"]["slides"][0]["html"].endswith("διαφάνεια</p>")
        chat = (await c.get(f"/decks/{deck.id}")).json()["chat"]
        assert [m["role"] for m in chat] == ["user", "assistant"]
        assert chat[0]["content"] == "γράψε εισαγωγή" and chat[1]["edits"][0]["slide_id"] == a


async def test_chat_unknown_slide_retries_then_422(tmp_path):
    app = make_app(tmp_path, [reply([{"op": "delete", "slide": "ghost"}])] * 2)
    deck = app.state.decks.create(title="t", language="el", material_text="")
    async with api_client(app) as c:
        r = await c.post(f"/decks/{deck.id}/chat", json={"message": "σβήσε"})
        assert r.status_code == 422 and r.json()["detail"] == "The AI reply could not be applied. Please try again."
        assert (await c.get(f"/decks/{deck.id}")).json()["version"] == 1


async def test_chat_bad_slide_id_422_and_llm_error_502(tmp_path):
    app = make_app(tmp_path, [RuntimeError("boom")])
    deck = app.state.decks.create(title="t", language="el", material_text="")
    async with api_client(app) as c:
        r = await c.post(f"/decks/{deck.id}/chat", json={"message": "x", "slide_id": "nope"})
        assert r.status_code == 422 and r.json()["detail"] == "This slide does not exist"
        r = await c.post(f"/decks/{deck.id}/chat", json={"message": "x"})
        assert r.status_code == 502 and r.json()["detail"].startswith("The AI model request failed: ")


async def test_chat_history_trimmed_to_50(tmp_path):
    app = make_app(tmp_path, [reply([], "ok")] * 30)
    deck = app.state.decks.create(title="t", language="el", material_text="")
    async with api_client(app) as c:
        for _ in range(30):
            assert (await c.post(f"/decks/{deck.id}/chat", json={"message": "x"})).status_code == 200
        assert len((await c.get(f"/decks/{deck.id}")).json()["chat"]) == 50


async def test_chat_keeps_a_slide_added_while_the_model_was_thinking(tmp_path):
    """Review finding: the chat reply must apply to the deck as it is when the model answers, not as it was."""
    import asyncio
    import threading

    app = make_app(tmp_path, [])
    deck = app.state.decks.create(title="t", language="el", material_text="")
    a = deck.slides[0].id
    gate = threading.Event()

    class GatedLLM:
        def __call__(self, system, messages):
            gate.wait(timeout=5)
            return reply([{"op": "replace", "slide": a, "html": "<h1>Από το μοντέλο</h1>"}])

    app.state.llm = GatedLLM()
    async with api_client(app) as c:
        chat = asyncio.create_task(c.post(f"/decks/{deck.id}/chat", json={"message": "x"}))
        await asyncio.sleep(0.2)  # the model is "thinking"
        r = await c.put(f"/decks/{deck.id}", json={"title": "t", "version": 1, "slides": [
            {"id": a, "html": "<h1>t</h1>", "video": None}, {"id": None, "html": "<p>typed meanwhile</p>", "video": None}]})
        assert r.status_code == 200 and r.json()["version"] == 2
        gate.set()
        result = await chat
        assert result.status_code == 200, result.text
        slides = result.json()["deck"]["slides"]
        assert [s["html"] for s in slides] == ["<h1>Από το μοντέλο</h1>", "<p>typed meanwhile</p>"]
        assert result.json()["deck"]["version"] == 3


async def test_chat_409_when_the_edited_slide_vanished_meanwhile(tmp_path):
    import asyncio
    import threading

    app = make_app(tmp_path, [])
    deck = app.state.decks.create(title="t", language="el", material_text="")
    a = deck.slides[0].id
    gate = threading.Event()

    class GatedLLM:
        def __call__(self, system, messages):
            gate.wait(timeout=5)
            return reply([{"op": "replace", "slide": a, "html": "<h1>Από το μοντέλο</h1>"}])

    app.state.llm = GatedLLM()
    async with api_client(app) as c:
        chat = asyncio.create_task(c.post(f"/decks/{deck.id}/chat", json={"message": "x"}))
        await asyncio.sleep(0.2)
        await c.put(f"/decks/{deck.id}", json={"title": "t", "version": 1,
                                               "slides": [{"id": None, "html": "<p>replaced the only slide</p>", "video": None}]})
        gate.set()
        result = await chat
        assert result.status_code == 409 and result.json()["detail"] == "The slides were changed elsewhere"
        assert len((await c.get(f"/decks/{deck.id}")).json()["chat"]) == 0
