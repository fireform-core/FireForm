"""Tests for template field detection (app/services/template_detection.py).

commonforms is mocked throughout. What is exercised here is everything around
it: reading widget rectangles into layout boxes, naming fields, picking the
label next to a box, scoring mapping suggestions, and writing the draft back.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    TextStringObject,
)
from sqlmodel import Session

from app.api.schemas.enums import DetectionStatus, FieldSource
from app.api.schemas.templates import MappingSuggestion, TemplateFieldLayout
from app.db.repositories import create_job, create_template_upload, get_job_by_uuid
from app.models import Job, TemplateUpload
from app.services import template_detection as detection


# ---------------------------------------------------------------------------
# Fixtures: a small PDF carrying real form widgets
# ---------------------------------------------------------------------------
def _widget(name, rect):
    return DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/FT"): NameObject("/Tx"),
            NameObject("/Rect"): ArrayObject([FloatObject(v) for v in rect]),
            NameObject("/T"): TextStringObject(name),
        }
    )


@pytest.fixture
def widget_pdf(tmp_path):
    """A one-page PDF with two text widgets, the lower one listed first."""
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    page = writer.pages[0]
    annotations = ArrayObject()
    for name, rect in (
        ("fire_cause", (188.33, 560.0, 388.33, 578.0)),
        ("Incident No.", (188.33, 621.33, 315.66, 650.0)),
    ):
        annotations.append(writer._add_object(_widget(name, rect)))
    page[NameObject("/Annots")] = annotations

    path = tmp_path / "form.pdf"
    with path.open("wb") as handle:
        writer.write(handle)
    return path


@pytest.fixture
def flat_pdf(tmp_path):
    """A page with no widgets at all, the case commonforms exists for."""
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    path = tmp_path / "flat.pdf"
    with path.open("wb") as handle:
        writer.write(handle)
    return path


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def test_read_pages_returns_points(widget_pdf):
    pages = detection.read_pages(widget_pdf)
    assert [p.model_dump() for p in pages] == [{"page": 0, "width": 612.0, "height": 792.0}]


def test_widget_rects_become_layout_boxes(widget_pdf):
    drafts = detection.build_draft_fields(widget_pdf)
    layout = drafts[0].field.layout
    assert layout.page == 0
    assert layout.x == pytest.approx(188.33)
    assert layout.y == pytest.approx(621.33)
    assert layout.width == pytest.approx(127.33, abs=0.01)
    assert layout.height == pytest.approx(28.67, abs=0.01)


def test_boxes_come_back_in_reading_order(widget_pdf):
    drafts = detection.build_draft_fields(widget_pdf)
    # The higher box on the page comes first even though it is second in the
    # annotation array.
    assert [d.field.layout.y for d in drafts] == sorted(
        [d.field.layout.y for d in drafts], reverse=True
    )


# ---------------------------------------------------------------------------
# Field naming
# ---------------------------------------------------------------------------
def test_widget_names_are_turned_into_slugs(widget_pdf):
    names = [d.field.field_name for d in detection.build_draft_fields(widget_pdf)]
    assert names == ["incident_no", "fire_cause"]


def test_repeated_names_are_made_unique():
    used = set()
    assert detection._field_name("Date", used, 1) == "date"
    assert detection._field_name("Date", used, 2) == "date_2"
    assert detection._field_name("Date", used, 3) == "date_3"


def test_an_unnamed_box_falls_back_to_its_position():
    assert detection._field_name(None, set(), 7) == "field_7"


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------
def _layout(**over):
    base = {"page": 0, "x": 200.0, "y": 600.0, "width": 120.0, "height": 18.0}
    base.update(over)
    return TemplateFieldLayout(**base)


def test_label_to_the_left_is_preferred():
    texts = [("Incident No.", 120.0, 604.0), ("Section B", 200.0, 622.0)]
    assert detection._nearest_label(_layout(), texts) == "Incident No."


def test_label_above_is_used_when_nothing_sits_to_the_left():
    texts = [("Incident No.", 200.0, 622.0)]
    assert detection._nearest_label(_layout(), texts) == "Incident No."


def test_far_away_text_is_not_a_label():
    texts = [("Unrelated", 5.0, 604.0)]
    assert detection._nearest_label(_layout(), texts) is None


def test_no_text_means_no_label(widget_pdf):
    # The fixture PDF has widgets but no page text.
    assert all(d.detected_label is None for d in detection.build_draft_fields(widget_pdf))


# ---------------------------------------------------------------------------
# Mapping suggestions
# ---------------------------------------------------------------------------
def test_a_clear_label_gets_suggestions():
    suggestions = detection.suggest_mappings("Incident No.")
    assert suggestions
    assert suggestions[0].path == "report_metadata.incident_number"
    assert suggestions[0].section == "report_metadata"


def test_a_meaningless_label_gets_nothing():
    assert detection.suggest_mappings("qwertyuiop") == []


def test_a_missing_label_gets_nothing():
    assert detection.suggest_mappings(None) == []


def test_a_confident_suggestion_is_pre_applied(widget_pdf):
    drafts = detection.build_draft_fields(widget_pdf)
    incident = drafts[0].field
    # The widget is named "Incident No.", which scores high enough to apply.
    assert incident.source == FieldSource.schema
    assert incident.incident_mapping == "report_metadata.incident_number"


def test_a_weak_suggestion_is_only_offered(monkeypatch):
    from app.api.schemas.templates import TemplateField
    from app.api.schemas.enums import TemplateFieldType

    field = TemplateField(
        field_name="box_1",
        field_type=TemplateFieldType.string,
        source=FieldSource.manual,
        required=False,
    )
    weak = [MappingSuggestion(path="location.postal_code", score=0.6)]
    applied = detection._apply_suggestion(field, weak)
    assert applied.source == FieldSource.manual
    assert applied.incident_mapping is None


def test_an_applied_enum_mapping_brings_its_values():
    from app.api.schemas.templates import TemplateField
    from app.api.schemas.enums import TemplateFieldType

    entry = next(e for e in detection.field_catalog.catalog() if e.enum_values)
    field = TemplateField(
        field_name="box_1",
        field_type=TemplateFieldType.string,
        source=FieldSource.manual,
        required=False,
    )
    applied = detection._apply_suggestion(
        field, [MappingSuggestion(path=entry.path, score=0.99)]
    )
    assert applied.field_type == TemplateFieldType.enum
    assert applied.allowed_values == list(entry.enum_values)


# ---------------------------------------------------------------------------
# Running commonforms
# ---------------------------------------------------------------------------
def test_detection_skips_commonforms_when_widgets_exist(widget_pdf):
    with patch("app.services.controller.Controller") as controller:
        drafts = detection.detect_fields(widget_pdf)
    controller.assert_not_called()
    assert len(drafts) == 2


def test_a_flat_pdf_goes_through_commonforms(flat_pdf, widget_pdf):
    instance = MagicMock()
    instance.prepare_fillable.return_value = str(widget_pdf)
    with patch("app.services.controller.Controller", return_value=instance):
        drafts = detection.detect_fields(flat_pdf)
    assert len(drafts) == 2


def test_a_one_page_pdf_is_padded_before_commonforms(flat_pdf, widget_pdf):
    """commonforms cannot read a one-page document, so it never sees one."""
    seen = {}

    def capture(path):
        seen["path"] = path
        seen["pages"] = len(PdfReader(path).pages)
        return str(widget_pdf)

    instance = MagicMock()
    instance.prepare_fillable.side_effect = capture
    with patch("app.services.controller.Controller", return_value=instance):
        detection.detect_fields(flat_pdf)

    assert seen["path"] != str(flat_pdf)
    assert seen["pages"] == 2
    # The padded copy and the fillable it produced are scratch, not artefacts.
    assert not Path(seen["path"]).exists()
    assert not widget_pdf.exists()
    assert flat_pdf.exists()


def test_a_multi_page_pdf_is_passed_through_as_is(tmp_path, widget_pdf):
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    writer.add_blank_page(612, 792)
    flat = tmp_path / "two_pages.pdf"
    with flat.open("wb") as handle:
        writer.write(handle)

    instance = MagicMock()
    instance.prepare_fillable.return_value = str(widget_pdf)
    with patch("app.services.controller.Controller", return_value=instance):
        detection.detect_fields(flat)
    instance.prepare_fillable.assert_called_once_with(str(flat))


def test_boxes_found_on_the_padding_are_dropped(flat_pdf, tmp_path):
    """A box detected on the blank page belongs to no page of the real PDF."""
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    writer.add_blank_page(612, 792)
    for page_ix, name in ((0, "real_box"), (1, "padding_box")):
        page = writer.pages[page_ix]
        annots = ArrayObject()
        annots.append(writer._add_object(_widget(name, (100.0, 100.0, 200.0, 118.0))))
        page[NameObject("/Annots")] = annots
    fillable = tmp_path / "detected.pdf"
    with fillable.open("wb") as handle:
        writer.write(handle)

    instance = MagicMock()
    instance.prepare_fillable.return_value = str(fillable)
    with patch("app.services.controller.Controller", return_value=instance):
        drafts = detection.detect_fields(flat_pdf)

    assert [d.field.layout.page for d in drafts] == [0]


# ---------------------------------------------------------------------------
# The background run
# ---------------------------------------------------------------------------
def _seed_upload(session, pdf_path):
    upload = TemplateUpload(
        pdf_path=str(pdf_path),
        pdf_template_ref="templates/uploads/x.pdf",
        page_count=1,
        pages=[{"page": 0, "width": 612.0, "height": 792.0}],
    )
    return create_template_upload(session, upload)


def _seed_job(session):
    return create_job(
        session, Job(celery_task_id="t", job_type="template_field_detection", status="queued")
    )


def test_run_detection_writes_the_draft(test_engine, widget_pdf):
    with Session(test_engine) as session:
        upload = _seed_upload(session, widget_pdf)
        job = _seed_job(session)

        result = detection.run_detection(session, upload.upload_id, job.job_id)

        assert result["status"] == "completed"
        assert result["detected_fields"] == 2

        session.refresh(upload)
        assert upload.status == DetectionStatus.completed
        assert len(upload.detected_fields) == 2
        assert upload.detected_fields[0]["field"]["layout"]["page"] == 0

        finished = get_job_by_uuid(session, job.job_id)
        assert finished.status == "completed"
        assert finished.progress_percent == 100
        assert finished.result_url == f"/api/v1/templates/pdf/{upload.upload_id}"


def test_run_detection_records_a_failure_without_losing_the_upload(test_engine, flat_pdf):
    with Session(test_engine) as session:
        upload = _seed_upload(session, flat_pdf)
        job = _seed_job(session)

        with patch.object(detection, "detect_fields", side_effect=RuntimeError("model gone")):
            result = detection.run_detection(session, upload.upload_id, job.job_id)

        assert result["status"] == "failed"
        session.refresh(upload)
        assert upload.status == DetectionStatus.failed
        assert upload.detection_error == "model gone"
        # Geometry survives, so the editor can still be used by hand.
        assert upload.page_count == 1

        failed_job = get_job_by_uuid(session, job.job_id)
        assert failed_job.status == "failed"
        assert failed_job.error["error_code"] == "DETECTION_FAILED"


def test_run_detection_on_a_vanished_upload(test_engine):
    from uuid import uuid4

    with Session(test_engine) as session:
        job = _seed_job(session)
        result = detection.run_detection(session, uuid4(), job.job_id)
        assert result["status"] == "failed"
        assert get_job_by_uuid(session, job.job_id).error["error_code"] == "UPLOAD_NOT_FOUND"


def test_run_detection_without_a_job(test_engine, widget_pdf):
    with Session(test_engine) as session:
        upload = _seed_upload(session, widget_pdf)
        assert detection.run_detection(session, upload.upload_id)["status"] == "completed"
