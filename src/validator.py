from typing import Any

# Minimum required fields for a valid incident report.
# Extend this tuple to enforce additional fields across the pipeline.
INCIDENT_REQUIRED_FIELDS: tuple[str, ...] = ("incident_type", "location", "time")


def validate_incident(
    data: Any,
    required_fields: tuple[str, ...] = INCIDENT_REQUIRED_FIELDS,
) -> list[str]:
    """
    Validates structured incident data at the pipeline input boundary.

    This gate runs before extracted data is written to any PDF form, ensuring
    that the minimum required incident fields are present and meaningful.

    This is an *input-side* validator — it checks logical completeness of the
    incident dict produced by LLM extraction. It is distinct from LLM output
    schema validation (see issue #114), which verifies type correctness and
    hallucination confidence of individual extracted values.

    Pipeline position::

        raw text → LLM.main_loop() → [validate_incident()] → Filler → PDF

    Args:
        data: The incident data dict to validate. Must be a plain ``dict``.
        required_fields: Tuple of field names that must be present and
            non-empty. Defaults to ``INCIDENT_REQUIRED_FIELDS``.

    Returns:
        A list of human-readable validation error strings.
        Returns an empty list when all checks pass.

    Examples:
        >>> validate_incident({"incident_type": "Fire", "location": "", "time": None})
        ['Field cannot be empty: location', 'Field cannot be empty: time']

        >>> validate_incident({"incident_type": "Fire", "location": "HQ", "time": "09:00"})
        []
    """
    if not isinstance(data, dict):
        return ["Input data must be a dictionary."]

    errors: list[str] = []

    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")
            continue

        value = data[field]
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"Field cannot be empty: {field}")

    return errors
