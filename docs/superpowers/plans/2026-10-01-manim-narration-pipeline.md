# Manim + Narration Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A professor uploads course material + a concept, approves an AI storyboard, gets AI-written Manim scenes (with an automatic repair loop and per-scene chat revision), voices each scene with an AI voice or their own recording, and exports one MP4.

**Architecture:** Python 3.12 FastAPI service (`api/`) owns LLM (Bedrock), Manim rendering, TTS (ElevenLabs) and ffmpeg; a Next.js app (`web/`) is the educator dashboard and polls the API. Projects are folders under `data/` — no database. Every external dependency (LLM, renderer, TTS) is injected into `create_app` so tests use fakes.

**Tech Stack:** uv, Python 3.12, FastAPI, Pydantic v2, boto3 (Bedrock Converse), httpx, pypdf, Manim Community Edition, ffmpeg/ffprobe, pytest + pytest-asyncio; Next.js (App Router, TypeScript, Tailwind), Node 22.

**Spec:** `docs/superpowers/specs/2026-10-01-manim-narration-pipeline-design.md`

**Time budget:** ~19 h total (per-task estimates in headings). **Cut line:** after Task 11 you have a demoable silent-animation product; Tasks 12–15 add voice; Task 16 is pitch insurance and must not be skipped — if short on time, shrink Task 15's UI polish instead.

## Global Constraints

- Python 3.12 via `uv` (system Python 3.14 is not used). All Python commands run from `api/` as `uv run ...`.
- Env vars (repo-root `.env`, never committed): `AWS_BEDROCK_ACCESS_KEY_ID`, `AWS_BEDROCK_SECRET_ACCESS_KEY`, `AWS_BEDROCK_REGION` (default `eu-central-1`), `AWS_BEDROCK_MODEL` (default `eu.anthropic.claude-sonnet-4-5-20250929-v1:0`), `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` (default `JBFqnCBsd6RMkjVDRZzb`), `RENDER_QUALITY` (`l`|`m`, default `m`), `DATA_DIR` (default `<repo>/data`). Empty values mean "use default".
- Generated Manim class name: `GeneratedScene`. Natural-language text: `Text(..., font="DejaVu Sans")`. `MathTex`/`Tex` only for math.
- Constants: `MAX_MATERIAL_CHARS = 60_000`; `CODEGEN_MATERIAL_CHARS = 8_000`; `MAX_REPAIRS = 3` (max 4 render attempts); `ERROR_TAIL_CHARS = 3_000`; `RENDER_TIMEOUT_S = 180`; `MAX_CONCURRENT_RENDERS = 4`; `WORDS_PER_SECOND = 2.5`; minimum target 6 s; `TAIL_PAD_S = 0.3`.
- Export format: 1280×720, 30 fps, H.264 `yuv420p`, AAC 44.1 kHz. Normalized audio: `audio.wav`, 44.1 kHz mono.
- Language codes: `"el"` (Greek) and `"en"` (English). Dashboard UI copy is English; generated content is in the project language.
- IDs: project `uuid4().hex[:10]`, scene `uuid4().hex[:8]`.
- No auth, no database. `data/` is git-ignored.
- Error copy (exact): `"No readable text found in the uploaded material"`, `"Could not read the uploaded PDF"`, `"Render timed out after {timeout_s}s"`, `"Interrupted by server restart"`, `"Code must define class GeneratedScene"`, `"All scenes must be rendered before export"`, `"Could not read the recording"`, `"Storyboard can only be edited before rendering starts"`, `"Scene is already being processed"`.
- Commit after every task with a `feat:`/`chore:`/`test:` message; each commit leaves `uv run pytest` green.

## Review Focus

1. **LLM wraps JSON or code in prose/fences** → parsing still extracts it; storyboard retries once with the error. Pinned in Task 4 (`test_extract_json_*`, `test_retries_once_on_invalid_json`).
2. **Scanned/image-only PDF and no pasted text** → HTTP 422 with `"No readable text found in the uploaded material"`, no project created. Pinned in Task 3 and Task 5.
3. **Generated scene loops forever / is extremely long** → subprocess killed at timeout, counted as a failed attempt and fed to repair. Pinned in Task 6 (`test_timeout_kills_render`).
4. **Chrome MediaRecorder webm without duration metadata** → normalized `audio.wav` has a correct duration so export timing is right. Pinned in Task 13 (`test_recording_without_duration_metadata`).
5. **API restarts mid-render (e.g., during the pitch)** → stuck scenes become `failed` with a retry button instead of spinning forever. Pinned in Task 2 (`test_recover_interrupted`) and Task 8 (`test_startup_recovers_interrupted`).

---

## File Structure

```
.gitignore                       (modify: data/, .venv, node_modules, .next, __pycache__)
README.md                        (modify in Task 16)
api/
  pyproject.toml
  app/
    config.py        Settings + load_settings
    main.py          create_app factory, lifespan, router registration
    models.py        Pydantic Project / Scene / SceneDraft + request bodies
    store.py         ProjectStore: file storage, per-project locks, recovery
    ingest.py        PDF/text → material string
    parsing.py       extract_json / extract_code_block
    llm.py           LLM type + BedrockLLM
    storyboard.py    generate_storyboard
    render.py        render_scene (Manim subprocess) + make_renderer (semaphore)
    codegen.py       prompts: generate / repair / revise, precheck, target_seconds
    pipeline.py      build_scene: generate→check→render→repair loop
    jobs.py          JobRunner (keyed background tasks)
    tts.py           TTSProvider, ElevenLabsTTS, CachedTTS
    media.py         ffmpeg helpers: probe_duration, normalize_audio, assemble
    voice.py         generate_ai_voice / attach_recording / clear_voice
    export.py        export_project
    routes/{projects,scenes,voice,export}.py
  scripts/check_bedrock.py, scripts/seed_demo.py
  tests/conftest.py, tests/fakes.py, tests/test_*.py
web/
  lib/types.ts, lib/api.ts, lib/useProject.ts
  app/page.tsx, app/new/page.tsx, app/projects/[id]/page.tsx
  components/{Stepper,StoryboardEditor,ScenesBoard,SceneCard,VoiceStudio,SceneRecorder,ExportPanel}.tsx
```

---

### Task 1: Backend scaffold, config, Manim install (~1 h)

**Files:**
- Create: `api/pyproject.toml`, `api/app/__init__.py`, `api/app/config.py`, `api/app/main.py`, `api/tests/conftest.py`, `api/tests/test_config.py`, `api/tests/test_health.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `Settings` (frozen dataclass: `data_dir: Path, bedrock_access_key_id: str, bedrock_secret_access_key: str, bedrock_region: str, bedrock_model: str, elevenlabs_api_key: str, elevenlabs_voice_id: str, render_quality: str, render_timeout_s: int = 180, max_concurrent_renders: int = 4, cors_origins: tuple[str, ...] = ("http://localhost:3000",)`); `load_settings(env_file: Path | None = None) -> Settings`; `create_app(settings: Settings) -> FastAPI` (later tasks add keyword-only injections); `create_default_app() -> FastAPI`; test helper `make_settings(tmp_path: Path, **overrides) -> Settings` in `tests/conftest.py`.

- [ ] **Step 1: Install uv and Python 3.12**

Run: `curl -LsSf https://astral.sh/uv/install.sh | sh && uv python install 3.12`
Expected: `uv --version` prints a version.

- [ ] **Step 2: Create `api/pyproject.toml`**

