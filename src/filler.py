import logging
import re
from datetime import datetime
from typing import Any, Optional, Tuple

from pdfrw import PdfReader, PdfWriter

from src.llm import LLM

logger = logging.getLogger(__name__)

# Truncate logged values to avoid huge log lines / PII dumps
_LOG_PREVIEW_LEN = 80

# Reasonable cap for PDF text fields (sanitization)
_MAX_FIELD_CHARS = 8000

_ACTION_OK = "ok"
_ACTION_COERCED = "coerced"
_ACTION_SKIPPED = "skipped"

# Loose date patterns (YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY)
_DATE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}$|^\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}$"
)


def _log_preview(value: Any) -> str:
    s = repr(value)
    if len(s) > _LOG_PREVIEW_LEN:
        return s[:_LOG_PREVIEW_LEN] + "..."
    return s


def _pdf_field_name(t: Any) -> str:
    """Normalize a PDF annotation field name to a plain string."""
    if t is None:
        return ""
    s = str(t)
    if len(s) >= 2 and s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
    return s.strip()


def _normalize_expected_type(raw: Optional[str]) -> str:
    if not raw or not str(raw).strip():
        return "string"
    x = str(raw).strip().lower()
    if x in ("number", "numeric", "float", "int", "integer", "decimal"):
        return "number"
    if x in ("email", "e-mail"):
        return "email"
    if x in ("date",):
        return "date"
    return "string"


def _strip_control_chars(s: str) -> str:
    return "".join(ch for ch in s if ch == "\n" or ch == "\t" or (ord(ch) >= 32))


def _prepare_value_for_pdf(
    raw: Any,
    expected_type: Optional[str],
    field_label: str,
) -> Tuple[Optional[str], str, str]:
    """
    Validate and sanitize a value for writing to a PDF field.

    Returns (string to write, action, reason). action is ok|coerced|skipped.
    If skipped, returned string is None.
    """
    t = _normalize_expected_type(expected_type)

    if raw is None:
        return None, _ACTION_SKIPPED, "value is None"

    if isinstance(raw, list):
        joined = "; ".join(str(x).strip() for x in raw if x is not None)
        raw = joined
        if not raw:
            return None, _ACTION_SKIPPED, "empty list after join"

    if isinstance(raw, bool):
        return None, _ACTION_SKIPPED, "boolean values are not written to PDF fields"

    if not isinstance(raw, (str, int, float)):
        return (
            None,
            _ACTION_SKIPPED,
            f"unsupported type {type(raw).__name__}",
        )

    if isinstance(raw, (int, float)):
        s = str(raw)
        if t == "number":
            return s, _ACTION_OK, ""
        if t == "string":
            return s, _ACTION_COERCED, "numeric coerced to string for text field"
        if t == "email":
            return None, _ACTION_SKIPPED, "numeric incompatible with email field"
        if t == "date":
            return None, _ACTION_SKIPPED, "numeric incompatible with date field"

    assert isinstance(raw, str)
    s = raw.strip().replace('"', "")
    if s == "" or s == "-1":
        return None, _ACTION_SKIPPED, "empty or sentinel -1 (no value extracted)"

    if t == "number":
        try:
            v = float(s.replace(",", ""))
            out = str(int(v)) if v == int(v) else str(v)
            if out != s:
                return out, _ACTION_COERCED, f"coerced string to number: {_log_preview(s)} -> {out}"
            return out, _ACTION_OK, ""
        except ValueError:
            return None, _ACTION_SKIPPED, f"not a valid number: {_log_preview(s)}"

    if t == "email":
        if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s):
            return s, _ACTION_OK, ""
        return None, _ACTION_SKIPPED, f"invalid email format: {_log_preview(s)}"

    if t == "date":
        if _DATE_PATTERN.match(s):
            return s, _ACTION_OK, ""
        return None, _ACTION_SKIPPED, f"date format not recognized: {_log_preview(s)}"

    # string (default)
    cleaned = _strip_control_chars(s)
    if len(cleaned) > _MAX_FIELD_CHARS:
        cleaned = cleaned[:_MAX_FIELD_CHARS]
        logger.info(
            "Field %r truncated to %s characters for PDF",
            field_label,
            _MAX_FIELD_CHARS,
        )
    if cleaned != s:
        return cleaned, _ACTION_COERCED, "removed control characters or truncated"
    return cleaned, _ACTION_OK, ""


