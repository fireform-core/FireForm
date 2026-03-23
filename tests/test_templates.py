def test_create_template_schema(client):
    """
    Test that sending an empty or invalid payload to the template 
    creation route raises a validation error (422), confirming the
    route is correctly registered.
    """
    response = client.post("/templates/create", json={"name": "test"})
    # Since required fields like pdf_path and fields are missing, it should fail validation
    assert response.status_code == 422