Project `educator-api`, `requires-python = ">=3.12,<3.13"`. Dependencies: `fastapi`, `uvicorn[standard]`, `python-multipart`, `pydantic>=2`, `python-dotenv`, `boto3>=1.39`, `httpx`, `pypdf`, `manim`. Dev group: `pytest`, `pytest-asyncio`, `reportlab`. Pytest config: `asyncio_mode = "auto"`, `markers = ["slow: uses real manim/ffmpeg"]`, `testpaths = ["tests"]`. Then `cd api && uv sync`.
Expected: `uv run python -c "import manim; print(manim.__version__)"` prints a version. If pycairo/manimpango fail to build, run `sudo apt install libcairo2-dev libpango1.0-dev` and retry.

- [ ] **Step 3: Write failing tests**

```python
# tests/test_config.py
def test_defaults_when_values_empty(tmp_path, monkeypatch):
    for k in ["AWS_BEDROCK_REGION", "AWS_BEDROCK_MODEL", "RENDER_QUALITY", "ELEVENLABS_VOICE_ID", "DATA_DIR"]:
        monkeypatch.delenv(k, raising=False)
    env = tmp_path / ".env"
    env.write_text("AWS_BEDROCK_ACCESS_KEY_ID=abc\nAWS_BEDROCK_REGION=\nAWS_BEDROCK_MODEL=\n")
    s = load_settings(env)
    assert s.bedrock_access_key_id == "abc"
    assert s.bedrock_region == "eu-central-1"
    assert s.bedrock_model == "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert s.render_quality == "m"
    assert s.elevenlabs_voice_id == "JBFqnCBsd6RMkjVDRZzb"
    assert s.data_dir.name == "data"

def test_env_values_override(tmp_path, monkeypatch):
    monkeypatch.setenv("RENDER_QUALITY", "l")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "d"))
    s = load_settings(tmp_path / "missing.env")
    assert s.render_quality == "l" and s.data_dir == tmp_path / "d"

# tests/test_health.py
def test_health(tmp_path):
    client = TestClient(create_app(make_settings(tmp_path)))
    assert client.get("/health").json() == {"status": "ok"}
```

- [ ] **Step 4: Run tests — expect FAIL (import errors)**

Run: `uv run pytest -v`

- [ ] **Step 5: Implement `app/config.py` and `app/main.py`**

`load_settings` calls `load_dotenv(env_file or <repo>/.env, override=False)`, then reads `os.environ`, treating `""` as unset. `<repo>` = `Path(__file__).resolve().parents[2]`. `create_app` adds `CORSMiddleware` (origins from settings, all methods/headers) and `GET /health`. `create_default_app()` returns `create_app(load_settings())`. `make_settings` builds a `Settings` with `data_dir=tmp_path/"data"`, `render_quality="l"`, dummy keys, applying overrides via `dataclasses.replace`.

- [ ] **Step 6: Run tests — expect PASS**

Run: `uv run pytest -v`. Also `uv run uvicorn app.main:create_default_app --factory --port 8000` and `curl localhost:8000/health` → `{"status":"ok"}`.

- [ ] **Step 7: Update `.gitignore`** with `data/`, `.venv/`, `__pycache__/`, `media/`, `node_modules/`, `.next/` (keep `.env`).

- [ ] **Step 8: Commit** — `git add .gitignore api && git commit -m "chore: scaffold FastAPI service with config and manim"`

---

### Task 2: Models and file store (~1 h)

**Files:**
- Create: `api/app/models.py`, `api/app/store.py`, `api/tests/test_store.py`

**Interfaces:**
- Produces (`models.py`): `Language = Literal["el","en"]`; `RenderStatus = Literal["pending","generating","rendering","repairing","done","failed"]`; `AudioStatus = Literal["none","generating","done","failed"]`; `SceneDraft(id: str | None = None, title: str, visual: str, narration: str)` — all three text fields `min_length=1`; `Scene(id, title, visual, narration, code_version: int = 0, render_status: RenderStatus = "pending", attempts: int = 0, last_error: str | None = None, audio_source: Literal["ai","professor"] | None = None, audio_status: AudioStatus = "none")`; `Project(id, created_at: datetime, title, concept, style, tone, language: Language, stage: Literal["storyboard","scenes"] = "storyboard", scenes: list[Scene])`.
- Produces (`store.py`): `class ProjectNotFound(KeyError)`; `class SceneNotFound(KeyError)`; `class ProjectStore(root: Path)` with
  - `create(*, title, concept, style, tone, language, material_text, scenes: list[SceneDraft]) -> Project`
  - `get(project_id) -> Project`, `list() -> list[Project]` (newest first), `material(project_id) -> str`
  - `project_dir(project_id) -> Path`, `scene_dir(project_id, scene_id) -> Path` (creates dir)
  - `async mutate(project_id, fn: Callable[[Project], None]) -> Project` (load → fn → save under a per-project `asyncio.Lock`)
  - `async update_scene(project_id, scene_id, **fields) -> Scene`
  - `recover_interrupted() -> int` (sync; number of scenes changed)
  - `Project.scene(scene_id) -> Scene` helper method raising `SceneNotFound`.

- [ ] **Step 1: Write failing tests**

```python
def draft(t="A"): return SceneDraft(title=t, visual="v", narration="n")

def test_create_and_get_roundtrip(tmp_path):
    store = ProjectStore(tmp_path)
    p = store.create(title="Κλίση", concept="gradient descent", style="", tone="", language="el",
                     material_text="notes", scenes=[draft()])
    assert store.get(p.id) == p
    assert p.scenes[0].render_status == "pending" and p.scenes[0].code_version == 0
    assert store.material(p.id) == "notes"
    assert "Κλίση" in (tmp_path / "projects" / p.id / "project.json").read_text(encoding="utf-8")

def test_get_missing_raises(tmp_path):
    with pytest.raises(ProjectNotFound): ProjectStore(tmp_path).get("nope")

def test_list_newest_first(tmp_path):
    s = ProjectStore(tmp_path)
    a = s.create(title="a", concept="c", style="", tone="", language="en", material_text="m", scenes=[draft()])
    b = s.create(title="b", concept="c", style="", tone="", language="en", material_text="m", scenes=[draft()])
    assert [p.id for p in s.list()] == [b.id, a.id]

async def test_concurrent_update_scene_keeps_all_writes(tmp_path):
    s = ProjectStore(tmp_path)
    p = s.create(title="t", concept="c", style="", tone="", language="en", material_text="m", scenes=[draft("A"), draft("B")])
    a, b = p.scenes
    await asyncio.gather(*[s.update_scene(p.id, a.id, attempts=i) for i in range(10)],
                         s.update_scene(p.id, b.id, render_status="done"))
    got = s.get(p.id)
    assert got.scene(b.id).render_status == "done" and got.scene(a.id).attempts in range(10)

def test_recover_interrupted(tmp_path):
    s = ProjectStore(tmp_path)
    p = s.create(title="t", concept="c", style="", tone="", language="en", material_text="m", scenes=[draft("A"), draft("B")])
    asyncio.run(s.update_scene(p.id, p.scenes[0].id, render_status="rendering"))
    asyncio.run(s.update_scene(p.id, p.scenes[1].id, render_status="done", audio_status="generating"))
    assert s.recover_interrupted() == 2
    a, b = s.get(p.id).scenes
    assert a.render_status == "failed" and a.last_error == "Interrupted by server restart"
    assert b.render_status == "done" and b.audio_status == "failed"
```

- [ ] **Step 2: Run — expect FAIL.** `uv run pytest tests/test_store.py -v`
- [ ] **Step 3: Implement** `models.py` and `store.py`. Layout `root/projects/<id>/project.json` (`model_dump_json(indent=2)`, written via temp file + `os.replace`) and `material.txt`, both UTF-8. Ordering for `list()` by `created_at`.
- [ ] **Step 4: Run — expect PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat: project models and file-based store"`

---

### Task 3: Material ingestion (~0.5 h)

**Files:**
- Create: `api/app/ingest.py`, `api/tests/test_ingest.py`

