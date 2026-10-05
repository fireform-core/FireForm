"""Shared fixtures for FireForm API tests.

Uses an in-memory SQLite database and mocks the heavy dependencies
(Controller → LLM / commonforms) so tests run fast without Docker or Ollama.
"""

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.deps import get_db
from app.main import app
from app.models import (  # noqa: F401 — registers tables
    Extraction,
    Form,
    FormSubmission,
    Incident,
    Input,
    Job,
    Report,
    Template,
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


@pytest.fixture
def pdf_upload(pdf_bytes):
    """A tuple suitable for httpx/TestClient file upload."""
    return ("file", ("test_form.pdf", io.BytesIO(pdf_bytes), "application/pdf"))


# ---------------------------------------------------------------------------
# Pipeline mock — patches the heavy dependencies (LLM + filesystem) directly
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_controller():
    """Patch filler.fill and extract_pdf_template so tests don't touch the FS or LLM."""
    with patch("app.services.form.filler.fill") as mock_fill, \
         patch("app.services.template.extract_pdf_template") as mock_extract:

        # filler.fill writes the output PDF; we return a fake relative path
        mock_fill.return_value = None  # fill() writes to disk; path is computed in service

        # extract_pdf_template returns (schema, tables, groups)
        mock_extract.return_value = (
            {"properties": {"field1": {"type": "string", "description": "Field 1"}}},
            [],
            {},
        )

        yield {
            "mock_fill": mock_fill,
            "mock_extract": mock_extract,
        }
