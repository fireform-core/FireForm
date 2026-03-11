from fastapi import APIRouter
from typing import List, Dict
from src.profiles import ProfileLoader

router = APIRouter(prefix="/profiles", tags=["profiles"])

@router.get("/", response_model=List[str])
def list_profiles():
    """
    List all available department profiles.
    
    Returns:
        List of profile names (e.g., ['fire_department', 'police_report', 'ems_medical'])
    """
    return ProfileLoader.list_profiles()


@router.get("/{profile_name}", response_model=Dict)
def get_profile(profile_name: str):
    """
    Get detailed information about a specific profile.
    
    Args:
        profile_name: Name of the profile (e.g., 'fire_department')
    
    Returns:
        Complete profile configuration including fields and metadata
    """
    try:
        return ProfileLoader.load_profile(profile_name)
    except FileNotFoundError as e:
        from api.errors.base import AppError
        raise AppError(str(e), status_code=404)


@router.get("/{profile_name}/info", response_model=Dict)
def get_profile_info(profile_name: str):
    """
    Get metadata about a profile without the full field mapping.
    
    Args:
        profile_name: Name of the profile
    
    Returns:
        Dictionary with department, description, and example_transcript
    """
    try:
        return ProfileLoader.get_profile_info(profile_name)
    except FileNotFoundError as e:
        from api.errors.base import AppError
        raise AppError(str(e), status_code=404)
