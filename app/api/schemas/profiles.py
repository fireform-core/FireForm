from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional, Dict, Any
from datetime import datetime

class ProfileBase(BaseModel):
    name: str = Field(..., description="Name of the person filling the form")
    profession: str = Field(..., description="Profession of the person")
    role: str = Field(..., description="Role of the person")
    description: Optional[str] = Field(None, description="Optional profile description")
    custom_fields: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Extensible fields")

class ProfileCreate(ProfileBase):
    pass

class ProfileUpdate(ProfileBase):
    name: Optional[str] = None
    profession: Optional[str] = None
    role: Optional[str] = None

class ProfileResponse(ProfileBase):
    profile_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True