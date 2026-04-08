"""
Comprehensive tests for the incident data validation module.

These tests verify that the validation gate correctly catches
incomplete or malformed incident data before PDF generation.

Author: dhanasai2
Tests for: Issue #305
"""

import pytest
from src.validator import (
    validate_incident,
    validate_incident_strict,
    validate_transcript,
    validate_transcript_strict,
    validate_template_fields,
    validate_all_inputs,
    IncidentValidator,
    TranscriptValidator,
    ValidationError,
    ValidationResult,
    ValidationException,
    ErrorSeverity,
)
from src.filler import FormValidationError


class TestValidateIncidentFunction:
    """Tests for the main validate_incident() convenience function."""

    def test_valid_incident_returns_empty_list(self):
        """Valid data with all required fields should return empty error list."""
        valid_data = {
            "incident_type": "Structure Fire",
            "location": "123 Main Street, Springfield",
            "time": "14:30",
            "date": "03/28/2026",
            "reporting_officer": "Captain John Smith"
        }
        errors = validate_incident(valid_data)
        assert errors == []

    def test_missing_required_field_returns_error(self):
        """Missing required fields should return appropriate error messages."""
        data_missing_location = {
            "incident_type": "Medical Emergency",
            "time": "09:15",
            "date": "03/28/2026",
            "reporting_officer": "Lt. Jane Doe"
        }
        errors = validate_incident(data_missing_location)
        assert len(errors) > 0
        assert any("location" in error.lower() for error in errors)

    def test_empty_field_returns_error(self):
        """Empty string fields should return validation errors."""
        data_with_empty = {
            "incident_type": "",
            "location": "456 Oak Avenue",
            "time": "10:00",
            "date": "03/28/2026",
            "reporting_officer": "Sgt. Bob Wilson"
        }
        errors = validate_incident(data_with_empty)
        assert len(errors) > 0
        assert any("incident_type" in error.lower() for error in errors)

    def test_whitespace_only_field_returns_error(self):
        """Whitespace-only fields should be treated as empty."""
        data_with_whitespace = {
            "incident_type": "   ",
            "location": "789 Pine Road",
            "time": "11:30",
            "date": "03/28/2026",
            "reporting_officer": "Chief Mary Johnson"
        }
        errors = validate_incident(data_with_whitespace)
        assert len(errors) > 0
        assert any("incident_type" in error.lower() for error in errors)

    def test_invalid_type_returns_error(self):
        """Non-dictionary input should return type error."""
        errors = validate_incident("not a dictionary")
        assert len(errors) > 0
        assert any("dictionary" in error.lower() for error in errors)

        errors = validate_incident(["list", "of", "items"])
        assert len(errors) > 0

        errors = validate_incident(None)
        assert len(errors) > 0

    def test_empty_dict_returns_error(self):
        """Empty dictionary should return validation error."""
        errors = validate_incident({})
        assert len(errors) > 0
        assert any("empty" in error.lower() for error in errors)

    def test_custom_required_fields(self):
        """Custom required fields should be validated correctly."""
        custom_fields = ["name", "phone", "address"]
        data = {
            "name": "John Doe",
            "phone": "555-1234"
            # address is missing
        }
        errors = validate_incident(data, required_fields=custom_fields)
        assert len(errors) > 0
        assert any("address" in error.lower() for error in errors)

    def test_llm_not_found_marker_treated_as_empty(self):
        """The LLM's '-1' not-found marker should be treated as empty."""
        data_with_not_found = {
            "incident_type": "Fire",
            "location": "-1",  # LLM couldn't find this
            "time": "15:00",
            "date": "03/28/2026",
            "reporting_officer": "Officer Smith"
        }
        errors = validate_incident(data_with_not_found)
        assert len(errors) > 0
        assert any("location" in error.lower() for error in errors)


