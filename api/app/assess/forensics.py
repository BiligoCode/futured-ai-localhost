"""Document forensics (design §9): what a file says about where it came from, and text nobody can see.

Hidden text is found by comparing the text layer with the rendered page: a line of text whose box shows no ink
(white on white, invisible render mode, covered, or a font too small to see) is hidden. It is reported and removed
from what the grader reads, so instructions hidden for an AI grader never reach it."""
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import ExifTags, Image
from pypdf import PdfReader

from app.assess.answers import normalize_text
from app.assess.ingest import MIN_TEXT_LETTERS, PDFIUM, SCAN_IMAGE_SHARE, RenderedPage, letters, open_pdf
from app.assess.lexicon import (ADDRESSES_GRADER, CHAT_ARTIFACTS, CITATION_ARTIFACTS, invisible_counts,
                                mixed_script_words)
from app.assess.models import Finding, Forensics, SourceKind

MIN_INK_SHARE = 0.012     # a visible line of text puts ink on well over 1 % of its box
TINY_TEXT_PT = 2.0        # glyphs shorter than this cannot be read on paper
SAMPLE_CHARS = 160
AI_SOFTWARE = re.compile(r"dall[·\-\s]?e|midjourney|stable ?diffusion|firefly|imagen|gpt-4o|gpt-image|chatgpt|openai|"
                         r"gemini|leonardo\.ai|ideogram|flux", re.IGNORECASE)
GENERIC_AUTHORS = {"", "user", "admin", "administrator", "owner", "microsoft office user", "χρήστης", "windows user",
                   "unknown", "author", "pc", "home", "student", "anonymous", "(anonymous)", "unspecified", "none",
                   "ανώνυμος", "συγγραφέας"}


@dataclass
class Run:
    text: str
    left: float
    top: float
    right: float
    bottom: float


@dataclass
class PdfFacts:
    """What forensics hands to the pipeline besides the Forensics record."""
    forensics: Forensics
    visible_text: dict[int, str] = field(default_factory=dict)   # page → visible text (text pages)
    methods: dict[int, str] = field(default_factory=dict)        # page → "text" | "vision" after hidden text is gone
    hidden: list[dict] = field(default_factory=list)


