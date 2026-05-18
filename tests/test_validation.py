import pytest
from src.validation import validate_extracted_data


def test_valid_data():
    data = {
        "patient_name": "John Doe",
        "age": 30,
        "diagnosis": "Flu"
    }
    assert validate_extracted_data(data) == True


def test_missing_field():
    data = {
        "patient_name": "John Doe",
        "age": 30
    }
    assert validate_extracted_data(data) == False


def test_empty_field():
    data = {
        "patient_name": "",
        "age": 30,
        "diagnosis": "Flu"
    }
    assert validate_extracted_data(data) == False
