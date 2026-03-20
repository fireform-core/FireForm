from src.schema import REQUIRED_FIELDS

def validate_extracted_data(data: dict) -> bool:
    for field, field_type in REQUIRED_FIELDS.items():
        if field not in data:
            return False
        if not isinstance(data[field], field_type):
            return False
        if data[field] in ["", None]:
            return False
    return True
