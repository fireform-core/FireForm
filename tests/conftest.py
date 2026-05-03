"""Shared fixtures for FireForm API tests.

Uses an in-memory SQLite database and mocks the heavy dependencies
(Controller → LLM / commonforms) so tests run fast without Docker or Ollama.
"""

import io
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from api.main import app
from api.deps import get_db
from api.db.models import Template, FormSubmission  # noqa: F401 — registers tables

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


@pytest.fixture
def pdf_upload(pdf_bytes):
    """A tuple suitable for httpx/TestClient file upload."""
    return ("file", ("test_form.pdf", io.BytesIO(pdf_bytes), "application/pdf"))


# ---------------------------------------------------------------------------
# Controller mock — patches the heavy dependencies at the route level
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_controller():
    """Patch Controller so create_template / fill_form don't touch the FS or LLM."""
    with patch("api.routes.templates.Controller") as tpl_cls, \
         patch("api.routes.forms.Controller") as form_cls:
        tpl_instance = MagicMock()
        tpl_instance.create_template.return_value = "src/inputs/test_template.pdf"
        tpl_cls.return_value = tpl_instance

        form_instance = MagicMock()
        form_instance.fill_form.return_value = "src/outputs/filled_output.pdf"
        form_cls.return_value = form_instance

        yield {
            "template_ctrl": tpl_instance,
            "form_ctrl": form_instance,
        }
