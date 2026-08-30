"""Tests for PATCH /api/v1/extract/{extract_id}.

The review-screen write path: a merge patch lands on the contract document
held by the incident row, the promoted analytics columns are recomputed from
it, and every real change is appended to the corrections trail.
"""

from datetime import datetime, timezone
from uuid import uuid4

from app.api.schemas.enums import ExtractionStatus, InputStatus, InputType, ReportStatus
from app.db.repositories import (
    create_extraction,
    create_incident,
    create_input,
    get_extraction,
    get_incident,
)
from app.api.schemas.incident_contract import IncidentContract
from app.models import Extraction, Incident, Input
from app.services.extraction_review import merge_patch, patch_paths, unknown_paths

URL = "/api/v1/extract"
MERGE_PATCH = {"Content-Type": "application/merge-patch+json"}

_CONTRACT = {
    "schema_version": "1.1.0",
    "schema_name": "fireform_incident_contract",
    "incident": {"name": "Bear Creek Wildfire"},
    "location": {"city": "Reno", "state": "NV", "country": "US"},
    "casualties": {"total_civilian_injuries": 1, "total_responder_injuries": 0},
    "losses": {"property_loss": {"amount": 10000, "currency": "USD"}},
    "fire": {"cause_certainty": "suspected"},
}


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _seed(
    db,
    contract=None,
    extraction_status=ExtractionStatus.completed,
    report_status=ReportStatus.draft,
) -> tuple[Extraction, Incident]:
    now = datetime.now(timezone.utc)
    inp = create_input(
        db,
        Input(
            input_type=InputType.text,
            status=InputStatus.ready,
            transcript="Structure fire at 42 Oak St, one civilian injury.",
            created_at=now,
            updated_at=now,
        ),
    )
    extraction = create_extraction(
        db,
        Extraction(
            input_id=inp.input_id,
            status=extraction_status,
            started_at=now,
            completed_at=now if extraction_status == ExtractionStatus.completed else None,
            model_used="qwen2.5:1.5b",
        ),
    )
    incident = create_incident(
        db,
        Incident(
            extract_id=extraction.extract_id,
            status=report_status,
            incident_contract=_CONTRACT if contract is None else contract,
        ),
    )
    return extraction, incident


def _patch(client, extract_id, body):
    return client.patch(f"{URL}/{extract_id}", json=body, headers=MERGE_PATCH)


# ---------------------------------------------------------------------------
# The merge itself
# ---------------------------------------------------------------------------

class TestMergePatch:

    def test_nested_keys_merge_not_replace(self):
        target = {"losses": {"property_loss": {"amount": 1, "currency": "USD"}}}
        merged = merge_patch(target, {"losses": {"property_loss": {"amount": 2}}})
        assert merged["losses"]["property_loss"] == {"amount": 2, "currency": "USD"}

    def test_null_deletes_the_key(self):
        merged = merge_patch({"a": 1, "b": 2}, {"b": None})
        assert merged == {"a": 1}

    def test_null_for_absent_key_is_a_no_op(self):
        assert merge_patch({"a": 1}, {"b": None}) == {"a": 1}

    def test_list_is_replaced_whole(self):
        merged = merge_patch({"units": [{"id": "E1"}, {"id": "E2"}]}, {"units": [{"id": "E3"}]})
        assert merged["units"] == [{"id": "E3"}]

    def test_target_is_not_mutated(self):
        target = {"incident": {"name": "old"}}
        merge_patch(target, {"incident": {"name": "new"}})
        assert target["incident"]["name"] == "old"

    def test_patch_paths_walks_to_leaves(self):
        paths = dict(patch_paths({"losses": {"property_loss": {"amount": 250000}}, "a": None}))
        assert paths == {"losses.property_loss.amount": 250000, "a": None}

    def test_unknown_paths_reports_dotted_path(self):
        assert unknown_paths({"losses": {"nope": 1}}, IncidentContract) == ["losses.nope"]

    def test_custom_fields_keys_are_open(self):
        patch = {"custom_fields": {"state_texas.marshal_signature_name": "A. Ruiz"}}
        assert unknown_paths(patch, IncidentContract) == []


# ---------------------------------------------------------------------------
# PATCH /api/v1/extract/{extract_id}
# ---------------------------------------------------------------------------

