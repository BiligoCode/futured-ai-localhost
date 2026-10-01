# Lara Slides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the **Slides** material type to Lara: a 16:9 slide editor with an AI chat beside it, PDF/Word export, and embedded Manim animations made with the existing flow.

**Architecture:** Decks are files under `data/decks/<id>/` served by a new FastAPI router; each slide is a whitelisted HTML fragment that the sanitiser, the TipTap editor and both exporters share. The chat is one Bedrock call returning `{reply, edits}` JSON applied server-side (same pattern as `revise.py`). The web adds a chooser, a deck setup page and a split-pane deck workspace; the dashboard lists decks and animations together.

**Tech Stack:** FastAPI + pydantic v2, WeasyPrint 70 (PDF), python-docx (Word), ffmpeg (posters); Next.js 16 / React 19 / Tailwind v4, TipTap 3.31 (`@tiptap/react`, `@tiptap/pm`, `@tiptap/starter-kit`, `@tiptap/extension-text-style`, `@tiptap/extension-highlight`, `@tiptap/extension-text-align`), Vitest for pure web helpers.

**Spec:** `docs/slides/2026-10-01-slides-design.md` — read it first; every task below argues from it.

## Global Constraints

- Python `>=3.12,<3.13` via `uv`; run API tests with `cd api && uv run pytest -m "not slow"`; anything that runs ffmpeg or WeasyPrint on real files is marked `@pytest.mark.slow` *only* if it takes > 2 s (WeasyPrint on a 3-slide deck is fast and stays unmarked).
- Web: Node 22+, `cd web && npm run build && npm run lint && npm test` must pass after every web task. Read `web/node_modules/next/dist/docs/01-app/01-getting-started/03-layouts-and-pages.md` and `04-linking-and-navigating.md` before the first web task; mirror the existing pages (`app/projects/[id]/page.tsx`, `app/new/page.tsx`).
- API errors are raised as **English sentences**; every new sentence gets a Greek entry in `api/app/i18n.py` `EXACT`. Web strings live only in `web/lib/messages.ts` (`en` and `el`, type-checked); no literals in JSX.
- Ids: deck `uuid4().hex[:10]`, slide `uuid4().hex[:8]`. Slide size **1280×720 px**, padding `64px 72px 56px`. Slide HTML cap **20,000** chars. Chat keeps the last **50** messages, sends the last **10**; material excerpt **12,000** chars; LLM **2 attempts**. Autosave debounce **800 ms**; split ratio key `lara-deck-split`, range 0.30–0.75, default 0.60.
- Whitelist (exact): tags `h1 h2 p ul ol li strong em u mark span br`; `style` may carry only `text-align: left|center|right` on `h1 h2 p li`, and `color: #rrggbb` / `font-size: NNpx` (12–96) on `span`.
- Palette: `#18212e #566173 #1b6f8c #0f7b6c #74490a #c93838 #6d3fb8 #e2a13b`; highlight `#fff3b0`.
- Commit after every task (`feat:` / `test:` / `chore:` / `docs:`); each commit leaves the API tests and the web build green.
- Design: follow `web/app/globals.css` tokens and `.btn/.field/.panel/.notice` classes; serif (`font-serif`) for titles, sans for chrome; no new UI libraries beyond TipTap.

## Review Focus

Inputs the spec implies but a careless implementation breaks; each has a test pinned in the owning task:

1. **Pasted rich text from Word/Google Docs** (nested `div`/`span` soup, `font-family`, `background-color`) must come out as clean whitelisted HTML, never 422 — Task 1 `test_sanitize_unwraps_unknown_tags_and_drops_unknown_styles`.
2. **The AI replies with an edit for a slide id that no longer exists** (stale from history) — must retry, then 422, never 500 — Task 5 `test_chat_unknown_slide_retries_then_422`.
3. **Autosave races the chat**: professor types in slide B while the AI edits slide A — B's local text must survive the merge — Task 14 `deckMerge.test.ts` `keeps local html of untouched slides`.
4. **A Greek deck title in the export filename** must download as `<title>.pdf` and the zip must open — Task 9 `test_export_filename_keeps_greek`.
5. **An embedded animation whose project was deleted** must not break the editor, the export or the dashboard — Task 3 `test_view_marks_missing_animation`, Task 9 `test_export_skips_missing_animation`.

---

## File structure

**API (new)**: `app/slides_html.py` (sanitiser + text), `app/deck_store.py`, `app/deck_view.py` (DeckView/DeckSummary builders), `app/deck_chat.py`, `app/slides_pdf.py`, `app/slides_docx.py`, `app/deck_export.py`, `app/routes/decks.py`, `app/assets/slide.css`, `app/assets/fonts/`. **Modified**: `app/models.py`, `app/media.py` (`make_poster`), `app/main.py`, `app/i18n.py`, `app/routes/projects.py`, `pyproject.toml`.

**Web (new)**: `app/new/animation/page.tsx` (moved form), `app/new/slides/page.tsx`, `app/decks/[id]/page.tsx`, `app/slide.css`, `components/MaterialFields.tsx`, `components/deck/{DeckWorkspace,SlideEditor,SlideToolbar,SlideStrip,SlideThumb,SlideFrame,VideoBlock,DeckChat,EmbedDialog,DeckTile,AnimationsMenu,ExportMenu}.tsx`, `lib/slideHtml.ts`, `lib/deckMerge.ts`, `lib/useDeckSplit.ts`, `lib/*.test.ts`, `vitest.config.ts`. **Modified**: `app/layout.tsx`, `app/page.tsx`, `app/new/page.tsx` (chooser), `app/projects/[id]/page.tsx`, `components/{Stepper,Icon,VideoWorkspace}.tsx`, `lib/{api,types,messages}.ts`, `package.json`.

---

### Task 1: Slide HTML — sanitiser and text helpers

**Files:**
- Create: `api/app/slides_html.py`
- Test: `api/tests/test_slides_html.py`

**Interfaces:**
- Produces: `sanitize_slide_html(html: str) -> str` (raises `SlideTooLong(ValueError)` when the *input* exceeds `MAX_SLIDE_CHARS = 20_000`), `slide_text(html: str) -> str` (block-separated plain text, `- ` before list items), `slide_title(html: str) -> str` (text of the first `h1`/`h2`, else the first 60 chars of text, else `""`), `deck_material_text(title: str, slides: list[str]) -> str` (`"Lecture slides: {title}\n\nSlide 1: {slide_title}\n{slide_text}\n\n…"`), constants `ALLOWED_TAGS`, `PALETTE`.

- [ ] **Step 1: Write the failing tests**

```python
from app.slides_html import SlideTooLong, deck_material_text, sanitize_slide_html, slide_text, slide_title

def test_sanitize_keeps_whitelisted_markup():
    html = '<h1 style="text-align: center">Τίτλος</h1><ul><li><p><strong>a</strong> <em>b</em> <u>c</u> <mark>d</mark></p></li></ul>'
    assert sanitize_slide_html(html) == html

def test_sanitize_unwraps_unknown_tags_and_drops_unknown_styles():
    html = ('<div class="x"><p style="font-family: Arial; text-align: right; background: red">Hi '
            '<span style="color: #C93838; font-weight: bold; font-size: 34px">there</span></p></div>'
            '<script>alert(1)</script><table><tr><td>cell</td></tr></table>')
    assert sanitize_slide_html(html) == ('<p style="text-align: right">Hi <span style="color: #c93838; font-size: 34px">there</span></p>cell')

def test_sanitize_escapes_text_and_rejects_bad_values():
    assert sanitize_slide_html('<p>a < b &amp; c</p>') == '<p>a &lt; b &amp; c</p>'
    assert sanitize_slide_html('<span style="color: red; font-size: 200px">x</span>') == '<span>x</span>'
    assert sanitize_slide_html('<p style="text-align: justify">x</p>') == '<p>x</p>'

def test_sanitize_too_long():
    with pytest.raises(SlideTooLong):
        sanitize_slide_html("<p>" + "x" * 20_001 + "</p>")

def test_slide_text_and_title():
    html = "<h1>Ταξινόμηση</h1><p>Εισαγωγή</p><ul><li><p>ένα</p></li><li>δύο</li></ul>"
    assert slide_text(html) == "Ταξινόμηση\nΕισαγωγή\n- ένα\n- δύο"
    assert slide_title(html) == "Ταξινόμηση"
    assert slide_title("<p>" + "λ" * 80 + "</p>") == "λ" * 60
    assert slide_title("") == ""

def test_deck_material_text():
    out = deck_material_text("Αλγόριθμοι", ["<h1>Α</h1><p>κείμενο</p>", "<p>μόνο σώμα</p>"])
    assert out == "Lecture slides: Αλγόριθμοι\n\nSlide 1: Α\nκείμενο\n\nSlide 2: μόνο σώμα\nμόνο σώμα"
```

