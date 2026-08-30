"""Tests for the contract Layer 6 template registry (app/api/routes/form_templates.py).

Covers list / create / get / replace / fields against the in-memory DB.
"""

from app.core.config import API_PREFIX

TEMPLATES_URL = f"{API_PREFIX}/templates"


def _layout(**over) -> dict:
    base = {"page": 0, "x": 188.33, "y": 621.33, "width": 127.33, "height": 28.67}
    base.update(over)
    return base


def _payload(form_type: str = "state_texas") -> dict:
    return {
        "form_type": form_type,
        "display_name": "Texas State Fire Marshal Incident Report",
        "jurisdiction": "US-TX",
        "agency_type": "fire_department",
        "fields": [
            {
                "field_name": "incident_number",
                "field_type": "string",
                "source": "schema",
                "required": True,
                "max_length": 20,
                "description": "State-assigned incident number",
                "incident_mapping": "report_metadata.incident_number",
                "layout": _layout(font="Helvetica", font_size=10, color="#000000", align="left"),
            },
            {
                "field_name": "fire_cause",
                "field_type": "enum",
                "source": "schema",
                "required": False,
                "allowed_values": ["accidental", "natural", "intentional", "undetermined"],
                "incident_mapping": "fire.cause_category",
                "layout": _layout(y=560.0),
            },
        ],
        "source_standard": "Texas SFM 2026",
    }


def _create(client, **overrides):
    body = _payload(**overrides)
    return client.post(TEMPLATES_URL, json=body)


def test_list_empty(client):
    resp = client.get(TEMPLATES_URL)
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_returns_201_with_server_fields(client):
    resp = _create(client)
    assert resp.status_code == 201
    body = resp.json()

    assert body["form_type"] == "state_texas"
    assert body["display_name"] == "Texas State Fire Marshal Incident Report"
    assert body["field_count"] == 2
    assert body["status"] == "active"
    assert body["version"] == "1.0"
    assert body["template_id"]
    assert body["last_updated"]
    assert body["created_at"]
    assert len(body["fields"]) == 2


def test_create_duplicate_form_type_returns_409(client):
    assert _create(client).status_code == 201
    dup = _create(client)
    assert dup.status_code == 409
    assert dup.json()["error_code"] == "TEMPLATE_EXISTS"


def test_create_then_list(client):
    _create(client)
    resp = client.get(TEMPLATES_URL)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["form_type"] == "state_texas"
    assert items[0]["field_count"] == 2
    # Summary is a projection — no full field list.
    assert "fields" not in items[0]


