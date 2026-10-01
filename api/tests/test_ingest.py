import pytest

from app.ingest import MAX_MATERIAL_CHARS, EmptyMaterialError, build_material
from tests.conftest import make_pdf


def test_pasted_text_only():
    assert build_material(None, "  hello ") == "hello"


def test_pdf_text_extracted():
    assert "Gradient descent notes" in build_material(make_pdf("Gradient descent notes"), None)


def test_pdf_then_text_joined():
    out = build_material(make_pdf("PDFTEXT"), "PASTED")
    assert out.index("PDFTEXT") < out.index("PASTED") and "\n\n" in out


def test_truncates():
    assert len(build_material(None, "x" * 70_000)) == MAX_MATERIAL_CHARS


def test_blank_pdf_and_no_text_raises():
    with pytest.raises(EmptyMaterialError, match="No readable text found in the uploaded material"):
        build_material(make_pdf(None), "   ")


def test_corrupt_pdf_raises():
    with pytest.raises(EmptyMaterialError, match="Could not read the uploaded PDF"):
        build_material(b"not a pdf", None)
