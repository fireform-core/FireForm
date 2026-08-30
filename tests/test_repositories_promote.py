"""Tests for the extraction/incident repositories and the analytics recompute.

Repositories run against the shared in-memory SQLite engine from conftest.py.
`promote` is a pure function and is tested directly over an empty and a full
contract.
"""

from app.db import repositories as repo
from app.models import Input, Extraction
from app.api.schemas.enums import InputType, ExtractionStatus, ReportStatus
from app.services.incidents import promote, PROMOTED_COLUMNS


# ---------------------------------------------------------------------------
# Repository paths
# ---------------------------------------------------------------------------

def _make_input(db):
    return repo.create_input(db, Input(input_type=InputType.text, transcript="x"))


def _make_extraction(db, input_id):
    return repo.create_extraction(db, Extraction(input_id=input_id))


class TestExtractionRepository:

    def test_create_and_get_extraction(self, db):
        inp = _make_input(db)
        created = _make_extraction(db, inp.input_id)
        assert created.extract_id is not None

        fetched = repo.get_extraction(db, created.extract_id)
        assert fetched is not None
        assert fetched.extract_id == created.extract_id
        assert fetched.input_id == inp.input_id
        assert fetched.status == ExtractionStatus.processing

    def test_get_extraction_unknown_returns_none(self, db):
        from uuid import uuid4
        assert repo.get_extraction(db, uuid4()) is None

    def test_update_extraction_persists_changes(self, db):
        inp = _make_input(db)
        extraction = _make_extraction(db, inp.input_id)

        extraction.status = ExtractionStatus.completed
        extraction.model_used = "llama3:8b"
        repo.update_extraction(db, extraction)

        reloaded = repo.get_extraction(db, extraction.extract_id)
        assert reloaded.status == ExtractionStatus.completed
        assert reloaded.model_used == "llama3:8b"


class TestIncidentRepository:

    def test_create_draft_incident_links_to_extraction(self, db):
        inp = _make_input(db)
        extraction = _make_extraction(db, inp.input_id)

        incident = repo.create_draft_incident(db, extraction.extract_id)
        assert incident.incident_id is not None
        assert incident.extract_id == extraction.extract_id
        assert incident.status == ReportStatus.draft

    def test_get_incident_and_by_extract(self, db):
        inp = _make_input(db)
        extraction = _make_extraction(db, inp.input_id)
        incident = repo.create_draft_incident(db, extraction.extract_id)

        assert repo.get_incident(db, incident.incident_id).incident_id == incident.incident_id
        by_extract = repo.get_incident_by_extract(db, extraction.extract_id)
        assert by_extract.incident_id == incident.incident_id

    def test_get_incident_unknown_returns_none(self, db):
        from uuid import uuid4
        assert repo.get_incident(db, uuid4()) is None

    def test_update_incident_persists_promoted_columns(self, db):
        inp = _make_input(db)
        extraction = _make_extraction(db, inp.input_id)
        incident = repo.create_draft_incident(db, extraction.extract_id)

        incident.incident_number = "CA-SQF-2024-0421"
        incident.city = "Springfield"
        incident.civilian_injuries = 3
        repo.update_incident(db, incident)

        reloaded = repo.get_incident(db, incident.incident_id)
        assert reloaded.incident_number == "CA-SQF-2024-0421"
        assert reloaded.city == "Springfield"
        assert reloaded.civilian_injuries == 3


# ---------------------------------------------------------------------------
# promote
# ---------------------------------------------------------------------------

class TestPromoteEmptyContract:

    def test_empty_dict_yields_all_none(self):
        result = promote({})
        assert set(result) == set(PROMOTED_COLUMNS)
        assert all(value is None for value in result.values())

    def test_none_contract_yields_all_none(self):
        assert all(value is None for value in promote(None).values())

    def test_partial_contract_only_fills_present_fields(self):
        result = promote({"location": {"city": "Reno", "state": "NV"}})
        assert result["city"] == "Reno"
        assert result["state"] == "NV"
        assert result["country"] is None
        assert result["incident_datetime"] is None


FULL_CONTRACT = {
    "incident": {
        "name": "Bear Creek Wildfire",
        "types": [
            {"primary": False, "category": "ems", "subcategory": "medical_assist"},
            {"primary": True, "category": "fire", "subcategory": "wildland_fire"},
        ],
        "alarm_datetime": "2024-07-10T13:50:00-07:00",
        "start_datetime": "2024-07-10T13:40:00-07:00",
        "first_arrival_datetime": "2024-07-10T13:56:00-07:00",
        "cleared_datetime": "2024-07-10T15:56:00-07:00",
    },
    "dispatch": {"call_received_datetime": "2024-07-10T13:52:00-07:00"},
    "location": {"city": "Reno", "state": "NV", "country": "US"},
    "casualties": {
        "total_civilian_injuries": 2,
        "total_civilian_fatalities": 1,
        "total_responder_injuries": 3,
        "total_responder_fatalities": 0,
    },
    "rescues": [{"person_type": "civilian"}, {"person_type": "civilian"}],
    "evacuation_displacement": {"total_people_evacuated": 40},
    "structure": {"structures_destroyed": 2},
    "wildland": {"area_burned_ha": 12.5},
    "losses": {
        "property_loss": {"amount": 100000, "currency": "USD"},
        "contents_loss": {"amount": 25000, "currency": "USD"},
    },
    "units": [
        {
            "unit_id": "E2",
            "arrived_datetime": "2024-07-10T13:58:00-07:00",
            "dispatched_datetime": "2024-07-10T13:52:00-07:00",
            "enroute_datetime": "2024-07-10T13:53:00-07:00",
        },
        {
            "unit_id": "E1",
            "arrived_datetime": "2024-07-10T13:56:00-07:00",
            "turnout_seconds": 60,
            "travel_seconds": 180,
        },
    ],
}