def _sample(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SAMPLE_CHARS else text[: SAMPLE_CHARS - 1] + "…"


def _ink_share(gray: np.ndarray, box: tuple[int, int, int, int]) -> float:
    x0, y0, x1, y1 = box
    region = gray[y0:y1, x0:x1]
    if region.size == 0:
        return 0.0
    background = float(np.median(region))
    return float(np.mean(np.abs(region - background) > 48))


def _runs(textpage: pdfium.PdfTextPage) -> list[Run]:
    runs = []
    for i in range(textpage.count_rects()):
        left, bottom, right, top = textpage.get_rect(i)
        text = textpage.get_text_bounded(left, bottom, right, top)
        if text and text.strip():
            runs.append(Run(text, left, top, right, bottom))
    return runs


def _visible_text(runs: list[Run]) -> str:
    out: list[str] = []
    last_top: float | None = None
    for run in runs:
        if last_top is not None:
            out.append("\n" if abs(run.top - last_top) > 3 else " ")
        out.append(run.text.strip())
        last_top = run.top
    return "".join(out).strip()


def _hidden_runs(page: pdfium.PdfPage, rendered: RenderedPage, runs: list[Run]) -> list[tuple[Run, str]]:
    """Runs that do not show on the rendered page, with the reason."""
    if page.get_rotation() % 360:
        return []  # rotated pages are rare in typed work; their boxes would need re-mapping
    width, height = page.get_size()
    gray = np.asarray(rendered.image.convert("L"), dtype=np.float32)
    scale = rendered.scale
    hidden: list[tuple[Run, str]] = []
    for run in runs:
        if letters(run.text) < 3:
            continue
        if run.right <= 0 or run.left >= width or run.top <= 0 or run.bottom >= height:
            hidden.append((run, "offpage"))
            continue
        if run.top - run.bottom < TINY_TEXT_PT:
            hidden.append((run, "tiny"))
            continue
        box = (max(0, int(run.left * scale)), max(0, int((height - run.top) * scale)),
               min(gray.shape[1], int(run.right * scale) + 1), min(gray.shape[0], int((height - run.bottom) * scale) + 1))
        if _ink_share(gray, box) < MIN_INK_SHARE:
            hidden.append((run, "invisible"))
    return hidden


def _pypdf_facts(data: bytes) -> tuple[dict[str, str], dict[str, str], str | None, list[str], list[Finding]]:
    metadata: dict[str, str] = {}
    xmp: dict[str, str] = {}
    file_id = None
    fonts: set[str] = set()
    findings: list[Finding] = []
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except Exception:  # noqa: BLE001 - forensics is best effort; pypdfium2 already read the file
        return metadata, xmp, file_id, [], findings
    try:
        for key, value in (reader.metadata or {}).items():
            if isinstance(key, str) and value is not None and str(value).strip():
                metadata[key.lstrip("/")] = str(value).strip()[:300]
    except Exception:  # noqa: BLE001
        pass
    try:
        if (x := reader.xmp_metadata) is not None:
            for attr, name in (("xmp_creator_tool", "CreatorTool"), ("xmpmm_document_id", "DocumentID"),
                               ("xmpmm_instance_id", "InstanceID"), ("xmp_create_date", "CreateDate"),
                               ("xmp_modify_date", "ModifyDate"), ("pdf_producer", "Producer")):
                value = getattr(x, attr, None)
                if value:
                    xmp[name] = (value.isoformat() if isinstance(value, datetime) else str(value))[:300]
            creators = getattr(x, "dc_creator", None)
            if creators:
                xmp["Creator"] = ", ".join(str(c) for c in creators)[:300]
    except Exception:  # noqa: BLE001
        pass
    try:
        ids = reader.trailer.get("/ID")
        if ids:
            first = ids[0]
            raw = first.original_bytes if hasattr(first, "original_bytes") else bytes(str(first), "latin-1")
            file_id = raw.hex() or None
    except Exception:  # noqa: BLE001
        pass
    try:
        for page in reader.pages[:40]:
            res = page.get("/Resources")
            font_dict = res.get_object().get("/Font") if res is not None else None
            if font_dict is None:
                continue
            for ref in font_dict.get_object().values():
                base = str(ref.get_object().get("/BaseFont", "")).lstrip("/")
                if base:
                    fonts.add(re.sub(r"^[A-Z]{6}\+", "", base))
    except Exception:  # noqa: BLE001
        pass
    try:
        signers = []
        for name, fld in (reader.get_fields() or {}).items():
            if fld.get("/FT") == "/Sig" and fld.get("/V") is not None:
                v = fld["/V"].get_object()
                signers.append(str(v.get("/Name") or name)[:120])
        if signers:
            findings.append(Finding(code="digital_signature", severity="info", detail={"signers": signers[:5]}))
    except Exception:  # noqa: BLE001
        pass
    try:
        root = reader.trailer["/Root"].get_object()
        names = root.get("/Names")
        has_js = "/JavaScript" in (names.get_object() if names is not None else {}) or "/JS" in str(root.get("/OpenAction", ""))
        attachments = list((reader.attachments or {}).keys())
        if has_js or attachments:
            findings.append(Finding(code="scripts_or_attachments", severity="warn",
                                    detail={"javascript": bool(has_js), "attachments": attachments[:5]}))
    except Exception:  # noqa: BLE001
        pass
    return metadata, xmp, file_id, sorted(fonts)[:30], findings


def _image_findings(blobs: list[bytes]) -> list[Finding]:
    """EXIF (camera, software), C2PA content credentials and generative-AI provenance of embedded or uploaded images."""
    findings: list[Finding] = []
    cameras: list[str] = []
    ai_marks: list[str] = []
    credentials = False
    for blob in blobs[:24]:
        lowered = blob.lower()
        if b"c2pa" in lowered or b"jumb" in lowered:
            credentials = True
        if b"trainedalgorithmicmedia" in lowered or b"compositesynthetic" in lowered:
            ai_marks.append("trainedAlgorithmicMedia")
        try:
            with Image.open(io.BytesIO(blob)) as img:
                exif = img.getexif()
                tags = {ExifTags.TAGS.get(k, str(k)): str(v).strip("\x00 ") for k, v in exif.items()}
                camera = " ".join(t for t in (tags.get("Make", ""), tags.get("Model", "")) if t).strip()
                software = tags.get("Software", "")
                when = tags.get("DateTime", "")
                if camera or software:
                    cameras.append(", ".join(t for t in (camera, software, when) if t)[:160])
                texts = " ".join(str(v) for v in img.info.values() if isinstance(v, (str, bytes)))[:4000]
                if (m := AI_SOFTWARE.search(software + " " + texts)) is not None:
                    ai_marks.append(m.group(0))
                if "parameters" in img.info and "steps:" in str(img.info.get("parameters", "")).lower():
                    ai_marks.append("Stable Diffusion parameters")
        except Exception:  # noqa: BLE001 - an image Pillow cannot open has no metadata for us
            continue
    if ai_marks:
        findings.append(Finding(code="ai_image", severity="warn", detail={"marks": sorted(set(ai_marks))[:5]}))
    elif credentials:
        findings.append(Finding(code="content_credentials", severity="info", detail={}))
    if cameras:
        findings.append(Finding(code="camera", severity="info", detail={"devices": sorted(set(cameras))[:5]}))
    return findings


def _embedded_jpegs(pdf: pdfium.PdfDocument) -> list[bytes]:
    blobs: list[bytes] = []
    for i in range(min(len(pdf), 40)):
        page = pdf[i]
        try:
            for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=3):
                try:
                    if "DCTDecode" in obj.get_filters():
                        blobs.append(bytes(obj.get_data(decode_simple=False)))
                except Exception:  # noqa: BLE001
                    continue
                if len(blobs) >= 24:
                    return blobs
        finally:
            page.close()
    return blobs


