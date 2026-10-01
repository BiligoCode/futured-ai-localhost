# Educator Visual Explanations — Manim + Narration Pipeline (Design)

Date: 2026-10-01
Status: Draft for review

## Context & intent

Hackathon project (education). An AI platform for **educators** (professors, tutors), not students. This spec covers only the first sub-project and the pitch's headline feature: **AI-generated Manim animations tailored to the professor's course material, narrated by an AI voice or by the professor.**

- Team: 1 developer, ~20 hours of build time, 7-minute pitch.
- Judging: AI Innovation, Real World Impact, Presentation (each 1–5).
- Primary output language: **Greek**; English must also work.
- Professor stays in control at every step (approve storyboard, revise scenes, choose voice).

Out of scope for this spec (future sub-projects): question/assignment generation, grading, plagiarism/AI-use detection, LMS integration, auth, multi-user.

Deferred follow-ups (first candidates after this spec ships):
1. Auto-captions on every export (from script for AI voice, transcription for professor voice).
2. Vision-model check of rendered frames + plain-language audio description of each scene (for blind/low-vision educators).
3. Amazon Polly as an alternative TTS provider.

## User flow

1. **Setup** — Professor uploads course material (PDF) and/or pastes text, types the concept to explain, optional style and tone, picks language (`el` or `en`).
2. **Storyboard** — AI proposes 4–6 scenes. Each scene: `title`, `visual` (what is shown on screen), `narration` (what is said). Professor edits text, reorders, deletes, adds scenes, then approves. Nothing renders before approval.
3. **Scenes** — Each scene is generated as Manim code by the LLM and rendered, in parallel. On render error the error output is fed back to the LLM to repair. Professor previews each clip and can type a revision instruction per scene; only that scene is regenerated.
4. **Voice & Export** — Per scene, professor chooses **AI voice** (ElevenLabs) or **records their own voice** in a teleprompter view (record / stop / play back / retake). Scenes can mix sources. Export joins everything into one MP4.

## Architecture

Monorepo:
- `api/` — Python 3.12 (managed with `uv`), FastAPI. Owns LLM calls, Manim rendering, TTS, ffmpeg.
- `web/` — Next.js (App Router, TypeScript, Tailwind). Talks to `api/` over REST (CORS), polls for job status.
- `data/` — file-based storage, git-ignored. No database.

### Storage layout

```
data/projects/<project_id>/
  project.json
  material.txt
  scenes/<scene_id>/
    code_v<N>.py
    render_v<N>.mp4
    voice.webm          (raw professor upload, if any)
    audio.wav           (normalized audio actually used: AI or professor)
  export.mp4
data/tts_cache/<sha256>.mp3
```

### Data model (`project.json`)

Project: `id`, `created_at`, `title`, `concept`, `style`, `tone`, `language` (`"el" | "en"`), `stage` (`"storyboard" | "scenes"`), `scenes: Scene[]` (list order = scene order).

Scene: `id`, `title`, `visual`, `narration`, `code_version` (int, 0 = none), `render_status` (`"pending" | "generating" | "rendering" | "repairing" | "done" | "failed"`), `attempts` (int), `last_error` (str | null), `audio_source` (`"ai" | "professor" | null`), `audio_status` (`"none" | "generating" | "done" | "failed"`).

### Generation approach (chosen: free-form code generation)