class TestPromoteFullContract:

    def setup_method(self):
        self.result = promote(FULL_CONTRACT)

    def test_category_from_primary_type(self):
        assert self.result["incident_category"] == "fire"

    def test_name_promoted(self):
        assert self.result["incident_name"] == "Bear Creek Wildfire"

    def test_type_is_the_primary_subcategory(self):
        # Both come off the same entry, so they can never describe two
        # different types: the non-primary ems/medical_assist pair is ignored.
        assert self.result["incident_type"] == "wildland_fire"

    def test_incident_datetime_prefers_alarm(self):
        # Alarm wins over start and dispatch call-received.
        assert self.result["incident_datetime"].isoformat() == "2024-07-10T13:50:00-07:00"

    def test_location_promoted(self):
        assert self.result["city"] == "Reno"
        assert self.result["state"] == "NV"
        assert self.result["country"] == "US"

    def test_casualty_counts_from_totals(self):
        assert self.result["civilian_injuries"] == 2
        assert self.result["civilian_fatalities"] == 1
        assert self.result["responder_injuries"] == 3
        assert self.result["responder_fatalities"] == 0

    def test_people_rescued_is_array_length(self):
        assert self.result["people_rescued"] == 2

    def test_people_evacuated_from_total(self):
        assert self.result["people_evacuated"] == 40

    def test_structures_and_area(self):
        assert self.result["structures_destroyed"] == 2
        assert self.result["area_burned_ha"] == 12.5

    def test_total_loss_is_property_plus_contents(self):
        assert self.result["total_loss_amount"] == 125000
        assert self.result["total_loss_currency"] == "USD"

    def test_call_to_arrival_uses_call_received(self):
        # 13:52 call received -> 13:56 first arrival = 4 minutes.
        assert self.result["call_to_arrival_seconds"] == 240

    def test_on_scene_duration(self):
        # 13:56 first arrival -> 15:56 cleared = 2 hours.
        assert self.result["on_scene_duration_seconds"] == 7200

    def test_first_unit_is_earliest_arrival_with_precomputed_timing(self):
        # E1 arrived first (13:56) and carries precomputed turnout/travel.
        assert self.result["turnout_seconds_first_unit"] == 60
        assert self.result["travel_seconds_first_unit"] == 180


class TestPromoteFallbacks:

    def test_incident_datetime_falls_back_to_start_then_call_received(self):
        start_only = promote({"incident": {"start_datetime": "2024-07-10T13:40:00-07:00"}})
        assert start_only["incident_datetime"].isoformat() == "2024-07-10T13:40:00-07:00"

        dispatch_only = promote({"dispatch": {"call_received_datetime": "2024-07-10T13:52:00-07:00"}})
        assert dispatch_only["incident_datetime"].isoformat() == "2024-07-10T13:52:00-07:00"

    def test_call_to_arrival_falls_back_to_alarm_when_no_call_received(self):
        result = promote({
            "incident": {
                "alarm_datetime": "2024-07-10T13:50:00-07:00",
                "first_arrival_datetime": "2024-07-10T13:56:00-07:00",
            },
        })
        assert result["call_to_arrival_seconds"] == 360

    def test_first_unit_turnout_travel_computed_from_timestamps(self):
        result = promote({
            "units": [{
                "unit_id": "E7",
                "arrived_datetime": "2024-07-10T13:58:00-07:00",
                "dispatched_datetime": "2024-07-10T13:52:00-07:00",
                "enroute_datetime": "2024-07-10T13:53:00-07:00",
            }],
        })
        assert result["turnout_seconds_first_unit"] == 60   # 13:52 -> 13:53
        assert result["travel_seconds_first_unit"] == 300   # 13:53 -> 13:58

    def test_negative_interval_is_none(self):
        result = promote({
            "incident": {
                "first_arrival_datetime": "2024-07-10T14:00:00-07:00",
                "cleared_datetime": "2024-07-10T13:00:00-07:00",
            },
        })
        assert result["on_scene_duration_seconds"] is None

    def test_single_loss_side_still_totals(self):
        result = promote({"losses": {"property_loss": {"amount": 5000, "currency": "GBP"}}})
        assert result["total_loss_amount"] == 5000
        assert result["total_loss_currency"] == "GBP"

    def test_unparseable_datetime_is_none(self):
        assert promote({"incident": {"alarm_datetime": "not a date"}})["incident_datetime"] is None