def text_findings(visible: str, hidden: str) -> list[Finding]:
    """Findings about the text itself: AI leftovers, text addressed to a grader, invisible characters, homoglyphs."""
    findings: list[Finding] = []
    norm = normalize_text(visible).replace("’", "'")
    artifacts = [m.group(0) for m in CHAT_ARTIFACTS.finditer(norm)] + [m.group(0) for m in CITATION_ARTIFACTS.finditer(visible)]
    if artifacts:
        findings.append(Finding(code="ai_artifact", severity="alert", detail={"samples": sorted(set(artifacts))[:5]}))
    steering = [m.group(0) for m in ADDRESSES_GRADER.finditer(norm)]
    hidden_steering = [m.group(0) for m in ADDRESSES_GRADER.finditer(normalize_text(hidden))] if hidden else []
    if steering or hidden_steering:
        findings.append(Finding(code="addresses_grader", severity="alert",
                                detail={"samples": sorted(set(steering + hidden_steering))[:5], "hidden": bool(hidden_steering)}))
    counts = invisible_counts(visible + hidden)
    if counts:
        findings.append(Finding(code="invisible_chars", severity="warn", detail={"counts": counts}))
    if len(mixed := mixed_script_words(visible)) >= 2:
        findings.append(Finding(code="mixed_script", severity="warn", detail={"words": mixed}))
    return findings


def _revisions(data: bytes) -> int:
    return max(1, data.count(b"%%EOF"))


def analyze_pdf(source: Path, rendered: list[RenderedPage]) -> PdfFacts:
    data = source.read_bytes()
    facts = PdfFacts(Forensics(sha256=hashlib.sha256(data).hexdigest()))
    by_n = {p.info.n: p for p in rendered}
    hidden_texts: list[str] = []
    with PDFIUM:
        _read_pdf(data, by_n, facts, hidden_texts)
        blobs = _embedded_jpegs_locked(data)
    _finish_pdf(data, facts, hidden_texts, blobs)
    return facts


