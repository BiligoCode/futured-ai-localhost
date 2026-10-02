"""PDFs and images for the assessment tests, drawn with reportlab and Pillow."""
import io

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_registered = False


def _font() -> str:
    global _registered
    if not _registered:
        pdfmetrics.registerFont(TTFont("DejaVu", FONT))
        _registered = True
    return "DejaVu"


def typed_pdf(pages: list[list[str]], *, white: str | None = None, invisible: str | None = None, tiny: str | None = None,
              offpage: str | None = None, author: str = "", creator: str = "", title: str = "", encrypt: str = "") -> bytes:
    """Pages of visible lines, optionally with hidden text on the first page (white, render mode 3, 1 pt, off page)."""
    buf = io.BytesIO()
    kwargs = {}
    if encrypt:
        from reportlab.lib.pdfencrypt import StandardEncryption
        kwargs["encrypt"] = StandardEncryption(encrypt, canPrint=1)
    c = canvas.Canvas(buf, pagesize=A4, **kwargs)
    if author:
        c.setAuthor(author)
    if creator:
        c.setCreator(creator)
    if title:
        c.setTitle(title)
    font = _font()
    for i, lines in enumerate(pages):
        c.setFont(font, 12)
        y = 780
        for line in lines:
            c.drawString(60, y, line)
            y -= 20
        if i == 0:
            if white:
                c.setFillColorRGB(1, 1, 1)
                c.drawString(60, 300, white)
                c.setFillColorRGB(0, 0, 0)
            if invisible:
                t = c.beginText(60, 260)
                t.setFont(font, 12)
                t.setTextRenderMode(3)
                t.textLine(invisible)
                c.drawText(t)
            if tiny:
                c.setFont(font, 1)
                c.drawString(60, 220, tiny)
                c.setFont(font, 12)
            if offpage:
                c.drawString(60, -200, offpage)
        c.showPage()
    c.save()
    return buf.getvalue()


def handwriting_image(lines: list[str], size=(1240, 1754)) -> Image.Image:
    img = Image.new("RGB", size, (250, 249, 245))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 40)
    y = 120
    for line in lines:
        d.text((90, y), line, fill=(25, 40, 120), font=font)
        y += 90
    return img


def scanned_pdf(pages: list[list[str]], *, ocr_layer: bool = False) -> bytes:
    """Image-only pages (like a scanner's output), optionally with an invisible OCR text layer on top."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    font = _font()
    for lines in pages:
        img = handwriting_image(lines)
        b = io.BytesIO()
        img.save(b, "JPEG", quality=80)
        b.seek(0)
        from reportlab.lib.utils import ImageReader
        c.drawImage(ImageReader(b), 0, 0, width, height)
        if ocr_layer:
            t = c.beginText(60, 760)
            t.setFont(font, 12)
            t.setTextRenderMode(3)
            for line in lines:
                t.textLine(line + " lorem ipsum dolor sit amet")
            c.drawText(t)
        c.showPage()
    c.save()
    return buf.getvalue()


def jpeg_bytes(img: Image.Image, *, make: str = "", model: str = "", software: str = "") -> bytes:
    exif = Image.Exif()
    if make:
        exif[0x010F] = make
    if model:
        exif[0x0110] = model
    if software:
        exif[0x0131] = software
    b = io.BytesIO()
    img.save(b, "JPEG", quality=85, exif=exif)
    return b.getvalue()


def png_bytes(img: Image.Image) -> bytes:
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()
