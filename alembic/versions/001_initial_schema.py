"""Initial schema — Template, FormSubmission, and Job tables.

Revision ID: 001
Revises:
Create Date: 2026-06-22

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "template",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString, nullable=False),
        sa.Column("fields", sa.JSON, nullable=False),
        sa.Column("pdf_path", sqlmodel.sql.sqltypes.AutoString, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "formsubmission",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.Integer, sa.ForeignKey("template.id"), nullable=False),
        sa.Column("input_text", sqlmodel.sql.sqltypes.AutoString, nullable=False),
        sa.Column("output_pdf_path", sqlmodel.sql.sqltypes.AutoString, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "job",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", sqlmodel.sql.sqltypes.AutoString, nullable=False),
        sa.Column("celery_task_id", sqlmodel.sql.sqltypes.AutoString, nullable=False),
        sa.Column("job_type", sqlmodel.sql.sqltypes.AutoString, nullable=False),
        sa.Column("template_id", sa.Integer, sa.ForeignKey("template.id"), nullable=True),
        sa.Column("input_text", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString, nullable=False),
        sa.Column("progress_percent", sa.Integer, nullable=False),
        sa.Column("result_url", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("error", sa.JSON, nullable=True),
        sa.Column("model", sqlmodel.sql.sqltypes.AutoString, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_job_job_id", "job", ["job_id"], unique=True)
    op.create_index("ix_job_celery_task_id", "job", ["celery_task_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_job_celery_task_id", table_name="job")
    op.drop_index("ix_job_job_id", table_name="job")
    op.drop_table("job")
    op.drop_table("formsubmission")
    op.drop_table("template")
