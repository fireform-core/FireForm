from pydantic import BaseModel, ValidationError
from typing import Optional


class ExtractionSchema(BaseModel):
    name: Optional[str]
    location: Optional[str]
    date: Optional[str]
    incident_type: Optional[str]
    description: Optional[str]

    class Config:
        extra = "allow"


def validate_extraction(data: dict):
    try:
        validated = ExtractionSchema(**data)
        return validated.dict(), None
    except ValidationError as e:
        formatted_errors = []

        for err in e.errors():
            formatted_errors.append({
                "field": err.get("loc", ["unknown"])[0],
                "issue": err.get("msg", "Invalid value")
            })

        return data, formatted_errors