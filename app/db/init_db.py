import datetime
import logging
from pathlib import Path

from alembic.config import Config
from alembic.util import CommandError
from sqlmodel import Session, select, text

from alembic import command
from app.db.database import engine
from app.models import Template

logger = logging.getLogger(__name__)

ALEMBIC_INI = str(Path(__file__).resolve().parents[2] / "alembic.ini")


def _alembic_cfg() -> Config:
    cfg = Config(ALEMBIC_INI)
    return cfg


def run_migrations():
    logger.info("Running Alembic migrations...")
    try:
        command.upgrade(_alembic_cfg(), "head")
    except CommandError as e:
        if "Can't locate revision" not in str(e):
            raise
        # Exit non-zero with a readable message instead of a bare stack trace.
        raise SystemExit(
            f"[init_db] {e}.\n"
            "The database is stamped with a migration revision this code does not know\n"
            "(e.g. a DB created by another branch). Either reset the dev database:\n"
            "    make down && docker volume rm dev_postgres_data\n"
            "or re-stamp it to a revision in alembic/versions/:\n"
            "    alembic stamp <revision>"
        ) from e
    logger.info("Migrations complete.")


def seed_db():
    with Session(engine) as session:
        statement = select(Template)
        try:
            results = session.exec(statement).first()
        except Exception:
            results = None

        if not results:
            logger.info("Seeding database with default template...")
            fields = {
                "Employee's name": "string",
                "Employee's job title": "string",
                "Employee's department supervisor": "string",
                "Employee's phone number": "string",
                "Employee's email": "string",
                "Signature": "string",
                "Date": "string",
            }

            default_template = Template(
                id=2,
                name="Manual Test Template",
                description=(
                    "Employee contact and sign-off form used to manually verify that "
                    "FireForm fills a PDF correctly. Captures who completed the form, "
                    "their contact details, and their signature."
                ),
                fields=fields,
                pdf_path="data/inputs/file_template_manual.pdf",
                created_at=datetime.datetime.now(datetime.timezone.utc),
            )
            session.add(default_template)
            session.commit()
            logger.info("Database seeded successfully.")


def sync_template_id_sequence():
    # The seed row sets its id explicitly, which does not advance Postgres'
    # SERIAL sequence, so the next created template would collide with it.
    # Only ever moves the sequence forward (this runs on every start), so ids
    # of deleted templates are not handed out again.
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        conn.execute(text(
            "SELECT setval(pg_get_serial_sequence('template', 'id'), GREATEST("
            "COALESCE((SELECT MAX(id) FROM template), 0) + 1, "
            "nextval(pg_get_serial_sequence('template', 'id'))), false)"
        ))


def init_db():
    run_migrations()
    seed_db()
    sync_template_id_sequence()


if __name__ == "__main__":
    init_db()
