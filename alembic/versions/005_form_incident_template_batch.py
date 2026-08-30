"""forms: key by template, require incident, group by batch, drop extract_id

Revision ID: 005
Revises: 004
Create Date: 2026-08-17

Form generation (contract Layer 3, #552) keys a form by which template filled
it and reaches the extraction through the incident rather than a direct link
(incidents already FK the extraction, so extract_id was a redundant hop).
Batching is a grouping key only — batch_id has no Batch table, batch status is
derived on the fly from the Form rows that share an id.

No route or repository writes a v1 Form row yet (form generation itself is
still unimplemented), so the forms table is empty in every environment and
the NOT NULL adds below are safe — there is no existing data to backfill.

FK constraints are named explicitly, matching Postgres' own default
`<table>_<column>_fkey` pattern, so downgrade can drop them by name. The same
naming_convention is handed to batch_alter_table so SQLite's reflect-and-
recreate path (needed for the incident_id nullable flip and the extract_id
drop, neither of which SQLite can ALTER in place) assigns identical names.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NAMING_CONVENTION = {"fk": "%(table_name)s_%(column_0_name)s_fkey"}


def upgrade() -> None:
    with op.batch_alter_table('forms', naming_convention=NAMING_CONVENTION) as batch_op:
        batch_op.add_column(sa.Column('template_id', sa.Uuid(), nullable=False))
        batch_op.create_foreign_key(
            'forms_template_id_fkey', 'form_templates', ['template_id'], ['template_id']
        )
        batch_op.add_column(sa.Column('batch_id', sa.Uuid(), nullable=True))
        batch_op.drop_constraint('forms_extract_id_fkey', type_='foreignkey')
        batch_op.drop_column('extract_id')
        batch_op.alter_column('incident_id', existing_type=sa.Uuid(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('forms', naming_convention=NAMING_CONVENTION) as batch_op:
        batch_op.alter_column('incident_id', existing_type=sa.Uuid(), nullable=True)
        batch_op.add_column(sa.Column('extract_id', sa.Uuid(), nullable=False))
        batch_op.create_foreign_key(
            'forms_extract_id_fkey', 'extractions', ['extract_id'], ['extract_id']
        )
        batch_op.drop_constraint('forms_template_id_fkey', type_='foreignkey')
        batch_op.drop_column('template_id')
        batch_op.drop_column('batch_id')
