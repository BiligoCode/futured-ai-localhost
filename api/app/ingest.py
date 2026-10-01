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
    """The course material as text; empty when the professor gave none (the model then uses its own knowledge).

    Uploaded PDFs without any readable text are an error: the professor expects them to be used."""
    pdfs = [data for data in pdfs if data]
    parts = [extract_pdf_text(data).strip() for data in pdfs]
    if pdfs and not any(parts):
        raise EmptyMaterialError("No readable text found in the uploaded material")
    if pasted_text:
        parts.append(pasted_text.strip())
    return "\n\n".join(p for p in parts if p)[:MAX_MATERIAL_CHARS]