**Interfaces:**
- Produces: `MAX_MATERIAL_CHARS = 60_000`; `class EmptyMaterialError(ValueError)`; `extract_pdf_text(data: bytes) -> str` (raises `EmptyMaterialError("Could not read the uploaded PDF")` on unparsable bytes); `build_material(pdf_bytes: bytes | None, pasted_text: str | None) -> str` (PDF text, then pasted text, joined by `"\n\n"`, stripped, truncated; raises `EmptyMaterialError("No readable text found in the uploaded material")` when empty).

- [ ] **Step 1: Write failing tests** (helper `make_pdf(text: str | None) -> bytes` with reportlab; `None` → blank page)

```python
def test_pasted_text_only(): assert build_material(None, "  hello ") == "hello"
def test_pdf_text_extracted(): assert "Gradient descent notes" in build_material(make_pdf("Gradient descent notes"), None)
def test_pdf_then_text_joined():
    out = build_material(make_pdf("PDFTEXT"), "PASTED")
    assert out.index("PDFTEXT") < out.index("PASTED") and "\n\n" in out
def test_truncates(): assert len(build_material(None, "x" * 70_000)) == MAX_MATERIAL_CHARS
def test_blank_pdf_and_no_text_raises():
    with pytest.raises(EmptyMaterialError, match="No readable text found in the uploaded material"):
        build_material(make_pdf(None), "   ")
def test_corrupt_pdf_raises():
    with pytest.raises(EmptyMaterialError, match="Could not read the uploaded PDF"):
        build_material(b"not a pdf", None)
```

- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** with `pypdf.PdfReader(io.BytesIO(data))`, joining `page.extract_text() or ""`; catch `pypdf.errors.PdfReadError` and `ValueError`.
- [ ] **Step 4: Run — expect PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat: extract course material from PDF and text"`

---

### Task 4: LLM client, parsing, storyboard generation (~1.5 h)

**Files:**
- Create: `api/app/parsing.py`, `api/app/llm.py`, `api/app/storyboard.py`, `api/scripts/check_bedrock.py`, `api/tests/fakes.py`, `api/tests/test_parsing.py`, `api/tests/test_storyboard.py`

**Interfaces:**
- Produces: `extract_json(text: str) -> Any` (raises `ValueError`); `extract_code_block(text: str) -> str`; `LLM = Callable[[str, list[dict[str, str]]], str]` — `(system, messages)` where messages are `{"role": "user"|"assistant", "content": str}`; `class BedrockLLM(settings: Settings)` implementing `LLM`; `class StoryboardError(RuntimeError)`; `generate_storyboard(llm: LLM, *, material: str, concept: str, style: str, tone: str, language: Language) -> tuple[str, list[SceneDraft]]`.
- Produces (`tests/fakes.py`): `ScriptedLLM(responses: list[str | Exception])` — callable, pops responses in order (raises if an item is an Exception), records `.calls: list[tuple[str, list[dict]]]`; `STORYBOARD_JSON: str` — valid storyboard with title `"Κάθοδος κλίσης"` and 4 scenes.

- [ ] **Step 1: Write failing tests**

```python
# test_parsing.py
def test_extract_json_from_fence(): assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
def test_extract_json_with_prose(): assert extract_json('Sure! {"a": [1, 2]} Hope this helps.') == {"a": [1, 2]}
def test_extract_json_none_raises():
    with pytest.raises(ValueError): extract_json("no json here")
def test_extract_code_python_fence(): assert extract_code_block("Here:\n```python\nx = 1\n```\nDone") == "x = 1"
def test_extract_code_plain_fence(): assert extract_code_block("```\nx = 1\n```") == "x = 1"
def test_extract_code_no_fence(): assert extract_code_block("  x = 1\n") == "x = 1"

# test_storyboard.py
ARGS = dict(material="Course notes on optimisation", concept="gradient descent", style="visual", tone="friendly", language="el")
def test_parses_valid_storyboard():
    title, scenes = generate_storyboard(ScriptedLLM([STORYBOARD_JSON]), **ARGS)
    assert title == "Κάθοδος κλίσης" and len(scenes) == 4 and all(s.narration for s in scenes)
def test_prompt_contains_inputs():
    llm = ScriptedLLM([STORYBOARD_JSON]); generate_storyboard(llm, **ARGS)
    system, messages = llm.calls[0]
    text = system + messages[0]["content"]
    assert "gradient descent" in text and "Course notes on optimisation" in text and "Greek" in text
def test_retries_once_on_invalid_json():
    llm = ScriptedLLM(["not json", STORYBOARD_JSON])
    assert len(generate_storyboard(llm, **ARGS)[1]) == 4
    assert len(llm.calls) == 2 and "not valid" in llm.calls[1][1][-1]["content"].lower()
def test_retries_on_empty_scene_field():
    bad = '{"title": "t", "scenes": [{"title": "a", "visual": "", "narration": "n"}]}'
    llm = ScriptedLLM([bad, STORYBOARD_JSON]); generate_storyboard(llm, **ARGS)
    assert len(llm.calls) == 2
def test_raises_after_second_failure():
    with pytest.raises(StoryboardError): generate_storyboard(ScriptedLLM(["x", "y"]), **ARGS)
```

- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement `parsing.py`.** `extract_json`: try fenced ```json / ``` block first, else the span from the first `{` or `[` to the last matching `}`/`]`, `json.loads`. `extract_code_block`: first ```python block, else first ``` block, else the stripped text.
- [ ] **Step 4: Implement `storyboard.py`.** System prompt: the AI is an instructional designer creating a 4–6 scene animated explanation for a university course; all `title`/`visual`/`narration` written in the project language (`"el"` → "Greek", `"en"` → "English"); narration 1–3 sentences per scene; use the notation and examples from the course material; respond only with JSON `{"title": str, "scenes": [{"title","visual","narration"}]}`. User message contains concept, style, tone, and material. Validate with `SceneDraft`; accept 1–8 scenes. On failure, append the assistant reply and a user message `"Your previous reply was not valid: <error>. Reply with only the JSON."` and call once more; then raise `StoryboardError`.
- [ ] **Step 5: Implement `llm.py`** `BedrockLLM.__call__`:

```python
resp = self.client.converse(
    modelId=self.model,
    system=[{"text": system}],
    messages=[{"role": m["role"], "content": [{"text": m["content"]}]} for m in messages],
    inferenceConfig={"maxTokens": 8000, "temperature": 0.4},
)
return "".join(b.get("text", "") for b in resp["output"]["message"]["content"])
```
Client: `boto3.client("bedrock-runtime", region_name=..., aws_access_key_id=..., aws_secret_access_key=..., config=botocore.config.Config(read_timeout=300, retries={"max_attempts": 3}))`.

- [ ] **Step 6: Run tests — expect PASS.**
- [ ] **Step 7: Live check.** `scripts/check_bedrock.py` loads settings, calls `BedrockLLM` with `"Reply with the single word: ok"`, prints the reply.
Run: `uv run python scripts/check_bedrock.py` → prints `ok`. If it fails with access/model errors, fix `AWS_BEDROCK_REGION`/`AWS_BEDROCK_MODEL` in `.env` (the model must be enabled in the Bedrock console for that region).
- [ ] **Step 8: Commit** — `git commit -m "feat: bedrock client and storyboard generation"`

---

### Task 5: Project API — create, list, get, edit storyboard (~1 h)

**Files:**
- Create: `api/app/routes/__init__.py`, `api/app/routes/projects.py`, `api/tests/test_api_projects.py`
- Modify: `api/app/main.py` (signature `create_app(settings, *, llm: LLM | None = None)`, `app.state.settings/store/llm`, include router), `api/app/models.py` (add `StoryboardUpdate(scenes: list[SceneDraft])`)

