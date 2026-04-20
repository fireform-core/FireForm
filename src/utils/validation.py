def requires_review(data: dict, required_fields: list):
    for field in required_fields:
        value = data.get(field)

        if value is None:
            return True

        if isinstance(value, str) and value.strip() in ["", "-1"]:
            return True

    return False