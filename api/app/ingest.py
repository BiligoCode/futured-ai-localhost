import io
from collections.abc import Iterable

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


def build_material(pdfs: Iterable[bytes], pasted_text: str | None) -> str:
    parts = [extract_pdf_text(data).strip() for data in pdfs if data]
    if pasted_text:
        parts.append(pasted_text.strip())
    material = "\n\n".join(p for p in parts if p)
    if not material:
        raise EmptyMaterialError("No readable text found in the uploaded material")
    return material[:MAX_MATERIAL_CHARS]
