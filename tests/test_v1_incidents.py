"""Tests for the five incident endpoints (contracts/path/incidents.yaml).

Rows are seeded directly rather than driven through extraction, so these cover
the CRUD surface itself: finalizing the draft, list filtering/paging/sorting,
the full record shape, metadata updates, and soft delete.

The submitted-status lock is deliberately not built yet, so the tests here
assert the current behaviour: status moves freely and a submitted incident is
still editable.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.api.schemas.enums import (
    ExtractionStatus,
    FormStatus,
    IncidentCategory,
    InputStatus,
    InputType,
    ReportStatus,
)
from app.core.config import API_PREFIX
from app.db.repositories import (
    create_extraction,
    create_form_template,
    create_generated_form,
    create_incident,
    create_input,
)
from app.models import Extraction, Form, FormTemplate, Incident, Input

INCIDENTS_URL = f"{API_PREFIX}/incidents"

_CONTRACT = {
    "schema_version": "1.1.0",
    "schema_name": "fireform_incident_contract",
    "incident": {
        "name": "Bear Creek Wildfire",
        "alarm_datetime": "2024-07-10T13:52:00-07:00",
        "types": [{"primary": True, "category": "fire", "subcategory": "wildland_fire"}],
    },
    "location": {"city": "Reno", "state": "NV", "country": "US"},
    "casualties": {"total_civilian_injuries": 2},
}


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _extraction(db, status=ExtractionStatus.completed) -> Extraction:
    now = datetime.now(timezone.utc)
    inp = create_input(
        db,
        Input(
            input_type=InputType.text,
            status=InputStatus.ready,
            transcript="Wildfire off Bear Creek, two injured.",
            created_at=now,
            updated_at=now,
        ),
    )
    return create_extraction(
        db,
        Extraction(
            input_id=inp.input_id,
            status=status,
            started_at=now,
            completed_at=now if status == ExtractionStatus.completed else None,
        ),
    )


def _incident(db, extraction=None, **kwargs) -> Incident:
    """A draft incident with the promoted columns already filled, as the
    extraction worker would leave it."""
    extraction = extraction or _extraction(db)
    defaults = dict(
        extract_id=extraction.extract_id,
        status=ReportStatus.draft,
        incident_contract=_CONTRACT,
        incident_name="Bear Creek Wildfire",
        incident_type="wildland_fire",
        incident_category=IncidentCategory.fire,
        incident_datetime=datetime(2024, 7, 10, 13, 52),
        city="Reno",
        state="NV",
        country="US",
        civilian_injuries=2,
    )
    defaults.update(kwargs)
    return create_incident(db, Incident(**defaults))


def _form(db, incident, form_type="neris") -> Form:
    template = create_form_template(
        db,
        FormTemplate(
            form_type=f"{form_type}-{uuid4().hex[:6]}",
            display_name=form_type.upper(),
            fields=[],
        ),
    )
    return create_generated_form(
        db,
        Form(
            form_type=form_type,
            status=FormStatus.completed,
            template_id=template.template_id,
            incident_id=incident.incident_id,
        ),
    )


# ---------------------------------------------------------------------------
# POST /incidents
# ---------------------------------------------------------------------------

class TestCreateIncident:
    def test_finalizes_the_existing_draft(self, client, db):
        incident = _incident(db)
        body = {
            "extract_id": str(incident.extract_id),
            "incident_number": "CA-SQF-2024-0421",
            "tags": ["wildland", "mutual_aid"],
        }
        response = client.post(INCIDENTS_URL, json=body)

        assert response.status_code == 201
        payload = response.json()
        # The same row, not a second one.
        assert payload["incident_id"] == str(incident.incident_id)
        assert payload["incident_number"] == "CA-SQF-2024-0421"
        assert payload["tags"] == ["wildland", "mutual_aid"]
        assert payload["status"] == "draft"

    def test_promoted_fields_are_returned(self, client, db):
        incident = _incident(db)
        payload = client.post(
            INCIDENTS_URL, json={"extract_id": str(incident.extract_id)}
        ).json()

        assert payload["incident_name"] == "Bear Creek Wildfire"
        assert payload["incident_type"] == "wildland_fire"
        assert payload["incident_category"] == "fire"
        assert payload["analytics"]["city"] == "Reno"
        assert payload["analytics"]["civilian_injuries"] == 2

    def test_is_idempotent(self, client, db):
        incident = _incident(db)
        body = {"extract_id": str(incident.extract_id), "incident_number": "CA-1"}

        first = client.post(INCIDENTS_URL, json=body)
        second = client.post(INCIDENTS_URL, json=body)

        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["incident_id"] == second.json()["incident_id"]

    def test_omitted_fields_leave_the_draft_alone(self, client, db):
        incident = _incident(db, incident_number="CA-1", tags=["existing"])
        payload = client.post(
            INCIDENTS_URL, json={"extract_id": str(incident.extract_id)}
        ).json()

        assert payload["incident_number"] == "CA-1"
        assert payload["tags"] == ["existing"]

    def test_unknown_extract_id_is_404(self, client, db):
        response = client.post(INCIDENTS_URL, json={"extract_id": str(uuid4())})

        assert response.status_code == 404
        assert response.json()["error_code"] == "EXTRACT_NOT_FOUND"

    def test_extraction_without_a_draft_is_409(self, client, db):
        extraction = _extraction(db, status=ExtractionStatus.processing)
        response = client.post(
            INCIDENTS_URL, json={"extract_id": str(extraction.extract_id)}
        )

        assert response.status_code == 409
        assert response.json()["error_code"] == "EXTRACTION_NOT_COMPLETED"

    def test_duplicate_incident_number_is_409(self, client, db):
        _incident(db, incident_number="CA-SQF-2024-0421")
        other = _incident(db)

        response = client.post(
            INCIDENTS_URL,
            json={
                "extract_id": str(other.extract_id),
                "incident_number": "CA-SQF-2024-0421",
            },
        )

        assert response.status_code == 409
        assert response.json()["error_code"] == "DUPLICATE_INCIDENT_NUMBER"

    def test_a_deleted_incident_frees_its_number(self, client, db):
        _incident(
            db,
            incident_number="CA-SQF-2024-0421",
            deleted_at=datetime.now(timezone.utc),
        )
        other = _incident(db)

        response = client.post(
            INCIDENTS_URL,
            json={
                "extract_id": str(other.extract_id),
                "incident_number": "CA-SQF-2024-0421",
            },
        )

        assert response.status_code == 201


# ---------------------------------------------------------------------------
# GET /incidents
# ---------------------------------------------------------------------------

class TestListIncidents:
    def test_returns_rows_and_pagination(self, client, db):
        incident = _incident(db)
        _form(db, incident)
        _form(db, incident)

        payload = client.get(INCIDENTS_URL).json()

        assert payload["pagination"] == {
            "total": 1,
            "page": 1,
            "per_page": 20,
            "total_pages": 1,
            "has_next": False,
            "has_prev": False,
        }
        row = payload["data"][0]
        assert row["incident_name"] == "Bear Creek Wildfire"
        assert row["incident_type"] == "wildland_fire"
        assert row["incident_category"] == "fire"
        assert row["city"] == "Reno"
        assert row["forms_count"] == 2

    def test_forms_count_is_zero_without_forms(self, client, db):
        _incident(db)
        assert client.get(INCIDENTS_URL).json()["data"][0]["forms_count"] == 0

    def test_excludes_soft_deleted(self, client, db):
        _incident(db)
        _incident(db, deleted_at=datetime.now(timezone.utc))

        payload = client.get(INCIDENTS_URL).json()

        assert payload["pagination"]["total"] == 1
        assert len(payload["data"]) == 1

    def test_filters_by_status_and_category(self, client, db):
        _incident(db, status=ReportStatus.approved)
        _incident(db, status=ReportStatus.draft)
        _incident(db, incident_category=IncidentCategory.ems)

        approved = client.get(INCIDENTS_URL, params={"status": "approved"}).json()
        ems = client.get(INCIDENTS_URL, params={"incident_category": "ems"}).json()

        assert approved["pagination"]["total"] == 1
        assert ems["pagination"]["total"] == 1

    def test_date_bounds_are_inclusive(self, client, db):
        _incident(db, incident_datetime=datetime(2024, 7, 9, 23, 0))
        _incident(db, incident_datetime=datetime(2024, 7, 10, 13, 52))
        _incident(db, incident_datetime=datetime(2024, 7, 11, 0, 30))

        payload = client.get(
            INCIDENTS_URL, params={"date_from": "2024-07-10", "date_to": "2024-07-10"}
        ).json()

        assert payload["pagination"]["total"] == 1
        assert payload["data"][0]["incident_datetime"].startswith("2024-07-10T13:52")

    def test_rows_without_a_datetime_are_dropped_by_a_date_filter(self, client, db):
        _incident(db, incident_datetime=None)

        payload = client.get(INCIDENTS_URL, params={"date_from": "2024-07-10"}).json()

        assert payload["pagination"]["total"] == 0

    def test_sort_order(self, client, db):
        early = datetime(2024, 7, 1, 8, 0)
        late = datetime(2024, 7, 20, 8, 0)
        _incident(db, incident_datetime=early)
        _incident(db, incident_datetime=late)

        desc = client.get(INCIDENTS_URL).json()["data"]
        asc = client.get(INCIDENTS_URL, params={"sort": "date_asc"}).json()["data"]

        assert desc[0]["incident_datetime"].startswith("2024-07-20")
        assert asc[0]["incident_datetime"].startswith("2024-07-01")

    def test_rows_without_a_datetime_sort_last(self, client, db):
        _incident(db, incident_datetime=None)
        _incident(db, incident_datetime=datetime(2024, 7, 1, 8, 0))

        rows = client.get(INCIDENTS_URL).json()["data"]

        assert rows[0]["incident_datetime"] is not None
        assert rows[-1]["incident_datetime"] is None

    def test_paging(self, client, db):
        base = datetime(2024, 7, 1, 8, 0)
        for offset in range(3):
            _incident(db, incident_datetime=base + timedelta(days=offset))

        page_one = client.get(INCIDENTS_URL, params={"per_page": 2}).json()
        page_two = client.get(INCIDENTS_URL, params={"per_page": 2, "page": 2}).json()

        assert page_one["pagination"] == {
            "total": 3,
            "page": 1,
            "per_page": 2,
            "total_pages": 2,
            "has_next": True,
            "has_prev": False,
        }
        assert len(page_one["data"]) == 2
        assert len(page_two["data"]) == 1
        assert page_two["pagination"]["has_next"] is False
        assert page_two["pagination"]["has_prev"] is True

    def test_empty_list(self, client, db):
        payload = client.get(INCIDENTS_URL).json()

        assert payload["data"] == []
        assert payload["pagination"]["total"] == 0
        assert payload["pagination"]["total_pages"] == 0

    def test_reversed_date_range_is_422(self, client, db):
        response = client.get(
            INCIDENTS_URL, params={"date_from": "2024-07-20", "date_to": "2024-07-10"}
        )

        assert response.status_code == 422

    def test_bad_date_format_is_422(self, client, db):
        assert client.get(INCIDENTS_URL, params={"date_from": "15/07/2024"}).status_code == 422

    def test_per_page_over_the_cap_is_422(self, client, db):
        assert client.get(INCIDENTS_URL, params={"per_page": 101}).status_code == 422

    def test_unknown_sort_is_422(self, client, db):
        assert client.get(INCIDENTS_URL, params={"sort": "name_asc"}).status_code == 422


# ---------------------------------------------------------------------------
# GET /incidents/{incident_id}
# ---------------------------------------------------------------------------

class TestGetIncident:
    def test_returns_contract_and_forms(self, client, db):
        incident = _incident(db)
        form = _form(db, incident)

        payload = client.get(f"{INCIDENTS_URL}/{incident.incident_id}").json()

        assert payload["incident_contract"]["incident"]["name"] == "Bear Creek Wildfire"
        assert [f["form_id"] for f in payload["forms"]] == [str(form.form_id)]
        assert [f["form_id"] for f in payload["forms_generated"]] == [str(form.form_id)]

    def test_submission_log_is_empty_by_default(self, client, db):
        incident = _incident(db)
        payload = client.get(f"{INCIDENTS_URL}/{incident.incident_id}").json()

        assert payload["submission_log"] == []

    def test_submission_log_is_read_from_the_contract(self, client, db):
        contract = dict(_CONTRACT)
        contract["submission_log"] = [
            {"form_type": "neris", "submitted_to": "State FMO", "status": "accepted"}
        ]
        incident = _incident(db, incident_contract=contract)

        payload = client.get(f"{INCIDENTS_URL}/{incident.incident_id}").json()

        assert payload["submission_log"][0]["submitted_to"] == "State FMO"

    def test_soft_deleted_is_still_readable(self, client, db):
        incident = _incident(db, deleted_at=datetime.now(timezone.utc))

        response = client.get(f"{INCIDENTS_URL}/{incident.incident_id}")

        assert response.status_code == 200
        assert response.json()["deleted_at"] is not None

    def test_unknown_id_is_404(self, client, db):
        response = client.get(f"{INCIDENTS_URL}/{uuid4()}")

        assert response.status_code == 404
        assert response.json()["error_code"] == "INCIDENT_NOT_FOUND"


# ---------------------------------------------------------------------------
# PATCH /incidents/{incident_id}
# ---------------------------------------------------------------------------

class TestUpdateIncident:
    def test_updates_metadata(self, client, db):
        incident = _incident(db)

        payload = client.patch(
            f"{INCIDENTS_URL}/{incident.incident_id}",
            json={"status": "approved", "tags": ["reviewed"], "notes": "Ready to go."},
        ).json()

        assert payload["status"] == "approved"
        assert payload["tags"] == ["reviewed"]
        assert payload["notes"] == "Ready to go."

    def test_omitted_fields_are_untouched(self, client, db):
        incident = _incident(db, notes="Original note", tags=["wildland"])

        payload = client.patch(
            f"{INCIDENTS_URL}/{incident.incident_id}", json={"status": "under_review"}
        ).json()

        assert payload["notes"] == "Original note"
        assert payload["tags"] == ["wildland"]

    def test_does_not_touch_the_contract(self, client, db):
        incident = _incident(db)

        client.patch(
            f"{INCIDENTS_URL}/{incident.incident_id}", json={"notes": "Checked."}
        )

        db.refresh(incident)
        assert incident.incident_contract == _CONTRACT
        assert incident.incident_name == "Bear Creek Wildfire"

    def test_duplicate_number_is_409(self, client, db):
        _incident(db, incident_number="CA-1")
        target = _incident(db)

        response = client.patch(
            f"{INCIDENTS_URL}/{target.incident_id}", json={"incident_number": "CA-1"}
        )

        assert response.status_code == 409
        assert response.json()["error_code"] == "DUPLICATE_INCIDENT_NUMBER"

    def test_keeping_its_own_number_is_allowed(self, client, db):
        incident = _incident(db, incident_number="CA-1")

        response = client.patch(
            f"{INCIDENTS_URL}/{incident.incident_id}",
            json={"incident_number": "CA-1", "notes": "Same number."},
        )

        assert response.status_code == 200

    def test_submitted_is_still_editable_for_now(self, client, db):
        """The submitted lock is deferred, so this documents current behaviour."""
        incident = _incident(db, status=ReportStatus.submitted)

        response = client.patch(
            f"{INCIDENTS_URL}/{incident.incident_id}", json={"notes": "Late edit."}
        )

        assert response.status_code == 200

    def test_unknown_id_is_404(self, client, db):
        response = client.patch(f"{INCIDENTS_URL}/{uuid4()}", json={"notes": "x"})

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /incidents/{incident_id}
# ---------------------------------------------------------------------------

class TestDeleteIncident:
    def test_soft_deletes(self, client, db):
        incident = _incident(db)

        payload = client.delete(f"{INCIDENTS_URL}/{incident.incident_id}").json()

        assert payload["incident_id"] == str(incident.incident_id)
        assert payload["recoverable"] is True
        assert payload["deleted_at"] is not None

    def test_the_row_survives(self, client, db):
        incident = _incident(db)

        client.delete(f"{INCIDENTS_URL}/{incident.incident_id}")

        db.refresh(incident)
        assert incident.deleted_at is not None
        assert incident.incident_contract == _CONTRACT

    def test_deleting_twice_is_409(self, client, db):
        incident = _incident(db)
        client.delete(f"{INCIDENTS_URL}/{incident.incident_id}")

        response = client.delete(f"{INCIDENTS_URL}/{incident.incident_id}")

        assert response.status_code == 409
        assert response.json()["error_code"] == "ALREADY_DELETED"

    def test_unknown_id_is_404(self, client, db):
        assert client.delete(f"{INCIDENTS_URL}/{uuid4()}").status_code == 404
