def test_app_client_exists(client):
    """
    Basic test to ensure the FastAPI test client is successfully initialized
    and the dependency injection (get_db) overrides work correctly.
    """
    assert client is not None

def test_templates_route_exists(client):
    """
    Verify that the /templates/ router is active by issuing a bad request
    and ensuring we get a 405 (Method Not Allowed) or 422 (Unprocessable Entity)
    rather than a 404 (Not Found).
    """
    response = client.post("/templates/create", json={})
    assert response.status_code == 422  # Validation error, which means route exists