class TestValidateIncidentStrict:
    """Tests for the strict validation function with detailed results."""

    def test_valid_data_returns_valid_result(self):
        """Valid data should return ValidationResult with is_valid=True."""
        valid_data = {
            "incident_type": "Vehicle Accident",
            "location": "Highway 101, Mile Marker 42",
            "time": "08:45",
            "date": "03/28/2026",
            "reporting_officer": "Paramedic Lisa Chen"
        }
        result = validate_incident_strict(valid_data)
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_invalid_data_returns_detailed_errors(self):
        """Invalid data should return ValidationResult with error details."""
        invalid_data = {
            "incident_type": "",
            "time": "10:00"
        }
        result = validate_incident_strict(invalid_data)
        assert result.is_valid is False
        assert len(result.errors) > 0

        # Check that errors have proper structure
        for error in result.errors:
            assert isinstance(error, ValidationError)
            assert hasattr(error, 'field')
            assert hasattr(error, 'message')
            assert hasattr(error, 'error_type')

    def test_result_to_dict_serialization(self):
        """ValidationResult should serialize to dictionary properly."""
        data = {"incident_type": ""}  # Will fail validation
        result = validate_incident_strict(data)

        result_dict = result.to_dict()
        assert "is_valid" in result_dict
        assert "errors" in result_dict
        assert isinstance(result_dict["errors"], list)


class TestIncidentValidator:
    """Tests for the IncidentValidator class."""

    def test_default_required_fields(self):
        """Validator should have sensible default required fields."""
        validator = IncidentValidator()
        assert "incident_type" in validator.required_fields
        assert "location" in validator.required_fields
        assert "time" in validator.required_fields

    def test_custom_required_fields_initialization(self):
        """Validator should accept custom required fields."""
        custom_fields = ["field_a", "field_b", "field_c"]
        validator = IncidentValidator(required_fields=custom_fields)
        assert validator.required_fields == custom_fields

    def test_validate_method_returns_validation_result(self):
        """The validate method should return a ValidationResult object."""
        validator = IncidentValidator()
        result = validator.validate({"test": "data"})
        assert isinstance(result, ValidationResult)

    def test_validates_list_fields(self):
        """Validator should handle list values (plural fields from LLM)."""
        validator = IncidentValidator(required_fields=["items"])

        # Non-empty list should pass
        result = validator.validate({"items": ["item1", "item2"]})
        # May have errors for other missing default fields, but items should be OK
        items_errors = [e for e in result.errors if e.field == "items"]
        assert len(items_errors) == 0

        # Empty list should fail
        result = validator.validate({"items": []})
        items_errors = [e for e in result.errors if e.field == "items"]
        assert len(items_errors) > 0

    def test_validates_none_values(self):
        """Validator should catch None values."""
        validator = IncidentValidator(required_fields=["field"])
        result = validator.validate({"field": None})
        assert result.is_valid is False
        assert any(e.field == "field" for e in result.errors)


class TestValidationError:
    """Tests for the ValidationError dataclass."""

    def test_error_creation(self):
        """ValidationError should store field, message, and error_type."""
        error = ValidationError(
            field="test_field",
            message="Test error message",
            error_type="missing"
        )
        assert error.field == "test_field"
        assert error.message == "Test error message"
        assert error.error_type == "missing"

    def test_error_to_dict(self):
        """ValidationError should convert to dictionary properly."""
        error = ValidationError(
            field="location",
            message="Location is required",
            error_type="missing"
        )
        error_dict = error.to_dict()
        assert error_dict["field"] == "location"
        assert error_dict["message"] == "Location is required"
        assert error_dict["error_type"] == "missing"


