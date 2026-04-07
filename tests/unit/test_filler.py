import os
import sys
from pathlib import Path
from shutil import copyfile
from typing import Any

import pytest
from pdfrw import PdfReader

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.filler import Filler


BASE_DIR = Path(__file__).resolve().parent.parent
FW4_FIXTURE_PATH = BASE_DIR / "forms" / "fw4.pdf"


def _clean_pdf_value(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    # pdfrw commonly wraps strings as "(...)".
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
    return s.strip()


def _extract_widget_values(pdf_path: str) -> dict[str, str | None]:
    pdf = PdfReader(pdf_path)
    out: dict[str, str | None] = {}
    for page in pdf.pages:
        if not getattr(page, "Annots", None):
            continue
        for annot in page.Annots:
            if getattr(annot, "Subtype", None) != "/Widget" or not getattr(annot, "T", None):
                continue
            field_name = str(annot.T).strip("() /")
            out[field_name] = _clean_pdf_value(getattr(annot, "V", None))
    return out


def _get_widget_names_in_fill_order(pdf_path: str) -> list[str]:
    """
    Replicates the fill order in `src.filler.Filler.fill_form`:
    - For each page: sort page.Annots by (-Rect.y1, Rect.x0)
    - Then fill only widgets with a non-empty annot.T, in that sorted order.
    """
    pdf = PdfReader(pdf_path)
    order: list[str] = []

    for page in pdf.pages:
        if not getattr(page, "Annots", None):
            continue

        sorted_annots = sorted(page.Annots, key=lambda a: (-float(a.Rect[1]), float(a.Rect[0])))
        for annot in sorted_annots:
            if getattr(annot, "Subtype", None) == "/Widget" and getattr(annot, "T", None):
                order.append(str(annot.T).strip("() /"))
    return order


def test_fill_form_by_name_updates_matching_widget_values_and_writes_pdf(tmp_path: Path):
    filler = Filler()

    assert FW4_FIXTURE_PATH.exists(), f"Missing fixture: {FW4_FIXTURE_PATH}"
    input_pdf = FW4_FIXTURE_PATH

    # Pick two widget names from the real PDF.
    before_values = _extract_widget_values(str(input_pdf))
    widget_names = [k for k in before_values.keys() if before_values[k] is not None or before_values[k] is None]
    assert len(widget_names) >= 2, "Fixture PDF does not have at least 2 widgets"

    name1, name2 = widget_names[0], widget_names[1]
    out_value_1 = "UNIT_TEST_VALUE_1"
    out_value_2 = "UNIT_TEST_VALUE_2"

    out_pdf_path = filler.fill_form_by_name(
        pdf_form=str(input_pdf),
        field_values={name1: out_value_1, name2: out_value_2},
    )

    assert os.path.exists(out_pdf_path), f"Output PDF not created: {out_pdf_path}"

    after_values = _extract_widget_values(out_pdf_path)
    assert after_values[name1] == out_value_1
    assert after_values[name2] == out_value_2

    # Unmatched widgets should not be overwritten to our unit-test values.
    unmatched = widget_names[2]
    assert after_values[unmatched] not in {out_value_1, out_value_2}

    # Ensure NeedAppearances was forced (for visibility in viewers).
    out_pdf = PdfReader(out_pdf_path)
    if getattr(out_pdf.Root, "AcroForm", None):
        need = getattr(out_pdf.Root.AcroForm, "NeedAppearances", None)
        assert need is not None


def test_fill_form_assigns_answers_in_visual_order_and_stops_when_exhausted(tmp_path: Path):
    filler = Filler()

    assert FW4_FIXTURE_PATH.exists(), f"Missing fixture: {FW4_FIXTURE_PATH}"
    input_pdf = FW4_FIXTURE_PATH

    fill_order = _get_widget_names_in_fill_order(str(input_pdf))
    assert len(fill_order) >= 3, "Fixture PDF fill order is unexpectedly short"

    # Give fewer answers than widgets to ensure exhaustion behavior.
    answers = ["UNIT_TEST_FILL_0", "UNIT_TEST_FILL_1"]

    class _FakeT2J:
        def get_data(self) -> dict[str, str]:
            # In `Filler.fill_form`, answers_list = list(textbox_answers.values()).
            # Use insertion order to control which widgets get which value.
            return {"a": answers[0], "b": answers[1]}

    class _FakeLLM:
        def main_loop(self):
            return _FakeT2J()

    out_pdf_path = filler.fill_form(pdf_form=str(input_pdf), llm=_FakeLLM())
    assert os.path.exists(out_pdf_path), f"Output PDF not created: {out_pdf_path}"

    values = _extract_widget_values(out_pdf_path)

    # First two widgets in fill order should be set.
    assert values[fill_order[0]] == answers[0]
    assert values[fill_order[1]] == answers[1]

    # The next widget should not receive a value from `answers`.
    for next_widget in fill_order[2:]:
        assert values[next_widget] not in set(answers)

