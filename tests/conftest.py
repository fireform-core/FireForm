from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine, Session, delete
from sqlalchemy.pool import StaticPool
import pytest

from api.main import app
from api.deps import get_db
from api.db.models import Template, FormSubmission

# In-memory SQLite database for tests
TEST_DATABASE_URL = "sqlite://"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def override_get_db():
    with Session(engine) as session:
        yield session


# Apply dependency override
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def create_test_db():
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def clean_db():
    """Wipe all tables before each test — prevents data leaking between tests."""
    with Session(engine) as session:
        session.exec(delete(FormSubmission))
        session.exec(delete(Template))
        session.commit()
    yield


@pytest.fixture
def db_session():
    """Provide a DB session for tests that need to insert data directly."""
    with Session(engine) as session:
        yield session


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def tmp_pdf(tmp_path):
    """
    Creates a real minimal PDF file on disk for tests.
    Needed because forms.py validates pdf_path exists before calling Ollama.
    """
    pdf_file = tmp_path / "test_form.pdf"
    pdf_file.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f\n"
        b"0000000009 00000 n\n"
        b"0000000058 00000 n\n"
        b"0000000115 00000 n\n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\n"
        b"startxref\n190\n%%EOF\n"
    )
    return str(pdf_file)