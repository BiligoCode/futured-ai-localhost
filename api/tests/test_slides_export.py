import io
from datetime import datetime, timezone

from pypdf import PdfReader

from app.models import AnimationRef, Deck, Slide
from app.slides_pdf import render_pdf
from tests.conftest import ffmpeg_bytes

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def deck_with(*htmls: str, title="Ταξινόμηση") -> Deck:
    slides = [Slide(id=f"aaaaaaa{i + 1}", html=h) for i, h in enumerate(htmls)]
    return Deck(id="deck000001", created_at=NOW, updated_at=NOW, title=title, language="el", slides=slides)


def jpeg(path):
    path.write_bytes(ffmpeg_bytes("-f", "lavfi", "-i", "color=c=blue:s=640x360:d=1", "-frames:v", "1", "-f", "mjpeg", "pipe:1"))
    return path


def ref(project_id, title, status="ready", cut="preview", embedded=True):
    return AnimationRef(project_id=project_id, title=title, status=status, cut=cut, version=1 if cut else 0,
                        duration=5.0 if cut else 0.0, embedded=embedded)


def test_render_pdf_pages_and_text():
    deck = deck_with("<h1>Ταξινόμηση</h1><p>Εισαγωγή</p>", "<p>Δεύτερη</p>", "<p>Τρίτη</p>")
    pdf = render_pdf(deck, [], {}, {})
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 3
    page = reader.pages[0]
    assert round(float(page.mediabox.width) / float(page.mediabox.height), 3) == 1.778
    text = page.extract_text()
    assert "Ταξινόμηση" in text and "Εισαγωγή" in text and "1 / 3" in text
    assert "Τρίτη" in reader.pages[2].extract_text() and "3 / 3" in reader.pages[2].extract_text()


def test_render_pdf_with_poster_and_missing_animation(tmp_path):
    poster = jpeg(tmp_path / "p.jpg")
    deck = deck_with("<p>a</p>", "<p>b</p>")
    deck.slides[0].video = "pid"
    deck.slides[1].video = "ghost"
    refs = [ref("pid", "Φυσαλίδα"), ref("ghost", "", status="missing", cut=None)]
    pdf = render_pdf(deck, refs, {"pid": poster}, {"pid": "animations/01-Φυσαλίδα.mp4"})
    reader = PdfReader(io.BytesIO(pdf))
    text = "".join(p.extract_text() for p in reader.pages)
    assert len(reader.pages) == 2
    assert "Animation: Φυσαλίδα" in text and "animations/01-Φυσαλίδα.mp4" in text
    assert len(reader.pages[0].images) == 1  # the poster frame
    assert text.count("Animation:") == 1  # nothing for the deleted one


def test_render_pdf_uses_bundled_fonts():
    pdf = render_pdf(deck_with("<h1>Τίτλος</h1><p><em>πλάγια</em> κείμενο</p>"), [], {}, {})
    fonts = [str(f.get_object()["/BaseFont"]) for f in PdfReader(io.BytesIO(pdf)).pages[0]["/Resources"]["/Font"].values()]
    assert any("STIX-Two-Text-Semi-Bold" in f for f in fonts) and any(f.endswith("Commissioner") for f in fonts)
    assert any("Commissioner-Oblique" in f for f in fonts)


# --- Word ---------------------------------------------------------------------------------------------------------

import zipfile  # noqa: E402

from docx import Document  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.shared import Pt  # noqa: E402

from app.deck_export import export_deck, safe_filename  # noqa: E402
from app.slides_docx import render_docx  # noqa: E402


def test_render_docx_formatting():
    deck = deck_with(
        '<h1 style="text-align: center">Τίτλος</h1>'
        '<p><strong>έντονο</strong> <span style="color: #c93838; font-size: 34px">κόκκινο</span> <em>πλάγιο</em> <u>υπο</u> <mark>φως</mark></p>'
        "<ul><li><p>ένα</p></li><li>δύο</li></ul><ol><li><p>πρώτο</p></li></ol>",
        "<p>δύο</p>")
    doc = Document(io.BytesIO(render_docx(deck, [], {}, {})))
    paras = [p for p in doc.paragraphs if p.text]
    assert paras[0].text == "Τίτλος" and paras[0].alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert paras[0].runs[0].font.size == Pt(36) and paras[0].runs[0].bold
    runs = paras[1].runs
    assert runs[0].text == "έντονο" and runs[0].bold
    assert runs[2].text == "κόκκινο" and str(runs[2].font.color.rgb) == "C93838" and runs[2].font.size == Pt(24)
    assert runs[4].text == "πλάγιο" and runs[4].italic
    assert runs[6].text == "υπο" and runs[6].underline
    assert runs[8].text == "φως" and runs[8].font.highlight_color is not None
    assert [p.style.name for p in paras[2:5]] == ["List Bullet", "List Bullet", "List Number"]
    assert paras[5].text == "δύο"
    breaks = [r for p in doc.paragraphs for r in p.runs if 'w:type="page"' in r._r.xml]
    assert len(breaks) == 1
    section = doc.sections[0]
    assert round(section.page_width.inches, 2) == 13.33 and round(section.page_height.inches, 1) == 7.5
    assert "Ταξινόμηση" in section.footer.paragraphs[0].text


