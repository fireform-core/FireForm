def test_submit_form(client):
    pass
    # First create a template
    # form_payload = {
    #     "template_id": 3,
    #     "input_text": "Hi. The employee's name is John Doe. His job title is managing director. His department supervisor is Jane Doe. His phone number is 123456. His email is jdoe@ucsc.edu. The signature is <Mamañema>, and the date is 01/02/2005",
    # }

    # template_res = client.post("/templates/", json=template_payload)
    # template_id = template_res.json()["id"]

    # # Submit a form
    # form_payload = {
    #     "template_id": template_id,
    #     "data": {"rating": 5, "comment": "Great service"},
    # }

    # response = client.post("/forms/", json=form_payload)

    # assert response.status_code == 200

    # data = response.json()
    # assert data["id"] is not None
    # assert data["template_id"] == template_id
    # assert data["data"] == form_payload["data"]
