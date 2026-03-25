import os
from types import SimpleNamespace

from src.batch_orchestrator import BatchOrchestrator


def test_mapping_report_includes_direct_and_alias_evidence():
    template_fields = {
        "incident_id": {"type": "text", "required": True},
        "location": {"type": "text", "required": True, "aliases": ["site_location"]},
    }
    incident_record = {
        "incident_id": "INC-42",
        "site_location": "North Block",
    }

    report = BatchOrchestrator._build_mapping_report(template_fields, incident_record)
    evidence = report["field_evidence"]

    assert evidence["incident_id"]["matched"] is True
    assert evidence["incident_id"]["source_id"] == "incident_record"
    assert evidence["incident_id"]["method"] == "direct"
    assert evidence["incident_id"]["confidence"] == 1.0

    assert evidence["location"]["matched"] is True
    assert evidence["location"]["method"] == "inferred_alias"
    assert evidence["location"]["confidence"] == 0.95


def test_mapping_report_records_unmatched_required_field_evidence():
    template_fields = {
        "incident_id": {"type": "text", "required": True},
        "location": {"type": "text", "required": True},
    }
    incident_record = {"incident_id": "INC-404"}

    report = BatchOrchestrator._build_mapping_report(template_fields, incident_record)
    evidence = report["field_evidence"]

    assert report["compatible"] is False
    assert "location" in report["missing_fields"]
    assert evidence["location"]["matched"] is False
    assert evidence["location"]["source_id"] == "none"
    assert evidence["location"]["confidence"] == 0.0


def test_run_batch_result_contains_field_evidence(tmp_path):
    output_root = tmp_path / "batches"

    def fill_single_form(pdf_path, incident_record, template_fields):
        output_file = tmp_path / f"{os.path.basename(pdf_path)}.filled.pdf"
        output_file.write_text("pdf-bytes", encoding="utf-8")
        return str(output_file)

    orchestrator = BatchOrchestrator(fill_single_form)

    templates = [
        SimpleNamespace(
            id=1,
            name="Traceability Form",
            pdf_path="traceability.pdf",
            fields={"incident_id": {"type": "text", "required": True}},
        )
    ]

    result = orchestrator.run_batch(
        incident_record={"incident_id": "INC-777"},
        templates=templates,
        output_root=str(output_root),
    )

    mapping_report = result["results"][0]["mapping_report"]
    assert "field_evidence" in mapping_report
    assert mapping_report["field_evidence"]["incident_id"]["matched"] is True
    assert mapping_report["field_evidence"]["incident_id"]["method"] == "direct"