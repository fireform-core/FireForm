"""
Tests for POST /forms/fill/batch, GET /forms/batches/{id},
and GET /forms/batches/{id}/audit.

Mocking strategy:
  - IncidentExtractor.async_extract_canonical → returns a minimal canonical dict
  - IncidentExtractor.async_map_to_template   → returns a minimal field-value dict
  - Filler.fill_form_with_data               → returns a deterministic output path
  - IncidentExtractor.build_evidence_report   → returns filtered canonical fields

Templates are created through the real /templates/create endpoint (with
Controller mocked) so test IDs are stable and foreign-key constraints hold.
"""

from unittest.mock import patch, AsyncMock, MagicMock


# ── Shared canonical fixture ───────────────────────────────────────────────────

CANONICAL = {
    "reporting_officer": {
        "value": "Officer Jane Smith",
        "evidence": "Officer Jane Smith reporting.",
        "confidence": "high",
    },
    "incident_location": {
        "value": "123 Main St",
        "evidence": "incident occurred at 123 Main St",
        "confidence": "high",
    },
    "victim_names": {
        "value": ["Alice", "Bob"],
        "evidence": "victims Alice and Bob",
        "confidence": "high",
    },
    "incident_type": {
        "value": None,
        "evidence": None,
        "confidence": "low",
    },
}

EVIDENCE_REPORT = {k: v for k, v in CANONICAL.items() if v["value"] is not None}

MAPPED_FIELDS = {
    "reporting_officer": "Officer Jane Smith",
    "incident_location": "123 Main St",
}

