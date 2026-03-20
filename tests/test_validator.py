"""
Tests for src/validator.py — validate_incident()

Coverage matrix:
  - Invalid input type (str, list, None, int)
  - Valid input: minimal, with extra fields
  - Missing single required field (each of the 3)
  - Missing all required fields
  - Empty string value
  - None value
  - Whitespace-only string (space, tab, newline)
  - Multiple empty fields simultaneously
  - Mixed: missing + empty in same call
  - Numeric (non-string, non-None) value — should pass
  - Custom required_fields override
  - Empty required_fields tuple — must always pass
"""

import pytest
from src.validator import validate_incident, INCIDENT_REQUIRED_FIELDS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_incident() -> dict:
    return {
        "incident_type": "Fire",
        "location": "123 Main St",
        "time": "2026-03-20T09:15:00",
    }


# ---------------------------------------------------------------------------
# 1. Input type enforcement
# ---------------------------------------------------------------------------

class TestInputTypeEnforcement:
    def test_rejects_plain_string(self):
        assert validate_incident("incident summary text") == [
            "Input data must be a dictionary."
        ]

    def test_rejects_list(self):
        assert validate_incident([{"incident_type": "Fire"}]) == [
            "Input data must be a dictionary."
        ]

    def test_rejects_none(self):
        assert validate_incident(None) == ["Input data must be a dictionary."]

    def test_rejects_integer(self):
        assert validate_incident(42) == ["Input data must be a dictionary."]

    def test_rejects_float(self):
        assert validate_incident(3.14) == ["Input data must be a dictionary."]

    def test_rejects_bool(self):
        # bool is a subclass of int in Python — still not a dict
        assert validate_incident(True) == ["Input data must be a dictionary."]


# ---------------------------------------------------------------------------
# 2. Valid input
# ---------------------------------------------------------------------------

class TestValidInput:
    def test_minimal_valid_incident(self, valid_incident):
        assert validate_incident(valid_incident) == []

    def test_valid_with_extra_fields(self, valid_incident):
        valid_incident["reporting_officer"] = "Jane Doe"
        valid_incident["unit"] = "Engine 7"
        assert validate_incident(valid_incident) == []

    def test_numeric_time_value_passes(self, valid_incident):
        """Non-string, non-None values are not empty — they pass."""
        valid_incident["time"] = 1711000000
        assert validate_incident(valid_incident) == []

    def test_empty_dict_with_no_required_fields(self):
        """Overriding required_fields to empty means everything passes."""
        assert validate_incident({}, required_fields=()) == []


# ---------------------------------------------------------------------------
# 3. Missing required fields
# ---------------------------------------------------------------------------

class TestMissingFields:
    def test_missing_incident_type(self):
        data = {"location": "123 Main St", "time": "2026-03-20T09:15:00"}
        assert validate_incident(data) == ["Missing required field: incident_type"]

    def test_missing_location(self):
        data = {"incident_type": "Fire", "time": "2026-03-20T09:15:00"}
        assert validate_incident(data) == ["Missing required field: location"]

    def test_missing_time(self):
        data = {"incident_type": "Fire", "location": "123 Main St"}
        assert validate_incident(data) == ["Missing required field: time"]

    def test_missing_all_three_fields(self):
        assert validate_incident({}) == [
            "Missing required field: incident_type",
            "Missing required field: location",
            "Missing required field: time",
        ]

    def test_error_order_matches_required_fields_order(self):
        """Error list order must be deterministic — matches INCIDENT_REQUIRED_FIELDS."""
        errors = validate_incident({})
        expected = [f"Missing required field: {f}" for f in INCIDENT_REQUIRED_FIELDS]
        assert errors == expected


# ---------------------------------------------------------------------------
# 4. Present but empty values
# ---------------------------------------------------------------------------

class TestEmptyValues:
    def test_empty_string_location(self, valid_incident):
        valid_incident["location"] = ""
        assert validate_incident(valid_incident) == ["Field cannot be empty: location"]

    def test_none_time(self, valid_incident):
        valid_incident["time"] = None
        assert validate_incident(valid_incident) == ["Field cannot be empty: time"]

    def test_whitespace_only_incident_type(self, valid_incident):
        valid_incident["incident_type"] = "   "
        assert validate_incident(valid_incident) == [
            "Field cannot be empty: incident_type"
        ]

    def test_tab_character_location(self, valid_incident):
        valid_incident["location"] = "\t"
        assert validate_incident(valid_incident) == ["Field cannot be empty: location"]

    def test_newline_only_time(self, valid_incident):
        valid_incident["time"] = "\n"
        assert validate_incident(valid_incident) == ["Field cannot be empty: time"]

    def test_mixed_whitespace(self, valid_incident):
        valid_incident["location"] = " \t\n "
        assert validate_incident(valid_incident) == ["Field cannot be empty: location"]


# ---------------------------------------------------------------------------
# 5. Multiple errors in one call
# ---------------------------------------------------------------------------

class TestMultipleErrors:
    def test_two_fields_empty(self, valid_incident):
        valid_incident["location"] = ""
        valid_incident["time"] = None
        assert validate_incident(valid_incident) == [
            "Field cannot be empty: location",
            "Field cannot be empty: time",
        ]

    def test_one_missing_one_empty(self):
        data = {"incident_type": "Fire", "location": ""}
        errors = validate_incident(data)
        assert "Field cannot be empty: location" in errors
        assert "Missing required field: time" in errors

    def test_all_fields_empty(self):
        data = {"incident_type": "", "location": None, "time": "  "}
        assert validate_incident(data) == [
            "Field cannot be empty: incident_type",
            "Field cannot be empty: location",
            "Field cannot be empty: time",
        ]


# ---------------------------------------------------------------------------
# 6. Custom required_fields override
# ---------------------------------------------------------------------------

class TestCustomRequiredFields:
    def test_custom_single_field_missing(self):
        data = {"name": "John Doe"}
        errors = validate_incident(data, required_fields=("name", "badge_number"))
        assert errors == ["Missing required field: badge_number"]

    def test_custom_field_empty(self):
        data = {"report_id": "  "}
        errors = validate_incident(data, required_fields=("report_id",))
        assert errors == ["Field cannot be empty: report_id"]

    def test_custom_fields_all_valid(self):
        data = {"report_id": "RPT-001", "unit": "Engine 7"}
        assert validate_incident(data, required_fields=("report_id", "unit")) == []
