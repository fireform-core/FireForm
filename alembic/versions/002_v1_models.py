"""v1 models — Input, Extraction, Incident, Form, Report tables.

Revision ID: 002
Revises: 001
Create Date: 2026-06-26

JSON columns use sa.JSON (Postgres json type, not jsonb) for consistency with
migration 001 and SQLite test-harness compatibility. A follow-up can switch
high-query blobs (especially incident_contract) to jsonb via with_variant() if
containment operators or GIN indexing are needed.

Form.job_id and Report.job_id are plain UUID columns with no FK constraint.
The contract Job model (UUID-PK, enum-typed) is a separate decision; the FK
will be added when that model is resolved.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inputs",
        sa.Column("input_id", sa.Uuid(), primary_key=True),
        sa.Column("input_type", sqlmodel.sql.sqltypes.AutoString, nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString, nullable=False),
        sa.Column("transcript", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("original_filename", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("audio_duration_seconds", sa.Float, nullable=True),
        sa.Column("character_count", sa.Integer, nullable=True),
        sa.Column("word_count", sa.Integer, nullable=True),
        sa.Column("station_id", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("responder_badge", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("incident_date_hint", sa.Date, nullable=True),
        sa.Column("error_detail", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "extractions",
        sa.Column("extract_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "input_id",
            sa.Uuid(),
            sa.ForeignKey("inputs.input_id"),
            nullable=False,
        ),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("model_used", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("processing_time_seconds", sa.Float, nullable=True),
        sa.Column("incident_contract", sa.JSON, nullable=True),
        sa.Column("corrections", sa.JSON, nullable=True),
        sa.Column("error_type", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("error_detail", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "incidents",
        sa.Column("incident_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "extract_id",
            sa.Uuid(),
            sa.ForeignKey("extractions.extract_id"),
            nullable=False,
        ),
        sa.Column("incident_number", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString, nullable=False),
        sa.Column("incident_name", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("incident_type", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("incident_date", sa.Date, nullable=True),
        sa.Column("tags", sa.JSON, nullable=True),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "forms",
        sa.Column("form_id", sa.Uuid(), primary_key=True),
        sa.Column("form_type", sqlmodel.sql.sqltypes.AutoString, nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString, nullable=False),
        sa.Column(
            "extract_id",
            sa.Uuid(),
            sa.ForeignKey("extractions.extract_id"),
            nullable=False,
        ),
        sa.Column(
            "incident_id",
            sa.Uuid(),
            sa.ForeignKey("incidents.incident_id"),
            nullable=True,
        ),
        sa.Column("job_id", sa.Uuid(), nullable=True),  # no FK — see module docstring
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("pdf_ready", sa.Boolean, nullable=False),
        sa.Column("json_ready", sa.Boolean, nullable=False),
        sa.Column("field_mapping_summary", sa.JSON, nullable=True),
        sa.Column("pdf_path", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("json_data", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "reports",
        sa.Column("report_id", sa.Uuid(), primary_key=True),
        sa.Column("period_type", sqlmodel.sql.sqltypes.AutoString, nullable=False),
        sa.Column("period_label", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer, nullable=True),
        sa.Column("quarter", sa.Integer, nullable=True),
        sa.Column("output_format", sqlmodel.sql.sqltypes.AutoString, nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString, nullable=False),
        sa.Column("generated_at", sa.DateTime, nullable=True),
        sa.Column("summary", sa.JSON, nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),  # no FK — see module docstring
        sa.Column("pdf_path", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("json_data", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("reports")
    op.drop_table("forms")
    op.drop_table("incidents")
    op.drop_table("extractions")
    op.drop_table("inputs")