- [ ] **Step 2: Run to verify failure** — `cd api && uv run pytest tests/test_slides_html.py -v` → ImportError.

- [ ] **Step 3: Implement `api/app/slides_html.py`** with stdlib `html.parser.HTMLParser`: a subclass that rebuilds output, tracking a stack of open allowed tags so unknown tags are unwrapped (children kept), `script`/`style` content is dropped, attributes other than `style` are dropped, and `style` is parsed into `prop: value` pairs and filtered (`text-align` on `h1 h2 p li` with values `left|center|right`; `color` on `span` matching `#[0-9a-fA-F]{6}` lower-cased; `font-size` on `span` matching `(\d+)px` with 12 ≤ n ≤ 96). Style output order: `text-align`, then `color`, then `font-size`, joined with `; `. Text nodes go through `html.escape(text, quote=False)`. Void tag `br` is emitted as `<br>`. `slide_text` reuses the parser: block tags (`h1 h2 p li`) end a line, `li` prefixes `- ` (inner `p` adds no extra line), `br` → newline; collapse runs of blank lines; strip.

- [ ] **Step 4: Run to verify pass** — same command → 6 passed.

- [ ] **Step 5: Commit** — `git add api/app/slides_html.py api/tests/test_slides_html.py && git commit -m "feat(api): slide HTML sanitiser and text helpers"`

---

### Task 2: Deck models and store

**Files:**
- Modify: `api/app/models.py` (append after `ReviseResult`; add `deck_id` to `Project`)
- Create: `api/app/deck_store.py`
- Test: `api/tests/test_deck_store.py`

**Interfaces:**
- Produces (models, exactly as in spec §4): `Slide`, `EditLog`, `ChatMessage`, `Deck`, `AnimationRef`, `DeckView(Deck)`, `DeckSummary`, `SlideIn`, `DeckUpdate`, `DeckChatRequest` (`selection: str | None = Field(default=None, max_length=500)`), `DeckChatResult`, `EmbedRequest`, `ExportRequest`, `ExportResult`, exception `DeckNotFound(KeyError)`; `Project.deck_id: str | None = None`.
- Produces (store): `class DeckStore(root: Path)` with `decks_dir`, `deck_dir(id) -> Path`, `create(*, title: str, language: str, material_text: str) -> Deck` (one slide `<h1>{html.escape(title)}</h1>`, `version=1`), `get(id) -> Deck` (raises `DeckNotFound` for bad/unknown ids, same guard as `ProjectStore.get`), `list() -> list[Deck]` newest first, `material(id) -> str`, `write(deck)` (atomic write `deck.json.tmp` → `deck.json`, no bump; `create` uses it so a new deck has `version == 1`), `save(deck)` (sets `updated_at=now`, `version += 1`, then `write`), `async mutate(id, fn) -> Deck` (load → `fn` → `save`) under a per-id `asyncio.Lock`, `async delete(id)` (rmtree). `new_slide_id() -> str`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_create_get_list(tmp_path):
    store = DeckStore(tmp_path)
    a = store.create(title="Α <β>", language="el", material_text="υλικό")
    b = store.create(title="B", language="en", material_text="")
    assert a.slides[0].html == "<h1>Α &lt;β&gt;</h1>" and a.version == 1 and a.chat == []
    assert store.get(a.id).title == "Α <β>" and store.material(a.id) == "υλικό"
    assert [d.id for d in store.list()] == [b.id, a.id]
    assert (tmp_path / "decks" / a.id / "deck.json").is_file()

async def test_save_bumps_version_and_updated_at(tmp_path):
    store = DeckStore(tmp_path); d = store.create(title="t", language="el", material_text="")
    before = d.updated_at
    d2 = await store.mutate(d.id, lambda deck: deck.slides.append(Slide(id=new_slide_id(), html="<p>x</p>")))
    assert d2.version == 2 and d2.updated_at >= before and len(store.get(d.id).slides) == 2

async def test_get_rejects_bad_ids_and_delete(tmp_path):
    store = DeckStore(tmp_path); d = store.create(title="t", language="el", material_text="")
    for bad in ("", "../x", "nope"):
        with pytest.raises(DeckNotFound): store.get(bad)
    await store.delete(d.id)
    with pytest.raises(DeckNotFound): store.get(d.id)
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_deck_store.py -v` → ImportError.
- [ ] **Step 3: Add the models to `app/models.py` and implement `app/deck_store.py`** mirroring `ProjectStore` (`store.py:27-107`).
- [ ] **Step 4: Run** — `uv run pytest tests/test_deck_store.py tests/test_store.py -v` → all pass (existing `Project` tests still green with the new optional field).
- [ ] **Step 5: Commit** — `git commit -am "feat(api): deck models and DeckStore"` (add the new files first).

---

### Task 3: Deck CRUD routes, views, i18n, wiring

**Files:**
- Create: `api/app/deck_view.py`, `api/app/routes/decks.py`
- Modify: `api/app/main.py` (state `decks`, router, `DeckNotFound` handler → 404 "Slides not found"), `api/app/i18n.py` (6 EXACT entries from spec §9), `api/app/routes/projects.py:86-96` (deleting a project needs nothing new; `DELETE /decks` clears `deck_id` on projects)
- Test: `api/tests/test_api_decks.py`

**Interfaces:**
- Produces: `deck_view.animation_refs(deck: Deck, projects: list[Project]) -> list[AnimationRef]` (linked ∪ embedded, newest first; `status` per spec §4; `missing` projects are those referenced by `slide.video` but absent), `deck_view.build_view(deck: Deck, projects: list[Project]) -> DeckView`, `deck_view.summarize(deck: Deck, projects: list[Project]) -> DeckSummary`.
- Produces (routes, spec §9): `POST /decks` (multipart `title`, `language`, `material_text`, `files[]`; 422 on `EmptyMaterialError`), `GET /decks`, `GET /decks/{id}`, `PUT /decks/{id}` (`DeckUpdate`; 409 `"The slides were changed elsewhere"`; sanitises each slide — `SlideTooLong` → 422 `"Slide is too long"`; keeps a client id matching `^[0-9a-f]{8}$`, otherwise assigns `new_slide_id()`; sets `title`), `DELETE /decks/{id}` → 204 and `deck_id=None` on linked projects, `GET /decks/{id}/material`. Helper `_view(request, deck) -> DeckView` reads `request.app.state.store.list()`.
- Greek entries: "Slides not found" → "Οι διαφάνειες δεν βρέθηκαν"; "The slides were changed elsewhere" → "Οι διαφάνειες άλλαξαν από αλλού"; "The AI reply could not be applied. Please try again." → "Η απάντηση του AI δεν μπόρεσε να εφαρμοστεί. Δοκιμάστε ξανά."; "The animation is not ready yet" → "Η κινούμενη εικόνα δεν είναι ακόμα έτοιμη"; "Slide is too long" → "Η διαφάνεια είναι πολύ μεγάλη"; "This slide does not exist" → "Αυτή η διαφάνεια δεν υπάρχει".

- [ ] **Step 1: Write the failing tests** (pattern: `create_app(make_settings(tmp_path), llm=ScriptedLLM([]), renderer=FakeRenderer([...]), tts=FakeTTS(b""))` + `api_client(app)`)

```python
async def test_create_deck_with_pdf_and_text(tmp_path):
    r = await client.post("/decks", data={"title": "Αλγόριθμοι", "language": "el", "material_text": "σημειώσεις"},
                          files=[("files", ("a.pdf", make_pdf("pdf text"), "application/pdf"))])
    assert r.status_code == 200; d = r.json()
    assert d["slides"][0]["html"] == "<h1>Αλγόριθμοι</h1>" and d["animations"] == [] and d["version"] == 1
    assert (await client.get(f"/decks/{d['id']}/material")).text == "pdf text\n\nσημειώσεις"

async def test_create_deck_without_material_ok_but_unreadable_pdf_422(...)   # mirrors test_api_projects

async def test_list_summaries(...):  # slide_count, animation_count, first_slide_html, newest first

async def test_put_sanitises_assigns_ids_and_checks_version(...):
    body = {"title": "Νέος", "version": 1, "slides": [
        {"id": d["slides"][0]["id"], "html": "<h1>A</h1><div><p onclick='x'>b</p></div>"},
        {"id": None, "html": "<p>new</p>"}, {"id": "zzz", "html": "<p>bad id</p>"}]}
    r = await client.put(f"/decks/{id}", json=body); v = r.json()
    assert [s["html"] for s in v["slides"]] == ["<h1>A</h1><p>b</p>", "<p>new</p>", "<p>bad id</p>"]
    assert v["slides"][0]["id"] == d["slides"][0]["id"] and re.fullmatch(r"[0-9a-f]{8}", v["slides"][1]["id"])
    assert v["version"] == 2 and v["title"] == "Νέος"
    assert (await client.put(f"/decks/{id}", json=body)).status_code == 409   # stale version

