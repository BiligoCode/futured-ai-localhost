import asyncio
import time

import pytest

from app import render
from app.render import ERROR_TAIL_CHARS, RenderResult, render_scene
from tests.conftest import make_settings

GOOD = '''from manim import *
class GeneratedScene(Scene):
    def construct(self):
        self.play(Write(Text("Κάθοδος κλίσης", font="DejaVu Sans")))
        self.play(Write(MathTex(r"\\nabla f(x)")))
'''


def scene_with(body: str) -> str:
    return f"from manim import *\nclass GeneratedScene(Scene):\n    def construct(self):\n        {body}\n"


@pytest.mark.slow
async def test_renders_greek_and_math(tmp_path):
    code = tmp_path / "code_v1.py"
    code.write_text(GOOD, encoding="utf-8")
    out = tmp_path / "render_v1.mp4"
    r = await render_scene(code, out, quality="l", timeout_s=180)
    assert r.ok, r.error
    assert out.stat().st_size > 0


@pytest.mark.slow
async def test_reports_error_tail(tmp_path):
    code = tmp_path / "code_v1.py"
    code.write_text(scene_with("undefined_name()"), encoding="utf-8")
    out = tmp_path / "render_v1.mp4"
    r = await render_scene(code, out, quality="l", timeout_s=180)
    assert not r.ok
    assert "NameError" in r.error and len(r.error) <= ERROR_TAIL_CHARS
    assert not out.exists()


@pytest.mark.slow
async def test_timeout_kills_render(tmp_path):
    code = tmp_path / "code_v1.py"
    code.write_text(scene_with("self.wait(600)"), encoding="utf-8")
    start = time.monotonic()
    r = await render_scene(code, tmp_path / "render_v1.mp4", quality="l", timeout_s=5)
    assert not r.ok and r.error == "Render timed out after 5s"
    assert time.monotonic() - start < 20


async def test_make_renderer_limits_concurrency(tmp_path, monkeypatch):
    active = peak = 0

    async def fake(code, out, *, quality, timeout_s):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1
        return RenderResult(ok=True)

    monkeypatch.setattr(render, "render_scene", fake)
    r = render.make_renderer(make_settings(tmp_path, max_concurrent_renders=2))
    await asyncio.gather(*[r(tmp_path / f"{i}.py", tmp_path / f"{i}.mp4") for i in range(5)])
    assert peak == 2
