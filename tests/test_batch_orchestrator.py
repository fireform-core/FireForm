import os
from types import SimpleNamespace
from zipfile import ZipFile

from src.batch_orchestrator import BatchOrchestrator


def test_run_batch_processes_templates_independently(tmp_path):
    output_root = tmp_path / "batches"
    generated = []

    def fill_single_form(pdf_path, incident_record, template_fields):
        if "fail" in pdf_path:
            raise RuntimeError("Simulated fill failure")

        output_file = tmp_path / f"{os.path.basename(pdf_path)}.filled.pdf"
        output_file.write_text("pdf-bytes", encoding="utf-8")
        generated.append(str(output_file))
        return str(output_file)

    orchestrator = BatchOrchestrator(fill_single_form)

    templates = [
        SimpleNamespace(
            id=1,
            name="Fire Incident Form",
            pdf_path="fire.pdf",
            fields={"incident_id": {"type": "text", "required": True}},
        ),
        SimpleNamespace(
            id=2,
            name="Medical Incident Form",
            pdf_path="medical_fail.pdf",
            fields={"incident_id": {"type": "text", "required": True}},
        ),
        SimpleNamespace(
            id=3,
            name="Insurance Claim Form",
            pdf_path="insurance.pdf",
            fields={"incident_id": {"type": "text", "required": True}},
        ),
    ]

    result = orchestrator.run_batch(
        incident_record={"incident_id": "INC-123"},
        templates=templates,
        output_root=str(output_root),
    )

    assert result["total_templates"] == 3
    assert result["successful_count"] == 2
    assert result["failed_count"] == 1
    assert os.path.exists(result["package_zip_path"])

    statuses = {item["template_id"]: item["status"] for item in result["results"]}
    assert statuses[1] == "success"
    assert statuses[2] == "failed_runtime"
    assert statuses[3] == "success"

    with ZipFile(result["package_zip_path"], "r") as zip_file:
        names = set(zip_file.namelist())
        assert "batch_report.json" in names
        assert len([name for name in names if name.endswith(".pdf")]) == 2


def test_run_batch_reports_validation_failures(tmp_path):
    output_root = tmp_path / "batches"

    def fill_single_form(pdf_path, incident_record, template_fields):
        output_file = tmp_path / "unused.pdf"
        output_file.write_text("unused", encoding="utf-8")
        return str(output_file)

    orchestrator = BatchOrchestrator(fill_single_form)

    templates = [
        SimpleNamespace(
            id=7,
            name="Fire Validation Form",
            pdf_path="fire_validation.pdf",
            fields={
                "incident_id": {"type": "text", "required": True},
                "location": {"type": "text", "required": True},
            },
        ),
    ]

    result = orchestrator.run_batch(
        incident_record={"incident_id": "INC-7"},
        templates=templates,
        output_root=str(output_root),
    )

    assert result["successful_count"] == 0
    assert result["failed_count"] == 1
    assert result["results"][0]["status"] == "failed_validation"
    assert "location" in result["results"][0]["mapping_report"]["missing_fields"]
