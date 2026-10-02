# Lara Assessments — Implementation plan

**Goal:** the Assessments feature of [`2026-10-02-assessments-design.md`](2026-10-02-assessments-design.md) (grading of
scanned or typed exam papers with deterministic scoring of definitive answers, criterion-level open questions,
copying and AI-likeness scores, document forensics, exports) and the dashboard shell (sidebar, overview, section
pages).

**Architecture:** a new API package `api/app/assess/` (models, store, ingest, forensics, reading, rubric, grading,
scoring, signals, similarity, class analysis, stats, export, pipeline) behind `api/app/routes/assessments.py`;
assessments live under `data/assessments/<id>/`. Background work runs on the app's `JobRunner` with a global model
semaphore. The web adds the shell (`AppNav`), section pages, and the assessment pages under `web/app/assessments/`.

**Tech:** FastAPI + pydantic v2, pypdfium2 (render, text boxes, page objects), pypdf (metadata, XMP, trailer, revisions,
signatures), Pillow + numpy (ink maps, dHash, pixel checks), WeasyPrint (PDF report), Bedrock Converse
(Qwen3-VL reader, Kimi K2.5 second reader, grading model); Next.js 16 / React 19 / Tailwind v4, inline SVG charts.

## Global constraints

- `cd api && uv run pytest -m "not slow"` and `cd web && npm run build && npm run lint && npm test` stay green after
  every task. New API sentences are English with a Greek entry in `app/i18n.py`; web strings only in
  `web/lib/messages.ts` (`en` + `el`).
- Ids: assessment `uuid4().hex[:10]`, paper `uuid4().hex[:8]`, question `uuid4().hex[:6]`, criterion `c1…`.
- Limits: 50 MB per file, 40 pages per paper, render long side 2000 px JPEG q85, ink map 48×64, model slots 6, CPU
  slots 4, answer excerpt 1,500 chars, prompt 2,000 chars, pairs kept ≥ 10 points (≤ 400), pair checks ≤ 15.
- All model calls: temperature 0, JSON only, one retry with the validation error.
- Commit after each task with `feat(api|web): …` / `test: …` / `docs: …`.

## Review focus (each pinned by a test)

1. Greek answers: `Σ`/`Λ`, `β` vs `b`, "β) O(n log n)" — `test_answers.py`.
2. Decimal comma `0,5`, thousands `1.000`, fractions `7/1000` — `test_answers.py`.
3. Hidden white text with instructions in a typed PDF is removed from what the grader sees and reported —
   `test_forensics.py::test_white_text_is_hidden_and_removed`, `test_api_assessments.py::test_hidden_text_not_sent_to_grader`.
4. A scan with an OCR text layer is still read by the vision model — `test_ingest.py::test_scan_with_ocr_layer_is_vision`.
5. Rubric changed while a paper is grading → re-graded once; overrides on unchanged questions kept —
   `test_pipeline.py::test_regrade_after_rubric_change_keeps_overrides`.
6. Restart mid-run → nothing stuck in `reading`/`grading` — `test_pipeline.py::test_recovery_requeues`.
7. Printed exam template must not make every pair "same layout" — `test_similarity.py::test_template_removed_from_layout`.
8. Phrasing half the class shares is not evidence — `test_similarity.py::test_common_phrases_ignored`.
9. Professor overrides written while grading runs survive — `test_pipeline.py::test_override_during_grading_survives`.

---

## Phase A — API

### A1. Config, model wrappers, dependencies
Files: `app/config.py`, `app/llm.py`, `pyproject.toml` (+`pypdfium2`), `tests/test_config.py`, `tests/fakes.py`.
- `Settings`: `vision_model`, `verify_model`, `grading_model`, `grading_concurrency` (env per design §15).
- `BedrockLLM(settings, model=None, temperature=0.4, max_tokens=8000, adaptive=False)`; `BedrockVision(settings,
  model)` → `__call__(system, prompt, images: list[bytes]) -> str` (JPEG blocks); type `VisionLLM`.