**Interfaces:**
- Consumes: `ProjectStore`, `build_material`, `generate_storyboard`, `BedrockLLM`.
- Produces endpoints:
  - `POST /projects` multipart form: `concept` (required, min length 1), `style=""`, `tone=""`, `language="el"`, `material_text=""`, `file` (optional PDF) → `Project` (200). 422 on `EmptyMaterialError` (detail = its message); 502 on `StoryboardError`.
  - `GET /projects` → `list[Project]`; `GET /projects/{id}` → `Project` (404 if unknown).
  - `PUT /projects/{id}/storyboard` JSON `StoryboardUpdate` → `Project`. Drafts with an existing `id` keep that scene's id; others get new ids; scenes not listed are removed; list order = new order. 409 `"Storyboard can only be edited before rendering starts"` when `stage != "storyboard"`.
- Produces (tests): async fixture pattern used by all API tests:
  `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")`. Add `api_client(app)` helper to `conftest.py`.

- [ ] **Step 1: Write failing tests**

```python
async def test_create_with_text(tmp_path):
    app = create_app(make_settings(tmp_path), llm=ScriptedLLM([STORYBOARD_JSON]))
    async with api_client(app) as c:
        r = await c.post("/projects", data={"concept": "gradient descent", "material_text": "notes", "language": "el"})
    assert r.status_code == 200
    p = r.json(); assert p["stage"] == "storyboard" and len(p["scenes"]) == 4 and p["title"] == "Κάθοδος κλίσης"

async def test_create_with_pdf(tmp_path):  # file=("notes.pdf", make_pdf("Loss surface"), "application/pdf"); assert LLM prompt contains "Loss surface"
async def test_create_without_material_422(tmp_path):
    ...  # data={"concept": "x"} → 422, r.json()["detail"] == "No readable text found in the uploaded material"; GET /projects == []
async def test_storyboard_failure_502(tmp_path):  # ScriptedLLM(["bad", "bad"]) → 502
async def test_get_unknown_404(tmp_path): ...
async def test_put_storyboard_edit_reorder_add_delete(tmp_path):
    # create (4 scenes s0..s3); PUT [s2 edited title "New", new draft without id, s0] →
    # ids == [s2.id, <new id>, s0.id], titles[0] == "New", len == 3
async def test_put_storyboard_after_render_409(tmp_path):
    # await app.state.store.mutate(pid, lambda p: setattr(p, "stage", "scenes")); PUT → 409 with exact detail
```

- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** `routes/projects.py`. Run `build_material` and `generate_storyboard` via `asyncio.to_thread`. Map `ProjectNotFound`/`SceneNotFound` → 404 via exception handlers registered in `create_app`.
- [ ] **Step 4: Run — expect PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat: project creation and storyboard editing API"`

---

### Task 6: Manim renderer (~1 h)

**Files:**
- Create: `api/app/render.py`, `api/tests/test_render.py`

**Interfaces:**
- Produces: `@dataclass RenderResult(ok: bool, error: str = "")`; `ERROR_TAIL_CHARS = 3000`; `async render_scene(code_path: Path, output_path: Path, *, quality: str, timeout_s: int) -> RenderResult`; `Renderer = Callable[[Path, Path], Awaitable[RenderResult]]`; `make_renderer(settings: Settings) -> Renderer` (binds quality/timeout, limits concurrency with an `asyncio.Semaphore(settings.max_concurrent_renders)`).

- [ ] **Step 1: Write failing tests**

```python
GOOD = '''from manim import *
class GeneratedScene(Scene):
    def construct(self):
        self.play(Write(Text("Κάθοδος κλίσης", font="DejaVu Sans")))
        self.play(Write(MathTex(r"\\nabla f(x)")))
'''
@pytest.mark.slow
async def test_renders_greek_and_math(tmp_path):
    code = tmp_path / "code_v1.py"; code.write_text(GOOD, encoding="utf-8")
    out = tmp_path / "render_v1.mp4"
    r = await render_scene(code, out, quality="l", timeout_s=180)
    assert r.ok, r.error
    assert out.stat().st_size > 0

@pytest.mark.slow
async def test_reports_error_tail(tmp_path):
    # construct body: `undefined_name()` → not ok, "NameError" in error, len(error) <= ERROR_TAIL_CHARS, out does not exist

@pytest.mark.slow
async def test_timeout_kills_render(tmp_path):
    # construct body: `self.wait(600)`, timeout_s=5 → not ok, error == "Render timed out after 5s", finishes in < 20 s

async def test_make_renderer_limits_concurrency(tmp_path, monkeypatch):
    active = peak = 0
    async def fake(code, out, *, quality, timeout_s):
        nonlocal active, peak
        active += 1; peak = max(peak, active); await asyncio.sleep(0.05); active -= 1
        return RenderResult(ok=True)
    monkeypatch.setattr(render, "render_scene", fake)
    r = render.make_renderer(make_settings(tmp_path, max_concurrent_renders=2))
    await asyncio.gather(*[r(tmp_path / f"{i}.py", tmp_path / f"{i}.mp4") for i in range(5)])
    assert peak == 2
```

- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement.** Command: `[sys.executable, "-m", "manim", f"-q{quality}", "--format", "mp4", "--disable_caching", "--media_dir", <tempdir>, "-o", "out", str(code_path), "GeneratedScene"]` via `asyncio.create_subprocess_exec` (stdout+stderr piped, merged), `asyncio.wait_for(proc.communicate(), timeout_s)`; on timeout `proc.kill()` then `await proc.wait()`. On success locate `out.mp4` with `Path(tempdir).rglob("out.mp4")` and move to `output_path`; non-zero exit or missing file → `ok=False`, error = last `ERROR_TAIL_CHARS` of output. `make_renderer` must look up `render_scene` through the module at call time (so the monkeypatch works).
- [ ] **Step 4: Run — expect PASS.** `uv run pytest tests/test_render.py -v`
- [ ] **Step 5: Commit** — `git commit -m "feat: manim subprocess renderer with timeout and concurrency limit"`

---

### Task 7: Code generation prompts and the repair loop (~2 h)

**Files:**
- Create: `api/app/codegen.py`, `api/app/pipeline.py`, `api/tests/test_codegen.py`, `api/tests/test_pipeline.py`
- Modify: `api/tests/fakes.py` (add `FakeRenderer`, `VALID_CODE`, `INVALID_SYNTAX_CODE`)

**Interfaces:**
- Consumes: `LLM`, `extract_code_block`, `Renderer`, `RenderResult`, `ProjectStore`.
- Produces (`codegen.py`): `MAX_REPAIRS = 3`; `CODEGEN_MATERIAL_CHARS = 8000`; `target_seconds(narration: str) -> int`; `build_system_prompt(language: Language) -> str`; `precheck(code: str) -> str | None`; `generate_code(llm, scene: Scene, *, concept: str, style: str, material: str, language: Language) -> str`; `repair_code(llm, code: str, error: str, *, language: Language) -> str`; `revise_code(llm, code: str, scene: Scene, instruction: str, *, language: Language) -> str`.
- Produces (`pipeline.py`): `async build_scene(store, llm, renderer, project_id: str, scene_id: str, *, instruction: str | None = None) -> None`. Never raises; all failures end in `render_status="failed"` with `last_error`.
- Produces (fakes): `FakeRenderer(results: list[RenderResult])` — async callable `(code_path, output_path)`; on ok writes `b"fake-mp4"` to `output_path`; repeats the last result when the list runs out; records `.calls`.

- [ ] **Step 1: Write failing codegen tests**

