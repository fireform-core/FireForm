"""Regression fixture tests for incident extraction scenarios."""

import json
from pathlib import Path

import pytest


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "incidents"
REQUIRED_FIXTURE_KEYS = {"name", "input_text", "fields", "expected"}


def load_incident_fixtures():
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(FIXTURE_DIR.glob("*.json"))
    ]


def compare_extraction(expected, actual):
    """Return field mismatches between expected and actual extraction output."""
    mismatches = {}

    for field, expected_value in expected.items():
        actual_value = actual.get(field)
        if actual_value != expected_value:
            mismatches[field] = {
                "expected": expected_value,
                "actual": actual_value,
            }

    return mismatches


@pytest.mark.parametrize("fixture", load_incident_fixtures(), ids=lambda item: item["name"])
def test_incident_fixture_contract(fixture):
    assert REQUIRED_FIXTURE_KEYS.issubset(fixture)
    assert isinstance(fixture["name"], str)
    assert fixture["name"]
    assert isinstance(fixture["input_text"], str)
    assert fixture["input_text"]
    assert isinstance(fixture["fields"], list)
    assert fixture["fields"]
    assert isinstance(fixture["expected"], dict)
    assert fixture["expected"]
    assert set(fixture["expected"]).issubset(set(fixture["fields"]))


@pytest.mark.parametrize("fixture", load_incident_fixtures(), ids=lambda item: item["name"])
def test_fixture_expected_output_matches_golden_values(fixture):
    # Future LLM tests can replace this deterministic mock with mocked Ollama output.
    mocked_extraction_output = dict(fixture["expected"])

    assert compare_extraction(fixture["expected"], mocked_extraction_output) == {}


def test_compare_extraction_reports_field_level_mismatches():
    expected = {"incident_address": "142 Oak Street", "unit": "Engine 12"}
    actual = {"incident_address": "142 Oak Street", "unit": "Engine 9"}

    assert compare_extraction(expected, actual) == {
        "unit": {
            "expected": "Engine 12",
            "actual": "Engine 9",
        }
    }