- Fakes: `ScriptedVision` (responses or a function of (prompt, images)), `FnLLM` (a function of (system, messages)).

### A2. Models and store
Files: `app/assess/__init__.py`, `app/assess/models.py`, `app/assess/store.py`, `tests/test_assess_store.py`.
- Models exactly as design §4 (+ `AssessmentView`, `AssessmentSummary`, `Stats`).
- `AssessmentStore(root)`: `create`, `get`, `list`, `delete`, `mutate(aid, fn)`, `paper(aid, pid)`,
  `mutate_paper(aid, pid, fn)` (writes `paper.json` and refreshes its `PaperRow` under the assessment lock),
  `add_paper(aid, paper, source_bytes, ext)`, `remove_paper`, `paper_dir`, `exam_dir`, `exam_text`, `reset_busy(aid)`.
- Tests: rows follow papers; atomic writes; not-found for bad ids (`../x`); reset maps reading→queued, grading→read.

### A3. Answers and scoring
Files: `app/assess/answers.py`, `app/assess/scoring.py`, `tests/test_answers.py`, `tests/test_scoring.py`.
- `normalize_text`, `parse_true_false`, `parse_choices(final, options)`, `parse_numbers(final) -> list[float]`
  (ambiguity → several), `short_matches(final, key)`; `score_result(question, raw, language) -> QuestionResult`
  (design §6.4 table), `effective_points`, `grade_of(points, max, scale)`, `needs_review(paper)`.

### A4. Ingest and pages
Files: `app/assess/ingest.py`, `tests/test_ingest.py`.
- `sniff(data) -> "pdf"|"jpg"|"png"|None`, `split_upload(filename, data, split_every) -> list[Upload]`
  (limits, encrypted → error), `render_pages(source, out_dir) -> list[PageInfo]` (pypdfium2 / Pillow),
  `page_kinds(pdf)`: visible letters ≥ 40 and not (one image ≥ 80 % of the page + text) → text, `ink_map`, `dhash`.

### A5. Forensics
Files: `app/assess/forensics.py`, `tests/test_forensics.py`.
- `analyze(source, kind, rendered pages) -> (Forensics, visible_text_by_page)`; hidden-text detection by glyph boxes
  vs rendered pixels + render mode + size + crop box; metadata/XMP/IDs/fonts/revisions/signatures/JS/attachments;
  embedded images: EXIF, C2PA/JUMBF, `trainedAlgorithmicMedia`; invisible chars, homoglyph words, chat/citation
  artifacts, grader-addressing phrases.

### A6. Reading
Files: `app/assess/reading.py`, `tests/test_reading.py`.
- `READ_PROMPT`; `read_page(vision, image) -> (PageReading, name, sid)`; tolerant parsing (missing fields, blocks
  as strings), 2 attempts; `reading_text(paper) -> str` for the grader.

### A7. Rubric
Files: `app/assess/rubric.py`, `tests/test_rubric.py`.
- `draft_from_text(llm, exam_text, language)`, `draft_from_images(vision, images, language)`,
  `draft_from_papers(llm, readings, language)`; `normalize_rubric(questions)` (ids, defaults, criteria rescale);
  `validate_for_confirm(questions)` (422 messages); `changed_questions(old, new)`.

### A8. Grading
Files: `app/assess/grading.py`, `tests/test_grading.py`.
- `build_grading_prompt(assessment, paper)` (keys per §6.3), `grade_paper(llm, assessment, paper)`;
  `second_reading(vision, assessment, paper, results)`; `merge_overrides(old, new, changed)`.

### A9. AI signals
Files: `app/assess/lexicon.py`, `app/assess/signals.py`, `tests/test_signals.py`.
- `student_text(paper, exam_text)`, `ai_analysis(text, typed, llm_likelihood, llm_reasons, language)`,
  `class_ai_adjust(papers)` (over-elaboration).

