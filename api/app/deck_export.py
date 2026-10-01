"""Export a deck: the document alone, or a zip with the document and the embedded animations' video files."""
import re
import unicodedata
import zipfile
from pathlib import Path
from typing import Literal

from app.models import AnimationRef, Deck
from app.slides_docx import render_docx
from app.slides_pdf import render_pdf

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "zip": "application/zip",
}
MAX_FILENAME = 80
_UNSAFE = re.compile(r"[^\w \-]+", re.UNICODE)


def safe_filename(title: str) -> str:
    """A download name that keeps Greek letters but nothing a file system or a zip could choke on."""
    name = re.sub(r"-{2,}", "-", _UNSAFE.sub("-", unicodedata.normalize("NFC", title))).strip(" -")[:MAX_FILENAME].strip(" -")
    return name or "slides"


def export_deck(deck_dir: Path, deck: Deck, animations: list[AnimationRef], posters: dict[str, Path],
                project_video: dict[str, Path], fmt: Literal["pdf", "docx"]) -> tuple[Path, str, str]:
    """Write `export/deck.<fmt>` (and `export/deck-<fmt>.zip` when a ready animation is embedded).

    Returns (path to serve, download file name, media type)."""
    out_dir = deck_dir / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = safe_filename(deck.title)
    refs = {a.project_id: a for a in animations}
    videos: dict[str, tuple[str, Path]] = {}
    for slide in deck.slides:
        ref = refs.get(slide.video) if slide.video else None
        source = project_video.get(slide.video) if slide.video else None
        if ref and ref.status == "ready" and source and source.is_file() and slide.video not in videos:
            videos[slide.video] = (f"animations/{len(videos) + 1:02d}-{safe_filename(ref.title)}.mp4", source)
    video_files = {pid: rel for pid, (rel, _) in videos.items()}
    render = render_pdf if fmt == "pdf" else render_docx
    document = render(deck, animations, posters, video_files)
    doc_path = out_dir / f"deck.{fmt}"
    doc_path.write_bytes(document)
    if not videos:
        return doc_path, f"{name}.{fmt}", MEDIA_TYPES[fmt]
    zip_path = out_dir / f"deck-{fmt}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{name}.{fmt}", document)
        for rel, source in videos.values():
            z.write(source, rel, compress_type=zipfile.ZIP_STORED)  # already compressed video
    return zip_path, f"{name} ({'PDF' if fmt == 'pdf' else 'Word'}).zip", MEDIA_TYPES["zip"]
