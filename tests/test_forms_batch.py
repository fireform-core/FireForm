from pathlib import Path
from types import SimpleNamespace

import api.routes.forms as forms_route


def test_fill_batch_endpoint(client, monkeypatch):
    templates = [
        SimpleNamespace(id=1, name="Fire Form", pdf_path="fire.pdf", fields={"incident_id": "text"}),
        SimpleNamespace(id=2, name="Medical Form", pdf_path="medical.pdf", fields={"incident_id": "text"}),
    ]

    def fake_get_templates_by_ids(db, template_ids):
        return templates

    def fake_fill_multiple_forms(self, incident_record, templates):
        return {
            "batch_id": "batch_abc123",
            "total_templates": 2,
            "successful_count": 1,
            "failed_count": 1,
            "package_zip_path": "src/outputs/batches/batch_abc123.zip",
            "results": [
                {
                    "template_id": 1,
                    "template_name": "Fire Form",
                    "status": "success",
                    "output_pdf_path": "fire_filled.pdf",
                    "error": None,
                    "mapping_report": {
                        "compatible": True,
                        "missing_fields": [],
                        "extra_fields": [],
                        "unmapped_fields": [],
                        "type_mismatches": {},
                        "dependency_violations": [],
                        "warnings": [],
                        "matched_fields": ["incident_id"],
                    },
                },
                {
                    "template_id": 2,
                    "template_name": "Medical Form",
                    "status": "failed_runtime",
                    "output_pdf_path": None,
                    "error": "failed",
                    "mapping_report": {
                        "compatible": True,
                        "missing_fields": [],
                        "extra_fields": [],
                        "unmapped_fields": [],
                        "type_mismatches": {},
                        "dependency_violations": [],
                        "warnings": [],
                        "matched_fields": ["incident_id"],
                    },
                },
            ],
        }

    monkeypatch.setattr(forms_route, "get_templates_by_ids", fake_get_templates_by_ids)
    monkeypatch.setattr(forms_route.Controller, "fill_multiple_forms", fake_fill_multiple_forms)

    payload = {
        "template_ids": [1, 2],
        "incident_record": {"incident_id": "INC-42"},
    }
    response = client.post("/forms/fill-batch", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["batch_id"] == "batch_abc123"
    assert body["total_templates"] == 2
    assert body["successful_count"] == 1
    assert body["failed_count"] == 1
    assert body["download_url"] == "/forms/batch-download/batch_abc123"


def test_batch_download_endpoint(client):
    batch_id = "batch_test_download"
    zip_path = Path("src/outputs/batches")
    zip_path.mkdir(parents=True, exist_ok=True)

    target_file = zip_path / f"{batch_id}.zip"
    target_file.write_bytes(b"zip-content")

    response = client.get(f"/forms/batch-download/{batch_id}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"


def test_fill_batch_endpoint_missing_template(client, monkeypatch):
    templates = [
        SimpleNamespace(id=1, name="Fire Form", pdf_path="fire.pdf", fields={"incident_id": "text"}),
    ]

    def fake_get_templates_by_ids(db, template_ids):
        return templates

    monkeypatch.setattr(forms_route, "get_templates_by_ids", fake_get_templates_by_ids)

    payload = {
        "template_ids": [1, 2],
        "incident_record": {"incident_id": "INC-404"},
    }
    response = client.post("/forms/fill-batch", json=payload)

    assert response.status_code == 404


def test_fill_batch_endpoint_includes_field_evidence(client, monkeypatch):
    templates = [
        SimpleNamespace(id=1, name="Trace Form", pdf_path="trace.pdf", fields={"incident_id": "text"}),
    ]

    def fake_get_templates_by_ids(db, template_ids):
        return templates

    def fake_fill_multiple_forms(self, incident_record, templates):
        return {
            "batch_id": "batch_trace_001",
            "total_templates": 1,
            "successful_count": 1,
            "failed_count": 0,
            "package_zip_path": "src/outputs/batches/batch_trace_001.zip",
            "results": [
                {
                    "template_id": 1,
                    "template_name": "Trace Form",
                    "status": "success",
                    "output_pdf_path": "trace_filled.pdf",
                    "error": None,
                    "mapping_report": {
                        "compatible": True,
                        "missing_fields": [],
                        "extra_fields": [],
                        "unmapped_fields": [],
                        "type_mismatches": {},
                        "dependency_violations": [],
                        "warnings": [],
                        "matched_fields": ["incident_id"],
                        "field_evidence": {
                            "incident_id": {
                                "field_name": "incident_id",
                                "matched": True,
                                "source_id": "incident_record",
                                "method": "direct",
                                "confidence": 1.0,
                                "evidence_count": 1,
                            }
                        },
                    },
                }
            ],
        }

    monkeypatch.setattr(forms_route, "get_templates_by_ids", fake_get_templates_by_ids)
    monkeypatch.setattr(forms_route.Controller, "fill_multiple_forms", fake_fill_multiple_forms)

    payload = {
        "template_ids": [1],
        "incident_record": {"incident_id": "INC-TRACE-1"},
    }
    response = client.post("/forms/fill-batch", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert "field_evidence" in body["results"][0]["mapping_report"]
    assert body["results"][0]["mapping_report"]["field_evidence"]["incident_id"]["method"] == "direct"