async def test_put_too_long_slide_422(...)   # "Slide is too long"

async def test_delete_deck_clears_deck_id_on_projects(...):
    # project created directly via app.state.store.create(...) then mutate(deck_id=deck_id); DELETE deck → 204; project.deck_id is None; GET deck → 404

async def test_view_marks_missing_animation(...):
    # mutate deck: slides[0].video = "ghost"; GET → animations == [{"project_id": "ghost", "status": "missing", "embedded": True, "cut": None, ...}]

async def test_404_in_greek(...):
    r = await client.get("/decks/nope", headers={"X-Lara-Lang": "el"}); assert r.json()["detail"] == "Οι διαφάνειες δεν βρέθηκαν"
```

- [ ] **Step 2: Run to verify failure** → 404s / import errors.
- [ ] **Step 3: Implement `deck_view.py`, `routes/decks.py`, wire `main.py`, add i18n entries.** `AnimationRef` for a found project: `status = "draft" if stage == "storyboard" else "creating" if preview.version == 0 else "ready"`, `cut = "final" if final.version > 0 else "preview" if preview.version > 0 else None`, `version`/`duration` from that cut or 0.
- [ ] **Step 4: Run** — `uv run pytest -m "not slow"` → all green.
- [ ] **Step 5: Commit** — `git commit -m "feat(api): deck routes, views and translations"`

---

### Task 4: Animations created from a deck

**Files:**
- Modify: `api/app/routes/projects.py:16-51` (`deck_id: str = Form("")`), `api/app/models.py` (nothing new; `deck_id` exists)
- Test: `api/tests/test_api_projects.py` (append)

**Interfaces:**
- `POST /projects` with `deck_id`: loads the deck (404 if unknown), prepends `deck_material_text(deck.title, [s.html for s in deck.slides])` to the material (then PDFs, then pasted text, joined by `"\n\n"`, capped at `MAX_MATERIAL_CHARS`), stores `project.deck_id`. `ProjectStore.create` gains `deck_id: str | None = None`.

- [ ] **Step 1: Write the failing test**

```python
async def test_create_project_from_deck(tmp_path):
    deck = app.state.decks.create(title="Δέντρα", language="el", material_text="")
    r = await client.post("/projects", data={"concept": "BST", "language": "el", "deck_id": deck.id, "material_text": "extra"})
    p = r.json(); assert p["deck_id"] == deck.id
    assert (await client.get(f"/projects/{p['id']}/material")).text.startswith("Lecture slides: Δέντρα\n\nSlide 1: Δέντρα\nΔέντρα")
    assert (await client.get(f"/projects/{p['id']}/material")).text.endswith("extra")
    assert (await client.get("/projects")).json()[0]["deck_id"] == deck.id
```

- [ ] **Step 2: Run** → fails (`deck_id` ignored).
- [ ] **Step 3: Implement.** `material = "\n\n".join(p for p in [deck_text, build_material(pdfs, material_text)] if p)[:MAX_MATERIAL_CHARS]`.
- [ ] **Step 4: Run** `uv run pytest tests/test_api_projects.py -v` → pass.
- [ ] **Step 5: Commit** — `git commit -m "feat(api): create animations from a deck"`

---

### Task 5: Deck chat

**Files:**
- Create: `api/app/deck_chat.py`
- Modify: `api/app/routes/decks.py` (`POST /decks/{id}/chat`)
- Test: `api/tests/test_deck_chat.py`

**Interfaces:**
- Produces: `SYSTEM_PROMPT: str` (spec §6 text, `{language}` placeholder, palette inlined), `build_user_message(deck: Deck, material: str, message: str, *, slide_id: str | None, selection: str | None) -> str`, `apply_edits(slides: list[Slide], edits: list[_Edit]) -> tuple[list[Slide], list[EditLog]]` (pure; raises `ValueError` on unknown ids / deleting the only slide / moving after itself / empty text after sanitising), `class DeckChatError(RuntimeError)`, `run_chat(llm: LLM, deck: Deck, material: str, message: str, *, slide_id: str | None, selection: str | None) -> tuple[str, list[Slide], list[EditLog]]` (2 attempts; language check with `storyboard.check_language` on the joined text of inserted/replaced slides when it has ≥ 40 letters).
- Route: validates `slide_id` exists (422 "This slide does not exist"), runs `run_chat` in `asyncio.to_thread`, maps `DeckChatError` → 422 "The AI reply could not be applied. Please try again.", other exceptions → 502 `"The AI model request failed: {exc}"`, `await request.is_disconnected()` → 499 "Cancelled" (nothing saved); on success mutates the deck (slides, `chat` += user message + assistant message with `edits`, trimmed to the last 50) and returns `DeckChatResult(deck=_view(...), reply, edits)`.

- [ ] **Step 1: Write the failing tests**

```python
def deck_with(*htmls) -> Deck: ...  # slides s1.., ids "aaaaaaa1".. for readability

def test_user_message_lists_slides_history_and_context():
    deck = deck_with("<h1>Α</h1>", "<p>Β</p>"); deck.chat = [ChatMessage(role="user", content="γεια", at=now), ChatMessage(role="assistant", content="γεια σας", edits=[EditLog(op="replace", slide_id=deck.slides[0].id, title="Α")], at=now)]
    msg = build_user_message(deck, "υλικό" * 3000, "κάνε το έντονο", slide_id=deck.slides[1].id, selection="Β")
    assert f"[{deck.slides[0].id}] <h1>Α</h1>" in msg and "Course material (excerpt)" in msg and len(msg) < 14_000
    assert "Professor: γεια\nLara: γεια σας (changed slides " in msg
    assert f"looking at slide [{deck.slides[1].id}]" in msg and 'Selected text on that slide: "Β"' in msg
    assert msg.rstrip().endswith("Professor: κάνε το έντονο")

def test_apply_edits_each_op():
    slides = deck_with("<p>1</p>", "<p>2</p>", "<p>3</p>").slides; a, b, c = (s.id for s in slides)
    out, log = apply_edits(slides, [_Edit(op="replace", slide=a, html="<h1>Uno</h1>"), _Edit(op="insert_after", slide=a, html="<p>x</p>"), _Edit(op="insert_after", slide=a, html="<p>y</p>"), _Edit(op="delete", slide=c), _Edit(op="move", slide=b, after=None)])
    assert [s.html for s in out] == ["<p>2</p>", "<h1>Uno</h1>", "<p>x</p>", "<p>y</p>"]
    assert [(e.op, e.title) for e in log] == [("replace", "Uno"), ("insert_after", "x"), ("insert_after", "y"), ("delete", "3"), ("move", "2")]
    assert out[1].id == a and out[1].video is None

def test_apply_edits_errors():
    for bad in ([_Edit(op="replace", slide="nope", html="<p>x</p>")], [_Edit(op="replace", slide=a, html="<div></div>")], [_Edit(op="move", slide=a, after=a)]):
        with pytest.raises(ValueError): apply_edits(one_slide_deck.slides, bad)
    with pytest.raises(ValueError): apply_edits(one_slide_deck.slides, [_Edit(op="delete", slide=a)])

def test_run_chat_question_only_and_language_retry():
    llm = ScriptedLLM(['{"reply": "Ναι, …", "edits": []}'])
    reply, slides, log = run_chat(llm, deck, "", "τι λες;", slide_id=None, selection=None); assert log == [] and slides == deck.slides
    llm = ScriptedLLM(['{"reply":"ok","edits":[{"op":"replace","slide":"%s","html":"<p>This is English text that is long enough</p>"}]}' % a,
                       '{"reply":"ok","edits":[{"op":"replace","slide":"%s","html":"<p>Αυτό είναι ελληνικό κείμενο αρκετά μεγάλο</p>"}]}' % a])
    reply, slides, log = run_chat(llm, greek_deck, "", "γράψε", slide_id=None, selection=None)
    assert len(llm.calls) == 2 and "not valid" in llm.calls[1][1][-1]["content"] and slides[0].html.startswith("<p>Αυτό")

async def test_chat_route_applies_and_records(...):
    # POST /decks/{id}/chat {"message": "...", "slide_id": a} with ScriptedLLM replace → 200; body.reply, body.edits[0].op == "replace"; deck.version bumped; GET deck chat has 2 messages (user, assistant with edits)

async def test_chat_unknown_slide_retries_then_422(...):
    llm = ScriptedLLM(['{"reply":"x","edits":[{"op":"delete","slide":"ghost"}]}'] * 2)
    r = await client.post(...); assert r.status_code == 422 and r.json()["detail"] == "The AI reply could not be applied. Please try again."
    assert (await client.get(f"/decks/{id}")).json()["version"] == 1   # nothing saved

