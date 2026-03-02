def test_submit_form_requires_valid_template(client):
    """Form submission with non-existent template returns 404."""
    response = client.post(
        "/forms/fill",
        json={"template_id": 999, "input_text": "test data"},
    )
    assert response.status_code == 404
