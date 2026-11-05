from pydantic import BaseModel, Field, ConfigDict, field_validator
from uuid import UUID
from datetime import datetime

class ProfileBase(BaseModel):
    name: str = Field(..., description="Name of the person filling the form")
    profession: str = Field(..., description="Profession of the person")
    role: str = Field(..., description="Role of the person")
    description: str | None = Field(None, description="Optional profile description")
    custom_fields: dict | None = Field(default_factory=dict, description="Extensible fields")

class ProfileCreate(ProfileBase):
    pass

class ProfileUpdate(ProfileBase):
    name: str | None = None
    profession: str | None = None
    role: str | None = None

    # Leaving a field out keeps it, but these columns are NOT NULL, so an
    # explicit null is rejected here instead of failing on commit.
    @field_validator("name", "profession", "role")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("cannot be null")
        return value

class ProfileResponse(ProfileBase):
    profile_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
