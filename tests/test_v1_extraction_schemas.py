"""Validate the extraction schemas against the examples in the contract.

Each example below is copied from contracts/path/extraction.yaml. The point is
to catch drift: if the contract example changes shape, the matching model must
still accept it (and vice versa). No routes are exercised here, only the
Pydantic models from app/api/schemas/extraction.py.
"""

from app.api.schemas.enums import FieldSource
from app.api.schemas.extraction import (
    ExtractionCompleted,
    ExtractionProcessing,
    ExtractionRequest,
    ReadinessMatrix,
    ValidationResult,
)
from app.api.schemas.incident_contract import IncidentContract


# ---------------------------------------------------------------------------
# ExtractionRequest — POST /extract/{input_id} request body
# ---------------------------------------------------------------------------

def test_extraction_request_example():
    example = {
        "model_override": "llama3:8b",
        "extraction_hints": {
            "incident_type": "wildland_fire",
            "state": "CA",
        },
        "defaults": {
            "country": "US",
            "timezone": "America/Los_Angeles",
            "currency": "USD",
        },
    }
    model = ExtractionRequest.model_validate(example)
    assert model.model_dump(exclude_none=True) == example


def test_extraction_request_hints_allow_extra_keys():
    # extraction_hints is additionalProperties: true in the contract.
    model = ExtractionRequest.model_validate(
        {"extraction_hints": {"incident_type": "structure_fire", "battalion": "3"}}
    )
    assert model.extraction_hints.incident_type == "structure_fire"
    dumped = model.model_dump(exclude_none=True)
    assert dumped["extraction_hints"]["battalion"] == "3"


def test_extraction_request_all_fields_optional():
    assert ExtractionRequest.model_validate({}).model_dump(exclude_none=True) == {}


# ---------------------------------------------------------------------------
# ExtractionCompleted / ExtractionProcessing — GET /extract/{extract_id}
# ---------------------------------------------------------------------------

def test_extraction_completed_example():
    example = {
        "extract_id": "550e8400-e29b-41d4-a716-446655440020",
        "input_id": "550e8400-e29b-41d4-a716-446655440001",
        "incident_id": "550e8400-e29b-41d4-a716-446655440050",
        "status": "completed",
        "completed_at": "2024-07-15T14:31:05Z",
        "incident_contract": {
            "schema_version": "1.1.0",
            "schema_name": "fireform_incident_contract",
            "extraction_metadata": {
                "extract_id": "550e8400-e29b-41d4-a716-446655440020",
                "confidence_score": 0.91,
            },
            "incident": {"name": "Bear Creek Wildfire"},
        },
    }
    model = ExtractionCompleted.model_validate(example)
    assert model.status == "completed"
    assert isinstance(model.incident_contract, IncidentContract)
    assert model.incident_contract.incident.name == "Bear Creek Wildfire"


def test_extraction_processing_example():
    example = {
        "extract_id": "550e8400-e29b-41d4-a716-446655440020",
        "input_id": "550e8400-e29b-41d4-a716-446655440001",
        "status": "processing",
        "started_at": "2024-07-15T14:30:00Z",
        "retry_after_seconds": 5,
    }
    model = ExtractionProcessing.model_validate(example)
    assert model.status == "processing"
    assert model.retry_after_seconds == 5


def test_extraction_processing_failed_status_allowed():
    model = ExtractionProcessing.model_validate({
        "extract_id": "550e8400-e29b-41d4-a716-446655440020",
        "input_id": "550e8400-e29b-41d4-a716-446655440001",
        "status": "failed",
        "error_type": "LLM_TIMEOUT",
        "error_detail": "Ollama did not respond within the timeout",
    })
    assert model.status == "failed"
    assert model.error_type == "LLM_TIMEOUT"


# ---------------------------------------------------------------------------
# ReadinessMatrix — GET /extract/{extract_id}/readiness
# ---------------------------------------------------------------------------

def test_readiness_matrix_example():
    example = {
        "extract_id": "550e8400-e29b-41d4-a716-446655440020",
        "computed_at": "2026-07-15T14:35:00Z",
        "templates": [
            {
                "template_id": "550e8400-e29b-41d4-a716-446655440070",
                "form_type": "neris",
                "display_name": "NERIS Incident Report",
                "ready": True,
                "missing_required": [],
                "missing_recommended": [
                    {
                        "field_name": "smoke_alarm_presence",
                        "source": "schema",
                        "incident_mapping": "risk_reduction.smoke_alarm.presence",
                    }
                ],
                "field_coverage_percent": 94,
            },
            {
                "template_id": "550e8400-e29b-41d4-a716-446655440073",
                "form_type": "state_texas",
                "display_name": "Texas State Fire Marshal Incident Report",
                "ready": False,
                "missing_required": [
                    {
                        "field_name": "marshal_signature_name",
                        "source": "manual",
                        "incident_mapping": "custom_fields.state_texas.marshal_signature_name",
                        "description": "Reviewing marshal's printed name, entered per incident",
                    },
                    {
                        "field_name": "fire_cause",
                        "source": "schema",
                        "incident_mapping": "fire.cause_category",
                    },
                ],
                "missing_recommended": [],
                "field_coverage_percent": 78,
            },
        ],
    }
    model = ReadinessMatrix.model_validate(example)
    assert len(model.templates) == 2
    # form_type is an open string: state_texas is not in the built-in list.
    assert model.templates[1].form_type == "state_texas"
    assert model.templates[1].missing_required[0].source is FieldSource.manual


# ---------------------------------------------------------------------------
# ValidationResult — POST /extract/{extract_id}/validate
# ---------------------------------------------------------------------------

def test_validation_result_example():
    example = {
        "valid": True,
        "template_id": "550e8400-e29b-41d4-a716-446655440070",
        "form_type": "neris",
        "extract_id": "550e8400-e29b-41d4-a716-446655440020",
        "missing_required": [],
        "missing_recommended": [
            {
                "field_name": "smoke_alarm_presence",
                "source": "schema",
                "incident_mapping": "risk_reduction.smoke_alarm.presence",
            },
            {
                "field_name": "smoke_alarm_operation",
                "source": "schema",
                "incident_mapping": "risk_reduction.smoke_alarm.operation",
            },
        ],
        "warnings": [
            "losses.property_loss is null. NERIS recommends providing damage estimates"
        ],
        "field_coverage_percent": 94,
    }
    model = ValidationResult.model_validate(example)
    assert model.valid is True
    assert len(model.missing_recommended) == 2
    assert model.missing_recommended[0].source is FieldSource.schema
