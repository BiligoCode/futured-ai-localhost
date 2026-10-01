"""The slide HTML contract: the small whitelist the editor, the AI and both exporters share (spec §3).

Anything else is unwrapped (text kept) or dropped, so pasted Word/Docs markup and model output both come out as
the same clean fragment."""
import html as htmllib
import re
from html.parser import HTMLParser

MAX_SLIDE_CHARS = 20_000
ALLOWED_TAGS = frozenset({"h1", "h2", "p", "ul", "ol", "li", "strong", "em", "u", "mark", "span", "br"})
BLOCK_TAGS = frozenset({"h1", "h2", "p", "li"})
HEADING_TAGS = frozenset({"h1", "h2"})
ALIGN_TAGS = BLOCK_TAGS
ALIGN_VALUES = frozenset({"left", "center", "right"})
DROP_WITH_CONTENT = frozenset({"script", "style"})
ALIASES = {"b": "strong", "i": "em"}  # what pasted Word/Docs markup uses
# Opening one of these closes a still-open one of the same group (HTML lets `</li>` and `</p>` be omitted).
IMPLICIT_CLOSE = {"li": frozenset({"li"}), "p": frozenset({"p", "h1", "h2"}), "h1": frozenset({"p", "h1", "h2"}),
                  "h2": frozenset({"p", "h1", "h2"})}
PALETTE = ["#18212e", "#566173", "#1b6f8c", "#0f7b6c", "#74490a", "#c93838", "#6d3fb8", "#e2a13b"]
TITLE_CHARS = 60

_HEX = re.compile(r"^#([0-9a-fA-F]{6})$")
_PX = re.compile(r"^(\d{1,3})px$")


class SlideTooLong(ValueError):
    pass


def _clean_style(tag: str, style: str) -> str | None:
    kept: dict[str, str] = {}
    for declaration in style.split(";"):
        prop, _, value = declaration.partition(":")
        prop, value = prop.strip().lower(), value.strip()
        if prop == "text-align" and tag in ALIGN_TAGS and value.lower() in ALIGN_VALUES:
            kept[prop] = value.lower()
        elif prop == "color" and tag == "span" and (m := _HEX.match(value)):
            kept[prop] = "#" + m.group(1).lower()
        elif prop == "font-size" and tag == "span" and (m := _PX.match(value)) and 12 <= int(m.group(1)) <= 96:
            kept[prop] = f"{int(m.group(1))}px"
    ordered = [f"{k}: {kept[k]}" for k in ("text-align", "color", "font-size") if k in kept]
    return "; ".join(ordered) or None


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.open: list[tuple[str, bool]] = []  # (tag, was emitted)
        self.dropping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in DROP_WITH_CONTENT:
            self.dropping += 1
            return
        if self.dropping:
            return
        if tag == "br":
            self.out.append("<br>")
            return
        tag = ALIASES.get(tag, tag)
        if tag in IMPLICIT_CLOSE and self.open and self.open[-1][0] in IMPLICIT_CLOSE[tag]:
            self.handle_endtag(self.open[-1][0])
        if tag in ALLOWED_TAGS:
            style = _clean_style(tag, dict(attrs).get("style") or "")
            self.out.append(f'<{tag} style="{style}">' if style else f"<{tag}>")
            self.open.append((tag, True))
        else:
            self.open.append((tag, False))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.handle_starttag(tag, attrs)
        else:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in DROP_WITH_CONTENT:
            self.dropping = max(0, self.dropping - 1)
            return
        if self.dropping or tag == "br":
            return
        tag = ALIASES.get(tag, tag)
        for i in range(len(self.open) - 1, -1, -1):
            if self.open[i][0] == tag:
                for inner, emitted in reversed(self.open[i + 1:]):  # tags left open inside: close them too
                    if emitted:
                        self.out.append(f"</{inner}>")
                if self.open[i][1]:
                    self.out.append(f"</{tag}>")
                del self.open[i:]
                return

    def handle_data(self, data: str) -> None:
        if not self.dropping:
            self.out.append(htmllib.escape(data, quote=False))

    def result(self) -> str:
        self.close()
        for tag, emitted in reversed(self.open):
            if emitted:
                self.out.append(f"</{tag}>")
        self.open = []
        return "".join(self.out)


def sanitize_slide_html(html: str) -> str:
    if len(html) > MAX_SLIDE_CHARS:
        raise SlideTooLong("Slide is too long")
    parser = _Sanitizer()
    parser.feed(html)
    return parser.result()


class _TextParser(HTMLParser):
    """Plain text of a slide, one line per block, `- ` before list items; also the first heading's text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = [""]
        self.heading: str | None = None
        self.heading_depth = 0
        self.dropping = 0

    def _newline(self) -> None:
        if self.lines[-1].strip() not in ("", "-"):
            self.lines.append("")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in DROP_WITH_CONTENT:
            self.dropping += 1
        elif self.dropping:
            return
        elif tag == "li":
            self._newline()
            self.lines[-1] = "- "
        elif tag in BLOCK_TAGS:
            self._newline()
            if tag in HEADING_TAGS and self.heading is None:
                self.heading_depth = 1
                self.heading = ""
        elif tag == "br":
            self.lines.append("")
        elif self.heading_depth:
            self.heading_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in DROP_WITH_CONTENT:
            self.dropping = max(0, self.dropping - 1)
        elif self.dropping:
            return
        elif tag in BLOCK_TAGS:
            if tag in HEADING_TAGS and self.heading_depth == 1:
                self.heading_depth = 0
            self.lines.append("")
        elif self.heading_depth > 1:
            self.heading_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.dropping:
            return
        self.lines[-1] += data
        if self.heading_depth and self.heading is not None:
            self.heading += data

    def text(self) -> str:
        self.close()
        cleaned = [" ".join(line.split()) for line in self.lines]
        return "\n".join(line for line in cleaned if line and line != "-")


def _parse_text(html: str) -> _TextParser:
    parser = _TextParser()
    parser.feed(html)
    return parser


def slide_text(html: str) -> str:
    return _parse_text(html).text()


def _heading(parser: _TextParser) -> str | None:
    if parser.heading is not None and parser.heading.strip():
        return " ".join(parser.heading.split())
    return None


def slide_title(html: str) -> str:
    parser = _parse_text(html)
    text = parser.text()
    return _heading(parser) or " ".join(text.split())[:TITLE_CHARS]


def deck_material_text(title: str, slides: list[str]) -> str:
    """The deck as course material for an animation. A slide's heading is its title and is not repeated in
    the body; a slide without a heading is titled by its first words."""
    parts = [f"Lecture slides: {title}"]
    for i, html in enumerate(slides, 1):
        parser = _parse_text(html)
        lines = parser.text().split("\n") if parser.text() else []
        heading = _heading(parser)
        if heading is not None:
            if heading in lines:
                lines.remove(heading)
            slide_title_text = heading
        else:
            slide_title_text = " ".join(lines)[:TITLE_CHARS]
        parts.append(f"Slide {i}: {slide_title_text}\n" + "\n".join(lines).rstrip())
    return "\n\n".join(p.rstrip() for p in parts)