```python
def test_target_seconds():
    assert target_seconds(" ".join(["w"] * 25)) == 10
    assert target_seconds("too short") == 6
def test_system_prompt_rules():
    p = build_system_prompt("el")
    for s in ["GeneratedScene", 'font="DejaVu Sans"', "MathTex", manim.__version__, "Greek"]: assert s in p
def test_precheck():
    assert precheck(VALID_CODE) is None
    assert precheck("def (").startswith("SyntaxError")
    assert precheck("x = 1") == "Code must define class GeneratedScene"
def test_generate_code_prompt_and_extraction():
    llm = ScriptedLLM([f"```python\n{VALID_CODE}\n```"])
    scene = Scene(id="s", title="T", visual="Draw a parabola", narration=" ".join(["w"] * 25))
    code = generate_code(llm, scene, concept="gd", style="minimal", material="M" * 20_000, language="el")
    assert code == VALID_CODE.strip()
    user = llm.calls[0][1][0]["content"]
    assert "Draw a parabola" in user and "10 seconds" in user and "M" * 8000 in user and "M" * 8001 not in user
def test_repair_sends_error_tail():
    llm = ScriptedLLM([VALID_CODE]); repair_code(llm, "bad", "E" * 5000 + "TAIL", language="en")
    msg = llm.calls[0][1][0]["content"]; assert "TAIL" in msg and "E" * 3001 not in msg
def test_revise_includes_instruction_and_code():
    llm = ScriptedLLM([VALID_CODE]); revise_code(llm, "OLD_CODE", Scene(id="s", title="t", visual="v", narration="n"), "make the arrow red", language="el")
    msg = llm.calls[0][1][0]["content"]; assert "OLD_CODE" in msg and "make the arrow red" in msg
```

- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement `codegen.py`.** System prompt (exact rules, in English, regardless of language): expert Manim Community Edition v`{manim.__version__}` developer making a 16:9 educational animation for university students; output exactly one ```python block containing a complete file starting with `from manim import *` and defining `class GeneratedScene(Scene)` (or `MovingCameraScene`/`ThreeDScene`); all natural-language on-screen text in `{language name}` using `Text(..., font="DejaVu Sans")`; `MathTex`/`Tex` only for mathematical expressions, never for sentences; keep everything inside the frame and avoid overlapping text (use `.next_to`, `.arrange`, `.scale_to_fit_width`, `FadeOut` old elements); no external files, images, sounds or network; total duration about the target seconds, padding with `self.wait`. Generate user message contains concept, style, scene title, visual, narration, `"Target duration: {n} seconds"`, and `material[:CODEGEN_MATERIAL_CHARS]` labelled as course material whose notation must be reused. Repair message: the code plus `"The render failed with this error:"` plus `error[-ERROR_TAIL_CHARS:]` and an instruction to return the full corrected file. Revise message: the current code, scene, and the professor's instruction; return the full updated file. `precheck`: `ast.parse` (SyntaxError → `f"SyntaxError: {e.msg} (line {e.lineno})"`), then require a `ClassDef` named `GeneratedScene`.
- [ ] **Step 4: Run codegen tests — expect PASS.**
- [ ] **Step 5: Write failing pipeline tests** (real `ProjectStore(tmp_path)`; helper `new_project(store)` with 1 scene)

```python
OK, BAD = RenderResult(ok=True), RenderResult(ok=False, error="Traceback: boom")
async def test_success_first_try(tmp_path):
    store, pid, sid = new_project(tmp_path)
    await build_scene(store, ScriptedLLM([VALID_CODE]), FakeRenderer([OK]), pid, sid)
    s = store.get(pid).scene(sid)
    assert (s.render_status, s.code_version, s.attempts, s.last_error) == ("done", 1, 1, None)
    d = store.scene_dir(pid, sid); assert (d / "code_v1.py").exists() and (d / "render_v1.mp4").exists()
async def test_repairs_then_succeeds(tmp_path):
    # renderer [BAD, BAD, OK], llm [VALID_CODE]*3 → done, attempts 3, code_version 3, len(llm.calls) == 3,
    # and the 2nd llm call's message contains "Traceback: boom"
async def test_fails_after_max_repairs(tmp_path):
    # renderer [BAD], llm [VALID_CODE]*4 → failed, attempts 4, code_version 0, last_error "Traceback: boom", len(renderer.calls) == 4
async def test_precheck_failure_skips_render(tmp_path):
    # llm [INVALID_SYNTAX_CODE, VALID_CODE], renderer [OK] → done, len(renderer.calls) == 1, attempts 2
async def test_failed_revise_keeps_previous_video(tmp_path):
    # first build ok (v1); then build_scene(..., instruction="red") with renderer [BAD], llm [VALID_CODE]*4
    # → render_status failed, code_version == 1, render_v1.mp4 still exists
async def test_llm_exception_marks_failed(tmp_path):
    # llm [RuntimeError("throttled")] → failed, "throttled" in last_error
```

- [ ] **Step 6: Run — expect FAIL.**
- [ ] **Step 7: Implement `pipeline.py`.** Flow: set `render_status="generating", attempts=0, last_error=None`; get code via `generate_code` (or `revise_code` with the current `code_v{code_version}.py` when `instruction` is given) in `asyncio.to_thread`. Loop up to `1 + MAX_REPAIRS` attempts: version = (highest existing `code_v*.py` number) + 1; write `code_v{version}.py`; `attempts += 1`; error = `precheck(code)`; if none, set `rendering`, call `renderer(code_path, scene_dir / f"render_v{version}.mp4")`; on success set `done`, `code_version=version`, `last_error=None` and return; otherwise, if attempts remain, set `repairing` and `code = repair_code(...)`; after the last attempt set `failed` with `last_error=error`. Wrap everything in `try/except Exception` → `failed` with `str(exc)`.
- [ ] **Step 8: Run — expect PASS.** `uv run pytest -m "not slow" -v`
- [ ] **Step 9: Live check (manual, ~2 min).** Add `if __name__ == "__main__"` to `pipeline.py`: given a project id from Task 5, build its first scene with `BedrockLLM` and the real renderer, then print status and attempts. Open `data/projects/<id>/scenes/<sid>/render_v*.mp4` and confirm the animation plays with Greek text.
- [ ] **Step 10: Commit** — `git commit -m "feat: LLM manim codegen with self-repair loop and revisions"`

---

### Task 8: Render jobs and scene API (~1 h)

**Files:**
- Create: `api/app/jobs.py`, `api/app/routes/scenes.py`, `api/tests/test_jobs.py`, `api/tests/test_api_scenes.py`
- Modify: `api/app/main.py` (add `renderer: Renderer | None = None` injection, `app.state.renderer`, `app.state.jobs = JobRunner()`, lifespan calling `store.recover_interrupted()`), `api/app/models.py` (add `ReviseRequest(instruction: str = Field(min_length=1))`)

**Interfaces:**
- Produces: `class JobRunner` with `submit(key: str, factory: Callable[[], Awaitable[None]]) -> bool` (False if `key` already running), `is_running(key) -> bool`, `async wait_all() -> None`. Exceptions inside jobs are logged, never propagated; the key is freed when the job ends. Scene job key: `f"{project_id}:{scene_id}"`.
- Produces endpoints:
  - `POST /projects/{id}/render` → sets `stage="scenes"`; submits `build_scene` for every scene whose status is `pending` or `failed` and has no running job → `Project`.
  - `POST /projects/{id}/scenes/{sid}/retry` → submit `build_scene` → `Project`; 409 `"Scene is already being processed"` if running.
  - `POST /projects/{id}/scenes/{sid}/revise` JSON `ReviseRequest` → submit `build_scene(..., instruction=...)` → `Project`; 409 if running; 409 if `code_version == 0`.
  - `GET /projects/{id}/scenes/{sid}/video` → `FileResponse(render_v{code_version}.mp4, media_type="video/mp4")`; 404 if `code_version == 0`.
  - `GET /projects/{id}/scenes/{sid}/code` → `PlainTextResponse` of `code_v{code_version}.py`; 404 if `code_version == 0`.
- Before submitting, the endpoint sets the scene's status to `generating` itself, so the returned `Project` already shows the work as in progress.

- [ ] **Step 1: Write failing tests**

```python
# test_jobs.py
async def test_rejects_duplicate_while_running():
    j = JobRunner(); gate = asyncio.Event()
    async def job(): await gate.wait()
    assert j.submit("k", job) is True and j.submit("k", job) is False
    gate.set(); await j.wait_all(); assert j.submit("k", job) is True; await j.wait_all()
