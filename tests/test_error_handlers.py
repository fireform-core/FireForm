"""Tests for custom exception handlers registration."""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from api.errors.base import AppError
from api.errors.handlers import register_exception_handlers


@pytest.fixture
def app_with_handlers():
    """Create a test app with exception handlers registered."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/test-404")
    def raise_404():
        raise AppError("Resource not found", status_code=404)

    @app.get("/test-400")
    def raise_400():
        raise AppError("Bad request")

    @app.get("/test-500")
    def raise_500():
        raise AppError("Internal error", status_code=500)

    return app


@pytest.fixture
def client_with_handlers(app_with_handlers):
    """Create a test client with exception handlers."""
    return TestClient(app_with_handlers)


def test_app_error_returns_correct_404_status(client_with_handlers):
    """Test that AppError with status_code=404 returns 404, not 500."""
    response = client_with_handlers.get("/test-404")
    assert response.status_code == 404
    assert response.json() == {"error": "Resource not found"}


def test_app_error_returns_correct_400_status(client_with_handlers):
    """Test that AppError with default status_code returns 400."""
    response = client_with_handlers.get("/test-400")
    assert response.status_code == 400
    assert response.json() == {"error": "Bad request"}


def test_app_error_returns_correct_500_status(client_with_handlers):
    """Test that AppError with status_code=500 returns 500."""
    response = client_with_handlers.get("/test-500")
    assert response.status_code == 500
    assert response.json() == {"error": "Internal error"}


def test_exception_handlers_registered_in_main_app():
    """Test that the main app has exception handlers registered."""
    from api.main import app

    # Check that AppError handler is registered
    assert AppError in app.exception_handlers
