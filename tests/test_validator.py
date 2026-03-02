"""
Tests for src/validator.py — SchemaValidator
"""
import pytest
from src.validator import SchemaValidator, Confidence


SCHEMA = {
    "reporting_officer": "string",
    "incident_location": "string",
    "amount_of_victims": "int",
    "victim_name_s": "list",
}


# ---------------------------------------------------------------------------
# Happy path — all fields present and correctly typed
# ---------------------------------------------------------------------------

def test_all_fields_valid():
    extracted = {
        "reporting_officer": "Officer Voldemort",
        "incident_location": "456 Oak Street",
        "amount_of_victims": 2,
        "victim_name_s": ["Mark Smith", "Jane Doe"],
    }
    report = SchemaValidator().validate(extracted, SCHEMA)

    assert report.is_valid is True
    assert report.warnings == []
    assert report.missing_fields == []
    assert report.validated_data["reporting_officer"] == "Officer Voldemort"


def test_high_confidence_on_exact_match():
    extracted = {
        "reporting_officer": "Officer Voldemort",
        "incident_location": "456 Oak Street",
        "amount_of_victims": 2,
        "victim_name_s": ["Mark Smith", "Jane Doe"],
    }
    report = SchemaValidator().validate(extracted, SCHEMA)

    for result in report.fields:
        assert result.confidence == Confidence.HIGH


# ---------------------------------------------------------------------------
# Missing fields
# ---------------------------------------------------------------------------

def test_missing_field_flagged():
    extracted = {
        "reporting_officer": "Officer Voldemort",
        "incident_location": None,
        "amount_of_victims": 2,
        "victim_name_s": ["Mark Smith"],
    }
    report = SchemaValidator().validate(extracted, SCHEMA)

    assert report.is_valid is False
    assert "incident_location" in report.missing_fields
    assert len(report.warnings) == 1


def test_minus_one_treated_as_missing():
    """LLM returns '-1' as a sentinel when it cannot find a value."""
    extracted = {
        "reporting_officer": "-1",
        "incident_location": "456 Oak Street",
        "amount_of_victims": 2,
        "victim_name_s": ["Mark Smith"],
    }
    report = SchemaValidator().validate(extracted, SCHEMA)

    assert report.is_valid is False
    assert "reporting_officer" in report.missing_fields


def test_all_missing_fields():
    report = SchemaValidator().validate({}, SCHEMA)

    assert report.is_valid is False
    assert len(report.missing_fields) == len(SCHEMA)


# ---------------------------------------------------------------------------
# Type coercion — LOW confidence
# ---------------------------------------------------------------------------

def test_int_field_coerced_from_string():
    """amount_of_victims comes back as '2' (string) — should coerce to int."""
    extracted = {
        "reporting_officer": "Officer Voldemort",
        "incident_location": "456 Oak Street",
        "amount_of_victims": "2",
        "victim_name_s": ["Mark Smith"],
    }
    report = SchemaValidator().validate(extracted, SCHEMA)

    field_result = next(r for r in report.fields if r.field == "amount_of_victims")

    assert field_result.confidence == Confidence.LOW
    assert field_result.value == 2
    assert len(report.warnings) == 1
    assert report.is_valid is True


# ---------------------------------------------------------------------------
# Report properties
# ---------------------------------------------------------------------------

def test_validated_data_excludes_missing():
    extracted = {
        "reporting_officer": "Officer Voldemort",
        "incident_location": None,
        "amount_of_victims": 2,
        "victim_name_s": ["Mark Smith"],
    }
    report = SchemaValidator().validate(extracted, SCHEMA)

    assert "incident_location" not in report.validated_data
    assert "reporting_officer" in report.validated_data


def test_unknown_type_hint_defaults_to_string():
    """An unrecognised type hint in the schema should default to str."""
    schema = {"some_field": "unknown_type"}
    extracted = {"some_field": "hello"}

    report = SchemaValidator().validate(extracted, schema)

    assert report.is_valid is True
    assert report.validated_data["some_field"] == "hello"
