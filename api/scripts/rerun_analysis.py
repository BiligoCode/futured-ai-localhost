"""Re-run only the class analysis of an assessment (real grading model), e.g. after changing its prompts or weights.

    cd api && uv run python scripts/rerun_analysis.py DATA_DIR ASSESSMENT_ID

Prints the pairs that score 30 or more, with their evidence and the model's verdict."""
import asyncio
import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.assess.classwork import run_class_analysis  # noqa: E402
from app.assess.store import AssessmentStore  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.llm import BedrockLLM  # noqa: E402


async def main(data_dir: Path, aid: str) -> None:
    settings = dataclasses.replace(load_settings(), data_dir=data_dir)
    store = AssessmentStore(data_dir)
    llm = BedrockLLM(settings, model=settings.grading_model or settings.bedrock_model, temperature=0, max_tokens=12000, adaptive=True)
    slots = asyncio.Semaphore(settings.grading_concurrency)

    async def call(fn, *args, **kwargs):
        async with slots:
            return await asyncio.to_thread(fn, *args, **kwargs)
    await run_class_analysis(store, aid, llm, call)
    a = store.get(aid)
    names = {r.id: r.filename for r in a.papers}
    for p in a.analysis.pairs:
        if p.score >= 30:
            print(f"{names[p.a]}–{names[p.b]} {p.score} {p.verdict} {[(e.code, e.strength) for e in p.evidence]}")
            for x in p.shared:
                print(f"    shared{' (rare)' if x.rare else ''}: {x.what} — «{x.a[:80]}» / «{x.b[:80]}»")
    print("status:", a.analysis.status, a.analysis.error or "")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    asyncio.run(main(Path(sys.argv[1]), sys.argv[2]))