async def test_exception_frees_key():
    j = JobRunner()
    async def boom(): raise RuntimeError("x")
    j.submit("k", boom); await j.wait_all(); assert not j.is_running("k")

# test_api_scenes.py  (app = create_app(settings, llm=ScriptedLLM([STORYBOARD_JSON] + [VALID_CODE]*20), renderer=FakeRenderer([OK])))
async def test_render_all_scenes(tmp_path):
    # POST /projects then /render → stage "scenes"; await app.state.jobs.wait_all(); all scenes "done", code_version 1
async def test_render_twice_does_not_duplicate(tmp_path):
    # renderer that awaits a gate; POST /render twice before gate.set() → after wait_all, len(renderer.calls) == 4
async def test_revise_creates_new_version(tmp_path):
    # after render: POST revise {"instruction": "make it red"} → wait_all → code_version 2; GET /code contains "GeneratedScene"
async def test_revise_while_running_409(tmp_path): ...
async def test_revise_empty_instruction_422(tmp_path): ...
async def test_video_404_then_200(tmp_path):
    # before render GET /video → 404; after → 200, headers["content-type"] == "video/mp4"
async def test_retry_failed_scene(tmp_path):
    # renderer [BAD] for first render → failed; swap app.state.renderer = FakeRenderer([OK]); POST retry → done
def test_startup_recovers_interrupted(tmp_path):
    # create project via store directly, set scene render_status "rendering"; `with TestClient(create_app(settings)):` → scene "failed"
```

- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** `jobs.py` (keeps a `dict[str, asyncio.Task]`, removes the entry in a done-callback) and `routes/scenes.py`. Job factories read `app.state.renderer` / `app.state.llm` when the job starts (so tests can swap them).
- [ ] **Step 4: Run — expect PASS.** `uv run pytest -m "not slow" -v`
- [ ] **Step 5: Commit** — `git commit -m "feat: background render jobs, retry, revise and video endpoints"`

---

### Task 9: Web scaffold, dashboard, setup form (~1.5 h)

**Files:**
- Create: `web/` (create-next-app), `web/lib/types.ts`, `web/lib/api.ts`, `web/lib/useProject.ts`, `web/app/page.tsx`, `web/app/new/page.tsx`, `web/app/projects/[id]/page.tsx`, `web/components/Stepper.tsx`, `web/.env.local.example`

**Interfaces:**
- Consumes: Task 5 endpoints.
- Produces: `types.ts` mirrors `Project`, `Scene`, `SceneDraft`, `Language`, `RenderStatus`, `AudioStatus` exactly (snake_case field names as in JSON). `api.ts`: `API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"`; `listProjects(): Promise<Project[]>`, `getProject(id): Promise<Project>`, `createProject(form: FormData): Promise<Project>`; all non-2xx throw `ApiError(status, detail)` using the JSON `detail`. `useProject(id): { project: Project | null, error: string | null, refresh(): Promise<void>, setProject(p: Project): void }` — refetches every 2000 ms while `isBusy(project)` (any scene `render_status` in `generating|rendering|repairing` or `audio_status === "generating"`); export `isBusy`. `Stepper({ current: 1|2|3|4 })` shows Setup → Storyboard → Scenes → Voice & Export.

- [ ] **Step 1: Scaffold.** From the repo root: `npx create-next-app@latest web --ts --tailwind --eslint --app --no-src-dir --import-alias "@/*" --use-npm`. Expected: `cd web && npm run build` succeeds.
- [ ] **Step 2: Implement `lib/types.ts`, `lib/api.ts`, `lib/useProject.ts`.**
- [ ] **Step 3: Dashboard `app/page.tsx`** (client component): product name header, "New explanation" button → `/new`, project cards (title, concept, language badge, scene count, stage) linking to `/projects/[id]`, empty state.
- [ ] **Step 4: Setup `app/new/page.tsx`:** fields concept (required), PDF upload (`accept="application/pdf"`), pasted material textarea, style, tone, language select (Ελληνικά = `el`, default; English = `en`). Submit builds `FormData` → `createProject` → `router.push(/projects/{id})`. While waiting (up to ~40 s) show a progress state ("Reading your material and drafting a storyboard…") and disable submit; show `ApiError.detail` inline on failure.
- [ ] **Step 5: Project shell `app/projects/[id]/page.tsx`:** uses `useParams()` + `useProject`; shows `Stepper` and title. For now it lists scene titles; Tasks 10, 11 and 15 replace the body by stage/tab.
- [ ] **Step 6: Verify.** `npm run build` passes. Manual: with the API running, create a Greek project from a PDF → redirected to the project page listing 4–6 scene titles in Greek; the empty-material case shows the 422 message.
- [ ] **Step 7: Commit** — `git add web && git commit -m "feat: educator dashboard and project setup flow"`

---

### Task 10: Storyboard editor (~1 h)

**Files:**
- Create: `web/components/StoryboardEditor.tsx`
- Modify: `web/lib/api.ts` (add `saveStoryboard(id, scenes: SceneDraft[]): Promise<Project>`, `startRender(id): Promise<Project>`), `web/app/projects/[id]/page.tsx` (render editor when `stage === "storyboard"`)

**Interfaces:**
- Consumes: `PUT /projects/{id}/storyboard`, `POST /projects/{id}/render`.
- Produces: `StoryboardEditor({ project, onChange(p: Project) })`.

- [ ] **Step 1: Implement.** One card per scene: number, editable title, "On screen" textarea (`visual`), "Narration" textarea, move up/down, delete; "Add scene" appends an empty draft. Local draft state; "Save" → `saveStoryboard`; "Approve & render" → `saveStoryboard` then `startRender` → `onChange`. Disable approve if there are 0 scenes or any field is empty; show API errors inline.
- [ ] **Step 2: Verify.** `npm run build`. Manual: edit a narration, reorder two scenes, delete one, add one, reload page → changes persisted; Approve → page switches to the Scenes view (stage `scenes`).
- [ ] **Step 3: Commit** — `git commit -m "feat: storyboard editor with approve and render"`

---

### Task 11: Scenes board — previews, status, revise (~1.5 h)

**Files:**
- Create: `web/components/ScenesBoard.tsx`, `web/components/SceneCard.tsx`
- Modify: `web/lib/api.ts` (add `retryScene`, `reviseScene(id, sid, instruction)`, `getSceneCode(id, sid): Promise<string>`, `videoUrl(id, sid, version): string` → `${API_URL}/projects/${id}/scenes/${sid}/video?v=${version}`), `web/app/projects/[id]/page.tsx` (when `stage === "scenes"`: tabs "Scenes" | "Voice & Export"; Stepper 3 or 4)

**Interfaces:**
- Consumes: Task 8 endpoints, `useProject` polling.
- Produces: `SceneCard({ project, scene, onChange })`, `ScenesBoard({ project, onChange })`.

