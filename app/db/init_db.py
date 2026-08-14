import datetime
import logging
from pathlib import Path

from alembic.config import Config
from sqlmodel import Session, select

from alembic import command
from app.core.config import DEFAULT_TEMPLATE_DIR
from app.db.database import engine
from app.models import FormSubmission, Template  # noqa: F401

logger = logging.getLogger(__name__)

ALEMBIC_INI = str(Path(__file__).resolve().parents[2] / "alembic.ini")


def _alembic_cfg() -> Config:
    cfg = Config(ALEMBIC_INI)
    return cfg


def run_migrations():
    logger.info("Running Alembic migrations...")
    command.upgrade(_alembic_cfg(), "head")
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
                fields=fields,
                pdf_path=f"{DEFAULT_TEMPLATE_DIR}/file_template_manual.pdf",
                created_at=datetime.datetime.now(),
            )
            session.add(default_template)
            session.commit()
            logger.info("Database seeded successfully.")


def init_db():
    run_migrations()
    seed_db()


if __name__ == "__main__":
    init_db()
