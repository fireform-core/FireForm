"""Tests for the read side of the review screen.

GET /api/v1/extract/{extract_id}/readiness answers which registered forms can
be generated from what was extracted, and POST /api/v1/extract/{extract_id}/validate
answers the same question for one template. Both run the same engine, so the
gap rules are tested once on the engine and then confirmed through the routes.
"""

from datetime import datetime, timezone

from app.api.schemas.enums import (
    ExtractionStatus,
    InputStatus,
    InputType,
    ReportStatus,
    TemplateStatus,
)
from app.api.schemas.templates import TemplateField
from app.db.repositories import (
    create_extraction,
    create_form_template,
    create_incident,
    create_input,
)
from app.models import Extraction, FormTemplate, Incident, Input
from app.services.extraction_readiness import (
    gaps_for,
    is_filled,
    resolve,
    warnings_for,
)

URL = "/api/v1/extract"

_CONTRACT = {
    "schema_version": "1.1.0",
    "schema_name": "fireform_incident_contract",
    "incident": {"name": "Bear Creek Wildfire"},
    "location": {"city": "Reno", "state": "NV", "country": "US"},
    "fire": {"cause_certainty": "suspected"},
    "custom_fields": {"state_texas.marshal_signature_name": "A. Ruiz"},
}


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _field(name, source="schema", required=True, **extra) -> dict:
    field = {
        "field_name": name,
        "field_type": "string",
        "source": source,
        "required": required,
    }
    if source == "schema":
        field.setdefault("incident_mapping", "incident.name")
    if source == "static":
        field.setdefault("static_text", "Reno Fire Department")
    if source == "open":
        field.setdefault("description", "Anything the narrative says about it")
    field.update(extra)
    return field


def _template(
    db,
    form_type="state_texas",
    display_name="Texas SFM",
    fields=None,
    status=TemplateStatus.active,
) -> FormTemplate:
    return create_form_template(
        db,
        FormTemplate(
            form_type=form_type,
            display_name=display_name,
            fields=fields if fields is not None else [_field("incident_name")],
            status=status,
        ),
    )


def _seed(
    db,
    contract=None,
    extraction_status=ExtractionStatus.completed,
) -> tuple[Extraction, Incident]:
    now = datetime.now(timezone.utc)
    inp = create_input(
        db,
        Input(
            input_type=InputType.text,
            status=InputStatus.ready,
            transcript="Wildfire off Bear Creek, no injuries.",
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
            status=ReportStatus.draft,
            incident_contract=_CONTRACT if contract is None else contract,
        ),
    )
    return extraction, incident


def _validate(client, extract_id, template_id):
    return client.post(f"{URL}/{extract_id}/validate", json={"template_id": str(template_id)})


# ---------------------------------------------------------------------------
# When a field counts as filled
# ---------------------------------------------------------------------------

class TestIsFilled:

    def test_null_is_a_gap(self):
        assert is_filled(None) is False

    def test_blank_string_is_a_gap(self):
        assert is_filled("") is False
        assert is_filled("   ") is False

    def test_empty_container_is_a_gap(self):
        assert is_filled([]) is False
        assert is_filled({}) is False

    def test_zero_and_false_are_values(self):
        assert is_filled(0) is True
        assert is_filled(False) is True

    def test_text_and_numbers_are_values(self):
        assert is_filled("Reno") is True
        assert is_filled(10000) is True


# ---------------------------------------------------------------------------
# Where a value comes from
# ---------------------------------------------------------------------------

class TestResolve:

    def test_schema_field_reads_its_contract_path(self):
        field = TemplateField.model_validate(
            _field("city", incident_mapping="location.city")
        )
        assert resolve(_CONTRACT, field, "state_texas") == "Reno"

    def test_missing_path_resolves_to_none(self):
        field = TemplateField.model_validate(
            _field("loss", incident_mapping="losses.property_loss.amount")
        )
        assert resolve(_CONTRACT, field, "state_texas") is None

    def test_static_field_carries_its_own_text(self):
        field = TemplateField.model_validate(_field("agency", source="static"))
        assert resolve({}, field, "state_texas") == "Reno Fire Department"

    def test_manual_field_reads_the_flat_custom_fields_key(self):
        field = TemplateField.model_validate(
            _field("marshal_signature_name", source="manual")
        )
        assert resolve(_CONTRACT, field, "state_texas") == "A. Ruiz"

    def test_manual_field_of_another_form_type_does_not_match(self):
        field = TemplateField.model_validate(
            _field("marshal_signature_name", source="manual")
        )
        assert resolve(_CONTRACT, field, "neris") is None

    def test_contract_without_custom_fields_resolves_to_none(self):
        field = TemplateField.model_validate(_field("notes", source="open"))
        assert resolve({"incident": {"name": "x"}}, field, "state_texas") is None