async def test_chat_bad_slide_id_422_and_llm_error_502(...)   # "This slide does not exist"; ScriptedLLM([RuntimeError("boom")]) → 502 startswith "The AI model request failed: "

async def test_chat_history_trimmed_to_50(...)
```

- [ ] **Step 2: Run** → ImportError.
- [ ] **Step 3: Implement `deck_chat.py` and the route.** History block: last 10 messages, each `content[:600]`, assistant lines suffixed with `" (changed slides " + ", ".join(str(index+1) …) + ")"` when edits exist — use the slide's **current index** when still present, else its title. Retry message: `f"Your previous reply was not valid: {error}. Reply with only the JSON."`.
- [ ] **Step 4: Run** `uv run pytest -m "not slow"` → green.
- [ ] **Step 5: Commit** — `git commit -m "feat(api): deck chat with structured edits"`

---

### Task 6: Prompt tuning against the real model (throwaway)

**Files:**
- Create: `api/scripts/try_deck_chat.py` (committed as a dev tool, like `scripts/check_bedrock.py`)

- [ ] **Step 1:** Script builds a 4-slide Greek deck about bubble sort in memory and sends three messages through `run_chat` with `BedrockLLM(load_settings())`: (a) a pure question, (b) "γράψε δύο διαφάνειες για την πολυπλοκότητα και κάνε τους τίτλους μπλε", (c) "διόρθωσε τα ορθογραφικά στη διαφάνεια 2 και βάλε κουκκίδες". Prints reply, edit log and resulting HTML.
- [ ] **Step 2:** Run `cd api && uv run python scripts/try_deck_chat.py`. Acceptable: all three succeed on the first attempt at least 2 of 3 runs; HTML passes the sanitiser unchanged; replies are in Greek.
- [ ] **Step 3:** Adjust `SYSTEM_PROMPT` wording (never the contract) until Step 2 holds; re-run Task 5 tests.
- [ ] **Step 4: Commit** — `git commit -m "chore(api): deck chat prompt check script"`

---

### Task 7: Posters and embedding animations

**Files:**
- Modify: `api/app/media.py` (append `make_poster`), `api/app/routes/decks.py` (`POST /decks/{id}/embed`, `GET /decks/{id}/posters/{project_id}.jpg`)
- Test: `api/tests/test_api_embed.py`, `api/tests/test_media.py` (append, `slow`)

**Interfaces:**
- `media.make_poster(video: Path, out: Path, at: float) -> None` — `ffmpeg -v error -y -ss {at:.3f} -i video -frames:v 1 -vf scale=640:-2 -q:v 3 out`.
- Route `POST /decks/{id}/embed` (`EmbedRequest`): project 404 via `ProjectNotFound`; `preview.version == 0` → 409 "The animation is not ready yet"; cut = final if `final.version > 0` else preview; poster from `compose.FILES[cut]` path at `min(duration * 0.3, 8)` via `asyncio.to_thread(make_poster, …)` into `deck_dir/posters/{project_id}.jpg`; mutate per spec §7 (`append` replaces an existing video on that slide; new slides get `<h2>{html.escape(project.title)}</h2>`); unknown `slide_id` → 422 "This slide does not exist"; returns `DeckView`. The route calls `make_poster` through the module attribute `app.routes.decks.make_poster` so tests can `monkeypatch` it.
- `GET /decks/{id}/posters/{project_id}.jpg` → `FileResponse(media_type="image/jpeg")`, 404 when absent.

- [ ] **Step 1: Write the failing tests** — fixture builds a project via `app.state.store.create(...)` then `mutate` to `stage="scenes"`, `preview=Cut(status="done", version=1, duration=20)` and writes `preview.mp4` bytes; `monkeypatch.setattr("app.routes.decks.make_poster", fake)` where `fake` writes `b"jpg"` and records `at`.

```python
async def test_embed_append_new_after_new_end(...):
    # append → slides[0].video == pid; new_after slide 0 → slides[1].html == "<h2>{title}</h2>" and video; new_end → last slide; fake.at == 6.0; animations[0] == {"project_id": pid, "status": "ready", "cut": "preview", "version": 1, "duration": 20, "embedded": True, ...}
async def test_embed_replaces_existing_video_on_slide(...)
async def test_embed_not_ready_409_and_unknown_project_404_and_bad_slide_422(...)
async def test_poster_served(...):   # GET .../posters/{pid}.jpg → 200 image/jpeg b"jpg"; unknown → 404

@pytest.mark.slow
def test_make_poster_real(tmp_path):   # make_clip 2 s → make_poster(at=0.5) → file > 1000 bytes, probe width 640
```

- [ ] **Step 2: Run** → fails. **Step 3: Implement.** **Step 4: Run** `uv run pytest -m "not slow"` and `uv run pytest tests/test_media.py -m slow -k poster`. **Step 5: Commit** — `git commit -m "feat(api): embed animations in slides with posters"`

---

### Task 8: PDF export (WeasyPrint), slide stylesheet and fonts

**Files:**
- Create: `api/app/assets/slide.css`, `api/app/assets/fonts/` (`STIXTwoText[wght].ttf`, `STIXTwoText-Italic[wght].ttf`, `Commissioner[FLAR,VOLM,slnt,wght].ttf`, `OFL.txt` — from `https://github.com/google/fonts/raw/main/ofl/stixtwotext/` and `/ofl/commissioner/`; if a download fails, skip the font and rely on the DejaVu fallback in the stack, noting it in the commit message), `api/app/slides_pdf.py`
- Modify: `api/pyproject.toml` (`weasyprint`, `python-docx` dependencies; `uv sync`)
- Test: `api/tests/test_slides_export.py`

**Interfaces:**
- `slide.css` (canonical; header comment: `/* Twin of web/app/slide.css — keep in sync. 1280×720 px coordinate system. */`): `.slide` (1280×720, padding `64px 72px 56px`, white, ink, Commissioner 26px/1.35, relative, overflow hidden, flex column), `.slide h1` (STIX 56px/1.1 600, margin 0 0 28px, letter-spacing −0.01em), `.slide h2` (STIX 40px/1.15 600, margin 0 0 20px), `.slide p` (margin 0 0 16px), `.slide ul/ol` (margin 0 0 16px, padding-left 1.2em), `.slide li` (margin 0 0 8px), `.slide li p { margin: 0 }`, `.slide li::marker { color: #1b6f8c }`, `.slide mark` (`#fff3b0`, inherit colour, padding 0 .1em), `.slide-text` (flex 1 1 auto, min-height 0), `.slide-video` (margin-top 8px; `img, video` width 100%, max-height 400px, object-fit contain, background `#0f141b`, border-radius 8px; `figcaption` 16px muted margin-top 6px), `.slide-footer` (absolute, left/right 72px, bottom 22px, flex space-between, 16px, `#8a94a3`).
- `slides_pdf.render_pdf(deck: Deck, animations: list[AnimationRef], posters: dict[str, Path], video_files: dict[str, str]) -> bytes` — `video_files` maps project_id → relative path inside the zip (`animations/01-title.mp4`); slides whose `video` is missing/not ready render without the figure. HTML: `@page { size: 1280px 720px; margin: 0 }`, `@font-face` rules with `file://` URLs for the bundled fonts, one `<section class="slide">` per slide containing `<div class="slide-text">{html}</div>`, optional `<figure class="slide-video"><a href="{rel}"><img src="file://{poster}"></a><figcaption>▶ Animation: {title} — {rel}</figcaption></figure>`, and `<footer class="slide-footer"><span>{deck.title}</span><span>{n} / {total}</span></footer>`. Render with `HTML(string=…, base_url=str(deck_dir)).write_pdf()`.

- [ ] **Step 1: Write the failing tests**

```python
def test_render_pdf_pages_and_text(tmp_path):
    deck = deck_with("<h1>Ταξινόμηση</h1><p>Εισαγωγή</p>", "<p>Δεύτερη</p>", "<p>Τρίτη</p>")
    pdf = render_pdf(deck, [], {}, {})
    reader = PdfReader(io.BytesIO(pdf)); assert len(reader.pages) == 3
    assert round(float(reader.pages[0].mediabox.width) / float(reader.pages[0].mediabox.height), 3) == 1.778
    assert "Ταξινόμηση" in reader.pages[0].extract_text() and "1 / 3" in reader.pages[0].extract_text()

def test_render_pdf_with_poster_and_missing_animation(tmp_path):
    poster = tmp_path / "p.jpg"; write a 640×360 jpeg (reportlab or PIL-free: ffmpeg lavfi via conftest.ffmpeg_bytes)
    deck = deck_with("<p>a</p>", "<p>b</p>"); deck.slides[0].video = "pid"; deck.slides[1].video = "ghost"
    refs = [AnimationRef(project_id="pid", title="Φυσαλίδα", status="ready", cut="preview", version=1, duration=5, embedded=True),
            AnimationRef(project_id="ghost", title="", status="missing", cut=None, version=0, duration=0, embedded=True)]
    pdf = render_pdf(deck, refs, {"pid": poster}, {"pid": "animations/01-Φυσαλίδα.mp4"})
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "Animation: Φυσαλίδα" in text and "animations/01-Φυσαλίδα.mp4" in text and len(PdfReader(io.BytesIO(pdf)).pages) == 2
```

