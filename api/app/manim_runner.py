"""Run the Manim CLI with a layout check: after every animation, look for text that overlaps other text or leaves
the frame. Issues are written as JSON to the path in $LARA_LAYOUT_REPORT.

Runs as a standalone script (not imported by the API), so it only depends on Manim.
"""
import atexit
import json
import os
import sys

from manim import Mobject, Scene, config
from manim.__main__ import main

MAX_ISSUES = 8
OVERLAP_RATIO = 0.2   # share of the smaller text's box covered by the other one
FRAME_MARGIN = 0.05   # scene units a text may stick out of the frame before it counts as cut off
CAPTION_STRIP = 1.3  # scene units at the bottom of the default 8-unit-high frame, kept free for captions
MIN_FONT_SIZE = 14  # effective size on screen; the prompt asks for 30+ for labels

_TEXT_TYPES = ("Text", "MarkupText", "Paragraph", "MathTex", "Tex", "SingleStringMathTex",
               "DecimalNumber", "Integer", "Variable")

_issues: list[str] = []
_seen: set = set()


def _is_text(mob: Mobject) -> bool:
    return any(cls.__name__ in _TEXT_TYPES for cls in type(mob).__mro__)


def _texts(mobjects) -> list[Mobject]:
    """Top-most text-like mobjects on screen (we do not descend into a text's own glyphs)."""
    found: list[Mobject] = []

    def walk(mob: Mobject) -> None:
        if _is_text(mob):
            found.append(mob)
            return
        for sub in mob.submobjects:
            walk(sub)

    for mob in mobjects:
        walk(mob)
    return found


def _visible(mob: Mobject) -> bool:
    members = mob.family_members_with_points()
    if not members or mob.width < 1e-3 or mob.height < 1e-3:
        return False
    opacity = max(max(m.get_fill_opacity(), m.get_stroke_opacity()) for m in members)
    return opacity > 0.05


def _label(mob: Mobject) -> str:
    for attr in ("original_text", "text", "tex_string"):
        value = getattr(mob, attr, None)
        if isinstance(value, str) and value.strip():
            value = " ".join(value.split())
            return f'{type(mob).__name__} "{value[:40]}"'
    number = getattr(mob, "number", None)
    if number is not None:
        return f"{type(mob).__name__} {number}"
    return type(mob).__name__


def _font_size(mob: Mobject) -> float:
    """Effective font size after scaling. Bounding-box height would flag short glyphs such as "=" or "-"."""
    try:
        return float(mob.font_size)
    except (AttributeError, TypeError, ValueError, ZeroDivisionError):
        return mob.height / 0.0105  # digits are ~0.0105 scene units tall per point


def _box(mob: Mobject) -> tuple[float, float, float, float]:
    return mob.get_left()[0], mob.get_bottom()[1], mob.get_right()[0], mob.get_top()[1]


def _frame(scene: Scene) -> tuple[float, float, float, float]:
    frame = getattr(scene.camera, "frame", None)
    if frame is not None:
        return _box(frame)
    w, h = config.frame_width / 2, config.frame_height / 2
    return -w, -h, w, h


def _report(key, message: str) -> None:
    if key in _seen or len(_issues) >= MAX_ISSUES:
        return
    _seen.add(key)
    _issues.append(message)


