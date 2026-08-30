"""Tests for Alembic migration infrastructure.

Runs migrations against an in-memory SQLite database to verify:
- upgrade to head works
- downgrade to base works
- round-trip (up → down → up) works
- schema matches expected columns and foreign keys
"""

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

ALEMBIC_INI = "alembic.ini"


@pytest.fixture()
def alembic_engine():
    return create_engine("sqlite://")


@pytest.fixture()
def alembic_cfg(alembic_engine):
    cfg = Config(ALEMBIC_INI)
    cfg.set_main_option("sqlalchemy.url", "sqlite://")
    cfg.attributes["connection"] = alembic_engine.connect()
    return cfg


def test_upgrade_head(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    tables = inspector.get_table_names()
    assert "template" in tables
    assert "formsubmission" in tables
    assert "job" in tables
    assert "inputs" in tables
    assert "extractions" in tables
    assert "incidents" in tables
    assert "forms" in tables
    assert "reports" in tables
    assert "form_templates" in tables
    assert "alembic_version" in tables


def test_downgrade_base(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "base")

    inspector = inspect(alembic_engine)
    tables = inspector.get_table_names()
    assert "template" not in tables
    assert "formsubmission" not in tables
    assert "job" not in tables


def test_round_trip(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "-1")
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    tables = inspector.get_table_names()
    assert "template" in tables
    assert "formsubmission" in tables


def test_template_columns(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    columns = {c["name"] for c in inspector.get_columns("template")}
    assert columns == {"id", "name", "fields", "pdf_path", "created_at"}


def test_formsubmission_columns(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    columns = {c["name"] for c in inspector.get_columns("formsubmission")}
    assert columns == {"id", "template_id", "input_text", "output_pdf_path", "created_at"}


def test_formsubmission_fk(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    fks = inspector.get_foreign_keys("formsubmission")
    assert len(fks) == 1
    assert fks[0]["referred_table"] == "template"
    assert fks[0]["referred_columns"] == ["id"]


def test_job_columns(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    columns = {c["name"] for c in inspector.get_columns("job")}
    assert columns == {
        "id",
        "job_id",
        "celery_task_id",
        "job_type",
        "template_id",
        "input_text",
        "status",
        "progress_percent",
        "result_url",
        "error",
        "model",
        "created_at",
        "updated_at",
    }


def test_job_indexes(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    indexes = {ix["name"]: ix for ix in inspector.get_indexes("job")}
    assert indexes["ix_job_job_id"]["unique"]
    assert not indexes["ix_job_celery_task_id"]["unique"]


def test_job_fk(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    fks = inspector.get_foreign_keys("job")
    assert len(fks) == 1
    assert fks[0]["referred_table"] == "template"
    assert fks[0]["referred_columns"] == ["id"]


# ---------------------------------------------------------------------------
# 002 — v1 model tables
# ---------------------------------------------------------------------------

def test_inputs_columns(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    columns = {c["name"] for c in inspector.get_columns("inputs")}
    assert columns == {
        "input_id",
        "input_type",
        "status",
        "transcript",
        "original_filename",
        "audio_duration_seconds",
        "character_count",
        "word_count",
        "station_id",
        "responder_badge",
        "incident_date_hint",
        "error_detail",
        "created_at",
        "updated_at",
    }


def test_extractions_columns(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    columns = {c["name"] for c in inspector.get_columns("extractions")}
    assert columns == {
        "extract_id",
        "input_id",
        "status",
        "started_at",
        "completed_at",
        "model_used",
        "processing_time_seconds",
        "partial_result",
        "corrections",
        "error_type",
        "error_detail",
        "created_at",
        "updated_at",
    }


def test_extractions_fk(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    fks = inspector.get_foreign_keys("extractions")
    assert len(fks) == 1
    assert fks[0]["referred_table"] == "inputs"
    assert fks[0]["referred_columns"] == ["input_id"]


def test_incidents_columns(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    columns = {c["name"] for c in inspector.get_columns("incidents")}
    assert columns == {
        "incident_id",
        "extract_id",
        "incident_number",
        "status",
        "incident_name",
        "incident_type",
        "tags",
        "notes",
        "incident_contract",
        "incident_category",
        "incident_datetime",
        "city",
        "state",
        "country",
        "civilian_injuries",
        "civilian_fatalities",
        "responder_injuries",
        "responder_fatalities",
        "people_rescued",
        "people_evacuated",
        "structures_destroyed",
        "area_burned_ha",
        "total_loss_amount",
        "total_loss_currency",
        "call_to_arrival_seconds",
        "turnout_seconds_first_unit",
        "travel_seconds_first_unit",
        "on_scene_duration_seconds",
        "created_at",
        "updated_at",
        "deleted_at",
    }


def test_incidents_fk(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    fks = inspector.get_foreign_keys("incidents")
    assert len(fks) == 1
    assert fks[0]["referred_table"] == "extractions"
    assert fks[0]["referred_columns"] == ["extract_id"]


def test_forms_columns(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    columns = {c["name"] for c in inspector.get_columns("forms")}
    assert columns == {
        "form_id",
        "form_type",
        "status",
        "template_id",
        "incident_id",
        "batch_id",
        "job_id",
        "completed_at",
        "pdf_ready",
        "json_ready",
        "field_mapping_summary",
        "pdf_path",
        "json_data",
        "created_at",
        "updated_at",
    }


def test_forms_fk(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    fks = {fk["referred_table"]: fk for fk in inspector.get_foreign_keys("forms")}
    # template_id → form_templates and incident_id → incidents; job_id and
    # batch_id have NO FK constraint (batch_id is a grouping key, no Batch table)
    assert "form_templates" in fks
    assert fks["form_templates"]["referred_columns"] == ["template_id"]
    assert "incidents" in fks
    assert fks["incidents"]["referred_columns"] == ["incident_id"]
    assert len(fks) == 2


def test_reports_columns(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    columns = {c["name"] for c in inspector.get_columns("reports")}
    assert columns == {
        "report_id",
        "period_type",
        "period_label",
        "year",
        "month",
        "quarter",
        "output_format",
        "status",
        "generated_at",
        "summary",
        "job_id",
        "pdf_path",
        "json_data",
        "created_at",
        "updated_at",
    }


def test_reports_no_fk(alembic_cfg, alembic_engine):
    """job_id on reports is a plain UUID column — no FK constraint until contract Job is resolved."""
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    fks = inspector.get_foreign_keys("reports")
    assert len(fks) == 0


def test_downgrade_002(alembic_cfg, alembic_engine):
    """Downgrade to 001 removes the 002, 003 and 004 tables, leaving 001 intact."""
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "001")

    inspector = inspect(alembic_engine)
    tables = inspector.get_table_names()
    assert "inputs" not in tables
    assert "extractions" not in tables
    assert "incidents" not in tables
    assert "forms" not in tables
    assert "reports" not in tables
    assert "form_templates" not in tables
    assert "template_uploads" not in tables
    assert "template" in tables
    assert "formsubmission" in tables
    assert "job" in tables


# ---------------------------------------------------------------------------
# 004 — form_templates registry and template_uploads drafts
# ---------------------------------------------------------------------------

def test_form_templates_columns(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    columns = {c["name"] for c in inspector.get_columns("form_templates")}
    assert columns == {
        "template_id",
        "form_type",
        "display_name",
        "jurisdiction",
        "agency_type",
        "fields",
        "source_standard",
        "pdf_template_ref",
        "version",
        "status",
        "created_at",
        "updated_at",
    }


def test_form_templates_unique_form_type(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    indexes = {ix["name"]: ix for ix in inspector.get_indexes("form_templates")}
    assert indexes["ix_form_templates_form_type"]["unique"]


def test_form_templates_no_fk(alembic_cfg, alembic_engine):
    """form_templates is a standalone registry — no FK to legacy template/incidents."""
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    assert inspector.get_foreign_keys("form_templates") == []


def test_template_uploads_columns(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    columns = {c["name"] for c in inspector.get_columns("template_uploads")}
    assert columns == {
        "upload_id",
        "status",
        "pdf_path",
        "pdf_template_ref",
        "original_filename",
        "page_count",
        "pages",
        "detected_fields",
        "detection_error",
        "job_id",
        "created_at",
        "updated_at",
    }


def test_template_uploads_no_fk(alembic_cfg, alembic_engine):
    """Uploads are drafts, not templates, so nothing points at them yet."""
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    assert inspector.get_foreign_keys("template_uploads") == []


def test_downgrade_004(alembic_cfg, alembic_engine):
    """Downgrade to 003 removes both 004 tables, leaving 003 intact.

    Targets the "003" revision explicitly rather than "-1": 005 now sits on
    top of head, so a relative one-step downgrade only undoes 005, not 004.
    """
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "003")

    inspector = inspect(alembic_engine)
    tables = inspector.get_table_names()
    assert "form_templates" not in tables
    assert "template_uploads" not in tables
    assert "inputs" in tables
    assert "forms" in tables
    assert "reports" in tables


# ---------------------------------------------------------------------------
# 005 — forms: template_id/incident_id/batch_id, drop extract_id
# ---------------------------------------------------------------------------

def test_forms_template_id_not_nullable(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    columns = {c["name"]: c for c in inspector.get_columns("forms")}
    assert not columns["template_id"]["nullable"]


def test_forms_incident_id_not_nullable(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    columns = {c["name"]: c for c in inspector.get_columns("forms")}
    assert not columns["incident_id"]["nullable"]


def test_forms_batch_id_nullable_no_fk(alembic_cfg, alembic_engine):
    """batch_id is a plain grouping key — nullable, no FK (no Batch table)."""
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    columns = {c["name"]: c for c in inspector.get_columns("forms")}
    assert columns["batch_id"]["nullable"]
    referred_tables = {fk["referred_table"] for fk in inspector.get_foreign_keys("forms")}
    assert "batches" not in referred_tables


def test_forms_extract_id_removed(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    columns = {c["name"] for c in inspector.get_columns("forms")}
    assert "extract_id" not in columns


def test_downgrade_005(alembic_cfg, alembic_engine):
    """Downgrade to 004 restores 004's forms shape.

    Targets "004" explicitly rather than "-1": 006 now sits on top of head, so
    a relative one-step downgrade only undoes 006, not 005.
    """
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "004")

    inspector = inspect(alembic_engine)
    columns = {c["name"]: c for c in inspector.get_columns("forms")}
    assert "extract_id" in columns
    assert "template_id" not in columns
    assert "batch_id" not in columns
    assert columns["incident_id"]["nullable"]

    fks = {fk["referred_table"] for fk in inspector.get_foreign_keys("forms")}
    assert "extractions" in fks
    assert "form_templates" not in fks

    # form_templates itself is untouched — only introduced by 004, not by 005
    assert "form_templates" in inspector.get_table_names()


def test_round_trip_005(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "004")
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    columns = {c["name"] for c in inspector.get_columns("forms")}
    assert "template_id" in columns
    assert "batch_id" in columns
    assert "extract_id" not in columns


def test_incidents_indexes(alembic_cfg, alembic_engine):
    """006 adds the two indexes GET /incidents and the number check rely on."""
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    indexes = {ix["name"]: ix for ix in inspector.get_indexes("incidents")}

    assert indexes["ix_incidents_live_datetime"]["column_names"] == [
        "deleted_at",
        "incident_datetime",
    ]
    assert indexes["ix_incidents_number_live"]["unique"]


def test_downgrade_006(alembic_cfg, alembic_engine):
    """Downgrade to 005 drops the indexes and puts incident_date back."""
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "005")

    inspector = inspect(alembic_engine)
    assert "incident_date" in {c["name"] for c in inspector.get_columns("incidents")}
    assert "ix_incidents_live_datetime" not in {
        ix["name"] for ix in inspector.get_indexes("incidents")
    }


def test_round_trip_006(alembic_cfg, alembic_engine):
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "005")
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(alembic_engine)
    assert "incident_date" not in {c["name"] for c in inspector.get_columns("incidents")}
    assert "ix_incidents_number_live" in {
        ix["name"] for ix in inspector.get_indexes("incidents")
    }