def _read_pdf(data: bytes, by_n: dict[int, RenderedPage], facts: PdfFacts, hidden_texts: list[str]) -> None:
    pdf = open_pdf(data)
    try:
        for i in range(len(pdf)):
            n = i + 1
            page = pdf[i]
            try:
                textpage = page.get_textpage()
                runs = _runs(textpage)
                textpage.close()
                page_render = by_n.get(n)
                hidden = _hidden_runs(page, page_render, runs) if page_render and page_render.image_share < SCAN_IMAGE_SHARE else []
            finally:
                page.close()
            hidden_ids = {id(r) for r, _ in hidden}
            for run, reason in hidden:
                facts.hidden.append({"page": n, "text": _sample(run.text), "reason": reason})
                hidden_texts.append(run.text)
            visible = _visible_text([r for r in runs if id(r) not in hidden_ids])
            share = page_render.image_share if page_render else 1.0
            facts.methods[n] = "text" if letters(visible) >= MIN_TEXT_LETTERS and share < SCAN_IMAGE_SHARE else "vision"
            if facts.methods[n] == "text":
                facts.visible_text[n] = visible
    finally:
        pdf.close()


def _embedded_jpegs_locked(data: bytes) -> list[bytes]:
    pdf = open_pdf(data)
    try:
        return _embedded_jpegs(pdf)
    finally:
        pdf.close()


def _finish_pdf(data: bytes, facts: PdfFacts, hidden_texts: list[str], blobs: list[bytes]) -> None:
    f = facts.forensics
    methods = set(facts.methods.values())
    f.kind = "typed" if methods == {"text"} else "scanned" if methods <= {"vision"} else "mixed"
    f.metadata, f.xmp, f.file_id, f.fonts, extra = _pypdf_facts(data)
    findings: list[Finding] = []
    if facts.hidden:
        findings.append(Finding(code="hidden_text", severity="alert",
                                detail={"count": len(facts.hidden), "samples": facts.hidden[:6]}))
    findings += text_findings("\n".join(facts.visible_text.values()), "\n".join(hidden_texts))
    findings += _image_findings(blobs)
    if b"c2pa" in data.lower() and not any(x.code in ("ai_image", "content_credentials") for x in findings):
        findings.append(Finding(code="content_credentials", severity="info", detail={}))
    findings += extra
    revisions = _revisions(data)
    if revisions > 1:
        findings.append(Finding(code="edited_after_creation", severity="info", detail={"revisions": revisions}))
    producer = {k: v for k, v in (("creator", f.metadata.get("Creator") or f.xmp.get("CreatorTool", "")),
                                  ("producer", f.metadata.get("Producer") or f.xmp.get("Producer", ""))) if v}
    if producer:
        findings.append(Finding(code="producer", severity="info", detail=producer))
    f.findings = findings


def analyze_image(source: Path, kind: SourceKind) -> Forensics:
    data = source.read_bytes()
    f = Forensics(kind="image", sha256=hashlib.sha256(data).hexdigest())
    f.findings = _image_findings([data])
    return f


def author_mismatch(forensics: Forensics, student_name: str) -> Finding | None:
    """The PDF's author is a real name that is not the student's (a file written by someone else)."""
    author = (forensics.metadata.get("Author") or forensics.xmp.get("Creator") or "").strip()
    if normalize_text(author) in {normalize_text(g) for g in GENERIC_AUTHORS} or not student_name.strip():
        return None
    a = set(re.findall(r"\w{3,}", normalize_text(author)))
    s = set(re.findall(r"\w{3,}", normalize_text(student_name)))
    if not a or a & s or any(x[:4] == y[:4] for x in a for y in s):
        return None
    return Finding(code="author_mismatch", severity="info", detail={"author": author[:120]})