def test_render_docx_with_poster_and_missing(tmp_path):
    poster = jpeg(tmp_path / "p.jpg")
    deck = deck_with("<p>a</p>", "<p>b</p>")
    deck.slides[0].video, deck.slides[1].video = "pid", "ghost"
    data = render_docx(deck, [ref("pid", "Φυσαλίδα"), ref("ghost", "", status="missing", cut=None)], {"pid": poster},
                       {"pid": "animations/01-Φυσαλίδα.mp4"})
    doc = Document(io.BytesIO(data))
    assert len(doc.inline_shapes) == 1
    text = "\n".join(p.text for p in doc.paragraphs)
    assert text.count("Animation: Φυσαλίδα") == 1 and "animations/01-Φυσαλίδα.mp4" in text
    links = [r for r in doc.part.rels.values() if r.is_external and r.reltype.endswith("/hyperlink")]
    assert len(links) == 1 and links[0].target_ref == "animations/01-Φυσαλίδα.mp4"


def test_safe_filename():
    assert safe_filename("Αλγόριθμοι: Ταξινόμηση/2") == "Αλγόριθμοι- Ταξινόμηση-2"
    assert safe_filename("///") == "slides" and safe_filename("") == "slides"
    assert len(safe_filename("x" * 200)) == 80


def test_export_deck_zip_and_filename_keeps_greek(tmp_path):
    poster = jpeg(tmp_path / "p.jpg")
    video = tmp_path / "preview.mp4"
    video.write_bytes(b"mp4")
    deck = deck_with("<p>a</p>", title="Δέντρα")
    deck.slides[0].video = "pid"
    deck_dir = tmp_path / "deck"
    deck_dir.mkdir()
    path, filename, media_type = export_deck(deck_dir, deck, [ref("pid", "Φυσαλίδα")], {"pid": poster}, {"pid": video}, "pdf")
    assert path == deck_dir / "export" / "deck-pdf.zip" and filename == "Δέντρα (PDF).zip" and media_type == "application/zip"
    with zipfile.ZipFile(path) as z:
        assert set(z.namelist()) == {"Δέντρα.pdf", "animations/01-Φυσαλίδα.mp4"}
        assert z.read("animations/01-Φυσαλίδα.mp4") == b"mp4" and z.read("Δέντρα.pdf")[:5] == b"%PDF-"
        assert z.getinfo("animations/01-Φυσαλίδα.mp4").compress_type == zipfile.ZIP_STORED


def test_export_skips_missing_animation(tmp_path):
    deck = deck_with("<p>a</p>", title="Δέντρα")
    deck.slides[0].video = "ghost"
    deck_dir = tmp_path / "deck"
    deck_dir.mkdir()
    path, filename, media_type = export_deck(deck_dir, deck, [ref("ghost", "", status="missing", cut=None)], {}, {}, "docx")
    assert path == deck_dir / "export" / "deck.docx" and filename == "Δέντρα.docx"
    assert media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert Document(str(path)).paragraphs


def test_render_pdf_clips_overflowing_slide_to_one_page(tmp_path):
    long_slide = "<h2>Πολύ κείμενο</h2>" + "".join(f"<p>Γραμμή {i} με αρκετό κείμενο για να γεμίσει.</p>" for i in range(40))
    deck = deck_with(long_slide, "<p>μετά</p>")
    deck.slides[0].video = "pid"
    pdf = render_pdf(deck, [ref("pid", "Φυσαλίδα")], {"pid": jpeg(tmp_path / "p.jpg")}, {"pid": "animations/01-x.mp4"})
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 2
    assert "Animation: Φυσαλίδα" in reader.pages[0].extract_text() and "1 / 2" in reader.pages[0].extract_text()
    assert "μετά" in reader.pages[1].extract_text()


def test_render_docx_survives_control_characters(tmp_path):
    deck = deck_with("<p>a\x0cb</p>", title="Τ\x1bίτλος")
    doc = Document(io.BytesIO(render_docx(deck, [], {}, {})))
    assert [p.text for p in doc.paragraphs if p.text] == ["ab"]
    assert "Τίτλος" in doc.sections[0].footer.paragraphs[0].text


def test_safe_filename_normalises_decomposed_accents():
    assert safe_filename("Δε\u0301ντρα") == "Δέντρα"


def test_render_pdf_caption_without_poster(tmp_path):
    deck = deck_with("<p>a</p>")
    deck.slides[0].video = "pid"
    pdf = render_pdf(deck, [ref("pid", "Φυσαλίδα")], {"pid": tmp_path / "missing.jpg"}, {"pid": "animations/01-x.mp4"})
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "Animation: Φυσαλίδα" in text and "animations/01-x.mp4" in text
