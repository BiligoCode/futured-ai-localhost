"""Build a complete demo project headlessly (storyboard → scenes → AI voice → export).

Run the night before the pitch so the dashboard has a finished project to fall back on:

    uv run python scripts/seed_demo.py --concept "Κάθοδος κλίσης" --pdf notes.pdf --language el
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_settings  # noqa: E402
from app.export import export_project  # noqa: E402
from app.ingest import build_material  # noqa: E402
from app.llm import BedrockLLM  # noqa: E402
from app.pipeline import build_scene  # noqa: E402
from app.render import make_renderer  # noqa: E402
from app.store import ProjectStore  # noqa: E402
from app.storyboard import generate_storyboard  # noqa: E402
from app.tts import CachedTTS, ElevenLabsTTS  # noqa: E402
from app.voice import generate_ai_voice  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--concept", required=True)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--text", default="")
    parser.add_argument("--language", choices=["el", "en"], default="el")
    parser.add_argument("--style", default="")
    parser.add_argument("--tone", default="")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    settings = load_settings()
    store = ProjectStore(settings.data_dir)
    llm = BedrockLLM(settings)
    renderer = make_renderer(settings)
    tts = CachedTTS(ElevenLabsTTS(settings.elevenlabs_api_key, settings.elevenlabs_voice_id),
                    settings.data_dir / "tts_cache")

    material = build_material(args.pdf.read_bytes() if args.pdf else None, args.text)
    print(f"Drafting storyboard with {settings.bedrock_model}…")
    title, drafts = await asyncio.to_thread(generate_storyboard, llm, material=material, concept=args.concept,
                                            style=args.style, tone=args.tone, language=args.language)
    project = store.create(title=title, concept=args.concept, style=args.style, tone=args.tone,
                           language=args.language, material_text=material, scenes=drafts)
    await store.mutate(project.id, lambda p: setattr(p, "stage", "scenes"))
    print(f"Project {project.id}: {title} ({len(drafts)} scenes). Rendering at quality '{settings.render_quality}'…")

    await asyncio.gather(*[build_scene(store, llm, renderer, project.id, s.id) for s in project.scenes])
    failed = [s for s in store.get(project.id).scenes if s.render_status == "failed"]
    if failed:
        print(f"Retrying {len(failed)} failed scene(s)…")
        await asyncio.gather(*[build_scene(store, llm, renderer, project.id, s.id) for s in failed])

    project = store.get(project.id)
    for i, s in enumerate(project.scenes, 1):
        print(f"  {i}. {s.title}: {s.render_status} after {s.attempts} attempt(s)")
    if any(s.render_status == "failed" for s in project.scenes):
        print("Some scenes failed; fix them in the dashboard, then export there.")
        return 1

    print("Generating AI narration…")
    for s in project.scenes:
        await generate_ai_voice(store, tts, project.id, s.id)
    out = await export_project(store, project.id)
    print(f"Done. Export: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