- [ ] **Step 2: Run** → ImportError. **Step 3: `uv add weasyprint python-docx`, download fonts, write `slide.css` and `slides_pdf.py`.** **Step 4: Run** → pass (< 3 s). **Step 5: Commit** — `git commit -m "feat(api): PDF export of slides with WeasyPrint"`

---

### Task 9: Word export, zip, export routes

**Files:**
- Create: `api/app/slides_docx.py`, `api/app/deck_export.py`
- Modify: `api/app/routes/decks.py` (`POST /decks/{id}/export`, `GET /decks/{id}/export/{file}`)
- Test: `api/tests/test_slides_export.py` (append), `api/tests/test_api_decks.py` (append)

**Interfaces:**
- `slides_docx.render_docx(deck, animations, posters, video_files) -> bytes` — same signature as `render_pdf`. Section landscape 13.333″×7.5″, margins 0.67″; per slide: blocks via a small HTML walker over the whitelist (`h1` → paragraph, runs 36 pt Cambria bold; `h2` → 28 pt Cambria; `p` → 18 pt Calibri; `ul/ol` → style `List Bullet` / `List Number`; inline `strong/em/u/mark` → `run.bold/italic/underline/font.highlight_color = WD_COLOR_INDEX.YELLOW`; `span color` → `run.font.color.rgb`; `span font-size` → `Pt(round(px * 0.7))`; `text-align` → `paragraph.alignment`); poster → `add_picture(width=Inches(7))` + hyperlink paragraph `"▶ Animation: {title} ({rel})"` (OOXML `w:hyperlink` with an external relationship); `add_page_break()` between slides; footer paragraph = deck title + a `PAGE` field.
- `deck_export.safe_filename(title: str) -> str` (keep `\w`, space, `-`; replace the rest with `-`; collapse; strip; ≤ 80 chars; fallback `"slides"`), `deck_export.export_deck(deck_dir: Path, deck: Deck, animations: list[AnimationRef], project_video: dict[str, Path], fmt: Literal["pdf", "docx"]) -> tuple[Path, str, str]` → `(path, download_filename, media_type)`; writes `export/deck.{fmt}`; when any embedded animation is `ready` and its file exists, writes `export/deck-{fmt}.zip` (document + `animations/{n:02d}-{safe_filename(title)}.mp4`, stored not deflated) and returns it with `"{title}.zip"` / `application/zip`; else `"{title}.{fmt}"` with `application/pdf` / `application/vnd.openxmlformats-officedocument.wordprocessingml.document`.
- Routes: `POST /decks/{id}/export` (`ExportRequest`) → `asyncio.to_thread(export_deck, …)`; exceptions → 502 `"Export failed: {exc}"`; returns `ExportResult(url=f"/decks/{id}/export/{path.name}", filename)`. `GET /decks/{id}/export/{file}` → `FileResponse(path, media_type, filename=<download name stored alongside as export/{file}.name>)`; 404 otherwise. `project_video` built from `compose.FILES` for each `AnimationRef` with a cut.

- [ ] **Step 1: Write the failing tests**

```python
def test_render_docx_formatting(tmp_path):
    deck = deck_with('<h1 style="text-align: center">Τίτλος</h1><p><strong>έντονο</strong> <span style="color: #c93838; font-size: 34px">κόκκινο</span></p><ul><li><p>ένα</p></li></ul>', "<p>δύο</p>")
    doc = Document(io.BytesIO(render_docx(deck, [], {}, {})))
    paras = [p for p in doc.paragraphs if p.text]
    assert paras[0].text == "Τίτλος" and paras[0].alignment == WD_ALIGN_PARAGRAPH.CENTER and paras[0].runs[0].font.size == Pt(36)
    runs = paras[1].runs; assert runs[0].bold and str(runs[2].font.color.rgb) == "C93838" and runs[2].font.size == Pt(24)
    assert paras[2].style.name == "List Bullet"
    assert sum(1 for p in doc.paragraphs for r in p.runs if "w:br" in r._r.xml and 'w:type="page"' in r._r.xml) == 1

def test_safe_filename(): assert safe_filename("Αλγόριθμοι: Ταξινόμηση/2") == "Αλγόριθμοι- Ταξινόμηση-2" and safe_filename("///") == "slides"

def test_export_deck_zip_and_filename_keeps_greek(tmp_path): ...  # with a ready animation + fake mp4 → zip containing deck.pdf and animations/01-Φυσαλίδα.mp4; download name "Δέντρα.zip"
def test_export_skips_missing_animation(tmp_path): ...            # only a missing one → bare deck.pdf, "Δέντρα.pdf"

async def test_export_route_and_download(...):   # POST {"format": "docx"} → url; GET url → 200, content-type docx, content-disposition contains "filename*=utf-8''" and the encoded title
```

- [ ] **Step 2: Run** → fails. **Step 3: Implement.** **Step 4: Run** `uv run pytest -m "not slow"` → green. **Step 5: Commit** — `git commit -m "feat(api): Word export, zip with animations, export routes"`

---

### Task 10: Web foundation — layout width, chooser, moved setup form, shared material fields

**Files:**
- Modify: `web/app/layout.tsx` (`main` loses `max-w-6xl`; header inner div gets a fixed `h-14`; button → `href="/new"`, label `t.newMaterial`), `web/app/page.tsx` (wrap in `mx-auto max-w-6xl`; heading `t.yourMaterials`), `web/app/projects/[id]/page.tsx` (wrapper; `backToSetup` → `/new/animation?from=${id}`), `web/components/Stepper.tsx` (no change needed — callers pass hrefs), `web/lib/messages.ts`
- Create: `web/app/new/animation/page.tsx` (the current `app/new/page.tsx` content, wrapped in `mx-auto max-w-6xl`; `Stepper go` unchanged), `web/components/MaterialFields.tsx`, new `web/app/new/page.tsx` (chooser)
- Test: `npm run build && npm run lint`

**Interfaces:**
- `MaterialFields({ files, onFiles, defaultText, children? }: { files: File[]; onFiles: (f: File[]) => void; defaultText?: string; children?: React.ReactNode })` — renders the PDF picker (`name="files"`), the file list with remove buttons, `children` (slot between the picker and the textarea, used for the "Slides: …" item in Task 16) and the `material_text` textarea with `t.noMaterialHint`. The setup form keeps its `files` state and passes it in.
- Chooser `/new`: `h1 t.chooseTitle`, `p t.chooseSubtitle`, two `Link` cards in a `grid gap-6 sm:grid-cols-2`: Animation (`stage stage-grid` dark card with `CurveSketch`, `t.chooseAnimation`, `t.chooseAnimationBody`, → `/new/animation`) and Slides (`panel` paper card with a small inline SVG of a 16:9 frame with three text bars, `t.chooseSlides`, `t.chooseSlidesBody`, → `/new/slides`).
- New message keys (English copy; write the Greek in the same register as the existing `el` strings): `newMaterial: "New material"` / el `"Νέο υλικό"`, `yourMaterials: "Your materials"` / el `"Το υλικό σας"`, `chooseTitle: "What would you like to make?"`, `chooseSubtitle: "An animated explanation, or a deck of slides written with Lara beside you."`, `chooseAnimation: "Animation"`, `chooseAnimationBody: "Lara drafts a script, renders a Manim animation and narrates it — with an AI voice or yours."`, `chooseSlides: "Slides"`, `chooseSlidesBody: "Write lecture slides with an AI assistant, embed your animations, export to PDF or Word."`. Rename nothing else (keep `newTitle` etc. for the animation form).

- [ ] **Step 1:** Read the two Next.js guides named in Global Constraints. Move the form to `app/new/animation/page.tsx`; create the chooser; extract `MaterialFields`; adjust layout/dashboard/project page; add keys.
- [ ] **Step 2:** `cd web && npm run build && npm run lint` → clean. Start `npm run dev` and `google-chrome --headless --screenshot=/tmp/opencode/new.png --window-size=1440,900 http://localhost:3000/new`; view the PNG: two cards, header button says "Νέο υλικό".
- [ ] **Step 3: Commit** — `git commit -m "feat(web): material chooser, animation setup moved, shared material fields"`

---

### Task 11: Deck types, API client, deck setup page

**Files:**
- Modify: `web/lib/types.ts` (append), `web/lib/api.ts` (append), `web/lib/messages.ts`
- Create: `web/app/new/slides/page.tsx`
- Test: build + lint + screenshot

