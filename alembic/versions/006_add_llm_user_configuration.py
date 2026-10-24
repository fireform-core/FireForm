"""add local LLM provider configuration

Revision ID: 006
Revises: 005
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_provider_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("api_key_encrypted", sa.String(), nullable=True),
        sa.Column("key_hint", sa.String(), nullable=True),
        sa.Column("base_url", sa.String(), nullable=True),
        sa.Column("structured_output", sa.Boolean(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", name="uq_llm_provider_credential_provider"),
    )
    op.create_table(
        "llm_manual_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "model", name="uq_llm_manual_model_provider_model"),
    )
    op.create_table(
        "llm_runtime_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("allow_external", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("llm_runtime_config")
    op.drop_table("llm_manual_models")
    op.drop_table("llm_provider_credentials")
