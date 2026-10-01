"""A deck as a PDF: one 1280×720 px page per slide, styled by the same stylesheet as the editor (spec §8)."""
import html
from pathlib import Path

from app.models import AnimationRef, Deck

ASSETS = Path(__file__).parent / "assets"
FONTS = ASSETS / "fonts"

_FONT_FACES = [
    ("STIX Two Text", "STIXTwoText[wght].ttf", "normal"),
    ("STIX Two Text", "STIXTwoText-Italic[wght].ttf", "italic"),
    ("Commissioner", "Commissioner[FLAR,VOLM,slnt,wght].ttf", "normal"),
]


def _font_css() -> str:
    rules = []
    for family, file, style in _FONT_FACES:
        path = FONTS / file
        if path.is_file():  # a missing download leaves the DejaVu fallback in the stack
            rules.append(f'@font-face {{ font-family: "{family}"; font-style: {style}; '
                         f'src: url("{path.as_uri()}"); }}')
    return "\n".join(rules)


def video_figure(ref: AnimationRef | None, poster: Path | None, file: str | None) -> str:
    """The exported stand-in for an embedded animation: its poster frame, linked to the video file in the zip."""
    if ref is None or ref.status != "ready" or poster is None or not poster.is_file():
        return ""
    caption = f"▶ Animation: {html.escape(ref.title, quote=False)}" + (f" — {html.escape(file, quote=False)}" if file else "")
    img = f'<img src="{poster.resolve().as_uri()}" alt="">'
    if file:
        img = f'<a href="{html.escape(file)}">{img}</a>'
    return f'<figure class="slide-video">{img}<figcaption>{caption}</figcaption></figure>'


def render_html(deck: Deck, animations: list[AnimationRef], posters: dict[str, Path],
                video_files: dict[str, str]) -> str:
    refs = {a.project_id: a for a in animations}
    total = len(deck.slides)
    sections = []
    for n, slide in enumerate(deck.slides, 1):
        figure = video_figure(refs.get(slide.video), posters.get(slide.video), video_files.get(slide.video)) \
            if slide.video else ""
        sections.append(
            f'<section class="slide"><div class="slide-text">{slide.html}</div>{figure}'
            f'<footer class="slide-footer"><span>{html.escape(deck.title, quote=False)}</span>'
            f"<span>{n} / {total}</span></footer></section>")
    return (
        '<!doctype html><html><head><meta charset="utf-8"><style>'
        "@page { size: 1280px 720px; margin: 0 }\n"
        "body { margin: 0 }\n"
        ".slide { page-break-after: always }\n"
        f"{_font_css()}\n{(ASSETS / 'slide.css').read_text(encoding='utf-8')}"
        f"</style></head><body>{''.join(sections)}</body></html>")


def render_pdf(deck: Deck, animations: list[AnimationRef], posters: dict[str, Path],
               video_files: dict[str, str]) -> bytes:
    from weasyprint import HTML  # imported here: slow to import, only needed for exports

    return HTML(string=render_html(deck, animations, posters, video_files)).write_pdf()
