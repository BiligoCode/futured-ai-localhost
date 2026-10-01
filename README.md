# Lara — Learning Assessment & Resource Automation

Upload your course material, name a concept, and Lara drafts a script, writes and renders a
[Manim](https://www.manim.community/) animation for it, and narrates it with an AI voice or your own voice.
Greek and English.

**Flow:** Setup (concept, material, style & tone, length) → Script (edit / reorder / approve) → one video.
The professor only ever sees a single video:

- **Ask for a change** in plain words ("when the array gets iterated…", "at 0:32 …"). Lara works out which
  part of the video is meant (using timestamps and the paused player position as hints) and changes its
  animation, its narration, or both. Only that part is re-rendered and re-encoded.
- **Record your voice** over the whole animation. Pause the animation at any moment to explain longer
  (Space); the pause is kept in the final video as a held frame. Re-record from any point later.
- **AI voice** narrates the whole script instead.

**Layout quality gate.** Every render runs through `app/manim_runner.py`, which checks the frame after each
animation for text drawn on top of other text, text cut off by the frame edge, and unreadably small text.
Problems go back to the model with coordinates (like a crash would) for up to two fixes; if they persist,
the cleanest render is kept and the remaining issues are stored on the scene (`layout_issues`).

```
api/   FastAPI service: Bedrock LLM, Manim rendering, ElevenLabs TTS, ffmpeg
web/   Next.js dashboard
data/  projects on disk (git-ignored)
```

## Prerequisites

- ffmpeg/ffprobe, a LaTeX distribution with `dvisvgm` (for Manim's `MathTex`), Cairo/Pango (Manim)
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`) — Python 3.12 is installed by uv
- Node 22+

## Configuration (`.env` in the repo root)

| Variable | Default | Notes |
|---|---|---|
| `AWS_BEDROCK_ACCESS_KEY_ID` / `AWS_BEDROCK_SECRET_ACCESS_KEY` | — | Bedrock credentials |
| `AWS_BEDROCK_REGION` | `us-east-1` | |
| `AWS_BEDROCK_MODEL` | `zai.glm-5` | Any Bedrock Converse model. The hackathon account blocks Claude; GLM-5 won a Manim code bake-off (runner-up `deepseek.v3.2`). |
| `ELEVENLABS_API_KEY` | — | AI narration (`eleven_multilingual_v2`, speaks Greek) |
| `ELEVENLABS_VOICE_ID` | `JBFqnCBsd6RMkjVDRZzb` | |
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
cd web && npm run build && npm run lint
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
