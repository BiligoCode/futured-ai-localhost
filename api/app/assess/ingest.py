"""Uploaded papers: checking and splitting files, rendering pages, telling typed pages from scans (design §5).

Each paper keeps its rendered pages (`pages/pNN.jpg`, long side 2000 px — what the models and the viewer see), an ink
map per page for layout comparison (`pages/pNN.ink.png`) and a dHash of the page for spotting identical scans."""
import io
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import Image, ImageOps

from app.assess.models import PageInfo, SourceKind

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_PAGES = 40
LONG_SIDE = 2000
JPEG_QUALITY = 85
INK_SIZE = (48, 64)  # width, height
MIN_TEXT_LETTERS = 40
SCAN_IMAGE_SHARE = 0.7  # an image covering this much of a page makes it a scan, whatever text sits on top

Image.MAX_IMAGE_PIXELS = 120_000_000  # phone photos are large; decompression bombs are not

# PDFium is not thread-safe, not even across documents: every use of pypdfium2 holds this lock (the pipeline calls
# it from worker threads). Rendering is fast; the waiting is negligible next to the model calls.
PDFIUM = threading.RLock()


class UploadError(ValueError):
    """Why an uploaded file cannot become a paper (English; translated for the professor)."""


@dataclass
class Upload:
    filename: str
    kind: SourceKind
    data: bytes
    pages: int


def sniff(data: bytes) -> SourceKind | None:
    if data[:1024].lstrip().startswith(b"%PDF") or b"%PDF-" in data[:1024]:
        return "pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return None


def open_pdf(data: bytes | Path) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(data if isinstance(data, bytes) else str(data))
    except pdfium.PdfiumError as exc:
        if "password" in str(exc).lower():
            raise UploadError("The PDF is password-protected") from exc
        raise UploadError("Could not read the file") from exc


def split_upload(filename: str, data: bytes, split_every: int | None = None) -> list[Upload]:
    """One uploaded file as one or more papers. Raises UploadError with the reason it cannot be used."""
    if len(data) > MAX_FILE_BYTES:
        raise UploadError("The file is larger than 50 MB")
    kind = sniff(data)
    if kind is None:
        raise UploadError("Only PDF, JPG and PNG files can be graded")
    if kind != "pdf":
        try:
            with Image.open(io.BytesIO(data)) as img:
                img.verify()
        except Exception as exc:  # noqa: BLE001 - any decoder error means the image is unusable
            raise UploadError("Could not read the file") from exc
        return [Upload(filename, kind, data, 1)]
    with PDFIUM:
        pdf = open_pdf(data)
        try:
            n = len(pdf)
            if n == 0:
                raise UploadError("The PDF has no pages")
            if not split_every or split_every >= n:
                if n > MAX_PAGES:
                    raise UploadError("This paper has more than 40 pages")
                return [Upload(filename, "pdf", data, n)]
            if split_every > MAX_PAGES:
                raise UploadError("This paper has more than 40 pages")
            stem = filename.rsplit(".", 1)[0] if filename.lower().endswith(".pdf") else filename
            out = []
            for start in range(0, n, split_every):
                end = min(n, start + split_every)
                part = pdfium.PdfDocument.new()
                try:
                    part.import_pages(pdf, pages=list(range(start, end)))
                    buf = io.BytesIO()
                    part.save(buf)
                finally:
                    part.close()
                label = f"{stem} (p. {start + 1})" if end - start == 1 else f"{stem} (pp. {start + 1}–{end})"
                out.append(Upload(label, "pdf", buf.getvalue(), end - start))
            return out
        finally:
            pdf.close()


# --- Rendering --------------------------------------------------------------------------------------------------

def _scaled(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img).convert("RGB")
    long_side = max(img.size)
    if long_side > LONG_SIDE:
        ratio = LONG_SIDE / long_side
        img = img.resize((max(1, round(img.width * ratio)), max(1, round(img.height * ratio))), Image.LANCZOS)
    return img


def ink_map(img: Image.Image) -> Image.Image:
    """How much ink is in each cell of a 48×64 grid (0 = none, 255 = solid), robust to paper tone and exposure."""
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    paper = float(np.percentile(gray, 90)) or 255.0
    ink = (gray < paper * 0.72).astype(np.float32)
    small = Image.fromarray((ink * 255).astype(np.uint8)).resize(INK_SIZE, Image.BOX)
    return small


def dhash(img: Image.Image) -> str:
    """64-bit difference hash: near-identical pages (the same scan, a photocopy) differ in only a few bits."""
    small = np.asarray(img.convert("L").resize((9, 8), Image.BOX), dtype=np.int16)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return f"{int(''.join('1' if b else '0' for b in bits), 2):016x}"


