import ast
import builtins
import re
from functools import lru_cache
from importlib.metadata import version

from app.llm import LLM
from app.models import Language, Scene
from app.parsing import extract_code_block
from app.render import ERROR_TAIL_CHARS
from app.storyboard import language_name

MAX_REPAIRS = 3
CODEGEN_MATERIAL_CHARS = 12000
WORDS_PER_SECOND = 2.5
MIN_TARGET_SECONDS = 6

SYSTEM_PROMPT = """You are an expert Manim Community Edition v{manim_version} developer creating a 16:9 \
educational animation for university students.

Output exactly one ```python code block containing a complete file that:
- starts with `from manim import *`
- defines `class GeneratedScene(Scene)` (MovingCameraScene or ThreeDScene are also allowed) with a `construct` method.

Rules:
- All natural-language text shown on screen is in {language}, written with `Text(..., font="DejaVu Sans")`.
- Use `MathTex`/`Tex` only for mathematical expressions, never for sentences or {language} words.
- Never write the narration as on-screen text: it is spoken by a voice. On screen show only short \
titles, labels and formulas.
- Keep text readable: titles `font_size=40` or larger, labels and formulas `font_size=30` or larger.
- Layout (an automatic check rejects overlapping or cut-off text, so follow these exactly):
  - The bottom strip of the frame (below y = -2.7) is reserved for captions: never place or move anything \
there. Reserve zones: the title at the top (`.to_edge(UP)`), the main visual in the middle, at most one short \
status line just above the caption strip (`.to_edge(DOWN, buff=1.5)`). Formulas and side notes go in an upper \
corner or `.next_to` the visual, never on top of it.
  - A label that belongs to a shape is placed on that shape: build each element as \
`VGroup(box, Text(...).move_to(box))` (or `.next_to(box, DOWN)` for index labels). Never create a group of labels and \
position the group as a whole: every `Text`, `MathTex` and number must be moved to its own place.
  - Size labels to fit inside their shape (e.g. `label.scale_to_fit_width(box.width * 0.7)` when needed). \
Wide rows (arrays, lists) must fit the frame: `.scale_to_fit_width(config.frame_width - 1)` if needed.
  - One text per slot: before showing a new caption or status where another one is, use \
`ReplacementTransform(old, new)` or `FadeOut(old)` first. Never `Write` a second text on an occupied spot.
  - `FadeOut` elements you no longer need before adding new ones.
- Use the current API: `Create` (not ShowCreation), `axes.plot` (not get_graph), `Axes(x_range=[...], \
y_range=[...])`, `Text`/`MathTex` (not TextMobject/TexMobject), `Surface` (not ParametricSurface).
- No external files, images, sounds, or network access.
- The animation should last about the target duration; pad with `self.wait(...)` if needed.
- Precision: animate exactly what the scene description asks, with its actual values, symbols and steps, in the \
order the narration explains them. Every element on screen must carry part of the explanation: no decorative \
shapes, generic icons, or text-only slides. Show the method working (values changing, pointers moving, cells \
filling, terms transforming), one step at a time.
- Continuity: this scene is one part of a single video. Reuse the example values, notation and colors of the \
other parts listed in the brief, so the parts fit together.
- Prefer clear, uncluttered visuals: one idea at a time, consistent colors, smooth transitions."""


def _issue_list(issues: list[str]) -> str:
    return "\n".join(f"- {issue}" for issue in issues)


def target_seconds(narration: str) -> int:
    return max(MIN_TARGET_SECONDS, round(len(narration.split()) / WORDS_PER_SECOND))


def build_system_prompt(language: Language) -> str:
    return SYSTEM_PROMPT.format(manim_version=version("manim"), language=language_name(language))


def precheck(code: str) -> str | None:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"SyntaxError: {exc.msg} (line {exc.lineno})"
    if not any(isinstance(n, ast.ClassDef) and n.name == "GeneratedScene" for n in ast.walk(tree)):
        return "Code must define class GeneratedScene"
    return _greek_in_latex(tree) or _undefined_name(tree)


_GREEK = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")
_LATEX_CLASSES = {"MathTex", "Tex", "SingleStringMathTex", "TexTemplate"}


def _greek_in_latex(tree: ast.AST) -> str | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _LATEX_CLASSES:
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and _GREEK.search(arg.value):
                    return (f"Line {node.lineno}: {node.func.id}({arg.value!r}) contains Greek letters, which LaTeX "
                            "cannot render here. Write Greek words with Text(..., font=\"DejaVu Sans\") and Greek "
                            "math symbols with LaTeX commands such as \\alpha, \\pi.")
    return None


