import sys
from unittest.mock import MagicMock

# Mock all heavy dependencies BEFORE any app imports
mock_controller_class = MagicMock()
mock_controller_class.return_value.create_template.return_value = "/tmp/test_template.pdf"
mock_controller_class.return_value.fill_form.return_value = "/tmp/test_filled.pdf"

mock_src_controller = MagicMock()
mock_src_controller.Controller = mock_controller_class

sys.modules["commonforms"] = MagicMock()
sys.modules["src.controller"] = mock_src_controller
sys.modules["src.file_manipulator"] = MagicMock()
sys.modules["src.filler"] = MagicMock()
sys.modules["src.llm"] = MagicMock()

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy.pool import StaticPool
import pytest

from api.main import app
from api.deps import get_db

TEST_DATABASE_URL = "sqlite://"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def override_get_db():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def create_test_db():
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def client():
    return TestClient(app)
