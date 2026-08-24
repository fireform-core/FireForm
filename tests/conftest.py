"""Shared fixtures for FireForm API tests.

Uses an in-memory SQLite database and mocks the heavy dependencies
(Controller → LLM / commonforms) so tests run fast without Docker or Ollama.
"""

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.deps import get_db
from app.models import (  # noqa: F401 — importing these registers their tables
    Extraction,
    Form,
    FormSubmission,
    FormTemplate,
    Incident,
    Input,
    Job,
    Report,
    Template,
    TemplateUpload,
)

# ---------------------------------------------------------------------------
# In-memory database
# ---------------------------------------------------------------------------
_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def _override_get_db():
    with Session(_engine) as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def _reset_tables():
    """Create tables before each test and drop them after — full isolation."""
    SQLModel.metadata.create_all(_engine)
    yield
    SQLModel.metadata.drop_all(_engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    """Yield a raw Session for direct DB assertions."""
    with Session(_engine) as session:
        yield session


@pytest.fixture
def test_engine():
    """Expose the shared in-memory engine for tests that need to open extra sessions."""
    return _engine


# ---------------------------------------------------------------------------
# Minimal PDF bytes (valid 1-page blank PDF)
# ---------------------------------------------------------------------------
_MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000058 00000 n \n0000000115 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF\n"
)


@pytest.fixture
def pdf_bytes():
    """Raw bytes of a minimal valid PDF."""
    return _MINIMAL_PDF


# ---------------------------------------------------------------------------
# Controller mock — patches the heavy dependencies at the route level
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_controller():
    """Patch the forms Controller so fill_form doesn't touch the FS or LLM."""
    with patch("app.api.routes.forms.Controller") as form_cls:
        form_instance = MagicMock()
        form_instance.fill_form.return_value = "src/outputs/filled_output.pdf"
        form_cls.return_value = form_instance

        yield {"form_ctrl": form_instance}


@pytest.fixture
def seed_template():
    """Insert a legacy Template row directly (the /templates/create endpoint was
    removed in the contract migration). Returns a factory -> template id."""
    def _make(name: str = "T", pdf_path: str = "src/inputs/t.pdf", fields: dict | None = None) -> int:
        with Session(_engine) as session:
            tpl = Template(name=name, pdf_path=pdf_path, fields=fields if fields is not None else {"name": "string"})
            session.add(tpl)
            session.commit()
            session.refresh(tpl)
            return tpl.id

    return _make