**Interfaces:**
- Types (snake_case mirrors of spec §4): `Slide { id: string; html: string; video: string | null }`, `EditLog { op: "replace" | "insert_after" | "delete" | "move"; slide_id: string; title: string }`, `ChatMessage { role: "user" | "assistant"; content: string; edits: EditLog[]; at: string }`, `AnimationRef { project_id; title; status: "draft" | "creating" | "ready" | "missing"; cut: CutKind | null; version: number; duration: number; embedded: boolean }`, `Deck { id; created_at; updated_at; title; language: Language; slides: Slide[]; chat: ChatMessage[]; version: number; animations: AnimationRef[] }` (= DeckView), `DeckSummary { id; created_at; updated_at; title; language; slide_count; animation_count; first_slide_html }`, `SlideIn { id: string | null; html: string; video: string | null }`, `DeckUpdate { title: string; slides: SlideIn[]; version: number }`, `ChatResult { deck: Deck; reply: string; edits: EditLog[] }`, `EmbedMode = "append" | "new_after" | "new_end"`, `ExportFormat = "pdf" | "docx"`; `Project.deck_id: string | null`.
- API: `listDecks()`, `getDeck(id)`, `createDeck(form: FormData)`, `saveDeck(id, body: DeckUpdate)`, `deleteDeck(id)`, `chatDeck(id, body: { message: string; slide_id: string | null; selection: string | null }, signal?: AbortSignal) → ChatResult`, `embedAnimation(deckId, body: { project_id: string; slide_id: string | null; mode: EmbedMode }) → Deck`, `exportDeck(id, format: ExportFormat) → { url: string; filename: string }`, `posterUrl(deckId, projectId) → string` (`${API_URL}/decks/${deckId}/posters/${projectId}.jpg`), `exportUrl(url) → string` (`${API_URL}${url}`).
- Page `/new/slides`: `h1 t.deckNewTitle` ("New slides"), `p t.deckNewSubtitle`; `panel` form with title field (`name="title"`, required, `field font-serif text-2xl`, placeholder `t.deckTitlePlaceholder` "e.g. Lecture 4 — Sorting"), `Segmented` language (default `lang`), `MaterialFields`, submit `t.createDeck` ("Create slides") / busy `t.creatingDeck` ("Creating…"); on success `router.push(/decks/${deck.id})`. (Move `Segmented` from the animation page into `components/Segmented.tsx` so both pages share it.)

- [ ] **Step 1:** Implement. **Step 2:** `npm run build && npm run lint`; screenshot `/new/slides`. **Step 3: Commit** — `git commit -m "feat(web): deck API client and deck setup page"`

---

### Task 12: Slide rendering — theme CSS, frame, thumbnail, TipTap editor, toolbar; Vitest

**Files:**
- Create: `web/app/slide.css` (twin of `api/app/assets/slide.css`, same rules; plus editor-only rules: `.slide .ProseMirror { outline: none; min-height: 100%; }`, `.slide-overflow` red 3px bottom rule, `.slide.is-active` accent ring), `web/lib/slideHtml.ts`, `web/lib/slideHtml.test.ts`, `web/vitest.config.ts`, `web/components/deck/SlideFrame.tsx`, `web/components/deck/SlideThumb.tsx`, `web/components/deck/SlideEditor.tsx`, `web/components/deck/SlideToolbar.tsx`, `web/components/deck/VideoBlock.tsx`
- Modify: `web/app/globals.css` (`@import "./slide.css";` after the tailwind import), `web/package.json` (deps: `@tiptap/react @tiptap/pm @tiptap/starter-kit @tiptap/extension-text-style @tiptap/extension-highlight @tiptap/extension-text-align`; dev: `vitest`; script `"test": "vitest run"`), `web/components/Icon.tsx` (add `bold, italic, underline, bullets, numbers, alignLeft, alignCenter, alignRight, highlight, slides, film, undo, redo, grip, chat, sparkle`)
- Test: `npm test` + build + lint

**Interfaces:**
- `lib/slideHtml.ts`: `SLIDE_W = 1280`, `SLIDE_H = 720`, `PALETTE: { name: string; hex: string }[]` (8 entries, spec palette), `SIZES = [{ label: "S", px: 20 }, { label: "M", px: 26 }, { label: "L", px: 34 }, { label: "XL", px: 44 }]`, `slideTitle(html: string): string` and `slideText(html: string): string` — regex-based over the whitelisted subset (strip tags, decode `&amp; &lt; &gt; &quot; &#39;`, same semantics as the Python helpers), `slideLabel(index: number, html: string, t): string` → title or `t.slideN(index + 1)`.
- `SlideFrame({ children, className, active, overflow, footerLeft, footerRight })`: measures its width with `ResizeObserver`, renders `<div class="slide" style={{ zoom: width / SLIDE_W }}>` inside a wrapper whose height is `width * 9 / 16` (CSS `zoom`, not `transform`, so ProseMirror coordinates and `scrollHeight` stay correct); children go in `.slide-text`; footer from props.
- `SlideThumb({ html, video, title, index, total })`: read-only `SlideFrame` with `dangerouslySetInnerHTML` (HTML is server-sanitised) and a film icon badge when `video` is set.
- `SlideEditor({ slide, index, total, deckTitle, active, animation, onChange, onFocus, onSelection, onRemoveVideo, editorRef })`: `useEditor({ immediatelyRender: false, extensions: [StarterKit.configure({ heading: { levels: [1, 2] }, strike: false, code: false, codeBlock: false, blockquote: false, horizontalRule: false, link: false }), TextStyle, Color, FontSize, Highlight, TextAlign.configure({ types: ["heading", "paragraph"] })], content: slide.html, onUpdate → onChange(editor.getHTML()), onFocus → onFocus(slide.id), onSelectionUpdate → onSelection(textBetween(from, to).trim().slice(0, 500) || null) })`; `useEffect` sets content when `slide.html !== editor.getHTML()` (external change, `emitUpdate: false`); overflow = `.slide-text` `scrollHeight > clientHeight + 1`, re-checked on update and resize, shown as `.slide-overflow` + title attribute `t.overflowHint`; renders `VideoBlock` under the text when `slide.video`; exposes the editor through `editorRef(slide.id, editor | null)`.
- `VideoBlock({ animation, deckId, onRemove })`: `status === "missing"` → placeholder `t.animationDeleted`; `cut === null` → `t.animationNotReady`; else `<video controls preload="metadata" poster={posterUrl(deckId, project_id)} src={cutUrl(project_id, cut, version)}>` + caption `t.animationCaption(title)` + ✕ (`aria-label t.removeFromSlide`).
- `SlideToolbar({ editor })`: style `<select>` (Title → `setHeading({level: 1})`, Heading → level 2, Body → `setParagraph()`), B/I/U toggles with `aria-pressed`, size buttons (`setFontSize(px + "px")`, `unsetFontSize()` for M), colour swatches (`setColor(hex)`, "default" → `unsetColor()`), highlight toggle, bullets/numbers toggles, align ×3, undo/redo; all `btn-icon`, disabled when `editor` is null; labels from `t.tb.*`.
- Vitest: `vitest.config.ts` with `test: { include: ["lib/**/*.test.ts"], environment: "node" }`.

- [ ] **Step 1: Write failing tests** `lib/slideHtml.test.ts`: `slideTitle('<h1 style="text-align: center">Α &amp; Β</h1><p>x</p>') === "Α & Β"`; `slideTitle("<p>" + "λ".repeat(80) + "</p>") === "λ".repeat(60)`; `slideText("<h1>Τ</h1><ul><li><p>ένα</p></li><li>δύο</li></ul>") === "Τ\n- ένα\n- δύο"`; `slideTitle("") === ""`.
- [ ] **Step 2:** `npm i` deps; `npm test` → fails. **Step 3:** Implement helpers → `npm test` passes. **Step 4:** Implement components; `npm run build && npm run lint`. **Step 5: Commit** — `git commit -m "feat(web): slide theme, TipTap slide editor, toolbar, thumbnails"`

---

### Task 13: Deck workspace — split panes, strip, autosave, title, delete

**Files:**
- Create: `web/lib/useDeckSplit.ts`, `web/lib/useDeckSplit.test.ts`, `web/components/deck/DeckWorkspace.tsx`, `web/components/deck/SlideStrip.tsx`, `web/app/decks/[id]/page.tsx`
- Modify: `web/lib/messages.ts`
- Test: `npm test`, build, lint, screenshots at 1440×900 and 900×900

