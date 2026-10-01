import asyncio
import json
import os
import shutil
import signal
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from app.config import Settings

ERROR_TAIL_CHARS = 3000
RUNNER = Path(__file__).with_name("manim_runner.py")


@dataclass
class RenderResult:
    ok: bool
    error: str = ""
    # Layout problems found while rendering (overlapping or cut-off text): the video exists but needs fixing.
    issues: list[str] = field(default_factory=list)


Renderer = Callable[[Path, Path], Awaitable[RenderResult]]


def _kill_group(proc: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


async def render_scene(code_path: Path, output_path: Path, *, quality: str, timeout_s: int) -> RenderResult:
    with tempfile.TemporaryDirectory(prefix="manim-") as tmp:
        report = Path(tmp) / "layout.json"
        cmd = [sys.executable, str(RUNNER), "render", f"-q{quality}", "--format", "mp4", "--disable_caching",
               "--media_dir", tmp, "-o", "out", str(Path(code_path).resolve()), "GeneratedScene"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=tmp, env={**os.environ, "LARA_LAYOUT_REPORT": str(report)},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, start_new_session=True)
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout_s)
        except asyncio.TimeoutError:
            _kill_group(proc)
            await proc.wait()
            return RenderResult(ok=False, error=f"Render timed out after {timeout_s}s")
        except asyncio.CancelledError:
            _kill_group(proc)
            raise
        output = stdout.decode("utf-8", errors="replace")
        produced = next(Path(tmp).rglob("out.mp4"), None)
        if proc.returncode != 0 or produced is None:
            return RenderResult(ok=False, error=output[-ERROR_TAIL_CHARS:] or "Render produced no video")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(produced), output_path)
        issues = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else []
        return RenderResult(ok=True, issues=issues)


def make_renderer(settings: Settings) -> Renderer:
    semaphore = asyncio.Semaphore(settings.max_concurrent_renders)

    async def renderer(code_path: Path, output_path: Path) -> RenderResult:
        async with semaphore:
            return await sys.modules[__name__].render_scene(
                code_path, output_path, quality=settings.render_quality, timeout_s=settings.render_timeout_s)

    return renderer
