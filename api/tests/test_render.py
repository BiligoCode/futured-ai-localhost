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


SCREENSHOT_BUG = scene_with("""values = [2, 5, 8, 12, 16, 23]
        boxes = VGroup(*[Square(0.9) for _ in values]).arrange(RIGHT, buff=0.05)
        nums = VGroup(*[Text(str(v), font="DejaVu Sans", font_size=30) for v in values])
        self.play(Create(boxes), Write(nums))
        self.play(Write(Text("Βρέθηκε στη θέση 5", font="DejaVu Sans").to_edge(DOWN)))
        self.play(Write(Text("Βρέθηκε!", font="DejaVu Sans").to_edge(DOWN)))""")

CLEAN_LAYOUT = scene_with("""cells = VGroup(*[VGroup(Square(0.9), Text(str(v), font="DejaVu Sans", font_size=30))
                        for v in [2, 5, 8, 12, 16, 23]]).arrange(RIGHT, buff=0.05)
        for c in cells:
            c[1].move_to(c[0])
        first = Text("Βρέθηκε στη θέση 5", font="DejaVu Sans").to_edge(DOWN, buff=1.5)
        self.play(Create(cells), Write(first))
        self.play(ReplacementTransform(first, Text("Βρέθηκε!", font="DejaVu Sans").to_edge(DOWN, buff=1.5)))""")


@pytest.mark.slow
async def test_layout_check_reports_stacked_labels_and_captions(tmp_path):
    code = tmp_path / "code_v1.py"
    code.write_text(SCREENSHOT_BUG, encoding="utf-8")
    r = await render_scene(code, tmp_path / "render_v1.mp4", quality="l", timeout_s=180)
    assert r.ok, r.error
    overlaps = [i for i in r.issues if "drawn on top of each other" in i]
    assert len(overlaps) == 2
    assert "6 texts are drawn on top of each other" in overlaps[0]
    assert 'Text "Βρέθηκε στη θέση 5"' in overlaps[1] and 'Text "Βρέθηκε!"' in overlaps[1]
    # Both captions also sit on the bottom edge, which is reserved for burned-in captions.
    assert any("caption strip" in i for i in r.issues)


@pytest.mark.slow
async def test_layout_check_passes_clean_scene(tmp_path):
    code = tmp_path / "code_v1.py"
    code.write_text(CLEAN_LAYOUT, encoding="utf-8")
    r = await render_scene(code, tmp_path / "render_v1.mp4", quality="l", timeout_s=180)
    assert r.ok and r.issues == []


@pytest.mark.slow
async def test_layout_check_flags_tiny_text_but_not_short_glyphs(tmp_path):
    code = tmp_path / "code_v1.py"
    code.write_text(scene_with("""self.play(Write(MathTex("=", font_size=36).shift(UP)))
        self.play(Write(Text("tiny", font="DejaVu Sans", font_size=30).scale(0.3).shift(DOWN)))"""),
                    encoding="utf-8")
    r = await render_scene(code, tmp_path / "render_v1.mp4", quality="l", timeout_s=180)
    assert r.ok and r.issues == ['At 2.0s: Text "tiny" is too small to read.']


@pytest.mark.slow
async def test_layout_check_reports_where_cut_off_text_is(tmp_path):
    code = tmp_path / "code_v1.py"
    code.write_text(scene_with('self.play(Write(Text("Πολυπλοκότητα", font="DejaVu Sans").move_to(LEFT * 6)))'),
                    encoding="utf-8")
    r = await render_scene(code, tmp_path / "render_v1.mp4", quality="l", timeout_s=180)
    [issue] = r.issues
    assert "cut off by the edge of the frame: it spans x -" in issue and "visible frame is x -7.11..7.11" in issue


@pytest.mark.slow
async def test_layout_check_keeps_the_caption_strip_free(tmp_path):
    code = tmp_path / "code_v1.py"
    code.write_text(scene_with("""self.add(NumberPlane())  # full-frame backgrounds are fine
        self.play(Create(Square(1).to_edge(DOWN, buff=0.2)))"""), encoding="utf-8")
    r = await render_scene(code, tmp_path / "render_v1.mp4", quality="l", timeout_s=180)
    [issue] = r.issues
    assert issue.startswith("At 1.0s: Square reaches into the caption strip") and "below y -2.70" in issue
