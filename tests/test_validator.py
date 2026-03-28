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
    IncidentValidator,
    ValidationError,
    ValidationResult,
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