**Interfaces:**
- `useDeckSplit(): [ratio: number, setRatio: (r: number) => void]` with exported pure `clampRatio(r: number): number` (0.30–0.75) and `readRatio(raw: string | null): number` (default 0.6, NaN → default); persisted under `lara-deck-split`.
- `DeckWorkspace({ deck: Deck }: { deck: Deck })` owns local state `{ title, slides: Slide[], version, animations, chat }`, `activeId`, `selection`, `saveState: "saved" | "dirty" | "saving" | "error"`, `undoSnapshot: Slide[] | null`. Layout: full-bleed (`-mx-4 sm:-mx-6 -my-8 sm:-my-10 h-[calc(100dvh-3.5rem)] flex flex-col`); header row (title: `button` showing `font-serif text-3xl` → inline `input` on click/Enter; subtitle `t.deckMeta(n, m)` "N slides · M animations" where the animations part is `AnimationsMenu` (Task 16); actions right: Create animation, Export (Task 17), Delete `btn-ghost` → `confirm(t.confirmDeleteDeck(title, m))` → `deleteDeck` → `router.push("/")`); body `flex-1 min-h-0 flex` with left pane `style={{ flexBasis: ratio*100 + "%" }}` containing `SlideStrip` (w-40, own scroll) + the editor column (sticky `SlideToolbar` + scrolling list of `SlideEditor`s with `scroll-mt-20` and `id={"slide-" + id}`), the divider (`role="separator" aria-orientation="vertical" aria-valuenow={round(ratio*100)} tabIndex=0`, 8 px wide, `cursor-col-resize`, pointer capture drag, ←/→ ±2 %), and the right pane with `DeckChat` (Task 14). Below `lg`: `flex-col`, divider hidden, panes `min-h-[60dvh]`.
- Autosave: a `useEffect` on `[title, slides]` sets `dirty` and schedules `save()` after 800 ms; `save()` posts `{ title, slides: slides.map(s => ({ id: s.id, html: s.html, video: s.video })), version }`, then adopts `version`/`animations` from the reply and, for slides whose `id` was `null`-ish/new, adopts server ids by position; 409 → `getDeck` → replace local state, notice `t.reloadedNotice`; other errors → `saveState = "error"` + notice `t.saveFailed` with Retry. `flushSave(): Promise<void>` saves immediately if dirty (used by the chat and `beforeunload`). `beforeunload` guard while `saveState !== "saved"`.
- `SlideStrip({ slides, activeId, animations, onSelect, onMove, onAdd, onDelete })`: numbered `SlideThumb`s (`button`), active ring, hover/focus shows ↑ ↓ 🗑 icon buttons (`aria-label`s), drag reorder via pointer events with a drop indicator, `+` at the bottom (`t.addSlide`); deleting shows a 6 s toast `t.slideRemoved` with `t.undo` (restore at the same index). A deck never goes below one slide (delete disabled when `slides.length === 1`).
- Page `app/decks/[id]/page.tsx`: `useParams`, `getDeck` once, loading/error like the project page, `<DeckWorkspace key={deck.id} deck={deck} />`.
- Keys (English; add Greek): `slideN: (n) => "Slide " + n`, `deckMeta: (n, m) => …`, `addSlide: "Add slide"`, `deleteSlide: "Delete slide"`, `moveUp/moveDown`, `slideRemoved: "Slide removed"`, `undo: "Undo"`, `saved: "Saved"`, `saving: "Saving…"`, `unsaved: "Unsaved changes"`, `saveFailed: "Couldn't save your changes — retrying…"`, `retry: "Retry"`, `reloadedNotice: "The slides were changed elsewhere and have been reloaded."`, `overflowHint: "Doesn't fit on the slide — shorten it or ask Lara to split it"`, `confirmDeleteDeck: (title, m) => m ? "Delete the slides “" + title + "”? Its " + m + " animations are kept." : "Delete the slides “" + title + "”?"`, `deleteDeck: "Delete slides"`, `editTitle: "Edit title"`, `resizePanes: "Resize panes"`, `createAnimation: "Create animation"`, `leaveUnsaved: "You have unsaved changes."`, toolbar labels `tb: { style, title, heading, body, bold, italic, underline, size, color, defaultColor, highlight, bullets, numbers, alignLeft, alignCenter, alignRight, undo, redo }`, `animationDeleted`, `animationNotReady`, `animationCaption: (title) => "Animation: " + title`, `removeFromSlide: "Remove from slide"`.

- [ ] **Step 1:** `useDeckSplit.test.ts`: `clampRatio(0.1) === 0.3`, `clampRatio(0.9) === 0.75`, `readRatio(null) === 0.6`, `readRatio("abc") === 0.6`, `readRatio("0.5") === 0.5`. Run → fails; implement; passes.
- [ ] **Step 2:** Implement the workspace, strip and page. `npm run build && npm run lint`.
- [ ] **Step 3:** With both servers running, create a deck through the UI, type in two slides, reorder, delete + undo, resize the divider, reload the page — content persists; `deck.json` on disk shows sanitised HTML. Screenshot desktop and narrow widths; check the toolbar, the active ring, the footer numbers.
- [ ] **Step 4: Commit** — `git commit -m "feat(web): deck workspace with slide strip, autosave and split panes"`

---

### Task 14: Deck chat panel with merge and undo

**Files:**
- Create: `web/lib/deckMerge.ts`, `web/lib/deckMerge.test.ts`, `web/components/deck/DeckChat.tsx`
- Modify: `web/components/deck/DeckWorkspace.tsx` (mount the chat; wire `flushSave`, merge, undo, jump), `web/lib/messages.ts`
- Test: `npm test`, build, lint, live check against the real model

**Interfaces:**
- `deckMerge.mergeChatResult(local: Slide[], result: ChatResult): Slide[]` — order and membership from `result.deck.slides`; a slide keeps the *local* `html` unless its id is in `result.edits` (any op) or it is new; `video` always from the server.
- `DeckChat({ deck, messages, activeSlide, selection, busy, canUndo, onSend, onUndo, onClearSelection, onClearSlide, onJump }: { deck: Deck; messages: ChatMessage[]; activeSlide: { id: string; label: string } | null; selection: string | null; busy: boolean; canUndo: boolean; onSend: (message: string, useSlide: boolean, useSelection: boolean, signal: AbortSignal) => Promise<void>; onUndo: () => void; onClearSelection: () => void; onClearSlide: () => void; onJump: (slideId: string) => void })` — header `t.askLara`; empty state with three suggestion buttons (`t.chatSuggestions: string[]`) that fill the composer; message list (user: `self-end bg-sunken rounded-2xl px-4 py-2 max-w-[85%]`; assistant: `whitespace-pre-wrap`); under an assistant message with edits: chips `t.chip[op](title || t.slideN(n))` → `onJump`, and on the latest one **Undo** (`canUndo`); composer: chips for slide/selection with ✕, textarea (Ctrl/Cmd+Enter), Send `btn-primary`, while busy "Thinking…" (`pulse-soft` dot) and **Stop** (aborts); errors in `.notice-error` under the list; the failed message text stays in the textarea.
- Workspace wiring: `onSend` → `await flushSave()` → `chatDeck(id, { message, slide_id: useSlide ? activeId : null, selection: useSelection ? selection : null }, signal)` → `undoSnapshot = slides` → `slides = mergeChatResult(slides, result)`, `version = result.deck.version`, `chat = result.deck.chat`, `animations = result.deck.animations`; scroll to the first edited slide. `onUndo` → `slides = undoSnapshot; undoSnapshot = null` (autosave persists it). Abort → `ApiError`/`AbortError` is swallowed (no notice).
- Keys: `askLara: "Ask Lara"`, `chatIntro: "Ask a question, or tell Lara what to write or change on the slides."`, `chatPlaceholder: "e.g. Write a slide on the complexity, and make the titles blue"`, `chatSuggestions: ["Draft 8 slides from my material", "Make the titles shorter", "Add a summary slide at the end"]`, `send: "Send"`, `thinking: "Thinking…"`, `stop: "Stop"` (exists), `useSlide: (label) => label`, `useSelection: "Selection"`, `chip: { replace: (s) => "Changed " + s, insert_after: (s) => "Added " + s, delete: (s) => "Removed " + s, move: (s) => "Moved " + s }`, `undoAi: "Undo this change"`.

- [ ] **Step 1:** `deckMerge.test.ts` — `keeps local html of untouched slides` (local slide B edited, result edits only A → B keeps local html, A takes server html); `follows server order and membership` (server deleted C and inserted D after A → `[A, D, B]`, D has server html); `video comes from server`. Run → fails; implement; passes.
- [ ] **Step 2:** Implement `DeckChat` and the wiring; build + lint.
- [ ] **Step 3:** Live: with the real API, ask a question (no edits), ask for a rewrite of the active slide, ask a mixed request; verify chips, Undo, that typing in another slide during the wait survives, Stop works, and the error path shows a notice when the API is down.
- [ ] **Step 4: Commit** — `git commit -m "feat(web): deck chat with structured edits, merge and undo"`

