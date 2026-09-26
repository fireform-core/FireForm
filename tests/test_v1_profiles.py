from fastapi.testclient import TestClient
from sqlmodel import Session, select
from uuid import UUID

from app.models.models import Profile
from app.services.llm import append_profile_context

def test_profile_crud(client: TestClient, db: Session):
    # 1. TEST CREATE (POST)
    payload = {
        "name": "Jane Doe",
        "profession": "Firefighter",
        "role": "Captain",
        "description": "Station 42 commander",
        "custom_fields": {"badge_number": "12345"}
    }
    
    response = client.post("/api/v1/profiles/", json=payload)
    if response.status_code == 404:  
        response = client.post("/profiles/", json=payload)
        
    assert response.status_code == 201
    profile_data = response.json()
    profile_id = profile_data["profile_id"]
    assert profile_data["name"] == "Jane Doe"
    
    # 2. TEST READ (GET)
    get_url = f"/api/v1/profiles/{profile_id}" if "/api/v1/" in response.url.path else f"/profiles/{profile_id}"
    response = client.get(get_url)
    assert response.status_code == 200
    assert response.json()["role"] == "Captain"
    
    # 3. TEST UPDATE (PATCH)
    update_payload = {
        "role": "Battalion Chief",
        "description": "Promoted to Battalion Chief"
    }
    response = client.patch(get_url, json=update_payload)
    assert response.status_code == 200
    updated_data = response.json()
    assert updated_data["role"] == "Battalion Chief"
    assert updated_data["description"] == "Promoted to Battalion Chief"
    
    # 4. Verify it actually saved to the database (UUID cast fixes the SQLite string quirk)
    db_profile = db.exec(select(Profile).where(Profile.profile_id == UUID(profile_id))).first()
    assert db_profile.role == "Battalion Chief"


def test_append_profile_context():
    """Unit test to ensure the LLM prompt is correctly formatted with profile data."""
    base_prompt = "Extract the incident details."
    
    # 1. Test fallback when no profile is provided
    assert append_profile_context(base_prompt, None) == base_prompt
    
    # 2. Test context injection with a valid profile
    mock_profile = Profile(
        name="John Smith",
        profession="Paramedic",
        role="Lead Medic",
        description="Night shift supervisor",
        custom_fields={"certification": "ALS", "unit": "Medic 9"}
    )
    
    result_prompt = append_profile_context(base_prompt, mock_profile)
    
    # Verify core fields were injected
    assert "Name: John Smith" in result_prompt
    assert "Profession: Paramedic" in result_prompt
    assert "Role: Lead Medic" in result_prompt
    
    # Verify custom fields were injected and capitalized properly
    assert "Certification: ALS" in result_prompt
    assert "Unit: Medic 9" in result_prompt
    
    # Verify the original prompt is still at the end
    assert result_prompt.endswith(base_prompt)