TRANSCRIPT = (
    "Officer Jane Smith reporting. Incident occurred at 123 Main St. "
    "Two victims Alice and Bob sustained minor injuries."
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def create_template(client, name="Agency A", pdf_path="src/inputs/file.pdf"):
    """Create a template and return its id. Mocks Controller to avoid FS access."""
    with patch("api.routes.templates.Controller") as MockCtrl:
        MockCtrl.return_value.create_template.return_value = pdf_path
        payload = {
            "name": name,
            "pdf_path": pdf_path,
            "fields": {"reporting_officer": "string", "incident_location": "string"},
        }
        res = client.post("/templates/create", json=payload)
        assert res.status_code == 200, res.text
        return res.json()["id"]


def _mock_extractor():
    """
    Return a context-manager-compatible patch for IncidentExtractor
    that simulates a successful canonical extraction + mapping.
    """
    mock_instance = MagicMock()
    mock_instance.async_extract_canonical = AsyncMock(return_value=CANONICAL)
    mock_instance.async_map_to_template = AsyncMock(return_value=MAPPED_FIELDS)
    return mock_instance


# ── Batch fill — success paths ─────────────────────────────────────────────────

def test_batch_fill_single_template_complete(client):
    tid = create_template(client, "Agency A")
    mock_inst = _mock_extractor()

    with (
        patch("api.routes.batch.IncidentExtractor", return_value=mock_inst),
        patch("api.routes.batch.IncidentExtractor.build_evidence_report",
              return_value=EVIDENCE_REPORT),
        patch("src.filler.Filler.fill_form_with_data", return_value="src/outputs/out.pdf"),
    ):
        res = client.post("/forms/fill/batch", json={
            "input_text": TRANSCRIPT,
            "template_ids": [tid],
        })

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "complete"
    assert data["total_requested"] == 1
    assert data["total_succeeded"] == 1
    assert data["total_failed"] == 0
    assert len(data["results"]) == 1
    assert data["results"][0]["status"] == "complete"
    assert data["results"][0]["template_id"] == tid
    assert "batch_id" in data
    assert data["batch_id"]


def test_batch_fill_multiple_templates_complete(client):
    tid1 = create_template(client, "Agency B", "src/inputs/b.pdf")
    tid2 = create_template(client, "Agency C", "src/inputs/c.pdf")
    mock_inst = _mock_extractor()

    with (
        patch("api.routes.batch.IncidentExtractor", return_value=mock_inst),
        patch("api.routes.batch.IncidentExtractor.build_evidence_report",
              return_value=EVIDENCE_REPORT),
        patch("src.filler.Filler.fill_form_with_data", return_value="src/outputs/out.pdf"),
    ):
        res = client.post("/forms/fill/batch", json={
            "input_text": TRANSCRIPT,
            "template_ids": [tid1, tid2],
        })

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "complete"
    assert data["total_requested"] == 2
    assert data["total_succeeded"] == 2
    assert data["total_failed"] == 0
    result_ids = {r["template_id"] for r in data["results"]}
    assert result_ids == {tid1, tid2}


def test_batch_fill_returns_evidence_report(client):
    tid = create_template(client, "Agency Evidence")
    mock_inst = _mock_extractor()

    with (
        patch("api.routes.batch.IncidentExtractor", return_value=mock_inst),
        patch("api.routes.batch.IncidentExtractor.build_evidence_report",
              return_value=EVIDENCE_REPORT),
        patch("src.filler.Filler.fill_form_with_data", return_value="src/outputs/out.pdf"),
    ):
        res = client.post("/forms/fill/batch", json={
            "input_text": TRANSCRIPT,
            "template_ids": [tid],
        })

    data = res.json()
    er = data.get("evidence_report")
    assert er is not None
    # reporting_officer has a non-null value → should appear in evidence_report
    assert "reporting_officer" in er
    assert er["reporting_officer"]["value"] == "Officer Jane Smith"
    assert er["reporting_officer"]["evidence"] == "Officer Jane Smith reporting."
    # incident_type has value=None → must NOT appear in evidence_report
    assert "incident_type" not in er


def test_batch_fill_each_result_has_submission_id(client):
    tid = create_template(client, "Agency Sub")
    mock_inst = _mock_extractor()

    with (
        patch("api.routes.batch.IncidentExtractor", return_value=mock_inst),
        patch("api.routes.batch.IncidentExtractor.build_evidence_report",
              return_value=EVIDENCE_REPORT),
        patch("src.filler.Filler.fill_form_with_data", return_value="src/outputs/out.pdf"),
    ):
        res = client.post("/forms/fill/batch", json={
            "input_text": TRANSCRIPT,
            "template_ids": [tid],
        })

    result = res.json()["results"][0]
    assert result["submission_id"] is not None
    assert isinstance(result["submission_id"], int)


# ── Batch fill — validation / error paths ────────────────────────────────────

def test_batch_fill_404_on_unknown_template(client):
    res = client.post("/forms/fill/batch", json={
        "input_text": TRANSCRIPT,
        "template_ids": [999999],
    })
    assert res.status_code == 404


def test_batch_fill_422_empty_template_ids(client):
    res = client.post("/forms/fill/batch", json={
        "input_text": TRANSCRIPT,
        "template_ids": [],
    })
    assert res.status_code == 422


def test_batch_fill_422_duplicate_template_ids(client):
    tid = create_template(client, "Agency Dup")
    res = client.post("/forms/fill/batch", json={
        "input_text": TRANSCRIPT,
        "template_ids": [tid, tid],
    })
    assert res.status_code == 422


def test_batch_fill_422_too_many_template_ids(client):
    # 21 IDs > hard limit of 20
    res = client.post("/forms/fill/batch", json={
        "input_text": TRANSCRIPT,
        "template_ids": list(range(1, 22)),
    })
    assert res.status_code == 422


def test_batch_fill_422_missing_input_text(client):
    tid = create_template(client, "Agency Miss")
    res = client.post("/forms/fill/batch", json={"template_ids": [tid]})
    assert res.status_code == 422


# ── Partial failure ────────────────────────────────────────────────────────────

def test_batch_fill_partial_failure_when_one_pdf_fill_fails(client):
    """When one PDF fill raises, the other succeeds and status is 'partial'."""
    tid1 = create_template(client, "Agency Partial-Good", "src/inputs/good.pdf")
    tid2 = create_template(client, "Agency Partial-Bad", "src/inputs/bad.pdf")
    mock_inst = _mock_extractor()

    call_count = {"n": 0}

    def _fill_side_effect(pdf_path, data):
        call_count["n"] += 1
        if "bad" in pdf_path:
            raise RuntimeError("PDF fill failed")
        return "src/outputs/good_out.pdf"

    with (
        patch("api.routes.batch.IncidentExtractor", return_value=mock_inst),
        patch("api.routes.batch.IncidentExtractor.build_evidence_report",
              return_value=EVIDENCE_REPORT),
        patch("src.filler.Filler.fill_form_with_data", side_effect=_fill_side_effect),
    ):
        res = client.post("/forms/fill/batch", json={
            "input_text": TRANSCRIPT,
            "template_ids": [tid1, tid2],
        })

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "partial"
    assert data["total_succeeded"] == 1
    assert data["total_failed"] == 1

    statuses = {r["template_id"]: r["status"] for r in data["results"]}
    # The bad template should have status "failed"
    assert statuses[tid2] == "failed"
    assert statuses[tid1] == "complete"


def test_batch_fill_all_failed_status(client):
    """When every PDF fill raises, status must be 'failed' (not 'partial')."""
    tid = create_template(client, "Agency AllFail")
    mock_inst = _mock_extractor()

    with (
        patch("api.routes.batch.IncidentExtractor", return_value=mock_inst),
        patch("api.routes.batch.IncidentExtractor.build_evidence_report",
              return_value=EVIDENCE_REPORT),
        patch("src.filler.Filler.fill_form_with_data",
              side_effect=RuntimeError("disk full")),
    ):
        res = client.post("/forms/fill/batch", json={
            "input_text": TRANSCRIPT,
            "template_ids": [tid],
        })

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "failed"
    assert data["total_succeeded"] == 0
    assert data["total_failed"] == 1


# ── GET /forms/batches/{id} ────────────────────────────────────────────────────

def test_get_batch_status_200(client):
    tid = create_template(client, "Agency Status")
    mock_inst = _mock_extractor()

    with (
        patch("api.routes.batch.IncidentExtractor", return_value=mock_inst),
        patch("api.routes.batch.IncidentExtractor.build_evidence_report",
              return_value=EVIDENCE_REPORT),
        patch("src.filler.Filler.fill_form_with_data", return_value="src/outputs/out.pdf"),
    ):
        fill_res = client.post("/forms/fill/batch", json={
            "input_text": TRANSCRIPT,
            "template_ids": [tid],
        })

    batch_id = fill_res.json()["batch_id"]
    status_res = client.get(f"/forms/batches/{batch_id}")
    assert status_res.status_code == 200
    data = status_res.json()
    assert data["id"] == batch_id
    assert data["status"] == "complete"
    assert isinstance(data["template_ids"], list)


def test_get_batch_status_404_unknown(client):
    res = client.get("/forms/batches/nonexistent-batch-id")
    assert res.status_code == 404


def test_get_batch_status_has_output_paths(client):
    tid = create_template(client, "Agency Paths")
    mock_inst = _mock_extractor()

    with (
        patch("api.routes.batch.IncidentExtractor", return_value=mock_inst),
        patch("api.routes.batch.IncidentExtractor.build_evidence_report",
              return_value=EVIDENCE_REPORT),
        patch("src.filler.Filler.fill_form_with_data", return_value="src/outputs/paths_out.pdf"),
    ):
        fill_res = client.post("/forms/fill/batch", json={
            "input_text": TRANSCRIPT,
            "template_ids": [tid],
        })

    batch_id = fill_res.json()["batch_id"]
    data = client.get(f"/forms/batches/{batch_id}").json()
    assert data["output_paths"] is not None
    assert str(tid) in data["output_paths"]


# ── GET /forms/batches/{id}/audit ─────────────────────────────────────────────

def test_get_batch_audit_200(client):
    tid = create_template(client, "Agency Audit")
    mock_inst = _mock_extractor()

    with (
        patch("api.routes.batch.IncidentExtractor", return_value=mock_inst),
        patch("api.routes.batch.IncidentExtractor.build_evidence_report",
              return_value=EVIDENCE_REPORT),
        patch("src.filler.Filler.fill_form_with_data", return_value="src/outputs/out.pdf"),
    ):
        fill_res = client.post("/forms/fill/batch", json={
            "input_text": TRANSCRIPT,
            "template_ids": [tid],
        })

    batch_id = fill_res.json()["batch_id"]
    audit_res = client.get(f"/forms/batches/{batch_id}/audit")
    assert audit_res.status_code == 200
    data = audit_res.json()
    assert data["batch_id"] == batch_id
    assert data["input_text"] == TRANSCRIPT
    assert data["canonical_extraction"] is not None
    assert data["evidence_report"] is not None


def test_get_batch_audit_canonical_has_evidence_fields(client):
    """Every key in canonical_extraction must carry value/evidence/confidence."""
    tid = create_template(client, "Agency AuditEvidence")
    mock_inst = _mock_extractor()

    with (
        patch("api.routes.batch.IncidentExtractor", return_value=mock_inst),
        patch("api.routes.batch.IncidentExtractor.build_evidence_report",
              return_value=EVIDENCE_REPORT),
        patch("src.filler.Filler.fill_form_with_data", return_value="src/outputs/out.pdf"),
    ):
        fill_res = client.post("/forms/fill/batch", json={
            "input_text": TRANSCRIPT,
            "template_ids": [tid],
        })

    batch_id = fill_res.json()["batch_id"]
    data = client.get(f"/forms/batches/{batch_id}/audit").json()
    canonical = data["canonical_extraction"]

    for field, content in canonical.items():
        assert "value" in content, f"Missing 'value' in canonical field '{field}'"
        assert "evidence" in content, f"Missing 'evidence' in canonical field '{field}'"
        assert "confidence" in content, f"Missing 'confidence' in canonical field '{field}'"


def test_get_batch_audit_evidence_report_excludes_null_fields(client):
    """evidence_report must contain only fields where value is not None."""
    tid = create_template(client, "Agency AuditNull")
    mock_inst = _mock_extractor()

    with (
        patch("api.routes.batch.IncidentExtractor", return_value=mock_inst),
        patch("api.routes.batch.IncidentExtractor.build_evidence_report",
              return_value=EVIDENCE_REPORT),
        patch("src.filler.Filler.fill_form_with_data", return_value="src/outputs/out.pdf"),
    ):
        fill_res = client.post("/forms/fill/batch", json={
            "input_text": TRANSCRIPT,
            "template_ids": [tid],
        })

    batch_id = fill_res.json()["batch_id"]
    data = client.get(f"/forms/batches/{batch_id}/audit").json()
    evidence = data["evidence_report"]

    # incident_type has value=None in our CANONICAL fixture → must not be in evidence
    assert "incident_type" not in evidence
    # reporting_officer has value → must be present
    assert "reporting_officer" in evidence


def test_get_batch_audit_404_unknown(client):
    res = client.get("/forms/batches/no-such-batch/audit")
    assert res.status_code == 404


# ── Unit tests for BatchFill validator ────────────────────────────────────────

def test_batch_fill_schema_rejects_empty_list():
    from pydantic import ValidationError
    from api.schemas.batch import BatchFill
    import pytest

    with pytest.raises(ValidationError):
        BatchFill(input_text="x", template_ids=[])


def test_batch_fill_schema_rejects_duplicates():
    from pydantic import ValidationError
    from api.schemas.batch import BatchFill
    import pytest

    with pytest.raises(ValidationError):
        BatchFill(input_text="x", template_ids=[1, 1])


def test_batch_fill_schema_rejects_over_limit():
    from pydantic import ValidationError
    from api.schemas.batch import BatchFill
    import pytest

    with pytest.raises(ValidationError):
        BatchFill(input_text="x", template_ids=list(range(1, 22)))


def test_batch_fill_schema_accepts_valid():
    from api.schemas.batch import BatchFill

    b = BatchFill(input_text="test", template_ids=[1, 2, 3])
    assert b.template_ids == [1, 2, 3]


# ── Unit tests for IncidentExtractor.build_evidence_report ───────────────────

def test_build_evidence_report_filters_nulls():
    from src.extractor import IncidentExtractor

    canonical = {
        "field_a": {"value": "present", "evidence": "quote", "confidence": "high"},
        "field_b": {"value": None, "evidence": None, "confidence": "low"},
        "field_c": {"value": ["Alice", "Bob"], "evidence": "seen Alice and Bob", "confidence": "medium"},
    }
    report = IncidentExtractor.build_evidence_report(canonical)
    # field_a has a non-None value → should be included
    assert "field_a" in report
    # field_b value is None → excluded
    assert "field_b" not in report
    # field_c value is a non-None list → should be included
    assert "field_c" in report


def test_build_evidence_report_preserves_structure():
    from src.extractor import IncidentExtractor

    canonical = {
        "reporting_officer": {
            "value": "Sgt. Davis",
            "evidence": "Sgt. Davis at the scene.",
            "confidence": "high",
        }
    }
    report = IncidentExtractor.build_evidence_report(canonical)
    assert report["reporting_officer"]["value"] == "Sgt. Davis"
    assert report["reporting_officer"]["evidence"] == "Sgt. Davis at the scene."
    assert report["reporting_officer"]["confidence"] == "high"
