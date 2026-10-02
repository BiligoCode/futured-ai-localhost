# Lara — Learning Assessment & Resource Automation

Teaching material and the grading of exams, in Greek and English, from one dashboard (**Overview**, **Animations**,
**Slides**, **Assessments** in the sidebar):

- **Animation** — name a concept (optionally with your course material), and Lara drafts a script, writes and
  renders a [Manim](https://www.manim.community/) animation for it, and narrates it with an AI voice or your own voice.
- **Slides** — write 16:9 lecture slides in a rich-text editor with Lara beside you in a chat: ask questions, have
  her write or correct text, change the formatting — in any mix, from one message. Embed your animations, export
  to PDF or Word.
- **Assessments** — upload the students' exam papers or projects (scanned or typed PDFs, photos). Lara reads them,
  grades questions with a definitive answer exactly, suggests marks and feedback for open questions, summarises each
  paper and the class, and reports copying, AI-use and document signals for you to review.

**New** opens the chooser between the three. The **Overview** shows counts, what is in progress and the newest work.

## Animation

**Flow:** Setup (concept, optional material, style & tone, length) → Script (edit / reorder / approve) → one video.
The professor only ever sees a single video:

- **Ask for a change** in plain words ("when the array gets iterated…", "at 0:32 …"). Lara works out which
  part of the video is meant (using timestamps and the paused player position as hints) and changes its
  animation, its narration, or both. Only that part is re-rendered and re-encoded.
- **Record your voice** over the whole animation. Pause the animation at any moment to explain longer
  (Space); the pause is kept in the final video as a held frame. Re-record from any point later.
- **AI voice** narrates the whole script instead. With **Captions** on, the AI narration is burned into the
  video as captions, timed from ElevenLabs' character timestamps. Every animation keeps the bottom strip of the
  frame free for them (a codegen rule the layout gate enforces).

**No material?** Lecture notes, slides and pasted text are optional. Without them the model teaches the concept
from its own knowledge (standard notation, a textbook worked example); uploaded PDFs with no readable text are
still rejected.

**Stop and delete.** **Stop** halts everything being generated for a video (scene renders, AI narration);
finished parts are kept and **Continue** picks up the rest. **Cancel** on the setup form abandons a script that is
still being drafted. **Delete** (on the video page, or the bin on its tile) removes a video and all its files.

**Going back a step.** From the video, **Back to script** (or the Script step) reopens the script editor:
running work stops, finished parts are kept, and on approval only parts whose picture or title changed are
animated again (edited narration drops just that part's AI voice). From the script, **Back to setup** opens the
setup form filled in with the concept, style, length, language and material text; drafting again replaces the
old script and video.

**Languages.** The interface is in Greek (default) or English, switched top right (stored in the `lara-lang`
cookie; the API translates its messages from the `X-Lara-Lang` header). The *video's* language is only the one
selected in the setup form: drafts written in another language or script are rejected and redone.

**Layout quality gate.** Every render runs through `app/manim_runner.py`, which checks the frame after each
animation for text drawn on top of other text, text cut off by the frame edge, and unreadably small text.
Problems go back to the model with coordinates (like a crash would) for up to two fixes; if they persist,
the cleanest render is kept and the remaining issues are stored on the scene (`layout_issues`).

## Slides

**Flow:** Title, language, optional material → the workspace: slides on the left (a strip of thumbnails, the
formatting toolbar, one editable 16:9 slide after another), the chat on the right, a draggable divider between them.
Everything autosaves.

- **Writing.** Titles, headings and body text; bold, italic, underline, highlight; four sizes; eight colours; bullet
  and numbered lists; alignment. A slide that no longer fits its frame gets a red rule and a hint (exports clip at the
  frame). Add, reorder and delete slides from the strip (delete has an undo).
- **Ask Lara.** One message can ask a question, ask for text and ask for formatting at once; Lara answers in the chat
  and applies the changes, listing them as chips ("Changed slide 3", "Added Summary") with an undo. The current
  slide and any selected text are attached as hints and can be removed with one click. Slide text is written in the
  deck's language; she answers in the language you write in. Under the hood it is one model call returning
  `{reply, edits}` JSON, where each edit carries the full new HTML of a slide (a small whitelist the sanitiser,
  the editor and the exporters share — see `docs/slides/`).
- **Animations.** **Create animation** opens the animation setup with the deck attached as material; the project
  remembers its deck. When the video is ready, **Add to slides** on the project page puts it on a slide (or on a new
  slide) as an embedded video with a poster frame. The deck header lists all its animations.
- **Export.** PDF (WeasyPrint, Lara's own fonts, one slide per page) or Word (one slide per page, Cambria/Calibri,
  editable). Neither format can play a video, so a deck with embedded animations downloads as a **.zip** holding the
  document and the MP4 files; the document shows a still of each animation with its file name.

```
data/decks/<id>/deck.json      slides (HTML), chat history, version
data/decks/<id>/material.txt   the professor's material
data/decks/<id>/posters/       stills of embedded animations
data/decks/<id>/export/        the last PDF / Word / zip
```

## Assessments

**Flow:** Setup (title, course, feedback language, grade scale 0–10/0–20/0–100, the exam paper with its answer key —
optional, typed or scanned — grading instructions, and the papers: one file per student, or one batch PDF split every
N pages) → Lara reads the papers right away and drafts the **rubric** (questions, points, keys, criteria for open
questions) from the exam paper, or from the first papers when there is none → you check the rubric and **Save &
grade** → marks, summaries and the class analysis.

- **Reading.** Typed pages are read from their visible text; scanned pages by a vision model
  (`AWS_BEDROCK_VISION_MODEL`, Qwen3-VL) that only transcribes — never judges, never sees the key. Crossed-out text,
  unreadable characters and circled options are kept in the transcript.
- **Exact where the answer is definitive.** For true/false (Σ/Λ, T/F…), multiple choice (Greek or Latin letters,
  or the option written out), numbers (decimal comma, fractions, 1.000 vs 1,000, units) and short answers, the model
  only *extracts* what the student wrote and code compares it with the key. A second vision model
  (`AWS_BEDROCK_VERIFY_MODEL`, Kimi K2.5) reads every definitive answer on a scan again; when the readings differ the
  question is flagged and both readings are one click away.
- **Open questions** are scored per rubric criterion (met / half / not met) with feedback, at temperature 0.
- **Review.** Every mark, reading and comment can be changed; nothing is final until a paper is **marked reviewed**.
  Papers that need a look (unclear readings, keys Lara proposed, strong integrity signals, document alerts) are
  counted and filtered. `[` and `]` step through papers.
- **Copying score /100**, judged against the whole class: rare shared passages, identical *wrong* answers beyond what
  chance explains (being wrong together is not evidence; giving the same rare wrong answer is), the same unusual
  mistakes or examples (grouped per open question by the model, plus the same example values found in code),
  near-identical handwriting layout on scans, the same file, document ID or author. The strongest pairs are re-read
  side by side; the model quotes what both papers share and Lara keeps only quotes it finds in both. **Likely**
  needs strong evidence or two independent coincidences — one shared example is "worth a look". **Compare** shows
  two papers question by question with the shared passages and quotes highlighted.
- **AI-likeness score /100**, from explained signals: chatbot leftovers, ChatGPT citation markers, invisible
  characters, AI-typical vocabulary (English and Greek), em dashes on typed text, formulaic phrasing, answers far
  longer and more elaborate than the class, and the model's own reading relative to the class. Short handwritten
  answers are "too little text to judge". Shown as signals for a conversation, never as proof.
- **Document checks:** metadata, producer, revisions, digital signatures, camera EXIF, C2PA/AI-image provenance,
  homoglyphs, and **hidden text** (white, invisible, 1-pt or off-page text — found by comparing the text layer with the
  rendered page) — hidden text is reported and never reaches the grader.
- **Exports:** Excel (.xlsx), CSV (UTF-8, for an LMS) and a PDF report (class summary, then one page per student).
- **Pause / resume**, **Retry** for a failed paper, adding papers later, re-grading after a rubric change (your marks
  on unchanged questions are kept). A restarted API picks up where it stopped.

```
data/assessments/<id>/assessment.json   settings, rubric, one row per paper
data/assessments/<id>/analysis.json     the class analysis (pairs, clusters, insights)
data/assessments/<id>/exam/, exam.txt   the exam paper / answer key
data/assessments/<id>/papers/<pid>/     source file, paper.json (reading, results, forensics), pages/
```

Design, research and evaluation notes: `docs/assessments/`.

```
api/   FastAPI service: Bedrock LLM, Manim rendering, ElevenLabs TTS, ffmpeg, WeasyPrint / python-docx exports,
       assessments (pypdfium2, pypdf, Pillow, openpyxl)
web/   Next.js dashboard (TipTap slide editor)
data/  projects, decks and assessments on disk (git-ignored)
docs/  design specs and implementation plans (docs/slides/, docs/assessments/)
```

## Prerequisites

- ffmpeg/ffprobe, a LaTeX distribution with `dvisvgm` (for Manim's `MathTex`), Cairo/Pango (Manim; WeasyPrint uses them too)
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`) — Python 3.12 is installed by uv
- Node 22+

## Configuration (`.env` in the repo root)

| Variable | Default | Notes |
|---|---|---|
| `AWS_BEDROCK_ACCESS_KEY_ID` / `AWS_BEDROCK_SECRET_ACCESS_KEY` | — | Bedrock credentials |
| `AWS_BEDROCK_REGION` | `us-east-1` | |
| `AWS_BEDROCK_MODEL` | `zai.glm-5` | Any Bedrock Converse model. The hackathon account blocks Claude; GLM-5 won a Manim code bake-off (runner-up `deepseek.v3.2`). |
| `ELEVENLABS_API_KEY` | — | AI narration (`eleven_multilingual_v2`, speaks Greek) |
| `ELEVENLABS_VOICE_ID` | `JBFqnCBsd6RMkjVDRZzb` | Voice for any language without its own voice below |
| `ELEVENLABS_VOICE_ID_EL` / `ELEVENLABS_VOICE_ID_EN` | — | A voice per video language (a native Greek voice reads Greek best) |
| `ELEVENLABS_MODEL` | `eleven_multilingual_v2` | e.g. `eleven_v4` (tested with Greek, `language_code` and caption timestamps); models other than multilingual v2 also get `language_code` |
| `ELEVENLABS_SPEED` / `_STABILITY` / `_SIMILARITY` / `_STYLE` | — | Optional `voice_settings`, e.g. `ELEVENLABS_SPEED=0.95` for teaching |
| `AWS_BEDROCK_VISION_MODEL` | `qwen.qwen3-vl-235b-a22b` | Reads scanned papers (and scanned exam papers) |
| `AWS_BEDROCK_VERIFY_MODEL` | `moonshotai.kimi-k2.5` | Second reading of definitive answers on scans; set empty to switch off |
| `AWS_BEDROCK_GRADING_MODEL` | — | Grading, rubric drafting and class analysis; empty = `AWS_BEDROCK_MODEL` (GLM-5 won the grading bake-off) |
| `GRADING_CONCURRENCY` | `6` | Simultaneous model calls of the grading pipeline |
| `RENDER_QUALITY` | `m` | `m` = 720p30, `l` = 480p15 (faster while developing) |
| `DATA_DIR` | `<repo>/data` | |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated dashboard origins |

Check Bedrock access: `cd api && uv run python scripts/check_bedrock.py` (prints `ok`).

## Run

```bash
# API (port 8000)
cd api && uv sync && uv run uvicorn app.main:create_default_app --factory --reload --port 8000

# Dashboard (port 3000)
cd web && npm install && npm run dev
```

Open http://localhost:3000. Recording your voice needs microphone permission (Chrome recommended).

## Tests

```bash
cd api && uv run pytest -m "not slow"   # fast unit + API tests (fakes for LLM, renderer, TTS)
cd api && uv run pytest                 # everything, including real Manim and ffmpeg
cd web && npm run build && npm run lint && npm test   # typecheck + build, lint, Vitest for pure helpers
```

Browser QA for the slides workspace drives the installed Google Chrome through Playwright against running dev
servers (`web/qa/*.mjs`; pass the deck id, and the web/API URLs if not the defaults):

```bash
cd web && node qa/deck-editor.mjs <deckId>      # typing, toolbar, add/delete/undo, title, reload
cd web && node qa/deck-chat.mjs <deckId>        # a mixed request against the real model, chips, undo
cd web && node qa/deck-animation.mjs <deckId>   # deck → animation setup → Add to slides (drafts a real script)
cd web && node qa/deck-export.mjs <deckId>      # PDF and Word downloads
```

Prompt check for the slides assistant: `cd api && uv run python scripts/try_deck_chat.py`.

Assessments against the real models: generate a Greek test class with known answers (handwritten scans in four
hands, typed papers, a verbatim and a paraphrased copy, an AI-written paper, hidden text) and score the pipeline:

```bash
cd api && uv run python scripts/make_exam_class.py /tmp/class [--extra 24]  # + N students for a scale test
cd api && uv run python scripts/eval_assessment.py /tmp/class [--grader zai.glm-5] [--no-exam] [--language en]
cd api && uv run python scripts/rerun_analysis.py <data dir> <assessmentId>  # only the class analysis again
cd web && node qa/assess-flow.mjs /tmp/class [web] [api]      # the whole flow in the browser
cd web && node qa/assess-screens.mjs <assessmentId> [web] [out] [el|en]
cd web && node qa/overflow.mjs <assessmentId> <paperId> [web]  # horizontal overflow at phone width
```

## Pitch fallback

Renders depend on a live LLM and take ~20–40 s per scene. The night before the pitch, seed a finished project
and keep `data/` intact:

```bash
cd api && uv run python scripts/seed_demo.py --concept "Κάθοδος κλίσης (gradient descent)" \
  --pdf path/to/lecture.pdf --language el --style "φιλικός, για πρωτοετείς" --duration medium
```

It prints the project id and exits non-zero if any scene could not be rendered (retry them in the dashboard). During the pitch, if a live render is slow, open the seeded project
from the dashboard. If the API restarts mid-render, the dashboard offers **Try again**.
