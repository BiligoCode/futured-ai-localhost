# Lara Slides — AI-assisted slide editor (Design)

Date: 2026-10-01
Status: Approved for implementation (decisions taken in conversation on 2026-10-01)

## 1. Context & intent

Lara today makes one kind of material: a narrated Manim **animation** (Setup → Script → Video). Professors also
need the written material around it. This spec adds a second material type, **Slides**: a deck of 16:9 slides the
professor writes in a rich-text editor while an AI assistant sits beside it. The assistant answers questions,
writes or corrects slide text, and changes formatting — in any mix, from one message. A deck can spawn
animations through the existing flow and embed them, and exports to **PDF** and **Word**.

What the professor said they want (verbatim intent, condensed):

- First choose the material type: *Animation* (today's workflow, unchanged) or *Slides*.
- Slides: a screen split in two with an adjustable divider. Left: a real text editor for the slides with basic
  formatting (bold, italic, size…) that shows the slides as they will look. Right: a chat where the AI can
  (1) answer questions / give ideas, (2) edit the text on the left, (3) change the formatting on the left — and a
  single prompt may ask for all three, the AI deciding how to handle it.
- When done: export to Word or PDF, or **Create animation** → the existing animation flow with the deck attached
  as material. When the animation is finished, the professor is asked where to put it in the deck as an embedded
  video. Repeat for more animations, or export.
- Both the deck and every animation are saved as materials in the app. Polished, tested, Greek and English.

### Decisions taken (with the professor)

| Question | Decision |
|---|---|
| Export formats | **PDF + Word only.** Neither format can play an embedded video (PDF rich media works only in Acrobat; Word has no portable local-video embedding). Embedded animations therefore export as a **poster frame + the file name/link**, and when a deck has embedded animations the export is a **.zip** with the document plus the MP4 files in an `animations/` folder. |
| Slide shape | **Fixed 16:9 slides** (1280×720 CSS px = PowerPoint's 13.333″×7.5″). The editor warns when text overflows; the AI can split slides. PDF = one slide per landscape page; Word = one slide per page. |
| How a deck starts | **Short setup, then editor**: title, language (ΕΛ/EN), optional course material (PDFs / pasted text). The editor opens with one title slide; the AI knows the material. |
| Pictures | **Not in v1.** Text formatting and embedded animations only. |
| Document representation | **HTML per slide, AI replaces whole slides** (approach A below). |

### Evaluation: "AI decides" vs. mode selector, and Amazon Bedrock AgentCore

- **One prompt, three jobs — feasible without modes.** One LLM call returns structured JSON:
  `{"reply": "...", "edits": [...]}`. Questions are answered in `reply`; text *and* formatting changes are
  `edits` that carry the full new HTML of the affected slides. A mixed request simply yields both. This is the
  pattern Lara already uses for whole-video change requests (`api/app/revise.py`: JSON → pydantic → retry with
  "your previous reply was not valid"), and it is model-agnostic (the hackathon account only has GLM‑5 / DeepSeek).
- **Agent / Plan / Ask buttons are not needed.** Coding tools need them because edits are expensive and risky;
  here an edit is one slide's HTML, visible instantly and undoable. The professor keeps a lighter control: the
  current slide and any selected text are attached to the message as hints (like the paused-player timestamp in
  the video workspace) and can be removed with one click.
- **Amazon Bedrock AgentCore: no.** AgentCore is infrastructure for *hosting and operating* agents (Runtime,
  Memory, Gateway→MCP tools, Identity, Observability, Browser, Code Interpreter). It does not make a model better
  at deciding what to do; it adds deployment, latency and cost, and Lara already calls Bedrock Converse directly.
  The "deciding" lives in the prompt and the structured output. If the assistant ever becomes a long-running
  multi-tool agent, AgentCore is where it would be hosted — not now.

### Approaches considered for the document model

- **A. HTML per slide, whole-slide edits (chosen).** Each slide stores a small whitelisted HTML fragment that TipTap
  reads/writes natively, the sanitiser validates, and both exporters consume. The AI returns the full new HTML of a
  slide it changes. One mechanism for text and formatting; models are very good at HTML; validation is easy.
  Cost: a one-word change re-emits one slide (~200–600 chars) — negligible.
- **B. ProseMirror JSON + fine-grained operations.** Minimal edits, but models are far less reliable emitting
  ProseMirror JSON and addressing ranges; many more failure modes. Rejected.
- **C. Markdown per slide.** Most LLM-friendly text format, but no colour, size, underline or alignment; would need
  custom syntax parsed on both sides. Rejected.

### Out of scope (v1)

Pictures, tables, speaker notes, slide themes/backgrounds, LaTeX math (Unicode math only), streaming replies,
real-time collaboration, PowerPoint export, auth/multi-user.

## 2. User flow & screens

```
/                   dashboard: decks and animations together (newest first)
/new                chooser: Animation | Slides
/new/animation      the existing setup form (moved; ?from=<project> redraft, ?deck=<deck> animation from a deck)
/new/slides         deck setup: title, language, optional PDFs / pasted text  → POST /decks → /decks/<id>
/decks/[id]         deck workspace (split screen)
/projects/[id]      unchanged, plus for deck-linked projects: "Add to slides" → embed dialog → back to /decks/<id>
```

**Header** button becomes "New material" (ΕΛ: "Νέο υλικό") → `/new`. Dashboard heading becomes "Your materials"
(ΕΛ: "Το υλικό σας").

**Chooser (`/new`)**: two large cards. *Animation* — dark stage card with the curve sketch: "Lara drafts a script,
renders a Manim animation and narrates it." *Slides* — paper card with a small slide drawing: "Write lecture slides
with an AI assistant; embed your animations; export PDF or Word."

**Deck setup (`/new/slides`)**: title (required, large serif field like the concept field), language segmented
control (default = interface language), the same PDF picker + paste textarea as the animation setup (extracted into
a shared `MaterialFields` component). Submit → "Creating…" → `/decks/<id>`.

**Deck workspace (`/decks/[id]`)**

```
┌ title (click to edit) · "N slides · ΕΛ"          [Create animation] [Export ▾] [Delete] ┐
├──────────────────────────────────────┬─╫─┬──────────────────────────────────────────────┤
│ strip │ slide 1  (16:9 card)         │ ║ │ Ask Lara                                      │
│ ▣     │ ─────────────────────────────│ ║ │  ┌ assistant / professor messages ┐           │
│ ▢     │ slide 2                      │ ║ │  │ chips: "Changed slide 3" [Undo] │          │
│ ▢ +   │ …  (toolbar floats above     │ ║ │  └─────────────────────────────────┘          │
│       │     the active slide)        │ ║ │  [Slide 3 ×] [Selection “…” ×]                 │
│       │                              │ ║ │  ┌ message …                     ┐ [Send]      │
└───────┴──────────────────────────────┴─╫─┴──────────────────────────────────────────────┘
```

- The divider is draggable (pointer events; keyboard arrows when focused); the left pane width is stored in
  `localStorage` (`lara-deck-split`, 30–75 %). Below `lg` the panes stack vertically (editor, then chat).
- The workspace uses the full viewport width: the root layout's `main` loses `max-w-6xl`, and the existing pages
  wrap their content in `mx-auto max-w-6xl` instead.
- The deck page is the only page where the big panel fills the viewport height
  (`h-[calc(100dvh-<header>)]`); each pane scrolls on its own.
- The header subtitle "N slides · M animations" — "M animations" opens a small popover listing the deck's
  animations (title, status dot: draft / creating / ready; film icon when embedded), each linking to its project
  page where **Add to slides** lives. This is how a professor who left the animation flow without embedding
  comes back to it.

**Dashboard**: `GET /projects` and `GET /decks` in parallel, merged by `created_at`. Deck tile: a paper-coloured
16:9 card with the first slide rendered small (read-only `SlideThumb`), a "Slides" badge, title, and the status row
"N slides · M animations". Animation tiles created from a deck show a small "Slides" badge beside the language.
Delete on a deck tile: `confirm("Delete the slides “X”? Its N animations are kept.")`.

**Project page**: when `project.deck_id` is set, the aside gets a "Slides" section: "Part of your slides" with
**Add to slides** (enabled once a preview exists; uses the narrated cut when there is one) and a **Back to slides**
link. The Stepper's step 1 and "Back to setup" go to `/new/animation?from=<id>`.

**Add to slides dialog** (`EmbedDialog`, modal like `NarrationRecorder`): the deck's slides as a vertical list of
thumbnails with radio selection; mode: *Add to this slide* / *New slide after this one* / *New slide at the end*.
If the chosen slide already has an animation the dialog says it will be replaced. Confirm → `POST /decks/{id}/embed`
→ `router.push(/decks/<id>)`, where the new block is scrolled into view.

## 3. Slide format (the contract everything shares)

A slide is **1280×720 px** with padding `64px 72px 56px`, white background, a footer (deck title left, `n / total`
right, 16 px, faint). Typography: titles in STIX Two Text (serif), body in Commissioner (sans) — Lara's own fonts.

**HTML whitelist** (sanitiser, TipTap schema and both exporters agree on exactly this):

| Allowed | Notes |
|---|---|
| `h1` | Slide title, 56 px serif 600. At most one per slide (the sanitiser does not enforce; the prompt asks). |
| `h2` | Heading, 40 px serif 600 |
| `p` | Body, 26 px, line-height 1.35 |
| `ul`, `ol`, `li` | Markers in accent colour. TipTap emits `<li><p>…</p></li>`; the AI may emit `<li>…</li>`. Both are valid; `.slide li p { margin: 0 }`. |
| `strong`, `em`, `u`, `mark` | `mark` = highlight `#fff3b0` |
| `span style="color: #rrggbb"` | Palette (also any valid 6-digit hex) |
| `span style="font-size: NNpx"` | 12–96; the toolbar offers S 20 · M 26 · L 34 · XL 44 |
| `style="text-align: left|center|right"` | On `h1 h2 p li` |
| `br` | |

Everything else is removed: unknown tags are unwrapped (their text kept), `script`/`style` are dropped with
content, unknown attributes and style properties are dropped. Text is HTML-escaped on output. A slide's HTML is
capped at 20,000 characters (422 `"Slide is too long"`).

Palette (chosen for contrast on white): ink `#18212e`, muted `#566173`, accent `#1b6f8c`, green `#0f7b6c`,
gold `#74490a`, red `#c93838`, purple `#6d3fb8`, amber `#e2a13b`.

**Embedded animation**: a slide has at most one, stored as `slide.video = <project_id>`, rendered as a block
*below* the text: a `<video controls poster=…>` in the editor (max height 400 px, dark background, 8 px radius,
caption "Animation: <project title>"), and as the poster image + caption in exports. The block is not part of the
HTML; it is a separate field, so the AI never sees or edits it.

**Canonical stylesheet** `slide.css` lives in `api/app/assets/slide.css` (used by the PDF) with a twin in
`web/app/slide.css` (used by the editor and thumbnails); both carry a header comment naming the other. Both use the
same 1280×720 px coordinate system; the editor scales the slide with `transform: scale()` to the pane width.

## 4. Data model & storage

```
data/decks/<deck_id>/              deck_id = uuid4().hex[:10]
  deck.json                        Deck (atomic write via .json.tmp + os.replace, like project.json)
  material.txt                     extracted PDFs + pasted text (ingest.build_material, 60k cap; may be "")
  posters/<project_id>.jpg         poster frame of an embedded animation (640×360, frame at min(30 %, 8 s))
  export/deck.pdf | deck.docx | deck-pdf.zip | deck-docx.zip     regenerated on every export
```

```python
class Slide(BaseModel):
    id: str                          # uuid4().hex[:8]
    html: str = ""                   # sanitised fragment (whitelist above)
    video: str | None = None         # project_id of the embedded animation

class EditLog(BaseModel):            # what an assistant message changed (for the chips)
    op: Literal["replace", "insert_after", "delete", "move"]
    slide_id: str
    title: str                       # slide title at the time, or "" (UI shows "Slide N")

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    edits: list[EditLog] = []
    at: datetime

class Deck(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    title: str
    language: Language
    slides: list[Slide]
    chat: list[ChatMessage] = []     # last 50 kept
    version: int = 1                 # +1 on every save; clients send it back

class AnimationRef(BaseModel):       # computed per response, never stored
    project_id: str
    title: str
    status: Literal["draft", "creating", "ready", "missing"]   # script stage / no preview yet / preview exists / project deleted
    cut: CutKind | None              # "final" if narrated, else "preview", None if no video yet
    version: int
    duration: float
    embedded: bool                   # referenced by some slide.video

class DeckView(Deck):
    animations: list[AnimationRef]   # projects with deck_id == id ∪ projects referenced by slide.video, newest first

class DeckSummary(BaseModel):        # dashboard
    id, created_at, updated_at, title, language
    slide_count: int
    animation_count: int             # projects with deck_id == id
    first_slide_html: str

class SlideIn(BaseModel):  id: str | None = None; html: str = ""; video: str | None = None
class DeckUpdate(BaseModel):  title: str = Field(min_length=1); slides: list[SlideIn] = Field(min_length=1); version: int
class DeckChatRequest(BaseModel):  message: str = Field(min_length=1); slide_id: str | None = None; selection: str | None = None
class DeckChatResult(BaseModel):  deck: DeckView; reply: str; edits: list[EditLog]
class EmbedRequest(BaseModel):  project_id: str; slide_id: str | None = None; mode: Literal["append", "new_after", "new_end"]
class ExportRequest(BaseModel):  format: Literal["pdf", "docx"]
class ExportResult(BaseModel):  url: str; filename: str
```

`Project` gains `deck_id: str | None = None`.

`DeckStore` (`api/app/deck_store.py`) mirrors `ProjectStore`: `create(title, language, material_text)` (one slide
`<h1>{title}</h1>`), `get` (raises `DeckNotFound` → 404 "Slides not found"), `list` newest first, `material`,
`save` (bumps `version` and `updated_at`), `async mutate(id, fn)` under a per-id `asyncio.Lock`, `async delete`.

**Saving from the editor**: autosave `PUT /decks/{id}` 800 ms after the last change (also on blur and before
leaving the page; `beforeunload` guard while dirty). The server sanitises every slide, assigns ids to new slides,
checks `version` (mismatch → 409 `"The slides were changed elsewhere"`; the editor reloads the deck and shows a
notice), bumps the version and returns the `DeckView`. Simple optimistic concurrency, no OT/CRDT.

## 5. Editor (left pane)

- **TipTap v3** (`@tiptap/react`, `@tiptap/pm`, `@tiptap/starter-kit`, `@tiptap/extension-text-style` with its
  `color` and `font-size` sub-exports, `@tiptap/extension-highlight`, `@tiptap/extension-text-align`). StarterKit is
  configured to heading levels `[1, 2]` and with `strike`, `code`, `codeBlock`, `blockquote`, `horizontalRule` and
  `link` disabled, so the schema equals the whitelist; pasted content is normalised by the schema. `immediatelyRender:
  false` (Next.js). These are the only new web dependencies.
- **One editor instance per slide** (`SlideEditor`). Clean HTML boundaries, per-slide overflow detection, and the AI
  can replace one slide (`editor.commands.setContent(html)`) without disturbing the cursor in another.
- **Overflow**: the slide body has a fixed height; when `scrollHeight > clientHeight` a thin red rule appears at the
  bottom edge with the hint "Doesn't fit on the slide — shorten it or ask Lara to split it". Nothing is clipped in
  the editor; exports clip at the frame.
- **Toolbar** (floats above the active slide, sticky inside the pane): style select (Title / Heading / Body),
  B · I · U, size (S M L XL), colour (8 swatches + "default"), highlight, bullets, numbers, align left/centre/right,
  undo, redo. Keyboard: Ctrl/Cmd+B/I/U, Ctrl/Cmd+Z/Shift+Z (TipTap history).
- **Slide strip** (left edge of the pane): numbered thumbnails (`SlideThumb`, read-only scaled render of the HTML +
  a film icon when the slide has a video), click to scroll to/activate a slide, drag to reorder (pointer-based, with
  keyboard alternative: ↑/↓ buttons on hover/focus), **+** to add a slide after the active one, delete with a 6 s
  **Undo** toast (like the script editor's remove+undo). A deck always has at least one slide.
- **Active slide**: the one whose editor has focus or was last clicked in the strip. It drives the toolbar and the
  chat's "Slide N" chip; selected text (trimmed, ≤ 500 chars) becomes the "Selection" chip.
- **Video block** (`VideoBlock`, rendered by `SlideEditor` under the editor, not a ProseMirror node): `<video
  controls>` with the poster, caption "Animation: <title>", ✕ to remove it from the slide (does not delete the
  animation). When the project was deleted: a muted placeholder "Animation deleted" with ✕.
- **Title**: click the deck title in the header to edit inline (Enter/blur saves through the same autosave).

## 6. Chat & the AI contract (right pane)

**UI**: header "Ask Lara"; message list (professor messages right-aligned on `sunken`, assistant messages plain,
`whitespace-pre-wrap`); under an assistant message that edited slides, chips "Changed slide 3", "Added slide 4",
"Removed slide 5", "Moved slide 2" (click a chip → scroll to that slide) and an **Undo** button on the *latest*
assistant edit; composer with the context chips, a textarea (Ctrl/Cmd+Enter sends), **Send**, and while waiting a
pulsing "Thinking…" with **Stop** (AbortController). Empty state shows three suggestions: "Draft 8 slides from my
material", "Make the titles shorter", "Add a summary slide at the end" (localised).

**Request**: before sending, the client flushes any pending autosave (awaits the PUT), then
`POST /decks/{id}/chat {message, slide_id?, selection?}`. The editor stays editable while waiting.

**Prompt** (`api/app/deck_chat.py`). System prompt (English, `{language}` = Greek/English):

> You are Lara, an assistant to a university professor who is writing lecture slides. You see the whole deck as
> numbered slides written in a small HTML subset. The professor chats with you to (1) ask questions or for ideas,
> (2) have you write or correct slide text, (3) have you change the formatting. One message may ask for several of
> these; do all of them.
> Reply with only a JSON object: `{"reply": "<plain text, short>", "edits": [ {"op":"replace","slide":"<id>","html":"<full new html>"}, {"op":"insert_after","slide":"<id>|null","html":"…"}, {"op":"delete","slide":"<id>"}, {"op":"move","slide":"<id>","after":"<id>|null"} ]}` — `null` means "at the beginning of the deck". Edits are applied in order; several `insert_after` edits naming the same slide are placed one after another in the order given (so "insert A after s3, insert B after s3" yields s3, A, B).
> Slide HTML rules: allowed tags h1 h2 p ul ol li strong em u mark span br; alignment `style="text-align: center"`
> on h1/h2/p/li; colour `<span style="color: #1b6f8c">`; size `<span style="font-size: 34px">` (body is 26px; 20
> small, 34 large, 44 extra large); palette …; at most one h1 per slide (its title), h2 for sub-headings. A slide is
> 1280×720 px with 64 px padding: about 7 lines of body text, or a title and about 5 lines. Split content over
> several slides rather than overflowing. Keep everything the professor did not ask to change exactly as it is
> (same text, same formatting); never touch slides the professor did not ask about. Mathematics in Unicode (x², Σ,
> √); there is no LaTeX. The slides are written in {language}: all slide text you write must be in {language}.
> The professor may write in any language; answer in the language of the professor's message. When the professor
> only asks a question, "edits" is an empty list. When you edit, say briefly in "reply" what you changed.

User message: deck title; `Course material (excerpt):` first 12,000 chars of `material.txt` if any; `Slides:` as
`[<id>] <html>` lines; `Earlier in this conversation:` the last 10 messages as a transcript (`Professor:` /
`Lara:` + "(changed slides …)"), each truncated to 600 chars; `The professor is looking at slide [<id>].` and
`Selected text on that slide: "…"` when given; finally `Professor: <message>`. History goes *inside* the single user
turn so the JSON-only contract is never diluted by plain-text assistant turns.

**Validation & apply** (same shape as `revise.py`): `extract_json` → `_ChatReply` (pydantic; ≤ 40 edits) → apply
ops in order to a copy of the slides: `replace`/`insert_after` sanitise `html` and require non-empty text; unknown
slide ids, deleting the only remaining slide, or moving a slide after itself are errors. The text of all inserted/replaced
slides is checked with `storyboard.check_language` when it has ≥ 40 letters. Any error → one retry with
"Your previous reply was not valid: … Reply with only the JSON." (2 attempts total) → `DeckChatError` → 422
`"The AI reply could not be applied. Please try again."`. LLM/network errors → 502 `"The AI model request failed: …"`
(existing prefix). On success the deck is mutated (slides, `chat` += user + assistant message with `EditLog`s,
trimmed to 50, version +1) and `DeckChatResult` returned. The LLM call runs in `asyncio.to_thread`. If the
professor pressed **Stop** (the request is disconnected when the model answers), nothing is applied and the route
returns 499 `"Cancelled"`, like a cancelled script draft.

**Merging on the client**: the result's slide list defines order and membership; for each slide, if it is in the
reply's `edits` its HTML replaces the editor content, otherwise the professor's local HTML is kept (they may have
typed while waiting); the local `version` is set to the result's. The next autosave then persists any local edits.

**Undo**: before merging, the client snapshots `slides`; the latest assistant message's **Undo** restores the
snapshot (ids, order, HTML, videos) and saves. Only the most recent AI edit is undoable this way (editor-level
Ctrl+Z also works per slide).

## 7. Deck ↔ animation

- **Create animation** (deck header) → `/new/animation?deck=<id>`. The form loads the deck, defaults the language
  to the deck's, shows a non-removable material item "Slides: <title> (N slides)" above the PDF picker, and submits a
  hidden `deck_id`. `POST /projects` accepts `deck_id`: the API loads the deck, renders its text
  (`Lecture slides: <title>\n\nSlide 1: <title>\n<text>\n\n…`) as the first part of the material (then PDFs, then
  pasted text; 60k cap), and stores `project.deck_id`. Setting up again from the project (`?from=`) keeps `deck_id`.
- **Add to slides** (project page, `deck_id` set, preview ready) → `EmbedDialog` → `POST /decks/{id}/embed`.
  Server: 404 if the project is missing, 409 `"The animation is not ready yet"` if `preview.version == 0`; picks
  `final` if `final.version > 0` else `preview`; writes the poster with ffmpeg (`media.make_poster`, in a thread);
  mutates the deck: `append` → `slide.video = project_id` (replacing any existing); `new_after` → new slide
  `<h2>{project.title}</h2>` + video after `slide_id`; `new_end` → same, appended. Returns `DeckView`.
- `DeckView.animations` is computed on every deck read from the linked projects, so the editor always plays the
  current cut (`cutUrl(project_id, cut, version)`), and posters are served from `GET /decks/{id}/posters/{project_id}.jpg`.
- Deleting a **project** leaves `slide.video` dangling → `AnimationRef.status = "missing"` → placeholder in the
  editor, skipped in exports. Deleting a **deck** keeps its animations and clears `deck_id` on them.

## 8. Exports

`POST /decks/{id}/export {format}` builds synchronously in a thread (1–5 s) and returns `{url, filename}`;
`GET /decks/{id}/export/{file}` serves it (`FileResponse`, download name `<title>.pdf|docx|zip`). When at least one
embedded animation has a video, the result is `deck-<format>.zip` containing the document and
`animations/<n>-<project title>.mp4` (copied from `export.mp4`/`preview.mp4`); otherwise the bare document.

**PDF** (`api/app/slides_pdf.py`, WeasyPrint 70 — verified to render Greek here; needs Pango/Cairo, which Manim
already requires): `@page { size: 1280px 720px; margin: 0 }`, `slide.css`, `@font-face` for STIX Two Text and
Commissioner from `api/app/assets/fonts/*.ttf` (OFL; DejaVu fallback), one `<section class="slide">` per slide
with the body, the poster figure (`<a href="animations/…mp4"><img></a>` + caption naming the file) and the footer.

**Word** (`api/app/slides_docx.py`, python-docx): landscape 13.333″×7.5″, margins 0.67″; one slide per page (page
break between); `h1` → 36 pt Cambria bold, `h2` → 28 pt Cambria, `p`/`li` → 18 pt Calibri (fonts that exist on every
Word install), lists via `List Bullet`/`List Number`, `strong/em/u/mark` → run bold/italic/underline/highlight,
`span color` → run colour, `span font-size` → pt = round(px × 0.7) (20→14, 26→18, 34→24, 44→31), `text-align` → paragraph alignment, poster →
picture 7″ wide + a hyperlink paragraph "▶ Animation: <title> (animations/<file>)", footer = deck title + page number.

## 9. API summary

New router `api/app/routes/decks.py`:

| Method | Path | Body / result |
|---|---|---|
| POST | `/decks` | multipart `title`, `language`, `material_text`, `files[]` → `DeckView` (422 on unreadable PDFs, as for projects) |
| GET | `/decks` | `list[DeckSummary]` |
| GET | `/decks/{id}` | `DeckView` |
| PUT | `/decks/{id}` | `DeckUpdate` → `DeckView` (409 version) |
| DELETE | `/decks/{id}` | 204; clears `deck_id` on linked projects |
| GET | `/decks/{id}/material` | text/plain |
| POST | `/decks/{id}/chat` | `DeckChatRequest` → `DeckChatResult` (422 / 502) |
| POST | `/decks/{id}/embed` | `EmbedRequest` → `DeckView` (404 / 409) |
| GET | `/decks/{id}/posters/{project_id}.jpg` | image/jpeg |
| POST | `/decks/{id}/export` | `ExportRequest` → `ExportResult` (502 `"Export failed: …"`) |
| GET | `/decks/{id}/export/{file}` | the file |

Changed: `POST /projects` accepts `deck_id`; `Project.deck_id`. `main.py` registers `DeckStore` as
`app.state.decks`, the router, and a `DeckNotFound` handler. New i18n entries in `api/app/i18n.py`:
"Slides not found", "The slides were changed elsewhere", "The AI reply could not be applied. Please try again.",
"The animation is not ready yet", "Slide is too long", "This slide does not exist".

## 10. Web summary

```
app/layout.tsx                 main without max-width; header button → /new "New material"
app/page.tsx                   dashboard: decks + projects, DeckTile
app/new/page.tsx               chooser
app/new/animation/page.tsx     SetupForm (moved) + ?deck= material item + deck_id
app/new/slides/page.tsx        deck setup
app/decks/[id]/page.tsx        DeckWorkspace
app/slide.css                  slide theme (twin of api/app/assets/slide.css), imported from globals.css
components/MaterialFields.tsx  PDF picker + paste textarea (extracted from the setup form)
components/deck/DeckWorkspace.tsx  header, split panes, divider, autosave, merge/undo, export menu
components/deck/SlideEditor.tsx    TipTap per slide, overflow, video block
components/deck/SlideToolbar.tsx
components/deck/SlideStrip.tsx     thumbnails, reorder, add, delete+undo
components/deck/SlideThumb.tsx     read-only scaled slide (dashboard, strip, embed dialog)
components/deck/VideoBlock.tsx
components/deck/DeckChat.tsx
components/deck/EmbedDialog.tsx    used by VideoWorkspace
components/Icon.tsx                new glyphs
lib/types.ts, lib/api.ts, lib/messages.ts   deck types, calls, strings (en + el)
lib/slideHtml.ts               slideTitle(html), slideText(html), palette, SLIDE_W/H
lib/useDeckSplit.ts            divider state in localStorage
```

## 11. Error handling

- Every API error is an English sentence translated by the existing `i18n` layer; the web shows it in a `.notice-error`.
- Autosave failure: a persistent notice "Couldn't save your changes — retrying…" with a Retry button; the editor stays
  usable; the `beforeunload` guard stays on while unsaved.
- 409 on save: reload the deck from the server, replace editor contents, notice "The slides were changed elsewhere
  and have been reloaded."
- Chat failure (422/502/network): the professor's message stays in the composer; the error shows under the
  message list; nothing in the deck changes.
- Export failure: notice under the header with the server's message.
- Embed when the project has no video: the button is disabled with a hint; the server also enforces 409.
- Server restart: decks are plain files; nothing to recover.

## 12. Testing

API (`uv run pytest -m "not slow"` must stay green after every task):

- `test_slides_html.py` — sanitiser (whitelist, unwrap, script removal, style filtering, escaping, cap),
  `slide_text`, `slide_title`, `deck_material_text`.
- `test_deck_store.py` — create/get/list/save/version/updated_at/delete, atomic write, bad ids.
- `test_api_decks.py` — create with PDFs (reportlab `make_pdf`) / pasted text / nothing, list summaries, get view,
  PUT sanitises + assigns ids + 409, DELETE clears `deck_id` on projects, material endpoint, 404 translated to Greek.
- `test_deck_chat.py` — prompt contains slide ids/material/history/selection; apply each op; invalid JSON → retry →
  422; unknown slide → retry; language check; question-only reply; `EditLog` titles; chat trimmed to 50.
- `test_api_embed.py` — all modes, replace existing, 409 not ready, 404 project; poster via an injected
  `make_poster` (real ffmpeg version marked `slow`).
- `test_slides_export.py` — PDF has N pages (pypdf), Greek text extractable; DOCX paragraphs/runs carry
  bold/italic/colour/alignment/list styles; zip contains document + MP4s when animations exist; route + GET.
- `test_api_projects.py` — `deck_id` stored; material starts with the deck text.

Web: `npm run build && npm run lint` after every task; headless Chrome screenshots (`google-chrome --headless
--screenshot`) of the chooser, deck setup, workspace (desktop + narrow), embed dialog and dashboard, reviewed
visually; a manual checklist (typing, toolbar, reorder, chat edit + undo, export, create animation → add to slides).

Prompt quality: a throwaway script runs the real Bedrock model against a sample Greek deck with mixed requests
(question + rewrite + formatting) to tune the system prompt before the UI work is finished.
