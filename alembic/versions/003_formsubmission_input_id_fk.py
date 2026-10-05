"""formsubmission.input_id FK to inputs.

Revision ID: 003
Revises: 002
Create Date: 2026-08-07

Adds a nullable input_id FK on formsubmission -> inputs.input_id so submissions
can link to the Input they were filled from, instead of only duplicating the
transcript into input_text. input_text is kept for now (read by the
/forms/submissions and analytics endpoints); dropping it is a deferred
follow-up once those readers move to the FK.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # batch_alter_table: SQLite can't ALTER a table to add a FK constraint in
    # place (no ALTER-constraint support), so this goes through its
    # copy-and-move strategy. On Postgres it emits a plain ALTER TABLE.
    with op.batch_alter_table("formsubmission") as batch_op:
        batch_op.add_column(sa.Column("input_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_formsubmission_input_id_inputs",
            "inputs",
            ["input_id"],
            ["input_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("formsubmission") as batch_op:
        batch_op.drop_constraint("fk_formsubmission_input_id_inputs", type_="foreignkey")
        batch_op.drop_column("input_id")
