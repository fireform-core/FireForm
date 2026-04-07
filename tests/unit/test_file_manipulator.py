import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pdfrw import PdfReader
from sqlmodel import SQLModel, Session, create_engine

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from api.db.models import Datatype, ReportSchema, Template
from api.db.repositories import (
    add_template_to_schema,
    create_report_schema,
    create_template,
    get_schema_fields,
    update_schema_field,
)
from src.file_manipulator import FileManipulator
from src.report_schema import ReportSchemaProcessor


FORMS_DIR = Path(__file__).resolve().parent.parent / "forms"
FW4_PDF = FORMS_DIR / "fw4.pdf"
FW4_TEMPLATE_PDF = FORMS_DIR / "fw4_template.pdf"
I9_PDF = FORMS_DIR / "i-9.pdf"

test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})


@pytest.fixture(name="session")
def session_fixture():
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        yield session
    SQLModel.metadata.drop_all(test_engine)


def _clean_pdf_value(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
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


def _get_pdf_widget_raw_field_names(pdf_path: str) -> list[str]:
    """Raw widget names as `Filler.fill_form_by_name` matches them (order: first seen per page walk)."""
    pdf = PdfReader(pdf_path)
    names: list[str] = []
    for page in pdf.pages:
        if not getattr(page, "Annots", None):
            continue
        for annot in page.Annots:
            if getattr(annot, "Subtype", None) != "/Widget" or not getattr(annot, "T", None):
                continue
            raw = str(annot.T).strip("() /")
            if raw and raw not in names:
                names.append(raw)
    return names


def _widget_names_in_fill_order(pdf_path: str) -> list[str]:
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


def _widget_values_in_fill_order(pdf_path: str) -> list[str | None]:
    """`/V` per widget in the same order as `_widget_names_in_fill_order`."""
    pdf = PdfReader(pdf_path)
    out: list[str | None] = []
    for page in pdf.pages:
        if not getattr(page, "Annots", None):
            continue
        sorted_annots = sorted(page.Annots, key=lambda a: (-float(a.Rect[1]), float(a.Rect[0])))
        for annot in sorted_annots:
            if getattr(annot, "Subtype", None) == "/Widget" and getattr(annot, "T", None):
                out.append(_clean_pdf_value(getattr(annot, "V", None)))
    return out


def _ensure_fw4_template_pdf() -> str:
    assert FW4_PDF.is_file(), f"Missing fixture PDF: {FW4_PDF}"
    fm = FileManipulator()
    out = fm.create_template(str(FW4_PDF.resolve()))
    assert out == str(FW4_TEMPLATE_PDF.resolve())
    return str(FW4_TEMPLATE_PDF.resolve())


@pytest.mark.skipif(not FW4_PDF.is_file(), reason="tests/forms/fw4.pdf required")
def test_extract_template_field_map_matches_unique_widgets():
    template_pdf = _ensure_fw4_template_pdf()
    fm = FileManipulator()
    m = fm.extract_template_field_map(template_pdf)
    assert m == {n: "string" for n in _get_pdf_widget_raw_field_names(template_pdf)}


def test_file_manipulator_fill_form_visual_order_matches_val_i():
    """
    Real prepare_form -> fw4_template.pdf; LLM mocked. Dict values follow widget order (val_0, val_1, …).
    Filled PDF is written under tests/forms/.
    """
    template_pdf = _ensure_fw4_template_pdf()
    order = _widget_names_in_fill_order(template_pdf)
    n = len(order)
    assert n > 0

    fake_llm_payload = {f"__slot_{i}": f"val_{i}" for i in range(n)}

    with patch("src.file_manipulator.LLM") as MockLLM:
        mock_t2j = MagicMock()
        mock_t2j.get_data.return_value = fake_llm_payload
        MockLLM.return_value.main_loop.return_value = mock_t2j
        fm = FileManipulator()
        out_path = fm.fill_form(
            user_input="synthetic transcript for testing",
            fields=order,
            pdf_form_path=template_pdf,
        )

    assert out_path and os.path.isfile(out_path)
    assert Path(out_path).resolve().parent == FORMS_DIR.resolve()

    filled = _widget_values_in_fill_order(out_path)
    assert len(filled) == n
    for i in range(n):
        assert filled[i] == f"val_{i}", f"position {i} field {order[i]!r}"


def test_file_manipulator_fill_report_distributes_val_i_including_shared_canonical(session: Session):
    """
    Schema + fw4 template PDF; two PDF fields share one canonical name (same extracted value on both).
    LLM mocked with val_0..val_{m-1} for each canonical key (sorted). Assert filled PDF matches distribute().
    """
    template_pdf = _ensure_fw4_template_pdf()
    order = _widget_names_in_fill_order(template_pdf)
    assert len(order) >= 8

    # Two distinct widgets share this canonical key — both must receive the same value after fill.
    shared_canon = "shared_canon_key"
    i_a, i_b = 2, 5
    name_a, name_b = order[i_a], order[i_b]
    assert name_a != name_b

    unique_names = _get_pdf_widget_raw_field_names(template_pdf)
    fields_map = {w: "string" for w in unique_names}
    schema = create_report_schema(session, ReportSchema(name="fw4-schema", description="d", use_case="u"))
    tpl = create_template(
        session,
        Template(name="fw4-tpl", fields=fields_map, pdf_path=template_pdf),
    )
    add_template_to_schema(session, schema.id, tpl.id)

    rows_by_name = {f.field_name: f for f in get_schema_fields(session, schema.id)}
    update_schema_field(
        session, schema.id, rows_by_name[name_a].id, {"canonical_name": shared_canon, "data_type": Datatype.STRING}
    )
    update_schema_field(
        session, schema.id, rows_by_name[name_b].id, {"canonical_name": shared_canon, "data_type": Datatype.STRING}
    )

    # A couple of non-sequential canonical names (indices disjoint from the shared pair).
    extra = ("emp_alias", "tax_pin")
    for j, idx in enumerate((6, 7)):
        fn = order[idx]
        if fn in (name_a, name_b):
            continue
        update_schema_field(
            session,
            schema.id,
            rows_by_name[fn].id,
            {"canonical_name": extra[j], "data_type": Datatype.STRING},
        )

    canonical_schema = ReportSchemaProcessor.canonize(session, schema.id)
    canonical_target = ReportSchemaProcessor.build_extraction_target(canonical_schema)

    sorted_entries = sorted(canonical_schema.canonical_fields, key=lambda e: e.canonical_name)
    extracted = {e.canonical_name: f"val_{i}" for i, e in enumerate(sorted_entries)}

    with patch("src.file_manipulator.LLM") as MockLLM:
        mock_t2j = MagicMock()
        mock_t2j.get_data.return_value = extracted
        MockLLM.return_value.main_loop.return_value = mock_t2j
        fm = FileManipulator()
        outputs = fm.fill_report(
            session=session,
            user_input="synthetic report transcript",
            schema_id=schema.id,
            canonical_target=canonical_target,
        )

    assert tpl.id in outputs
    out_pdf = outputs[tpl.id]
    assert os.path.isfile(out_pdf)
    assert Path(out_pdf).resolve().parent == FORMS_DIR.resolve()

    distribution = ReportSchemaProcessor.distribute(session, schema.id, extracted)
    expected_by_pdf = distribution[tpl.id]

    shared_val = extracted[shared_canon]
    assert expected_by_pdf[name_a] == shared_val == expected_by_pdf[name_b]

    values = _extract_widget_values(out_pdf)
    for pdf_field, expected in expected_by_pdf.items():
        assert values.get(pdf_field) == str(expected), pdf_field


@pytest.mark.skipif(not I9_PDF.is_file(), reason=f"Missing {I9_PDF} (add USCIS I-9 PDF to tests/forms)")
def test_file_manipulator_fill_report_two_pdfs_shared_canonical_cross_file(session: Session):
    """
    One schema, fw4 + i-9 templates: a canonical name is assigned to one field on each PDF so both
    receive the same extracted value. LLM mocked; assert both outputs under tests/forms/ match distribute().
    Uses prepared *_template.pdf paths and widget names from those files (commonforms output).
    """
    assert FW4_PDF.is_file(), f"Missing {FW4_PDF}"
    fm0 = FileManipulator()
    fm0.create_template(str(FW4_PDF.resolve()))
    fm0.create_template(str(I9_PDF.resolve()))
    fw4_path = str(FW4_TEMPLATE_PDF.resolve())
    i9_path = str((I9_PDF.parent / (I9_PDF.stem + "_template.pdf")).resolve())

    fw4_names = _get_pdf_widget_raw_field_names(fw4_path)
    i9_names = _get_pdf_widget_raw_field_names(i9_path)
    assert len(fw4_names) >= 6
    assert len(i9_names) >= 7

    cross_canon = "cross_file_shared_value"
    fw4_field_a = fw4_names[2]
    fw4_field_b = fw4_names[5]
    i9_field_a = i9_names[3]
    i9_field_b = i9_names[6]

    fields_fw4 = {n: "string" for n in fw4_names}
    fields_i9 = {n: "string" for n in i9_names}

    schema = create_report_schema(
        session, ReportSchema(name="dual-pdf-schema", description="d", use_case="u")
    )
    tpl_fw4 = create_template(
        session,
        Template(name="fw4-tpl", fields=fields_fw4, pdf_path=fw4_path),
    )
    tpl_i9 = create_template(
        session,
        Template(name="i9-tpl", fields=fields_i9, pdf_path=i9_path),
    )
    add_template_to_schema(session, schema.id, tpl_fw4.id)
    add_template_to_schema(session, schema.id, tpl_i9.id)

    by_tpl_and_name: dict[tuple[int, str], object] = {}
    for f in get_schema_fields(session, schema.id):
        by_tpl_and_name[(f.source_template_id, f.field_name)] = f

    def _set_canon(tpl_id: int, field_name: str, canon: str) -> None:
        sf = by_tpl_and_name[(tpl_id, field_name)]
        update_schema_field(
            session,
            schema.id,
            sf.id,
            {"canonical_name": canon, "data_type": Datatype.STRING},
        )

    # Same canonical on two different files -> one extraction value applied to both widgets.
    _set_canon(tpl_fw4.id, fw4_field_a, cross_canon)
    _set_canon(tpl_i9.id, i9_field_a, cross_canon)

    # Second cross-file pair (different canonical) to stress junction mapping per template.
    cross_canon_2 = "cross_file_shared_value_2"
    _set_canon(tpl_fw4.id, fw4_field_b, cross_canon_2)
    _set_canon(tpl_i9.id, i9_field_b, cross_canon_2)

    canonical_schema = ReportSchemaProcessor.canonize(session, schema.id)
    canonical_target = ReportSchemaProcessor.build_extraction_target(canonical_schema)

    sorted_entries = sorted(canonical_schema.canonical_fields, key=lambda e: e.canonical_name)
    extracted = {e.canonical_name: f"val_{i}" for i, e in enumerate(sorted_entries)}

    with patch("src.file_manipulator.LLM") as MockLLM:
        mock_t2j = MagicMock()
        mock_t2j.get_data.return_value = extracted
        MockLLM.return_value.main_loop.return_value = mock_t2j
        fm = FileManipulator()
        outputs = fm.fill_report(
            session=session,
            user_input="synthetic cross-form transcript",
            schema_id=schema.id,
            canonical_target=canonical_target,
        )

    assert tpl_fw4.id in outputs and tpl_i9.id in outputs
    for tid in (tpl_fw4.id, tpl_i9.id):
        p = outputs[tid]
        assert os.path.isfile(p)
        assert Path(p).resolve().parent == FORMS_DIR.resolve()

    distribution = ReportSchemaProcessor.distribute(session, schema.id, extracted)

    shared = extracted[cross_canon]
    shared2 = extracted[cross_canon_2]
    assert distribution[tpl_fw4.id][fw4_field_a] == shared == distribution[tpl_i9.id][i9_field_a]
    assert distribution[tpl_fw4.id][fw4_field_b] == shared2 == distribution[tpl_i9.id][i9_field_b]

    for tid, tpl in (tpl_fw4.id, tpl_fw4), (tpl_i9.id, tpl_i9):
        expected_by_pdf = distribution[tid]
        values = _extract_widget_values(outputs[tid])
        for pdf_field, expected in expected_by_pdf.items():
            assert values.get(pdf_field) == str(expected), f"{tpl.name} {pdf_field!r}"