# ---------------------------------------------------------------------------
# Gaps and coverage
# ---------------------------------------------------------------------------

class TestGaps:

    def test_required_gap_blocks_and_optional_gap_does_not(self, db):
        template = _template(
            db,
            fields=[
                _field("city", incident_mapping="location.city"),
                _field("loss", required=True, incident_mapping="losses.property_loss.amount"),
                _field("alarm", required=False, incident_mapping="risk_reduction.smoke_alarm"),
            ],
        )
        gaps = gaps_for(_CONTRACT, template)

        assert gaps.ready is False
        assert [g.field_name for g in gaps.missing_required] == ["loss"]
        assert [g.field_name for g in gaps.missing_recommended] == ["alarm"]

    def test_ready_when_every_required_field_resolves(self, db):
        template = _template(
            db,
            fields=[
                _field("city", incident_mapping="location.city"),
                _field("alarm", required=False, incident_mapping="risk_reduction.smoke_alarm"),
            ],
        )
        gaps = gaps_for(_CONTRACT, template)

        assert gaps.ready is True
        assert gaps.missing_required == []

    def test_coverage_counts_filled_over_total(self, db):
        template = _template(
            db,
            fields=[
                _field("city", incident_mapping="location.city"),
                _field("agency", source="static"),
                _field("loss", incident_mapping="losses.property_loss.amount"),
                _field("cause", incident_mapping="fire.cause_certainty"),
            ],
        )
        assert gaps_for(_CONTRACT, template).coverage_percent == 75.0

    def test_template_without_fields_is_ready(self, db):
        template = _template(db, fields=[])
        gaps = gaps_for(_CONTRACT, template)

        assert gaps.ready is True
        assert gaps.coverage_percent == 0.0

    def test_gap_points_a_schema_field_at_its_contract_path(self, db):
        template = _template(
            db, fields=[_field("loss", incident_mapping="losses.property_loss.amount")]
        )
        gap = gaps_for(_CONTRACT, template).missing_required[0]

        assert gap.source == "schema"
        assert gap.incident_mapping == "losses.property_loss.amount"

    def test_gap_points_a_manual_field_at_its_custom_fields_key(self, db):
        template = _template(db, fields=[_field("chief_name", source="manual")])
        gap = gaps_for(_CONTRACT, template).missing_required[0]

        assert gap.source == "manual"
        assert gap.incident_mapping == "custom_fields.state_texas.chief_name"

    def test_warnings_describe_the_recommended_gaps(self, db):
        template = _template(
            db,
            fields=[
                _field(
                    "alarm",
                    required=False,
                    incident_mapping="risk_reduction.smoke_alarm",
                    description="NERIS recommends damage estimates",
                )
            ],
        )
        warnings = warnings_for(gaps_for(_CONTRACT, template).missing_recommended)

        assert len(warnings) == 1
        assert "risk_reduction.smoke_alarm" in warnings[0]
        assert "NERIS recommends damage estimates" in warnings[0]


# ---------------------------------------------------------------------------
# POST /api/v1/extract/{extract_id}/validate
# ---------------------------------------------------------------------------

