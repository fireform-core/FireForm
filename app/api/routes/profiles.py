from sqlmodel import select
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.api.deps import get_db
from app.models.models import Profile
from app.api.schemas.profiles import ProfileCreate, ProfileUpdate, ProfileResponse

router = APIRouter()

@router.post("/", response_model=ProfileResponse, status_code=201)
def create_profile(profile: ProfileCreate, db: Session = Depends(get_db)):
    db_profile = Profile(**profile.model_dump())
    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)
    return db_profile

@router.get("/{profile_id}", response_model=ProfileResponse)
def get_profile(profile_id: UUID, db: Session = Depends(get_db)):
    db_profile = db.exec(select(Profile).where(Profile.profile_id == profile_id)).first()
    if not db_profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return db_profile

@router.patch("/{profile_id}", response_model=ProfileResponse)
def update_profile(profile_id: UUID, profile_update: ProfileUpdate, db: Session = Depends(get_db)):
    db_profile = db.query(Profile).filter(Profile.profile_id == profile_id).first()
    if not db_profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    update_data = profile_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_profile, key, value)
        
    db.commit()
    db.refresh(db_profile)
    return db_profile