- [ ] **Step 1: Implement `SceneCard`.** Status badge: Pending / Writing animation code / Rendering (attempt n of 4) / Fixing an error (attempt n of 4) / Ready / Failed. When `code_version > 0`, show a `<video controls>` with `videoUrl` (version in the key so it reloads after revision). Failed: collapsible `last_error` (monospace) + "Retry". "View code" toggle fetches and shows the generated Python. A revise textarea + "Revise scene" button (disabled while busy or `code_version === 0`); show a "keeping the previous version" note when a revision fails but `code_version > 0`.
- [ ] **Step 2: Implement `ScenesBoard`:** progress summary ("3 of 5 scenes ready"), grid of `SceneCard`s, "Continue to voice" button enabled when all scenes are `done` (switches tab).
- [ ] **Step 3: Verify.** `npm run build`. Manual end-to-end with real Bedrock + Manim: statuses update live without refresh; all clips play; revise "make the main arrow red" updates only that scene; "View code" shows code; stopping the API mid-render and restarting it shows Failed + Retry for that scene.
- [ ] **Step 4: Commit** — `git commit -m "feat: scenes board with live status, previews and chat revisions"`

**➜ Cut line: the silent-animation product is demoable here.**

---

### Task 12: TTS provider, audio normalization, AI voice API (~1 h)

**Files:**
- Create: `api/app/tts.py`, `api/app/media.py`, `api/app/voice.py`, `api/app/routes/voice.py`, `api/tests/test_tts.py`, `api/tests/test_media.py`, `api/tests/test_api_voice.py`
- Modify: `api/app/main.py` (add `tts: TTSProvider | None = None`; default `CachedTTS(ElevenLabsTTS(settings.elevenlabs_api_key, settings.elevenlabs_voice_id), settings.data_dir / "tts_cache")`), `api/app/models.py` (add `NarrationUpdate(narration: str = Field(min_length=1))`), `api/tests/fakes.py` (add `FakeTTS(audio: bytes, fail: bool = False)` recording `.calls`), `api/tests/conftest.py` (fixture `mp3_bytes` — 1 s sine via `ffmpeg -f lavfi -i sine=d=1 -f mp3 pipe:1`)

**Interfaces:**
- Produces (`tts.py`): `class TTSError(RuntimeError)`; `Protocol TTSProvider: cache_key(text: str) -> str; synthesize(text: str, language: Language) -> bytes` (mp3); `ElevenLabsTTS(api_key, voice_id, model_id="eleven_multilingual_v2", transport: httpx.BaseTransport | None = None)`; `CachedTTS(inner: TTSProvider, cache_dir: Path)`.
- Produces (`media.py`): `probe_duration(path: Path) -> float`; `normalize_audio(src: Path, dst: Path) -> None` (→ wav 44.1 kHz mono; raises `MediaError` on ffmpeg failure); `class MediaError(RuntimeError)`.
- Produces (`voice.py`): `async generate_ai_voice(store, tts, project_id, scene_id) -> Scene`; (Task 13 adds the rest).
- Produces endpoints: `POST /projects/{id}/scenes/{sid}/voice/ai` → `Project` (502 on `TTSError`, scene `audio_status="failed"`); `POST /projects/{id}/voice/ai-all` → generates sequentially for every scene with `audio_status in ("none","failed")` → `Project`; `GET /projects/{id}/scenes/{sid}/audio` → `audio/wav` (404 if none); `PATCH /projects/{id}/scenes/{sid}` JSON `NarrationUpdate` → `Project`; if `audio_source == "ai"` it deletes `audio.wav` and resets `audio_source=None, audio_status="none"`.

- [ ] **Step 1: Write failing tests**

```python
# test_tts.py
def test_elevenlabs_request_shape():
    seen = {}
    def handler(req):
        seen.update(url=str(req.url), key=req.headers["xi-api-key"], body=json.loads(req.content))
        return httpx.Response(200, content=b"MP3")
    tts = ElevenLabsTTS("k", "voice1", transport=httpx.MockTransport(handler))
    assert tts.synthesize("Γεια σας", "el") == b"MP3"
    assert seen["url"].endswith("/v1/text-to-speech/voice1") and seen["key"] == "k"
    assert seen["body"] == {"text": "Γεια σας", "model_id": "eleven_multilingual_v2"}
def test_elevenlabs_error_raises():  # 401 → TTSError with "401" in message
def test_cache_hits(tmp_path):
    inner = FakeTTS(b"A"); c = CachedTTS(inner, tmp_path)
    c.synthesize("x", "el"); c.synthesize("x", "el"); c.synthesize("y", "el")
    assert len(inner.calls) == 2

# test_media.py
@pytest.mark.slow
def test_normalize_mp3_to_wav(tmp_path, mp3_bytes):
    src = tmp_path / "a.mp3"; src.write_bytes(mp3_bytes); dst = tmp_path / "a.wav"
    normalize_audio(src, dst); assert abs(probe_duration(dst) - 1.0) < 0.1
@pytest.mark.slow
def test_normalize_garbage_raises(tmp_path):  # b"junk" → MediaError

# test_api_voice.py (project with rendered scenes created via store; FakeTTS(mp3_bytes))
@pytest.mark.slow
async def test_ai_voice_for_scene(...):  # → audio_source "ai", audio_status "done"; GET /audio 200 "audio/wav"; FakeTTS called with the narration
async def test_ai_voice_failure_502(...):  # FakeTTS(fail=True) → 502, audio_status "failed"
@pytest.mark.slow
async def test_ai_all_skips_done(...):  # one scene already done → TTS called len(scenes)-1 times
@pytest.mark.slow
async def test_narration_edit_clears_ai_audio(...):  # after AI voice, PATCH narration → audio_status "none", audio.wav gone
async def test_narration_edit_keeps_professor_audio(...):  # set audio_source="professor", audio_status="done" via store → PATCH keeps both
```

- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement.** ElevenLabs: `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`, header `xi-api-key`, `Accept: audio/mpeg`, JSON `{"text", "model_id"}`, timeout 60 s. `cache_key` = sha256 of `f"elevenlabs|{voice_id}|{model_id}|{text}"`; `CachedTTS` stores `<cache_dir>/<key>.mp3`. ffmpeg: `ffmpeg -y -i src -ar 44100 -ac 1 dst`; ffprobe: `ffprobe -v error -show_entries format=duration -of csv=p=0`. `generate_ai_voice`: set `audio_status="generating"`, synthesize in `asyncio.to_thread`, write a temporary mp3, normalize to `audio.wav`, set `audio_source="ai", audio_status="done"`; on error set `failed` and re-raise.
- [ ] **Step 4: Run — expect PASS.**
- [ ] **Step 5: Live check.** With `ELEVENLABS_API_KEY` set, call `POST .../voice/ai` on a real Greek scene and listen to `audio.wav`.
- [ ] **Step 6: Commit** — `git commit -m "feat: ElevenLabs AI narration with caching"`

---

### Task 13: Professor recording upload (~0.5 h)

**Files:**
- Modify: `api/app/voice.py`, `api/app/routes/voice.py`, `api/tests/test_api_voice.py`, `api/tests/conftest.py` (fixture `webm_no_duration` — 1.5 s sine encoded `-c:a libopus -f webm pipe:1`; piping makes ffmpeg omit duration metadata like Chrome does)

**Interfaces:**
- Produces: `async attach_recording(store, project_id, scene_id, data: bytes) -> Scene`; `async clear_voice(store, project_id, scene_id) -> Scene`. Endpoints: `POST /projects/{id}/scenes/{sid}/voice/recording` multipart `file` → `Project` (422 `"Could not read the recording"` on `MediaError`); `DELETE /projects/{id}/scenes/{sid}/voice` → `Project`.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.slow
async def test_recording_without_duration_metadata(..., webm_no_duration):
    # POST recording → audio_source "professor", audio_status "done"
    # abs(probe_duration(scene_dir / "audio.wav") - 1.5) < 0.15; scene_dir / "voice.webm" exists
