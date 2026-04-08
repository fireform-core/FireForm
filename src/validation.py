def validate_extracted_data(data: dict) -> bool:
    """
    Basic validation for extracted form data.
    Ensures required fields are present and non-empty.
    """

    required_fields = ["patient_name", "age", "diagnosis"]

    for field in required_fields:
        if field not in data or not data[field]:
            return False

    return True
