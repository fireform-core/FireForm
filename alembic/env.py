from logging.config import fileConfig

import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from alembic import context
from app.core.config import DATABASE_URL
from app.models import (  # noqa: F401
    Extraction,
    Form,
    FormSubmission,
    Incident,
    Input,
    Job,
    Report,
    Template,
)

config = context.config

if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
    """Custom type comparison to handle SQLModel / PostgreSQL differences.

    SQLModel uses UTCDateTime (a TypeDecorator wrapping DateTime) for datetime fields,
    while PostgreSQL reflects them as TIMESTAMP (or TIMESTAMP WITHOUT TIME ZONE).
    Treat these as equivalent so Alembic autogenerate does not detect false-positive
    type modification operations.
    """
    meta_is_dt = (
        isinstance(metadata_type, (sa.DateTime, sa.TIMESTAMP))
        or isinstance(getattr(metadata_type, "impl", None), (sa.DateTime, sa.TIMESTAMP))
        or type(metadata_type).__name__ in ("UTCDateTime", "DateTime", "TIMESTAMP")
    )
    insp_is_dt = (
        isinstance(inspected_type, (sa.DateTime, sa.TIMESTAMP))
        or isinstance(getattr(inspected_type, "impl", None), (sa.DateTime, sa.TIMESTAMP))
        or type(inspected_type).__name__ in ("UTCDateTime", "DateTime", "TIMESTAMP")
    )
    if meta_is_dt and insp_is_dt:
        return False

    return None


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=compare_type,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = config.attributes.get("connection", None)

    if connectable is None:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=compare_type,
            )
            with context.begin_transaction():
                context.run_migrations()
    else:
        context.configure(
            connection=connectable,
            target_metadata=target_metadata,
            compare_type=compare_type,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