def _count_form_widgets(pdf) -> int:
    n = 0
    for page in pdf.pages:
        if not page.Annots:
            continue
        sorted_annots = sorted(
            page.Annots, key=lambda a: (-float(a.Rect[1]), float(a.Rect[0]))
        )
        for annot in sorted_annots:
            if annot.Subtype == "/Widget" and annot.T:
                n += 1
    return n


class Filler:
    """
    Fills PDF form widgets using LLM-extracted answers.

    For each widget (in visual order: top-to-bottom, left-to-right, pages in
    order), the i-th answer corresponds to the i-th key/value in
    ``LLM.get_data()`` iteration order. Optional per-field types are read from
    ``llm._target_fields`` (same dict the LLM uses: field name -> type string
    such as ``string``, ``number``, ``email``, ``date``).

    Values are validated and sanitized before writing. Missing or invalid values
    are skipped (widget left unchanged) and logged. Coercions and skips are
    recorded at INFO/WARNING for auditing.
    """

    def __init__(self):
        pass

    def fill_form(self, pdf_form: str, llm: LLM):
        """
        Run the LLM pipeline, then write answers into the PDF template.

        Uses ``llm._target_fields`` when present to choose validation rules by
        field name. Index ``i`` aligns the sorted PDF widgets (global order across
        pages) with ``list(llm.get_data().values())[i]`` and the parallel key
        ``list(llm.get_data().keys())[i]``.

        Sanitization: strings are stripped; lists are joined with ``"; "``;
        numbers may be coerced from numeric strings; overly long text is
        truncated. Sentinel ``-1`` or empty strings skip the field.
        """
        output_pdf = (
            pdf_form[:-4]
            + "_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_filled.pdf"
        )

        t2j = llm.main_loop()
        textbox_answers = t2j.get_data()
        field_keys = list(textbox_answers.keys())
        answers_list = list(textbox_answers.values())

        pdf = PdfReader(pdf_form)
        total_widgets = _count_form_widgets(pdf)
        n_answers = len(answers_list)
        if n_answers < total_widgets:
            logger.warning(
                "Fewer LLM answers (%s) than PDF fields (%s); some fields will be left blank",
                n_answers,
                total_widgets,
            )
        elif n_answers > total_widgets:
            logger.warning(
                "More LLM answers (%s) than PDF fields (%s); extra values are unused",
                n_answers,
                total_widgets,
            )

        i = 0
        for page in pdf.pages:
            if page.Annots:
                sorted_annots = sorted(
                    page.Annots, key=lambda a: (-float(a.Rect[1]), float(a.Rect[0]))
                )

                for annot in sorted_annots:
                    if annot.Subtype == "/Widget" and annot.T:
                        pdf_name = _pdf_field_name(annot.T)
                        if i >= len(answers_list):
                            logger.warning(
                                "No LLM answer for PDF field %r; leaving blank",
                                pdf_name or annot.T,
                            )
                            continue

                        raw = answers_list[i]
                        key = field_keys[i] if i < len(field_keys) else ""
                        schema = getattr(llm, "_target_fields", None) or {}
                        expected = None
                        if isinstance(schema, dict) and key in schema:
                            expected = schema[key]

                        final, action, reason = _prepare_value_for_pdf(
                            raw, expected, key or pdf_name
                        )

                        if action == _ACTION_SKIPPED:
                            logger.warning(
                                "Skipped PDF field %r (answer key %r): %s; raw=%s",
                                pdf_name or annot.T,
                                key,
                                reason,
                                _log_preview(raw),
                            )
                        elif action == _ACTION_COERCED:
                            logger.info(
                                "Coerced PDF field %r (answer key %r): %s; raw=%s -> %s",
                                pdf_name or annot.T,
                                key,
                                reason,
                                _log_preview(raw),
                                _log_preview(final),
                            )
                            annot.V = f"{final}"
                            annot.AP = None
                        else:
                            annot.V = f"{final}"
                            annot.AP = None

                        i += 1

        PdfWriter().write(output_pdf, pdf)

        return output_pdf
