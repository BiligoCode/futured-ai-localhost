import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_MATERIAL_CHARS = 60_000


class EmptyMaterialError(ValueError):
    pass


def extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise EmptyMaterialError("Could not read the uploaded PDF") from exc


def build_material(pdf_bytes: bytes | None, pasted_text: str | None) -> str:
    parts = []
    if pdf_bytes:
        parts.append(extract_pdf_text(pdf_bytes).strip())
    if pasted_text:
        parts.append(pasted_text.strip())
    material = "\n\n".join(p for p in parts if p)
    if not material:
        raise EmptyMaterialError("No readable text found in the uploaded material")
    return material[:MAX_MATERIAL_CHARS]
