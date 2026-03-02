from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine, Session
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


@pytest.fixture(autouse=True)
def reset_db():
    """
    Wipe and recreate all tables before every test.

    Previously the DB was created once per session (scope="session"), meaning
    rows written by one test persisted into the next. This caused tests to
    depend on execution order and fail when run in isolation or in a different
    order. Resetting per-test guarantees full isolation.
    """
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def client():
    return TestClient(app)
