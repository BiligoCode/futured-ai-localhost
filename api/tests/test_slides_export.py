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