class TestFormValidationError:
    """Tests for the FormValidationError exception."""

    def test_exception_creation(self):
        """FormValidationError should store errors and optional data."""
        errors = ["Field 'name' is missing", "Field 'date' is empty"]
        data = {"partial": "data"}

        exc = FormValidationError(errors=errors, data=data)
        assert exc.errors == errors
        assert exc.data == data
        assert "2 error(s)" in str(exc)

    def test_exception_without_data(self):
        """FormValidationError should work without data parameter."""
        errors = ["Single error"]
        exc = FormValidationError(errors=errors)
        assert exc.errors == errors
        assert exc.data is None

    def test_exception_is_raisable(self):
        """FormValidationError should be raisable and catchable."""
        with pytest.raises(FormValidationError) as exc_info:
            raise FormValidationError(errors=["Test error"])

        assert "Test error" in str(exc_info.value)


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_very_long_field_value(self):
        """Validator should handle very long string values."""
        long_value = "A" * 10000
        data = {
            "incident_type": long_value,
            "location": "Test Location",
            "time": "12:00",
            "date": "03/28/2026",
            "reporting_officer": "Test Officer"
        }
        errors = validate_incident(data)
        assert errors == []  # Long values are valid

    def test_special_characters_in_values(self):
        """Validator should handle special characters in field values."""
        data = {
            "incident_type": "Fire/Rescue & Medical",
            "location": "123 Main St. #4B, O'Brien's Corner",
            "time": "12:00",
            "date": "03/28/2026",
            "reporting_officer": "José García-López"
        }
        errors = validate_incident(data)
        assert errors == []

    def test_unicode_values(self):
        """Validator should handle unicode characters properly."""
        data = {
            "incident_type": "火災対応",  # Japanese: Fire response
            "location": "東京都渋谷区",  # Japanese address
            "time": "12:00",
            "date": "03/28/2026",
            "reporting_officer": "田中太郎"
        }
        errors = validate_incident(data)
        assert errors == []

    def test_numeric_values_as_strings(self):
        """Validator should accept numeric values stored as strings."""
        data = {
            "incident_type": "Code 10-54",
            "location": "12345",  # Numeric address
            "time": "0800",  # Military time as string
            "date": "20260328",
            "reporting_officer": "Unit 42"
        }
        errors = validate_incident(data)
        assert errors == []

    def test_extra_fields_ignored(self):
        """Extra fields beyond required ones should not cause errors."""
        data = {
            "incident_type": "Fire",
            "location": "123 Main St",
            "time": "12:00",
            "date": "03/28/2026",
            "reporting_officer": "Officer Smith",
            "extra_field_1": "extra value 1",
            "extra_field_2": "extra value 2",
            "custom_notes": "These are custom notes"
        }
        errors = validate_incident(data)
        assert errors == []


class TestTranscriptValidation:
    """Tests for transcript/user input validation."""

    def test_valid_transcript_returns_empty_list(self):
        """Valid transcript should return no errors."""
        transcript = "Fire reported at 123 Main Street at 14:30. Two victims rescued by Engine 5."
        errors = validate_transcript(transcript)
        assert errors == []

    def test_empty_transcript_returns_error(self):
        """Empty transcript should return error."""
        errors = validate_transcript("")
        assert len(errors) > 0
        assert any("empty" in e.lower() for e in errors)

    def test_whitespace_only_transcript_returns_error(self):
        """Whitespace-only transcript should return error."""
        errors = validate_transcript("   \t\n   ")
        assert len(errors) > 0

    def test_none_transcript_returns_error(self):
        """None transcript should return error."""
        errors = validate_transcript(None)
        assert len(errors) > 0

    def test_non_string_transcript_returns_error(self):
        """Non-string transcript should return type error."""
        errors = validate_transcript(12345)
        assert len(errors) > 0
        assert any("string" in e.lower() for e in errors)

    def test_short_transcript_returns_error(self):
        """Very short transcript should return error."""
        errors = validate_transcript("Hi")
        assert len(errors) > 0
        assert any("short" in e.lower() for e in errors)

    def test_minimum_valid_length_passes(self):
        """Transcript at minimum length should pass."""
        transcript = "Fire at 123"  # 11 chars > 10 min
        errors = validate_transcript(transcript)
        assert errors == []


class TestTranscriptValidatorStrict:
    """Tests for strict transcript validation with warnings."""

    def test_returns_validation_result(self):
        """Should return ValidationResult instance."""
        result = validate_transcript_strict("Test transcript content here")
        assert isinstance(result, ValidationResult)

    def test_non_incident_content_returns_warning(self):
        """Non-incident content should generate warning, not error."""
        transcript = "The weather is nice today and I went shopping at the mall"
        result = validate_transcript_strict(transcript)

        # Should still be valid (warnings don't block)
        assert result.is_valid is True
        # Should have warnings about content
        assert len(result.warnings) > 0

    def test_incident_content_no_warning(self):
        """Incident-related content should not generate content warning."""
        transcript = "Fire emergency reported at location 123 Main St with 2 victims"
        result = validate_transcript_strict(transcript)

        assert result.is_valid is True
        content_warnings = [w for w in result.warnings if "incident" in w.message.lower()]
        assert len(content_warnings) == 0


class TestTranscriptValidator:
    """Tests for the TranscriptValidator class."""

    def test_incident_keyword_detection(self):
        """Should detect incident-related keywords."""
        validator = TranscriptValidator()

        assert validator._contains_incident_keywords("There was a fire at the building")
        assert validator._contains_incident_keywords("Emergency response needed")
        assert validator._contains_incident_keywords("Accident reported on highway")
        assert validator._contains_incident_keywords("Victim found at scene")
        assert not validator._contains_incident_keywords("Nice weather today")
        assert not validator._contains_incident_keywords("Going to the store")