def _image_share(page: pdfium.PdfPage) -> float:
    """The largest share of the page covered by a single image."""
    width, height = page.get_size()
    area = max(width * height, 1.0)
    best = 0.0
    for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=3):
        left, bottom, right, top = obj.get_bounds()
        w = max(0.0, min(right, width) - max(left, 0.0))
        h = max(0.0, min(top, height) - max(bottom, 0.0))
        best = max(best, w * h / area)
    return best


def letters(text: str) -> int:
    return sum(1 for c in text if c.isalpha())


@dataclass
class RenderedPage:
    info: PageInfo
    image: Image.Image
    scale: float          # pixels per PDF point (1 for images)
    image_share: float    # largest image's share of the page (1 for photos/scans)
    dhash: str


def render_pages(source: Path, kind: SourceKind, out_dir: Path) -> list[RenderedPage]:
    """Render every page to `out_dir/pNN.jpg` (+ ink map). The page method is a first guess ("text" when the PDF
    page has text and is not a scan); forensics decides finally once hidden text has been removed."""
    out_dir.mkdir(exist_ok=True)  # never parents: a deleted paper must not be re-created by a late render
    pages: list[RenderedPage] = []

    def save(n: int, img: Image.Image) -> None:
        img.save(out_dir / f"p{n:02d}.jpg", "JPEG", quality=JPEG_QUALITY, optimize=True)
        ink_map(img).save(out_dir / f"p{n:02d}.ink.png")

    if kind != "pdf":
        with Image.open(source) as raw:
            img = _scaled(raw)
        save(1, img)
        info = PageInfo(n=1, method="vision", width=img.width, height=img.height, dhash=dhash(img))
        return [RenderedPage(info, img, 1.0, 1.0, info.dhash)]

    raw: list[tuple[Image.Image, float, float, str]] = []
    with PDFIUM:
        pdf = open_pdf(source)
        try:
            if len(pdf) > MAX_PAGES:
                raise UploadError("This paper has more than 40 pages")
            for i in range(len(pdf)):
                page = pdf[i]
                try:
                    width, height = page.get_size()
                    scale = min(4.0, LONG_SIDE / max(width, height, 1.0))
                    bitmap = page.render(scale=scale, may_draw_forms=True)
                    img = bitmap.to_pil().convert("RGB")
                    bitmap.close()
                    share = _image_share(page)
                    textpage = page.get_textpage()
                    text = textpage.get_text_range()
                    textpage.close()
                finally:
                    page.close()
                raw.append((img, scale, share, text))
        finally:
            pdf.close()
    for i, (img, scale, share, text) in enumerate(raw):
        n = i + 1
        save(n, img)
        method = "text" if letters(text) >= MIN_TEXT_LETTERS and share < SCAN_IMAGE_SHARE else "vision"
        info = PageInfo(n=n, method=method, width=img.width, height=img.height, dhash=dhash(img))
        pages.append(RenderedPage(info, img, scale, share, info.dhash))
    return pages


def page_image(out_dir: Path, n: int) -> bytes:
    return (out_dir / f"p{n:02d}.jpg").read_bytes()


def load_ink(out_dir: Path, n: int) -> np.ndarray | None:
    path = out_dir / f"p{n:02d}.ink.png"
    if not path.is_file():
        return None
    with Image.open(path) as img:
        return np.asarray(img.convert("L"), dtype=np.float32) / 255.0


def exam_images(files: list[Path], limit: int = 12) -> list[bytes]:
    """The exam paper's pages as JPEG bytes for the vision model (scanned exam papers)."""
    out: list[bytes] = []
    for path in files:
        kind = sniff(path.read_bytes()[:1024])
        if kind == "pdf":
            images = []
            with PDFIUM:
                pdf = open_pdf(path)
                try:
                    for i in range(min(len(pdf), limit - len(out))):
                        page = pdf[i]
                        try:
                            width, height = page.get_size()
                            bitmap = page.render(scale=min(4.0, LONG_SIDE / max(width, height, 1.0)))
                            images.append(bitmap.to_pil().convert("RGB"))
                            bitmap.close()
                        finally:
                            page.close()
                finally:
                    pdf.close()
            out.extend(_jpeg(img) for img in images)
        elif kind in ("jpg", "png"):
            with Image.open(path) as raw:
                out.append(_jpeg(_scaled(raw)))
        if len(out) >= limit:
            break
    return out[:limit]


def _jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()