---

### Task 15: Dashboard — decks and animations together

**Files:**
- Create: `web/components/deck/DeckTile.tsx`
- Modify: `web/app/page.tsx` (fetch both lists with `Promise.all`; `type Item = { kind: "project"; p: Project } | { kind: "deck"; d: DeckSummary }` sorted by `created_at` desc; render `ProjectTile` / `DeckTile`; deck delete handler), `web/lib/messages.ts`
- Test: build, lint, screenshot

**Interfaces:**
- `DeckTile({ d, onDelete })`: `Link` to `/decks/${d.id}`; card = `SlideThumb` of `first_slide_html` inside `rounded-xl ring-1 ring-black/5 bg-surface` (paper, not stage), a `Slides` badge top-left (`bg-ink/80 text-white text-xs rounded px-1.5`), title `font-serif text-xl`, status row `t.deckMeta(slide_count, animation_count)` with an accent dot; delete button like `ProjectTile` (`t.deleteDeckLabel(title)`), `confirm(t.confirmDeleteDeck(title, animation_count))`.
- `ProjectTile`: when `p.deck_id` show a `Slides` badge next to the language badge (`title={t.fromSlides}`).
- Empty state copy becomes material-neutral: `emptyTitle: "Start with one concept you teach."` (keep), `emptyBody` → "Make an animated explanation or a deck of slides from your own course material.", `createFirst` → "Create your first material", linking to `/new`. `dashSubtitle` → "Animated explanations and slide decks built from your own course material." `loadError` wording → "Could not load your materials: …".

- [ ] **Step 1:** Implement; build + lint. **Step 2:** Screenshot `/` with at least one deck and one animation. **Step 3: Commit** — `git commit -m "feat(web): dashboard lists slides and animations"`

---

### Task 16: Deck ↔ animation in the web — setup from a deck, Add to slides, animations menu

**Files:**
- Modify: `web/app/new/animation/page.tsx` (`?deck=` → `getDeck`; `MaterialFields` child item "Slides: {title} ({n} slides)" with a film icon, non-removable; hidden `deck_id`; language default = deck language; when `?from=` is a project with `deck_id`, pass it through as well), `web/components/VideoWorkspace.tsx` (aside section "Slides" when `project.deck_id`: `t.partOfSlides`, **Add to slides** `btn-primary` disabled until `preview.version > 0` with `t.addToSlidesHint`, **Back to slides** link → `/decks/${deck_id}`), `web/components/deck/DeckWorkspace.tsx` (header `AnimationsMenu`; **Create animation** → `router.push(/new/animation?deck=${id})` after `flushSave()`; on mount, if `location.hash === "#embedded"` scroll to the last slide with a video)
- Create: `web/components/deck/EmbedDialog.tsx`, `web/components/deck/AnimationsMenu.tsx`
- Test: build, lint, full manual flow

**Interfaces:**
- `EmbedDialog({ project, deckId, onClose })`: modal (`role="dialog" aria-modal`, Escape closes, focus trapped like `NarrationRecorder`), loads `getDeck(deckId)`, lists slides as `SlideThumb`s with a radio per slide (label `slideLabel`), a segmented mode control (`t.embedAppend` "Add to this slide" / `t.embedNewAfter` "New slide after it" / `t.embedNewEnd` "New slide at the end" — the first two disabled until a slide is chosen; `new_end` needs none), a warning `t.embedReplaces` when the chosen slide already has a video and mode is `append`, **Add** → `embedAnimation(deckId, { project_id, slide_id, mode })` → `router.push(/decks/${deckId}#embedded)`.
- `AnimationsMenu({ animations })`: `<details>` whose `<summary>` is the "M animations" text; the list shows each `AnimationRef` as a `Link` to `/projects/${project_id}` with a status dot (`draft` faint / `creating` gold pulse / `ready` manim / `missing` rec) and a film icon when `embedded`; empty → `t.noAnimationsYet`.
- Keys: `partOfSlides: "Part of your slides"`, `addToSlides: "Add to slides"`, `addToSlidesHint: "Available once the animation is ready."`, `backToSlides: "Back to slides"`, `fromSlides: "Made from your slides"`, `slidesMaterial: (title, n) => "Slides: " + title + " (" + n + " slides)"`, `embedTitle: "Where should the animation go?"`, `embedAppend`, `embedNewAfter`, `embedNewEnd`, `embedReplaces: "This slide already has an animation; it will be replaced."`, `embedConfirm: "Add"`, `noAnimationsYet: "No animations yet."`, `animationsCount: (m) => m + " animations"`.

- [ ] **Step 1:** Implement; build + lint.
- [ ] **Step 2:** Manual flow with the real API: deck → Create animation (form shows the slides item, language preselected) → draft, approve, render (or use an existing rendered project and set `deck_id` via the API for speed) → Add to slides → dialog → deck opens scrolled to the video block, which plays; the poster file exists; Remove from slide works; AnimationsMenu lists the project; dashboard shows the badge.
- [ ] **Step 3: Commit** — `git commit -m "feat(web): animations from a deck and embedding them in slides"`

---

### Task 17: Export menu

**Files:**
- Create: `web/components/deck/ExportMenu.tsx`
- Modify: `web/components/deck/DeckWorkspace.tsx`, `web/lib/messages.ts`

**Interfaces:**
- `ExportMenu({ deckId, onBeforeExport, onError })`: `<details>` with `summary.btn.btn-primary` `t.export` and two items `t.exportPdf` ("PDF") / `t.exportWord` ("Word (.docx)"); on click → `await onBeforeExport()` (= `flushSave`) → `exportDeck(id, fmt)` → create `<a href={exportUrl(url)} download={filename}>` and click it; while running the summary shows `t.preparingExport` ("Preparing…") and items are disabled; errors → `onError(message)` shown as a notice under the header. Hint under the items when the deck has embedded animations: `t.exportZipHint` ("Decks with animations download as a .zip with the video files.").

- [ ] **Step 1:** Implement; build + lint. **Step 2:** Export a deck with and without an embedded animation; open the PDF (page count, Greek text, poster) and the .docx in LibreOffice (`soffice --headless --convert-to pdf` to eyeball). **Step 3: Commit** — `git commit -m "feat(web): export slides to PDF and Word"`

---

### Task 18: Polish pass, visual QA, docs

**Files:**
- Modify: `README.md` (Slides section: flow, export behaviour, new routes; prerequisites gain WeasyPrint's Pango/Cairo note — already needed by Manim), `docs/slides/README.md` (status line), any component needing fixes
- Test: everything

- [ ] **Step 1:** Run `cd api && uv run pytest` (including slow) and `cd web && npm run build && npm run lint && npm test`.
- [ ] **Step 2:** Headless Chrome screenshots at 1440×900 and 1024×768 and 390×844 of: `/`, `/new`, `/new/slides`, `/decks/<id>` (with a video block and an overflowing slide), the embed dialog, the export menu open, `/projects/<id>` with the Slides section. Review each PNG for alignment, contrast, truncation, Greek/English copy, focus rings; fix and re-shoot.
- [ ] **Step 3:** Accessibility sweep: every icon button has an `aria-label`; the divider is keyboard-resizable; dialogs trap focus and close on Escape; `aria-live` on the save state and chat errors; reduced-motion respected (`pulse-soft` is already covered).
- [ ] **Step 4:** Manual checklist (both languages): create deck → type, format with every toolbar control → chat question → chat edit → undo → reorder/add/delete slides → export PDF/Word → create animation → add to slides → export zip → delete deck (animation kept, badge gone) → delete animation (placeholder in deck, export skips it).
- [ ] **Step 5:** Update the README and commit — `git commit -m "docs: Lara Slides in README; polish"`.

---

## Self-review notes

- **Spec coverage**: §2 screens → Tasks 10, 11, 13–17; §3 contract → Tasks 1, 8, 12; §4 model/store/saving → Tasks 2, 3, 13; §5 editor → Tasks 12, 13; §6 chat → Tasks 5, 6, 14; §7 handoff → Tasks 4, 7, 16; §8 exports → Tasks 8, 9, 17; §9 API → Tasks 3–9; §10 web files → Tasks 10–17; §11 errors → covered inside each task (409 reload, save retry, chat 422/502/499, export 502, embed 409); §12 testing → every task plus Task 18.
- **Type consistency**: `AnimationRef` fields (`project_id, title, status, cut, version, duration, embedded`) are used identically in Tasks 3, 7, 8, 9, 11, 12, 16; `ChatResult`/`DeckChatResult` carry `deck, reply, edits`; `EditLog.slide_id` is what `mergeChatResult` and the chips read; `render_pdf`/`render_docx` share `(deck, animations, posters, video_files)`.
- **Review Focus tests** are pinned in Tasks 1, 3, 5, 9, 14.
