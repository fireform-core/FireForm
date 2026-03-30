import pytest
import json
from fastapi.testclient import TestClient


class TestDataLake:

    def test_extract_creates_incident(self, client, db_session):
        """Extracting creates a new incident record in data lake."""
        response = client.post("/incidents/extract", params={
            "input_text": "Officer John Smith badge EMP-001 responding to structure fire at 742 Evergreen Terrace on March 29 2026",
            "incident_id": "INC-TEST-001"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["incident_id"] == "INC-TEST-001"
        assert data["status"] == "created"
        assert data["fields_extracted"] > 0

    def test_get_incident(self, client, db_session):
        """Can retrieve stored incident data."""
        # Create first
        client.post("/incidents/extract", params={
            "input_text": "John Smith EMP-001 fire department March 29 2026",
            "incident_id": "INC-TEST-002"
        })
        # Then retrieve
        response = client.get("/incidents/INC-TEST-002")
        assert response.status_code == 200
        data = response.json()
        assert data["incident_id"] == "INC-TEST-002"
        assert isinstance(data["master_json"], dict)

    def test_get_nonexistent_incident_returns_404(self, client):
        """404 for unknown incident ID."""
        response = client.get("/incidents/INC-NONEXISTENT-999")
        assert response.status_code == 404

    def test_merge_adds_to_existing_incident(self, client, db_session):
        """Second extraction merges into existing incident."""
        # First officer
        client.post("/incidents/extract", params={
            "input_text": "Officer Smith badge EMP-001",
            "incident_id": "INC-TEST-003"
        })
        # Second officer adds more data
        response = client.post("/incidents/extract", params={
            "input_text": "Location is 742 Evergreen Terrace, 2 victims",
            "incident_id": "INC-TEST-003"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "merged"

    def test_list_incidents(self, client, db_session):
        """Can list all incidents."""
        client.post("/incidents/extract", params={
            "input_text": "Test incident data",
            "incident_id": "INC-TEST-LIST"
        })
        response = client.get("/incidents")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_generate_returns_404_for_missing_incident(self, client):
        """Generate returns 404 when incident not in data lake."""
        response = client.post("/incidents/INC-MISSING/generate/1")
        assert response.status_code == 404

    def test_generate_returns_404_for_missing_template(self, client, db_session):
        """Generate returns 404 when template not found."""
        client.post("/incidents/extract", params={
            "input_text": "Test incident",
            "incident_id": "INC-TEST-GEN"
        })
        response = client.post("/incidents/INC-TEST-GEN/generate/99999")
        assert response.status_code == 404