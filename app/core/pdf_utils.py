import re
from pathlib import Path

from app.core import paths

# PDF field-type codes -> the type values the frontend field builder uses.
_FIELD_TYPE_BY_FT = {"/Tx": "string", "/Btn": "checkbox", "/Ch": "list", "/Sig": "signature"}


def _pdf_text(value) -> str:
    """Decode a pdfrw string (field name / tooltip) to plain text."""
    if value is None:
        return ""
    if hasattr(value, "to_unicode"):
        return value.to_unicode().strip()
    return str(value).strip()


def _humanize(name: str) -> str:
    """Turn a raw field name into a readable description (JobTitle -> Job Title)."""
    text = re.sub(r"_+", " ", name)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_pdf_fields(pdf_path: str) -> list[dict] | None:
    """Fillable widgets in the same order Filler.fill_form writes them
    (top-to-bottom, left-to-right per page), so seeded rows line up with the
    fill order. Returns None if the PDF can't be read."""
    try:
        from pdfrw import PdfReader
        candidate = Path(pdf_path)
        if not candidate.is_absolute():
            candidate = (paths.PROJECT_ROOT / candidate).resolve()
        pdf = PdfReader(str(candidate))
        fields: list[dict] = []
        for page in pdf.pages:
            widgets = [a for a in (page.Annots or []) if a.Subtype == "/Widget" and a.T]
            widgets.sort(key=lambda a: (-float(a.Rect[1]), float(a.Rect[0])))
            for annot in widgets:
                name = _pdf_text(annot.T)
                fields.append({
                    "name": name,
                    "description": _pdf_text(annot.TU) or _humanize(name),
                    "type": _FIELD_TYPE_BY_FT.get(str(annot.FT), "string"),
                })
        return fields
    except Exception:
        return None


def _count_pdf_widgets(pdf_path: str) -> int | None:
    """Number of fillable widgets in a PDF, or None if unreadable."""
    fields = _extract_pdf_fields(pdf_path)
    return None if fields is None else len(fields)