class TestUpdateExtraction:

    def test_200_applies_the_correction(self, client, db):
        extraction, incident = _seed(db)
        resp = _patch(
            client,
            extraction.extract_id,
            {"losses": {"property_loss": {"amount": 250000}}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["incident_id"] == str(incident.incident_id)
        loss = body["incident_contract"]["losses"]["property_loss"]
        # The untouched sibling survives the merge.
        assert loss == {"amount": 250000, "currency": "USD"}

    def test_200_writes_the_document_to_the_incident_row(self, client, db):
        extraction, incident = _seed(db)
        _patch(client, extraction.extract_id, {"incident": {"name": "Bear Creek Fire"}})
        db.expire_all()
        stored = get_incident(db, incident.incident_id)
        assert stored.incident_contract["incident"]["name"] == "Bear Creek Fire"

    def test_200_recomputes_promoted_columns(self, client, db):
        extraction, incident = _seed(db)
        _patch(
            client,
            extraction.extract_id,
            {
                "casualties": {"total_responder_injuries": 2},
                "losses": {"property_loss": {"amount": 250000}},
                "location": {"city": "Sparks"},
            },
        )
        db.expire_all()
        stored = get_incident(db, incident.incident_id)
        assert stored.responder_injuries == 2
        assert stored.total_loss_amount == 250000
        assert stored.total_loss_currency == "USD"
        assert stored.city == "Sparks"

    def test_200_null_deletes_a_field(self, client, db):
        extraction, incident = _seed(db)
        resp = _patch(client, extraction.extract_id, {"fire": {"cause_certainty": None}})
        assert resp.status_code == 200
        assert resp.json()["incident_contract"]["fire"]["cause_certainty"] is None
        # The stored document drops the key outright, per RFC 7396. The response
        # still carries it as null because the contract model serializes every
        # field, the same way GET does.
        db.expire_all()
        stored = get_incident(db, incident.incident_id)
        assert "cause_certainty" not in stored.incident_contract.get("fire", {})

    def test_200_delete_clears_the_promoted_column(self, client, db):
        extraction, incident = _seed(db)
        _patch(client, extraction.extract_id, {"losses": {"property_loss": None}})
        db.expire_all()
        stored = get_incident(db, incident.incident_id)
        assert stored.total_loss_amount is None
        assert stored.total_loss_currency is None

    def test_200_records_the_audit_trail(self, client, db):
        extraction, _ = _seed(db)
        resp = _patch(
            client,
            extraction.extract_id,
            {"casualties": {"total_responder_injuries": 2}},
        )
        corrections = resp.json()["corrections"]
        assert len(corrections) == 1
        entry = corrections[0]
        assert entry["field_path"] == "casualties.total_responder_injuries"
        assert entry["original_value"] == 0
        assert entry["corrected_value"] == 2
        assert entry["corrected_at"] is not None

    def test_200_audit_trail_records_a_delete(self, client, db):
        extraction, _ = _seed(db)
        resp = _patch(client, extraction.extract_id, {"fire": {"cause_certainty": None}})
        entry = resp.json()["corrections"][0]
        assert entry["field_path"] == "fire.cause_certainty"
        assert entry["original_value"] == "suspected"
        assert entry["corrected_value"] is None

    def test_200_audit_trail_appends_across_calls(self, client, db):
        extraction, _ = _seed(db)
        _patch(client, extraction.extract_id, {"incident": {"name": "First"}})
        resp = _patch(client, extraction.extract_id, {"incident": {"name": "Second"}})
        db.expire_all()
        stored = get_extraction(db, extraction.extract_id)
        assert len(stored.corrections) == 2
        assert [c["corrected_value"] for c in resp.json()["corrections"]] == ["First", "Second"]

    def test_200_unchanged_value_is_not_recorded(self, client, db):
        extraction, _ = _seed(db)
        resp = _patch(client, extraction.extract_id, {"incident": {"name": "Bear Creek Wildfire"}})
        assert resp.status_code == 200
        assert not resp.json()["corrections"]

    def test_200_adds_a_custom_field(self, client, db):
        extraction, _ = _seed(db)
        resp = _patch(
            client,
            extraction.extract_id,
            {"custom_fields": {"state_texas.marshal_signature_name": "A. Ruiz"}},
        )
        assert resp.status_code == 200
        custom = resp.json()["incident_contract"]["custom_fields"]
        assert custom["state_texas.marshal_signature_name"] == "A. Ruiz"

    def test_404_extraction_not_found(self, client, db):
        resp = _patch(client, uuid4(), {"incident": {"name": "x"}})
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "EXTRACT_NOT_FOUND"

    def test_409_extraction_still_processing(self, client, db):
        extraction, _ = _seed(db, extraction_status=ExtractionStatus.processing)
        resp = _patch(client, extraction.extract_id, {"incident": {"name": "x"}})
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "EXTRACT_NOT_COMPLETED"

    def test_409_locked_after_submission(self, client, db):
        extraction, incident = _seed(db, report_status=ReportStatus.submitted)
        resp = _patch(client, extraction.extract_id, {"incident": {"name": "x"}})
        assert resp.status_code == 409
        body = resp.json()
        assert body["error_code"] == "EXTRACT_LOCKED"
        assert body["detail"]["report_status"] == "submitted"
        db.expire_all()
        stored = get_incident(db, incident.incident_id)
        assert stored.incident_contract["incident"]["name"] == "Bear Creek Wildfire"

    def test_422_invalid_enum_value(self, client, db):
        extraction, _ = _seed(db)
        resp = _patch(client, extraction.extract_id, {"fire": {"cause_certainty": "maybe"}})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error_code"] == "VALIDATION_ERROR"
        assert body["validation_errors"][0]["field"] == "fire.cause_certainty"
        assert body["validation_errors"][0]["value"] == "maybe"

    def test_422_unknown_field_path(self, client, db):
        extraction, _ = _seed(db)
        resp = _patch(client, extraction.extract_id, {"losses": {"imaginary_loss": 5}})
        assert resp.status_code == 422
        assert resp.json()["validation_errors"][0]["field"] == "losses.imaginary_loss"

    def test_422_wrong_type_for_a_field(self, client, db):
        extraction, _ = _seed(db)
        resp = _patch(
            client,
            extraction.extract_id,
            {"casualties": {"total_responder_injuries": "two"}},
        )
        assert resp.status_code == 422
        assert resp.json()["validation_errors"][0]["field"] == (
            "casualties.total_responder_injuries"
        )

    def test_422_leaves_the_document_untouched(self, client, db):
        extraction, incident = _seed(db)
        _patch(client, extraction.extract_id, {"fire": {"cause_certainty": "maybe"}})
        db.expire_all()
        stored = get_incident(db, incident.incident_id)
        assert stored.incident_contract["fire"]["cause_certainty"] == "suspected"
        assert get_extraction(db, extraction.extract_id).corrections is None

    def test_422_non_json_body_does_not_500(self, client, db):
        extraction, _ = _seed(db)
        resp = client.patch(
            f"{URL}/{extraction.extract_id}",
            content=b"not json",
            headers={"Content-Type": "text/plain"},
        )
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "VALIDATION_ERROR"