class TestTemplateFieldValidation:
    """Tests for template field configuration validation."""

    def test_valid_dict_fields(self):
        """Valid dict fields should return empty error list."""
        fields = {"incident_type": "", "location": "", "time": ""}
        errors = validate_template_fields(fields)
        assert errors == []

    def test_valid_list_fields(self):
        """Valid list fields should return empty error list."""
        fields = ["incident_type", "location", "time"]
        errors = validate_template_fields(fields)
        assert errors == []

    def test_none_fields_returns_error(self):
        """None fields should return error."""
        errors = validate_template_fields(None)
        assert len(errors) > 0

    def test_empty_dict_returns_error(self):
        """Empty dict should return error."""
        errors = validate_template_fields({})
        assert len(errors) > 0

    def test_empty_list_returns_error(self):
        """Empty list should return error."""
        errors = validate_template_fields([])
        assert len(errors) > 0

    def test_invalid_type_returns_error(self):
        """Invalid type should return error."""
        errors = validate_template_fields("not a dict or list")
        assert len(errors) > 0


class TestValidateAllInputs:
    """Tests for the combined validation function."""

    def test_returns_validation_result(self):
        """Should return ValidationResult instance."""
        result = validate_all_inputs(
            transcript="Fire at location with emergency response",
            fields={"field1": "val"},
            pdf_path="test.pdf"
        )
        assert isinstance(result, ValidationResult)

    def test_invalid_transcript_fails(self):
        """Invalid transcript should cause failure."""
        result = validate_all_inputs(
            transcript="",
            fields={"field1": "val"},
            pdf_path="test.pdf"
        )
        assert result.is_valid is False
        assert any("transcript" in e.field for e in result.errors)

    def test_invalid_fields_fails(self):
        """Invalid fields should cause failure."""
        result = validate_all_inputs(
            transcript="Valid transcript with enough content for processing",
            fields=None,
            pdf_path="test.pdf"
        )
        assert result.is_valid is False
        assert any("fields" in e.field for e in result.errors)


class TestValidationResult:
    """Tests for ValidationResult class functionality."""

    def test_raise_if_invalid_raises_exception(self):
        """Should raise ValidationException when invalid."""
        error = ValidationError(
            field="test",
            message="Test error",
            error_type="test_error"
        )
        result = ValidationResult(is_valid=False, errors=[error])

        with pytest.raises(ValidationException):
            result.raise_if_invalid()

    def test_raise_if_invalid_silent_when_valid(self):
        """Should not raise when valid."""
        result = ValidationResult(is_valid=True, errors=[])
        result.raise_if_invalid()  # Should not raise

    def test_get_all_messages_includes_warnings(self):
        """Should include both errors and warnings."""
        error = ValidationError(field="e", message="Error msg", error_type="err")
        warning = ValidationError(
            field="w",
            message="Warning msg",
            error_type="warn",
            severity=ErrorSeverity.WARNING
        )
        result = ValidationResult(
            is_valid=False,
            errors=[error],
            warnings=[warning]
        )

        messages = result.get_all_messages()
        assert "Error msg" in messages
        assert "Warning msg" in messages


class TestValidationException:
    """Tests for ValidationException class."""

    def test_exception_contains_errors(self):
        """Exception should contain error list."""
        errors = [
            ValidationError(field="f1", message="Error 1", error_type="test"),
            ValidationError(field="f2", message="Error 2", error_type="test")
        ]
        exc = ValidationException(errors=errors)
        assert len(exc.errors) == 2

    def test_to_dict_serialization(self):
        """Should serialize to dict."""
        errors = [ValidationError(field="f", message="Msg", error_type="t")]
        exc = ValidationException(errors=errors, message="Test failure")

        result = exc.to_dict()
        assert result["message"] == "Test failure"
        assert len(result["errors"]) == 1

    def test_get_error_messages(self):
        """Should return list of error messages."""
        errors = [
            ValidationError(field="f1", message="First error", error_type="t"),
            ValidationError(field="f2", message="Second error", error_type="t")
        ]
        exc = ValidationException(errors=errors)

        messages = exc.get_error_messages()
        assert "First error" in messages
        assert "Second error" in messages
