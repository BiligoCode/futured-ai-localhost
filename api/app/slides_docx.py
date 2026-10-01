"""A deck as a Word document: one landscape page per slide, built from the slide HTML whitelist (spec §8).

Fonts are ones every Word install has (Cambria for headings, Calibri for body) so the file looks right wherever it
is opened; the PDF export keeps Lara's own fonts."""
import io
import re
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX, WD_TAB_ALIGNMENT
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from app.models import AnimationRef, Deck
from app.slides_html import clean_text

PAGE_W, PAGE_H, MARGIN = Inches(13.333), Inches(7.5), Inches(0.67)
HEADING_FONT, BODY_FONT = "Cambria", "Calibri"
SIZES = {"h1": Pt(36), "h2": Pt(28), "p": Pt(18)}
ALIGN = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER, "right": WD_ALIGN_PARAGRAPH.RIGHT}
PX_TO_PT = 0.7
LINK_COLOR = "1B6F8C"

_ALIGN = re.compile(r"text-align:\s*(left|center|right)")
_COLOR = re.compile(r"color:\s*#([0-9a-fA-F]{6})")
_SIZE = re.compile(r"font-size:\s*(\d+)px")


@dataclass(frozen=True)
class _Format:
    bold: bool = False
    italic: bool = False
    underline: bool = False
    highlight: bool = False
    color: str | None = None
    size: Pt | None = None


class _Writer(HTMLParser):
    """Streams one slide's HTML into paragraphs and runs of `doc`."""

    def __init__(self, doc: Document) -> None:
        super().__init__(convert_charrefs=True)
        self.doc = doc
        self.paragraph = None
        self.block = "p"
        self.formats: list[_Format] = [_Format()]
        self.tags: list[str] = []
        self.lists: list[str] = []

    def _new_paragraph(self, style: str | None = None, align: str | None = None):
        self.paragraph = self.doc.add_paragraph(style=style)
        if align:
            self.paragraph.alignment = ALIGN[align]
        self.paragraph.paragraph_format.space_after = Pt(6)
        return self.paragraph

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        style = dict(attrs).get("style") or ""
        align = m.group(1) if (m := _ALIGN.search(style)) else None
        fmt = self.formats[-1]
        if tag in ("h1", "h2"):
            self.block = tag
            self._new_paragraph(align=align)
            fmt = replace(fmt, bold=True, size=SIZES[tag])
        elif tag == "p":
            self.block = "p"
            if not (self.tags and self.tags[-1] == "li" and self.paragraph is not None and not self.paragraph.runs):
                self._new_paragraph(align=align)  # a <p> right inside <li> continues the item's paragraph
            elif align:
                self.paragraph.alignment = ALIGN[align]
        elif tag in ("ul", "ol"):
            self.lists.append(tag)
        elif tag == "li":
            self.block = "p"
            self._new_paragraph(style="List Number" if self.lists and self.lists[-1] == "ol" else "List Bullet",
                                align=align)
        elif tag == "strong":
            fmt = replace(fmt, bold=True)
        elif tag == "em":
            fmt = replace(fmt, italic=True)
        elif tag == "u":
            fmt = replace(fmt, underline=True)
        elif tag == "mark":
            fmt = replace(fmt, highlight=True)
        elif tag == "span":
            color = m.group(1).upper() if (m := _COLOR.search(style)) else fmt.color
            size = Pt(round(int(m.group(1)) * PX_TO_PT)) if (m := _SIZE.search(style)) else fmt.size
            fmt = replace(fmt, color=color, size=size)
        elif tag == "br":
            if self.paragraph is not None:
                self.paragraph.add_run().add_break()
            return
        self.tags.append(tag)
        self.formats.append(fmt)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "br":
            return
        if tag in self.tags:
            while self.tags:
                closed = self.tags.pop()
                self.formats.pop()
                if closed in ("ul", "ol") and self.lists:
                    self.lists.pop()
                if closed == tag:
                    break
        if tag in ("h1", "h2", "p", "li"):
            self.paragraph = None
            self.block = "p"

    def handle_data(self, data: str) -> None:
        if not data.strip() and self.paragraph is None:
            return
        if self.paragraph is None:
            self._new_paragraph()
        fmt = self.formats[-1]
        run = self.paragraph.add_run(clean_text(data))
        run.font.name = HEADING_FONT if self.block in ("h1", "h2") else BODY_FONT
        run.font.size = fmt.size or SIZES["p"]
        run.bold, run.italic, run.underline = fmt.bold or None, fmt.italic or None, fmt.underline or None
        if fmt.highlight:
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        if fmt.color:
            run.font.color.rgb = RGBColor.from_string(fmt.color)


def add_hyperlink(paragraph, url: str, text: str) -> None:
    r_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    props = OxmlElement("w:rPr")
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), LINK_COLOR)
    size = OxmlElement("w:sz")
    size.set(qn("w:val"), "22")  # 11 pt, like the caption around it
    props.append(underline)
    props.append(color)
    props.append(size)
    run.append(props)
    t = OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    run.append(t)
    link.append(run)
    paragraph._p.append(link)


def _page_number_field(paragraph) -> None:
    for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
        run = paragraph.add_run()
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)


def _setup_page(doc: Document, title: str) -> None:
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = PAGE_W, PAGE_H
    section.left_margin = section.right_margin = section.top_margin = section.bottom_margin = MARGIN
    footer = section.footer.paragraphs[0]
    footer.text = f"{clean_text(title)}\t"
    stops = footer.paragraph_format.tab_stops
    for inherited in (Inches(3.25), Inches(6.5)):  # the template's portrait-width centre/right stops
        stops.add_tab_stop(inherited, WD_TAB_ALIGNMENT.CLEAR)
    stops.add_tab_stop(PAGE_W - 2 * MARGIN, WD_TAB_ALIGNMENT.RIGHT)
    _page_number_field(footer)
    for run in footer.runs:
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor.from_string("8A94A3")


def render_docx(deck: Deck, animations: list[AnimationRef], posters: dict[str, Path],
                video_files: dict[str, str]) -> bytes:
    doc = Document()
    doc.styles["Normal"].font.name = BODY_FONT
    doc.styles["Normal"].font.size = SIZES["p"]
    _setup_page(doc, deck.title)
    refs = {a.project_id: a for a in animations}
    for i, slide in enumerate(deck.slides):
        if i:
            doc.add_page_break()
        writer = _Writer(doc)
        writer.feed(slide.html)
        writer.close()
        ref = refs.get(slide.video) if slide.video else None
        poster = posters.get(slide.video) if slide.video else None
        if ref and ref.status == "ready":
            if poster and poster.is_file():
                doc.add_picture(str(poster), width=Inches(7))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            caption = doc.add_paragraph()
            caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = caption.add_run(clean_text(f"▶ Animation: {ref.title}"))
            run.font.size = Pt(11)
            file = video_files.get(slide.video)
            if file:
                caption.add_run(" — ").font.size = Pt(11)
                add_hyperlink(caption, file, file)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