@pytest.mark.slow
async def test_bad_recording_keeps_previous_audio(...):
    # AI voice first; POST recording b"junk" → 422 with exact detail; audio_source still "ai", audio.wav unchanged
async def test_clear_voice(...):  # → audio_source None, audio_status "none", files removed
```

- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement.** Write the upload to `voice.upload.webm`, normalize to `audio.tmp.wav`; only on success `os.replace` both into `voice.webm` / `audio.wav` and update the scene; on failure delete the temporary files.
- [ ] **Step 4: Run — expect PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat: upload professor voice recordings per scene"`

---

### Task 14: Assemble and export (~1.5 h)

**Files:**
- Create: `api/app/export.py`, `api/app/routes/export.py`, `api/tests/test_assemble.py`, `api/tests/test_api_export.py`
- Modify: `api/app/media.py` (add `assemble`), `api/tests/conftest.py` (helper `make_clip(path, seconds, size="854x480", fps=15)` using `ffmpeg -f lavfi -i testsrc=...`; helper `make_wav(path, seconds)`)

**Interfaces:**
- Produces: `TAIL_PAD_S = 0.3`; `assemble(segments: list[tuple[Path, Path | None]], out: Path) -> None` (video path, optional audio path, in order); `async export_project(store, project_id) -> Path`. Endpoints: `POST /projects/{id}/export` → `{"url": "/projects/{id}/export.mp4"}`, 409 `"All scenes must be rendered before export"` unless every scene is `done`; `GET /projects/{id}/export.mp4` → `video/mp4` (404 if not exported).

- [ ] **Step 1: Write failing tests** (all `slow`; helper `probe(path) -> dict` returning width, height, fps, duration, has_audio via ffprobe JSON)

```python
def test_audio_longer_than_video_holds_last_frame(tmp_path):
    v = make_clip(tmp_path / "v.mp4", 2); a = make_wav(tmp_path / "a.wav", 3)
    assemble([(v, a)], tmp_path / "out.mp4"); p = probe(tmp_path / "out.mp4")
    assert abs(p["duration"] - 3.3) < 0.15 and p["has_audio"]
    assert (p["width"], p["height"], p["fps"]) == (1280, 720, 30)
def test_no_audio_gets_silent_track(tmp_path):  # 2 s clip, None → duration ≈ 2.0, has_audio True
def test_audio_shorter_keeps_video_length(tmp_path):  # 3 s clip + 1 s audio → ≈ 3.0
def test_mixed_resolutions_concat(tmp_path):  # 854x480@15 (2 s, audio 1 s) + 1280x720@30 (2 s, no audio) → ≈ 4.0
async def test_export_api(tmp_path):  # project with real clips at render_v1.mp4 + code_version 1/done → POST → url; GET 200 video/mp4
async def test_export_requires_all_done_409(tmp_path): ...
```

- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement `assemble`.** For each segment, in a temp dir, encode `seg_i.mp4`: `D = max(Dv, Da + TAIL_PAD_S)` with audio, or `Dv` without. Video filter: `scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=30,tpad=stop_mode=clone:stop_duration={max(0, D - Dv)}`. Audio is `apad` on the wav, or `-f lavfi -i anullsrc=r=44100:cl=mono` without; `-t D`, `-c:v libx264 -pix_fmt yuv420p -c:a aac -ar 44100`. Then a concat-demuxer list → `ffmpeg -f concat -safe 0 -i list.txt -c copy out`. `export_project` gathers `(render_v{code_version}.mp4, audio.wav if audio_status == "done" else None)` in scene order and runs `assemble` via `asyncio.to_thread` into `export.mp4`.
- [ ] **Step 4: Run — expect PASS.** `uv run pytest -v` (full suite including slow).
- [ ] **Step 5: Commit** — `git commit -m "feat: assemble narrated scenes into exported MP4"`

---

### Task 15: Voice studio, teleprompter recorder, export UI (~2 h)

**Files:**
- Create: `web/components/VoiceStudio.tsx`, `web/components/SceneRecorder.tsx`, `web/components/ExportPanel.tsx`
- Modify: `web/lib/api.ts` (add `updateNarration`, `generateAiVoice`, `generateAllAiVoice`, `uploadRecording(id, sid, blob: Blob)`, `clearVoice`, `exportProject(id): Promise<{url: string}>`, `audioUrl(id, sid, bust)`, `exportUrl(id, bust)`), `web/app/projects/[id]/page.tsx` ("Voice & Export" tab)

**Interfaces:**
- Consumes: Task 12–14 endpoints.
- Produces: `VoiceStudio({ project, onChange })`, `SceneRecorder({ project, scene, onDone(p: Project), onClose() })`, `ExportPanel({ project })`.

- [ ] **Step 1: `VoiceStudio`.** One row per scene: small video, editable narration (save on blur via `updateNarration`), source badge (None / AI voice / Your voice / Failed), buttons "AI voice", "Record my voice", "Remove", and an `<audio>` preview when done. Header button "AI voice for all remaining" → `generateAllAiVoice`.
- [ ] **Step 2: `SceneRecorder` (modal).** Muted scene video on top; narration below in large text (teleprompter). Flow: **Record** → `getUserMedia({audio: true})`, `new MediaRecorder(stream, {mimeType: "audio/webm;codecs=opus"})`, start recording and `video.currentTime = 0; video.play()` together; **Stop** → stop both, keep the blob; **Play take** → play the video from 0 together with an `<audio>` element for the blob; **Retake** → discard and record again; **Use this take** → `uploadRecording` → `onDone`. Show a clear message if microphone permission is denied. Release mic tracks on close.
- [ ] **Step 3: `ExportPanel`.** "Export video" (disabled unless every scene is `done`; note which scenes have no voice and will be silent) → spinner → `<video>` of `exportUrl` + "Download MP4" link (`download` attribute).
- [ ] **Step 4: Verify.** `npm run build`. Manual in Chrome: AI voice on all scenes; re-record one scene in your own voice with a retake; export; the downloaded MP4 plays with your voice on that scene and the AI voice elsewhere, each scene waits for its narration to finish (last frame held), and audio stays in sync.
- [ ] **Step 5: Commit** — `git commit -m "feat: voice studio with teleprompter recording and export"`

---

### Task 16: Demo seed script and README (~1 h)

**Files:**
- Create: `api/scripts/seed_demo.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `build_material`, `generate_storyboard`, `ProjectStore.create`, `build_scene`, `make_renderer`, `generate_ai_voice`, `export_project`, `load_settings`, `BedrockLLM`, `CachedTTS`/`ElevenLabsTTS`.

- [ ] **Step 1: Implement `seed_demo.py`.** CLI (argparse): `--concept` (required), `--pdf`, `--text`, `--language` (default `el`), `--style`, `--tone`. Runs the full pipeline headless: create the project → build all scenes concurrently (`asyncio.gather`) → for any `failed` scene, retry once → AI voice for all → export. Prints the project id, per-scene status/attempts, and the export path; exit code 1 if any scene ends `failed`.
- [ ] **Step 2: Verify.** `uv run python scripts/seed_demo.py --concept "Κάθοδος κλίσης (gradient descent)" --pdf <your lecture pdf> --language el` → exit code 0; the project appears on the dashboard with all steps complete; `export.mp4` plays.
- [ ] **Step 3: README.** Prerequisites (ffmpeg, LaTeX + dvisvgm, uv, Node 22); `.env` keys table; run commands (`cd api && uv sync && uv run uvicorn app.main:create_default_app --factory --reload --port 8000`; `cd web && npm install && npm run dev`); tests (`uv run pytest -m "not slow"`, full `uv run pytest`); a **pitch fallback** section: seed the demo project the night before, keep `data/` intact, and during the pitch show the cached project if a live render is slow.
- [ ] **Step 4: Commit** — `git commit -m "chore: demo seed script and setup docs"`
