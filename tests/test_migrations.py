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
        "incident_contract",
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
        "incident_date",
        "tags",
        "notes",
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
        "extract_id",
        "incident_id",
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
    # extract_id → extractions and incident_id → incidents; job_id has NO FK constraint
    assert "extractions" in fks
    assert fks["extractions"]["referred_columns"] == ["extract_id"]
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
    """Downgrade by one step removes only the 002 tables, leaving 001 tables intact."""
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "-1")

    inspector = inspect(alembic_engine)
    tables = inspector.get_table_names()
    assert "inputs" not in tables
    assert "extractions" not in tables
    assert "incidents" not in tables
    assert "forms" not in tables
    assert "reports" not in tables
    assert "template" in tables
    assert "formsubmission" in tables
    assert "job" in tables