The LLM writes a **complete Manim Community Edition scene file** per storyboard scene — no helper library or template menu. Reliability comes from:
- Each generation prompt includes the scene's `visual` + `narration`, the concept, style, and the first 8,000 characters of course material (so notation and examples match the course).
- A system prompt stating the installed Manim version, required class name `GeneratedScene`, a 16:9 frame, and the target duration (estimated from narration length at 2.5 words/second).
- Language rule: all natural-language text (Greek or English) uses `Text(..., font="DejaVu Sans")`; `MathTex`/`Tex` only for pure math. (LaTeX breaks on Greek prose; Pango does not.)
- Pre-render check: the code must parse (`ast.parse`) and define `class GeneratedScene`. A failed check counts as a failed attempt and goes to repair, without spending a render.
- **Repair loop:** 1 generation + up to 3 repairs (max 4 render attempts). Repair prompt receives the code and the last 3,000 characters of the error output. After the last failure the scene is `failed`, the error is shown, and the professor can retry or revise. If the scene already had a good render (a failed revision), it stays `done` on that previous version (still exportable) with `last_error` shown as "previous version kept".
- Render timeout: 180 s per attempt; a timeout is a failed attempt with error text `"Render timed out after 180s"`.
- **Revise:** current code + scene description + narration + professor's instruction → new code version, then the same check/render/repair loop.

### Rendering

`manim -q<quality> --format mp4` in a subprocess, max **4 concurrent renders**. Quality from config `RENDER_QUALITY` (`l` = 480p15 for development, `m` = 720p30, default `m`).

### Voice

- `TTSProvider` interface: `synthesize(text, language) -> bytes (mp3)`. First implementation: ElevenLabs REST API, model `eleven_multilingual_v2`, voice from `ELEVENLABS_VOICE_ID`. Results cached by sha256 of `(provider, voice, model, text)`.
- Professor recording: browser `MediaRecorder` (webm/opus) uploaded per scene. Every audio source is normalized with ffmpeg to `audio.wav` (44.1 kHz mono) because browser webm files often lack duration metadata.
- Editing a scene's narration clears its AI audio (`audio_status = "none"`) but keeps professor recordings.

### Export

Per scene, with `D_v` = clip duration and `D_a` = audio duration:
- output duration `D = max(D_v, D_a + 0.3)`; the video's last frame is held (`tpad=stop_mode=clone`) and the audio padded with silence to `D`;
- scenes without audio get a silent track for `D_v`;
- all segments normalized to 1280×720, 30 fps, H.264 yuv420p, AAC 44.1 kHz, then concatenated → `export.mp4`.

### LLM

AWS Bedrock Converse API via boto3, credentials from `.env`: `AWS_BEDROCK_ACCESS_KEY_ID`, `AWS_BEDROCK_SECRET_ACCESS_KEY`, `AWS_BEDROCK_REGION` (default `us-east-1`), `AWS_BEDROCK_MODEL` (default `zai.glm-5`, chosen by a Manim codegen comparison of 6 invokable models on 2 Greek scenes: cleanest layouts, first-try renders, ~25 s per 2 scenes; `deepseek.v3.2` was runner-up). The hackathon AWS account's organization policy blocks every Anthropic Claude model (only cross-region profiles exist, and their destination regions are denied), so the default is an in-region open model; the code is model-agnostic via Converse. Course material sent to the LLM is truncated to 60,000 characters.

### Error handling

- PDF with no extractable text and no pasted text → HTTP 422 `"No readable text found in the uploaded material"`.
- Storyboard LLM output that is not valid JSON after one retry → HTTP 502 with message; any other LLM/network error → HTTP 502 `"The AI model request failed: …"`.
- A failed AI-voice attempt keeps an existing voice (status restored to `done`).
- On API startup, scenes stuck in `generating | rendering | repairing` (server restarted mid-job) become `failed` with `last_error = "Interrupted by server restart"` (or stay `done` on their previous version if they had one); audio stuck in `generating` becomes `failed`.
- All job failures are visible in the UI per scene; nothing fails silently.

### Pitch safety

A seed script pre-generates a complete Greek demo project (storyboard, rendered scenes, AI audio, export), so the pitch can fall back to cached output if a live render fails.

## Testing

- `api/`: pytest. LLM and TTS are injected and faked in unit tests. Manim and ffmpeg are exercised for real in tests marked `slow`.
- `web/`: `npm run build` (typecheck + build) plus a manual browser checklist per step.
