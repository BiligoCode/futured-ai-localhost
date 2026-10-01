import ast
from importlib.metadata import version

from app.llm import LLM
from app.models import Language, Scene
from app.parsing import extract_code_block
from app.render import ERROR_TAIL_CHARS
from app.storyboard import language_name

MAX_REPAIRS = 3
CODEGEN_MATERIAL_CHARS = 8000
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
- Keep every element inside the frame and never let text overlap: position with `.to_edge`, `.next_to`, \
`.arrange`, scale long text with `.scale_to_fit_width(config.frame_width - 1)`, and `FadeOut` elements \
you no longer need before adding new ones.
- Use the current API: `Create` (not ShowCreation), `axes.plot` (not get_graph), `Axes(x_range=[...], \
y_range=[...])`, `Text`/`MathTex` (not TextMobject/TexMobject), `Surface` (not ParametricSurface).
- No external files, images, sounds, or network access.
- The animation should last about the target duration; pad with `self.wait(...)` if needed.
- Prefer clear, uncluttered visuals: one idea at a time, consistent colors, smooth transitions."""


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
    return None


def _ask(llm: LLM, language: Language, user: str) -> str:
    return extract_code_block(llm(build_system_prompt(language), [{"role": "user", "content": user}]))


def _scene_brief(scene: Scene) -> str:
    return (f"Scene title: {scene.title}\n"
            f"What is shown on screen: {scene.visual}\n"
            f"Narration spoken during the scene: {scene.narration}\n"
            f"Target duration: {target_seconds(scene.narration)} seconds")


def generate_code(llm: LLM, scene: Scene, *, concept: str, style: str, material: str,
                  language: Language) -> str:
    user = (f"Concept being explained: {concept}\n"
            f"Visual style requested by the professor: {style or 'clean and minimal'}\n\n"
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
            "Apply the change and return the full updated file.")
    return _ask(llm, language, user)
