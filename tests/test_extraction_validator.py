from src.utils.extraction_validator import ExtractionValidator


def test_missing_fields_requires_review():
    validator = ExtractionValidator()

    data = {
        "location": "Bangalore",
        "time": "",
        "severity": "",
        "description": ""
    }

    result = validator.validate(data)

    assert result["requires_review"] is True
    assert result["confidence_score"] < 100


def test_complete_fields_no_review():
    validator = ExtractionValidator()

    data = {
        "location": "Bangalore",
        "time": "5 PM",
        "severity": "High",
        "description": "Fire on third floor"
    }

    result = validator.validate(data)

    assert result["requires_review"] is False
    assert result["confidence_score"] == 100


def test_null_fields():
    validator = ExtractionValidator()

    data = {
        "location": None,
        "time": None,
        "severity": None,
        "description": None
    }

    result = validator.validate(data)

    assert result["requires_review"] is True


def test_placeholder_fields():
    validator = ExtractionValidator()

    data = {
        "location": "-1",
        "time": "-1",
        "severity": "-1",
        "description": "-1"
    }

    result = validator.validate(data)

    assert result["requires_review"] is True

def test_weighted_confidence_score():
    validator = ExtractionValidator()

    data = {
        "location": "",
        "time": "5 PM",
        "severity": "",
        "description": "Fire on third floor"
    }

    result = validator.validate(data)

    assert result["confidence_score"] == 40
    assert result["requires_review"] is True