def test_get_by_id(client):
    template_id = _create(client).json()["template_id"]
    resp = client.get(f"{TEMPLATES_URL}/{template_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["template_id"] == template_id
    first = body["fields"][0]
    assert first["incident_mapping"] == "report_metadata.incident_number"
    assert first["layout"]["x"] == 188.33
    assert first["layout"]["align"] == "left"


def test_get_missing_returns_404(client):
    resp = client.get(f"{TEMPLATES_URL}/550e8400-e29b-41d4-a716-446655440099")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "TEMPLATE_NOT_FOUND"


def test_get_invalid_uuid_returns_422(client):
    assert client.get(f"{TEMPLATES_URL}/not-a-uuid").status_code == 422


def test_replace_updates_fields(client):
    template_id = _create(client).json()["template_id"]

    updated = _payload()
    updated["display_name"] = "Texas SFM Incident Report v2"
    updated["fields"] = [updated["fields"][0]]  # drop one field

    resp = client.put(f"{TEMPLATES_URL}/{template_id}", json=updated)
    assert resp.status_code == 200
    body = resp.json()
    assert body["display_name"] == "Texas SFM Incident Report v2"
    assert body["field_count"] == 1
    assert body["template_id"] == template_id


def test_replace_onto_a_taken_form_type_returns_409(client):
    first = _create(client, form_type="tx_sfm_incident").json()["template_id"]
    _create(client, form_type="tx_sfm_casualty")

    resp = client.put(
        f"{TEMPLATES_URL}/{first}", json=_payload(form_type="tx_sfm_casualty")
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "TEMPLATE_EXISTS"


def test_replace_keeping_its_own_form_type_is_not_a_conflict(client):
    template_id = _create(client).json()["template_id"]
    resp = client.put(f"{TEMPLATES_URL}/{template_id}", json=_payload())
    assert resp.status_code == 200


def test_replace_missing_returns_404(client):
    resp = client.put(
        f"{TEMPLATES_URL}/550e8400-e29b-41d4-a716-446655440099", json=_payload()
    )
    assert resp.status_code == 404


def test_create_missing_required_field_returns_422(client):
    body = _payload()
    del body["fields"]
    assert client.post(TEMPLATES_URL, json=body).status_code == 422


def test_fields_endpoint(client):
    template_id = _create(client).json()["template_id"]
    resp = client.get(f"{TEMPLATES_URL}/{template_id}/fields")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_fields"] == 2
    assert body["required_fields"] == 1
    assert body["optional_fields"] == 1
    assert len(body["fields"]) == 2
    assert body["form_type"] == "state_texas"


def test_fields_required_only(client):
    template_id = _create(client).json()["template_id"]
    resp = client.get(f"{TEMPLATES_URL}/{template_id}/fields?required_only=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_fields"] == 2
    assert body["required_fields"] == 1
    assert len(body["fields"]) == 1
    assert body["fields"][0]["field_name"] == "incident_number"


def test_fields_missing_returns_404(client):
    resp = client.get(
        f"{TEMPLATES_URL}/550e8400-e29b-41d4-a716-446655440099/fields"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Validation (all 422 with the contract error envelope)
# ---------------------------------------------------------------------------
def _assert_422(resp):
    assert resp.status_code == 422, resp.json()
    body = resp.json()
    assert body["error_code"] == "VALIDATION_ERROR"
    assert len(body["validation_errors"]) >= 1


def test_jurisdiction_optional(client):
    body = _payload()
    del body["jurisdiction"]
    resp = client.post(TEMPLATES_URL, json=body)
    assert resp.status_code == 201
    assert resp.json()["jurisdiction"] is None


def test_static_text_field_ok(client):
    body = _payload()
    body["fields"].append({
        "field_name": "footer",
        "field_type": "string",
        "source": "static",
        "required": False,
        "static_text": "Generated by FireForm",
        "layout": _layout(y=40.0, align="center"),
    })
    resp = client.post(TEMPLATES_URL, json=body)
    assert resp.status_code == 201
    assert resp.json()["field_count"] == 3


def test_schema_field_without_mapping_rejected(client):
    body = _payload()
    del body["fields"][0]["incident_mapping"]
    _assert_422(client.post(TEMPLATES_URL, json=body))


def test_static_text_on_a_schema_field_rejected(client):
    body = _payload()
    body["fields"][0]["static_text"] = "x"  # source is schema
    _assert_422(client.post(TEMPLATES_URL, json=body))


def test_static_field_without_text_rejected(client):
    body = _payload()
    body["fields"].append({
        "field_name": "footer",
        "field_type": "string",
        "source": "static",
        "required": False,
        "layout": _layout(y=40.0),
    })
    _assert_422(client.post(TEMPLATES_URL, json=body))


def test_mapping_on_a_manual_field_rejected(client):
    body = _payload()
    body["fields"].append({
        "field_name": "marshal_name",
        "field_type": "string",
        "source": "manual",
        "required": True,
        "incident_mapping": "report_metadata.incident_number",
        "layout": _layout(y=120.0),
    })
    _assert_422(client.post(TEMPLATES_URL, json=body))


def test_manual_field_needs_nothing_else(client):
    body = _payload()
    body["fields"].append({
        "field_name": "marshal_name",
        "field_type": "string",
        "source": "manual",
        "required": True,
        "layout": _layout(y=120.0),
    })
    resp = client.post(TEMPLATES_URL, json=body)
    assert resp.status_code == 201, resp.json()
    assert resp.json()["field_count"] == 3


def test_open_field_without_description_rejected(client):
    body = _payload()
    body["fields"].append({
        "field_name": "insurance_company",
        "field_type": "string",
        "source": "open",
        "required": False,
        "layout": _layout(y=520.0),
    })
    _assert_422(client.post(TEMPLATES_URL, json=body))


def test_open_field_with_description_ok(client):
    body = _payload()
    body["fields"].append({
        "field_name": "insurance_company",
        "field_type": "string",
        "source": "open",
        "required": False,
        "description": "Name of the insurance company covering the property",
        "layout": _layout(y=520.0),
    })
    resp = client.post(TEMPLATES_URL, json=body)
    assert resp.status_code == 201, resp.json()


def test_missing_source_rejected(client):
    body = _payload()
    del body["fields"][0]["source"]
    _assert_422(client.post(TEMPLATES_URL, json=body))


def test_unit_is_kept(client):
    body = _payload()
    body["fields"][0]["unit"] = "acres"
    resp = client.post(TEMPLATES_URL, json=body)
    assert resp.status_code == 201
    assert resp.json()["fields"][0]["unit"] == "acres"


def test_negative_min_value_allowed(client):
    body = _payload()
    body["fields"][0]["min_value"] = -40
    body["fields"][0]["max_value"] = 50
    assert client.post(TEMPLATES_URL, json=body).status_code == 201


def test_enum_without_allowed_values_rejected(client):
    body = _payload()
    del body["fields"][1]["allowed_values"]  # fire_cause is enum
    _assert_422(client.post(TEMPLATES_URL, json=body))


def test_duplicate_field_names_rejected(client):
    body = _payload()
    body["fields"][1]["field_name"] = body["fields"][0]["field_name"]
    _assert_422(client.post(TEMPLATES_URL, json=body))


def test_empty_fields_rejected(client):
    body = _payload()
    body["fields"] = []
    _assert_422(client.post(TEMPLATES_URL, json=body))


def test_bad_form_type_rejected(client):
    _assert_422(_create(client, form_type="State Texas!"))


def test_min_greater_than_max_rejected(client):
    body = _payload()
    body["fields"][0]["min_value"] = 10
    body["fields"][0]["max_value"] = 5
    _assert_422(client.post(TEMPLATES_URL, json=body))


def test_layout_bad_color_rejected(client):
    body = _payload()
    body["fields"][0]["layout"]["color"] = "black"
    _assert_422(client.post(TEMPLATES_URL, json=body))


def test_layout_missing_required_coord_rejected(client):
    body = _payload()
    del body["fields"][0]["layout"]["width"]
    _assert_422(client.post(TEMPLATES_URL, json=body))


def test_layout_negative_coordinate_rejected(client):
    body = _payload()
    body["fields"][0]["layout"]["x"] = -5
    _assert_422(client.post(TEMPLATES_URL, json=body))


def test_layout_zero_width_rejected(client):
    body = _payload()
    body["fields"][0]["layout"]["width"] = 0
    _assert_422(client.post(TEMPLATES_URL, json=body))


def test_replace_validates_body(client):
    template_id = _create(client).json()["template_id"]
    bad = _payload()
    bad["fields"][0]["layout"]["color"] = "nope"
    _assert_422(client.put(f"{TEMPLATES_URL}/{template_id}", json=bad))