def check(scene: Scene) -> None:
    if type(scene).__name__ == "ThreeDScene" or any(c.__name__ == "ThreeDScene" for c in type(scene).__mro__):
        return  # projected 3D boxes are not meaningful
    at = f"At {scene.renderer.time:.1f}s"
    texts = [t for t in _texts(scene.mobjects) if _visible(t)]
    fx0, fy0, fx1, fy1 = _frame(scene)
    zoom = config.frame_width / max(fx1 - fx0, 1e-6)  # a zoomed-in camera makes text larger on screen
    for t in texts:
        x0, y0, x1, y1 = _box(t)
        if x0 < fx0 - FRAME_MARGIN or x1 > fx1 + FRAME_MARGIN or y0 < fy0 - FRAME_MARGIN or y1 > fy1 + FRAME_MARGIN:
            _report(("frame", id(t)),
                    f"{at}: {_label(t)} is cut off by the edge of the frame: it spans x {x0:.2f}..{x1:.2f}, "
                    f"y {y0:.2f}..{y1:.2f}, but the visible frame is x {fx0:.2f}..{fx1:.2f}, y {fy0:.2f}..{fy1:.2f}.")
        if _font_size(t) * zoom < MIN_FONT_SIZE:
            _report(("small", id(t)), f"{at}: {_label(t)} is too small to read.")
    _check_caption_strip(scene, texts, at, (fx0, fy0, fx1, fy1))
    # Group texts drawn on top of each other into clusters, so twelve stacked labels are one issue, not 66.
    parent = list(range(len(texts)))

    def root(i: int) -> int:
        while parent[i] != i:
            i = parent[i]
        return i

    new_pairs = set()
    for i, a in enumerate(texts):
        for j in range(i + 1, len(texts)):
            if _overlaps(a, texts[j]):
                parent[root(j)] = root(i)
                pair = ("overlap", *sorted((id(a), id(texts[j]))))
                if pair not in _seen:
                    new_pairs.add(pair)
    clusters: dict[int, list[Mobject]] = {}
    for i, t in enumerate(texts):
        clusters.setdefault(root(i), []).append(t)
    for members in clusters.values():
        ids = {id(m) for m in members}
        fresh = {p for p in new_pairs if p[1] in ids}
        if len(members) < 2 or not fresh:
            continue
        _seen.update(fresh)
        names = ", ".join(_label(m) for m in members[:6]) + (", …" if len(members) > 6 else "")
        _report(("cluster", frozenset(ids)),
                f"{at}: {len(members)} texts are drawn on top of each other: {names}.")


def _check_caption_strip(scene: Scene, texts: list[Mobject], at: str, frame) -> None:
    """Captions are burned into the bottom strip of the video, so the animation must leave it empty."""
    fx0, fy0, fx1, fy1 = frame
    limit = fy0 + CAPTION_STRIP * (fy1 - fy0) / config.frame_height
    # Texts first (the most precise culprit), then any other visible shape; full-frame backgrounds are fine.
    for mob in [*texts, *scene.mobjects]:
        if not _visible(mob):
            continue
        x0, y0, x1, y1 = _box(mob)
        if x1 - x0 >= 0.9 * (fx1 - fx0) and y1 - y0 >= 0.9 * (fy1 - fy0):
            continue
        if y0 < limit - FRAME_MARGIN and y1 > fy0 and x1 > fx0 and x0 < fx1:
            if ("caption", id(mob)) in _seen or any(("caption", id(t)) in _seen for t in _texts([mob])):
                continue
            _report(("caption", id(mob)),
                    f"{at}: {_label(mob)} reaches into the caption strip at the bottom of the frame: its lowest point "
                    f"is y {y0:.2f}, but nothing may go below y {limit:.2f}.")


def _overlaps(a: Mobject, b: Mobject) -> bool:
    ax0, ay0, ax1, ay1 = _box(a)
    bx0, by0, bx1, by1 = _box(b)
    w = min(ax1, bx1) - max(ax0, bx0)
    h = min(ay1, by1) - max(ay0, by0)
    if w <= 0 or h <= 0:
        return False
    smaller = min((ax1 - ax0) * (ay1 - ay0), (bx1 - bx0) * (by1 - by0))
    return smaller > 0 and w * h / smaller > OVERLAP_RATIO


def _write_report() -> None:
    path = os.environ.get("LARA_LAYOUT_REPORT")
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_issues, f, ensure_ascii=False)


_original_play = Scene.play


def _play(self, *args, **kwargs):
    _original_play(self, *args, **kwargs)
    try:
        check(self)
    except Exception:  # noqa: BLE001 - the check must never break a render
        pass


Scene.play = _play
atexit.register(_write_report)

if __name__ == "__main__":
    sys.argv = ["manim", *sys.argv[1:]]
    main()
