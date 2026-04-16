"""
Tests for the Field Mapping Wizard endpoint and PDFFieldDetector.

These tests create minimal PDF files with form fields programmatically
using pypdf, so no external test fixtures are needed.
"""

import io

from pypdf import PdfWriter
from pypdf.annotations import FreeText
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    TextStringObject,
)


def _create_pdf_with_fields(fields: list[dict]) -> bytes:
    """Create a minimal PDF with form widget annotations.

    Args:
        fields: List of dicts with keys:
            - name (str): Field name
            - field_type (str): "/Tx", "/Btn", or "/Ch"
            - rect (list[float]): [x1, y1, x2, y2]

    Returns:
        PDF content as bytes.
    """
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)

    for field_spec in fields:
        annotation = DictionaryObject()
        annotation.update(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/T"): TextStringObject(field_spec["name"]),
                NameObject("/FT"): NameObject(field_spec["field_type"]),
                NameObject("/Rect"): ArrayObject(
                    [FloatObject(v) for v in field_spec["rect"]]
                ),
            }
        )
        writer.add_annotation(page_number=0, annotation=annotation)

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _create_blank_pdf() -> bytes:
    """Create a minimal PDF with no form fields."""
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


# ─── Endpoint Tests ───────────────────────────────────────────────


def test_detect_fields_valid_pdf(client):
    """Upload a PDF with known form fields and verify detection."""
    fields = [
        {"name": "employee_name", "field_type": "/Tx", "rect": [72, 700, 272, 720]},
        {"name": "is_active", "field_type": "/Btn", "rect": [72, 660, 92, 680]},
        {"name": "department", "field_type": "/Ch", "rect": [72, 620, 272, 640]},
    ]
    pdf_bytes = _create_pdf_with_fields(fields)

    response = client.post(
        "/wizard/detect-fields",
        files={"file": ("test_form.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["filename"] == "test_form.pdf"
    assert data["total_pages"] == 1
    assert data["total_fields"] == 3

    page = data["pages"][0]
    assert page["page_number"] == 1
    assert len(page["fields"]) == 3

    # Verify field types are correctly classified
    type_map = {f["field_name"]: f["field_type"] for f in page["fields"]}
    assert type_map["employee_name"] == "Text"
    assert type_map["is_active"] == "Button"
    assert type_map["department"] == "Choice"


def test_detect_fields_bounding_box(client):
    """Verify bounding box coordinates are correctly extracted."""
    fields = [
        {"name": "test_field", "field_type": "/Tx", "rect": [72.0, 700.0, 272.0, 720.0]},
    ]
    pdf_bytes = _create_pdf_with_fields(fields)

    response = client.post(
        "/wizard/detect-fields",
        files={"file": ("test_rect.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200
    data = response.json()
    rect = data["pages"][0]["fields"][0]["rect"]

    assert rect["x"] == 72.0
    assert rect["y"] == 700.0
    assert rect["width"] == 200.0
    assert rect["height"] == 20.0


def test_detect_fields_no_widgets(client):
    """Upload a PDF without form fields and verify graceful handling."""
    pdf_bytes = _create_blank_pdf()

    response = client.post(
        "/wizard/detect-fields",
        files={"file": ("blank.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total_fields"] == 0
    assert data["total_pages"] == 1
    assert len(data["pages"]) == 1
    assert len(data["pages"][0]["fields"]) == 0


def test_detect_fields_non_pdf(client):
    """Upload a non-PDF file and expect 400 error."""
    response = client.post(
        "/wizard/detect-fields",
        files={"file": ("readme.txt", b"Hello world", "text/plain")},
    )

    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


def test_detect_fields_no_file(client):
    """POST with no file and expect 422 validation error."""
    response = client.post("/wizard/detect-fields")
    assert response.status_code == 422


def test_detect_fields_mixed_types(client):
    """Upload a PDF with all three field types and verify all are detected."""
    fields = [
        {"name": "full_name", "field_type": "/Tx", "rect": [50, 700, 250, 720]},
        {"name": "email", "field_type": "/Tx", "rect": [50, 660, 250, 680]},
        {"name": "agree_terms", "field_type": "/Btn", "rect": [50, 620, 70, 640]},
        {"name": "priority", "field_type": "/Ch", "rect": [50, 580, 200, 600]},
    ]
    pdf_bytes = _create_pdf_with_fields(fields)

    response = client.post(
        "/wizard/detect-fields",
        files={"file": ("mixed_form.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total_fields"] == 4

    types = [f["field_type"] for f in data["pages"][0]["fields"]]
    assert "Text" in types
    assert "Button" in types
    assert "Choice" in types


def test_detect_fields_response_schema(client):
    """Verify the response matches the expected schema structure."""
    fields = [
        {"name": "test", "field_type": "/Tx", "rect": [0, 0, 100, 20]},
    ]
    pdf_bytes = _create_pdf_with_fields(fields)

    response = client.post(
        "/wizard/detect-fields",
        files={"file": ("schema_test.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200
    data = response.json()

    # Top-level keys
    assert "filename" in data
    assert "total_pages" in data
    assert "total_fields" in data
    assert "pages" in data

    # Page-level keys
    page = data["pages"][0]
    assert "page_number" in page
    assert "fields" in page

    # Field-level keys
    field = page["fields"][0]
    assert "field_name" in field
    assert "field_type" in field
    assert "raw_type" in field
    assert "rect" in field

    # Rect keys
    rect = field["rect"]
    assert "x" in rect
    assert "y" in rect
    assert "width" in rect
    assert "height" in rect