### A10. Similarity, stats, class analysis
Files: `app/assess/similarity.py`, `app/assess/stats.py`, `app/assess/classwork.py`, tests for each.
- `pair_signals(papers, clusters, ink, forensics)`, `combine`; `stats(assessment, papers)`;
  `run_class_analysis(llm, store, aid)` (clusters → pairs → pair checks → AI class signal → insights → rows).

### A11. Pipeline
Files: `app/assess/pipeline.py`, `tests/test_assess_pipeline.py`.
- `AssessmentPipeline(app)`: `schedule_paper`, `schedule_all`, `draft_rubric`, `schedule_class`, `pause`, `resume`,
  `recover`, `cancel_all(aid)`; the per-paper job (render → forensics → read → grade → second reading → signals),
  coalescing and rubric-version checks.

### A12. Routes and wiring
Files: `app/routes/assessments.py`, `app/main.py`, `app/i18n.py`, `tests/test_api_assessments.py`.
- Every endpoint of design §11; `create_app(..., vision=, verifier=, grader=)`; lifespan recovery.

### A13. Exports
Files: `app/assess/export.py`, `app/assets/report.css`, tests.
- `grades_csv(assessment, papers)` (BOM, `;`-free CSV with comma, Greek headers when language el);
  `report_pdf(assessment, papers, stats)` (WeasyPrint, Lara fonts).

## Phase B — Web

### B1. Types, API client, messages
`lib/types.ts`, `lib/api.ts`, `lib/messages.ts`, `lib/assess.ts` + `lib/assess.test.ts`.

### B2. Shell and section pages
`components/AppNav.tsx`, `app/layout.tsx`, `components/ProjectTile.tsx`, `app/page.tsx` (overview),
`app/animations/page.tsx`, `app/slides/page.tsx`, `app/new/page.tsx`, `components/Icon.tsx`.

### B3. Assessment list and setup
`app/assessments/page.tsx`, `components/assess/AssessmentTile.tsx`, `app/new/assessment/page.tsx`,
`components/assess/PaperDrop.tsx`, `lib/upload.ts` (batching).

### B4. Workspace, overview, charts
`app/assessments/[id]/page.tsx`, `lib/useAssessment.ts`, `components/assess/{AssessmentHeader,ProgressStrip,
OverviewTab,charts}.tsx` (load the dataviz skill first).

### B5. Students table, rubric editor, integrity tab
`components/assess/{StudentsTable,RubricEditor,IntegrityTab,ScoreChip,SimilarityMatrix}.tsx`.

### B6. Paper page and compare page
`app/assessments/[id]/students/[sid]/page.tsx`, `app/assessments/[id]/compare/[a]/[b]/page.tsx`,
`components/assess/{PaperViewer,GradingPanel,QuestionCard,SignalList,ForensicsPanel}.tsx`.

### B7. Export menu
`components/assess/AssessmentExport.tsx`.

## Phase C — Quality

### C1. Synthetic class + live evaluation
`api/scripts/make_exam_class.py` (exam, truth, handwritten-looking scans with Greek-capable handwriting fonts —
Mynerve, Mansalva, Playpen Sans, Comic Relief — downloaded on first use; typed PDFs; planted copy/AI/hidden-text
cases) and `api/scripts/eval_assessment.py` (runs the real pipeline in-process and scores it against the truth).
Iterate prompts, model choice and thresholds until the targets of design §14 hold; record results in
`docs/assessments/2026-10-02-assessments-evaluation.md`.

### C2. Browser QA
`web/qa/assess-flow.mjs` (setup + upload + rubric + paper review + export), `web/qa/assess-screens.mjs`
(screenshots at 1440/1024/390), a11y and console checks on every new page; fix everything found.

### C3. Docs
README section (Assessments, dashboard, env vars), `docs/assessments/README.md` status.