@lru_cache(maxsize=1)
def _manim_names() -> frozenset[str]:
    import manim  # imported lazily: it is slow, and only the checks need it

    return frozenset(dir(manim)) | frozenset(dir(builtins))


def _bound_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, ast.MatchAs) and node.name:
            names.add(node.name)
    return names


def _undefined_name(tree: ast.AST) -> str | None:
    """A name used but neither defined in the file nor provided by Manim (e.g. a color like BROWN)."""
    if any(isinstance(n, ast.ImportFrom) and n.module not in ("manim", "__future__") for n in ast.walk(tree)):
        return None  # other star imports could provide anything
    known = _manim_names() | _bound_names(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in known:
            hint = (" For a color use an existing Manim constant (e.g. GREY_BROWN, TEAL) or a hex string like "
                    "\"#8B4513\"." if node.id.isupper() else "")
            return (f"Line {node.lineno}: NameError: name '{node.id}' is not defined and is not part of Manim "
                    f"{version('manim')}. Define it or use an existing Manim name.{hint}")
    return None


def _ask(llm: LLM, language: Language, user: str) -> str:
    return extract_code_block(llm(build_system_prompt(language), [{"role": "user", "content": user}]))


def _scene_brief(scene: Scene) -> str:
    return (f"Scene title: {scene.title}\n"
            f"What is shown on screen: {scene.visual}\n"
            f"Narration spoken during the scene: {scene.narration}\n"
            f"Target duration: {target_seconds(scene.narration)} seconds")


def outline(scenes: list[Scene], current: str) -> str:
    """The whole video in brief, so each scene keeps the same example, notation and colors as the others."""
    lines = []
    for i, s in enumerate(scenes, 1):
        mark = "  <- this scene" if s.id == current else ""
        lines.append(f"Part {i}: {s.title}: {s.visual[:300]}{mark}")
    return "\n".join(lines)


def generate_code(llm: LLM, scene: Scene, *, concept: str, style: str, material: str,
                  language: Language, video_outline: str = "") -> str:
    whole = f"The whole video, part by part:\n{video_outline}\n\n" if video_outline else ""
    user = (f"Concept being explained: {concept}\n"
            f"Style and tone requested by the professor: {style or 'clean and minimal'}\n\n"
            f"{whole}"
            f"{_scene_brief(scene)}\n\n"
            "Course material from the professor (reuse its notation, symbols and examples):\n<<<\n"
            f"{material[:CODEGEN_MATERIAL_CHARS]}\n>>>\n\n"
            "Write the complete Manim file for this scene.")
    return _ask(llm, language, user)


def repair_code(llm: LLM, code: str, error: str, *, language: Language) -> str:
    user = (f"This Manim file failed:\n```python\n{code}\n```\n\n"
            f"The render failed with this error:\n```\n{error[-ERROR_TAIL_CHARS:]}\n```\n\n"
            "Fix the problem and return the full corrected file.")
    return _ask(llm, language, user)


def revise_code(llm: LLM, code: str, scene: Scene, instruction: str, *, language: Language) -> str:
    user = (f"{_scene_brief(scene)}\n\nCurrent Manim file:\n```python\n{code}\n```\n\n"
            f"The professor asked for this change: {instruction}\n\n"
            "Apply the change, keep the rest of the scene as it is, and return the full updated file.")
    return _ask(llm, language, user)


def fix_layout(llm: LLM, code: str, issues: list[str], *, language: Language) -> str:
    user = (f"This Manim file renders, but an automatic layout check of the video found these problems:\n"
            f"{_issue_list(issues)}\n\n```python\n{code}\n```\n\n"
            "Fix every problem without changing what the animation explains: move each label onto its own shape "
            "or position, replace or fade out old text before showing new text in the same place, and keep "
            "everything inside the frame. For something cut off by the frame, place it relative to the edge "
            "(`.to_edge(LEFT, buff=0.5)`, `.to_corner(...)`) or shrink it, instead of moving it to fixed "
            "coordinates; check the target of every `.animate.move_to(...)` / `.shift(...)` too. Anything in "
            "the caption strip at the bottom must move up (above y = -2.7) or shrink. "
            "Return the full corrected file.")
    return _ask(llm, language, user)