class TestValidateExtraction:

    def test_200_valid_when_nothing_required_is_missing(self, client, db):
        extraction, _ = _seed(db)
        template = _template(db, fields=[_field("city", incident_mapping="location.city")])

        resp = _validate(client, extraction.extract_id, template.template_id)
        body = resp.json()

        assert resp.status_code == 200
        assert body["valid"] is True
        assert body["form_type"] == "state_texas"
        assert body["extract_id"] == str(extraction.extract_id)
        assert body["missing_required"] == []
        assert body["field_coverage_percent"] == 100.0

    def test_200_invalid_lists_the_blocking_fields(self, client, db):
        extraction, _ = _seed(db)
        template = _template(
            db,
            fields=[
                _field("city", incident_mapping="location.city"),
                _field("loss", incident_mapping="losses.property_loss.amount"),
            ],
        )

        body = _validate(client, extraction.extract_id, template.template_id).json()

        assert body["valid"] is False
        assert [g["field_name"] for g in body["missing_required"]] == ["loss"]

    def test_correcting_the_contract_flips_it_to_valid(self, client, db):
        extraction, _ = _seed(db)
        template = _template(
            db, fields=[_field("loss", incident_mapping="losses.property_loss.amount")]
        )
        assert _validate(client, extraction.extract_id, template.template_id).json()["valid"] is False

        client.patch(
            f"{URL}/{extraction.extract_id}",
            json={"losses": {"property_loss": {"amount": 250000}}},
            headers={"Content-Type": "application/merge-patch+json"},
        )

        assert _validate(client, extraction.extract_id, template.template_id).json()["valid"] is True

    def test_validate_checks_a_legacy_template_too(self, client, db):
        extraction, _ = _seed(db)
        template = _template(
            db,
            fields=[_field("city", incident_mapping="location.city")],
            status=TemplateStatus.legacy,
        )

        resp = _validate(client, extraction.extract_id, template.template_id)

        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_404_when_the_extraction_is_unknown(self, client, db):
        template = _template(db)
        resp = _validate(client, "550e8400-e29b-41d4-a716-446655440099", template.template_id)

        assert resp.status_code == 404
        assert resp.json()["error_code"] == "EXTRACT_NOT_FOUND"

    def test_404_when_the_template_is_unknown(self, client, db):
        extraction, _ = _seed(db)
        resp = _validate(
            client, extraction.extract_id, "550e8400-e29b-41d4-a716-446655440099"
        )

        assert resp.status_code == 404
        assert resp.json()["error_code"] == "TEMPLATE_NOT_FOUND"

    def test_409_while_the_extraction_is_still_running(self, client, db):
        extraction, _ = _seed(db, extraction_status=ExtractionStatus.processing)
        template = _template(db)

        resp = _validate(client, extraction.extract_id, template.template_id)

        assert resp.status_code == 409
        assert resp.json()["error_code"] == "EXTRACT_NOT_COMPLETED"


# ---------------------------------------------------------------------------
# GET /api/v1/extract/{extract_id}/readiness
# ---------------------------------------------------------------------------

class TestReadiness:

    def test_200_reports_every_active_template(self, client, db):
        extraction, _ = _seed(db)
        _template(db, form_type="neris", display_name="NERIS Incident Report")
        _template(
            db,
            form_type="state_texas",
            fields=[_field("loss", incident_mapping="losses.property_loss.amount")],
        )

        resp = client.get(f"{URL}/{extraction.extract_id}/readiness")
        body = resp.json()

        assert resp.status_code == 200
        assert body["extract_id"] == str(extraction.extract_id)
        assert body["computed_at"]

        rows = {row["form_type"]: row for row in body["templates"]}
        assert rows["neris"]["ready"] is True
        assert rows["neris"]["display_name"] == "NERIS Incident Report"
        assert rows["state_texas"]["ready"] is False
        assert rows["state_texas"]["missing_required"][0]["field_name"] == "loss"

    def test_drafts_and_legacy_templates_stay_out(self, client, db):
        extraction, _ = _seed(db)
        _template(db, form_type="neris")
        _template(db, form_type="old_form", status=TemplateStatus.legacy)
        _template(db, form_type="wip_form", status=TemplateStatus.draft)

        body = client.get(f"{URL}/{extraction.extract_id}/readiness").json()

        assert [row["form_type"] for row in body["templates"]] == ["neris"]

    def test_empty_registry_gives_an_empty_matrix(self, client, db):
        extraction, _ = _seed(db)

        body = client.get(f"{URL}/{extraction.extract_id}/readiness").json()

        assert body["templates"] == []

    def test_readiness_agrees_with_validate(self, client, db):
        extraction, _ = _seed(db)
        template = _template(
            db,
            fields=[
                _field("city", incident_mapping="location.city"),
                _field("loss", incident_mapping="losses.property_loss.amount"),
            ],
        )

        row = client.get(f"{URL}/{extraction.extract_id}/readiness").json()["templates"][0]
        single = _validate(client, extraction.extract_id, template.template_id).json()

        assert row["ready"] == single["valid"]
        assert row["missing_required"] == single["missing_required"]
        assert row["field_coverage_percent"] == single["field_coverage_percent"]

    def test_404_when_the_extraction_is_unknown(self, client, db):
        resp = client.get(f"{URL}/550e8400-e29b-41d4-a716-446655440099/readiness")

        assert resp.status_code == 404
        assert resp.json()["error_code"] == "EXTRACT_NOT_FOUND"

    def test_409_while_the_extraction_is_still_running(self, client, db):
        extraction, _ = _seed(db, extraction_status=ExtractionStatus.processing)

        resp = client.get(f"{URL}/{extraction.extract_id}/readiness")

        assert resp.status_code == 409
        assert resp.json()["error_code"] == "EXTRACT_NOT_COMPLETED"
