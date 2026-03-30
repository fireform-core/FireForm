import os
import json
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlmodel import Session
from api.deps import get_db
from api.db.models import IncidentMasterData, FormSubmission
from api.db.repositories import (
    create_incident, get_incident, get_all_incidents,
    update_incident_json, get_template, create_form
)
from api.errors.base import AppError
from src.filler import Filler
from src.llm import LLM
from src.controller import Controller
from datetime import datetime

router = APIRouter(prefix="/incidents", tags=["incidents"])


# ── Schema: Extract & Store ──────────────────────────────

@router.post("/extract")
async def extract_to_data_lake(
    input_text: str,
    incident_id: str = None,
    location_lat: float = None,
    location_lng: float = None,
    db: Session = Depends(get_db)
):
    """
    THE CORE DATA LAKE ENDPOINT.

    Extracts ALL possible fields from transcript and stores as
    Master Incident JSON. No template needed — extracts everything.
    Later: any agency generates their PDF from this stored data
    without re-running the LLM.

    If incident_id already exists — merges new data into existing.
    This supports multi-officer reports: each officer adds their
    perspective, system merges into one master record.
    """
    if not incident_id:
        # Auto-generate incident ID
        now = datetime.utcnow()
        incident_id = f"INC-{now.year}-{now.month:02d}{now.day:02d}-{now.hour:02d}{now.minute:02d}"

    print(f"[DATA LAKE] Extracting incident: {incident_id}")

    # Get all templates to build maximum superset of fields
    from api.db.repositories import get_all_templates
    all_templates = get_all_templates(db)

    # Start with an empty schema to allow fully dynamic LLM extraction
    # The LLM will use any uploaded template fields as a base guide, 
    # and autonomously invent new fields for the rest.
    merged_fields = {}

    if all_templates:
        # Build superset from all known templates
        for tpl in all_templates:
            if isinstance(tpl.fields, dict):
                merged_fields.update(tpl.fields)
        print(f"[DATA LAKE] Base schema: {len(merged_fields)} template fields across {len(all_templates)} templates")

    try:
        llm = LLM(transcript_text=input_text, target_fields=merged_fields)
        await llm.async_main_loop()
        extracted = llm.get_data()
        print(f"[DATA LAKE] Extracted {len(extracted)} fields")
    except ConnectionError:
        raise AppError("Could not connect to Ollama.", status_code=503)
    except Exception as e:
        raise AppError(f"Extraction failed: {str(e)}", status_code=500)

    # Check if incident already exists — merge if so
    existing = get_incident(db, incident_id)
    if existing:
        print(f"[DATA LAKE] Merging into existing incident {incident_id}")
        updated = update_incident_json(db, incident_id, extracted, new_transcript=input_text)
        return {
            "incident_id": incident_id,
            "status": "merged",
            "fields_extracted": len(extracted),
            "total_fields": len(json.loads(updated.master_json)),
            "message": f"Merged into existing incident. Total fields: {len(json.loads(updated.master_json))}"
        }

    # New incident — create record
    incident = IncidentMasterData(
        incident_id=incident_id,
        master_json=json.dumps(extracted),
        transcript_text=input_text,
        location_lat=location_lat,
        location_lng=location_lng,
    )
    saved = create_incident(db, incident)
    print(f"[DATA LAKE] Stored incident {incident_id} with {len(extracted)} fields")

    return {
        "incident_id": incident_id,
        "status": "created",
        "fields_extracted": len(extracted),
        "master_json": extracted,
        "message": f"Incident data stored. Generate PDFs with POST /incidents/{incident_id}/generate/{{template_id}}"
    }


# ── Generate PDF from stored data ────────────────────────

@router.post("/{incident_id}/generate/{template_id}")
def generate_pdf_from_lake(
    incident_id: str,
    template_id: int,
    db: Session = Depends(get_db)
):
    """
    Generates a PDF for any agency template from the stored Master Incident Data Lake.
    Supports dynamic multi-template generation from a single incident record —
    Record Once, Report Everywhere.
    """
    incident = get_incident(db, incident_id)
    if not incident:
        raise AppError(f"Incident {incident_id} not found in data lake", status_code=404)

    template = get_template(db, template_id)
    if not template:
        raise AppError(f"Template {template_id} not found", status_code=404)

    if not os.path.exists(template.pdf_path):
        raise AppError(f"Template PDF not found on disk: {template.pdf_path}", status_code=404)

    print(f"[DATA LAKE] Generating '{template.name}' from incident {incident_id}")

    master_data = json.loads(incident.master_json)
    tpl_fields = list(template.fields.keys()) if isinstance(template.fields, dict) else template.fields

    # Map stored Data Lake fields to this template's fields
    mapped_data = {k: master_data.get(k) for k in tpl_fields if master_data.get(k) is not None}

    print(f"[DATA LAKE] Template needs {len(tpl_fields)} fields, matched {len(mapped_data)}")

    # Fill PDF
    filler = Filler()
    try:
        output_path = filler.fill_form_with_data(
            pdf_form=template.pdf_path,
            data=mapped_data
        )
    except Exception as e:
        raise AppError(f"PDF generation failed: {str(e)}", status_code=500)

    if not output_path or not os.path.exists(output_path):
        raise AppError("PDF generation produced no output", status_code=500)

    # Save submission record
    submission = FormSubmission(
        template_id=template_id,
        input_text=f"[DATA LAKE] {incident_id}",
        output_pdf_path=output_path
    )
    saved = create_form(db, submission)

    return {
        "incident_id": incident_id,
        "template_id": template_id,
        "template_name": template.name,
        "submission_id": saved.id,
        "download_url": f"/forms/download/{saved.id}",
        "fields_matched": len(mapped_data),
        "fields_total": len(tpl_fields),
        "message": "PDF generated from Master Data Lake."
    }


# ── Get incident data ────────────────────────────────────

@router.get("/{incident_id}")
def get_incident_data(incident_id: str, db: Session = Depends(get_db)):
    """Get stored master JSON for an incident."""
    incident = get_incident(db, incident_id)
    if not incident:
        raise AppError(f"Incident {incident_id} not found", status_code=404)
    return {
        "incident_id": incident.incident_id,
        "master_json": json.loads(incident.master_json),
        "transcript": incident.transcript_text,
        "location": {
            "lat": incident.location_lat,
            "lng": incident.location_lng
        } if incident.location_lat else None,
        "created_at": incident.created_at,
        "updated_at": incident.updated_at
    }


# ── List all incidents ───────────────────────────────────

@router.get("")
def list_incidents(db: Session = Depends(get_db)):
    """List all incidents in the data lake."""
    incidents = get_all_incidents(db)
    return [
        {
            "incident_id": i.incident_id,
            "fields_count": len(json.loads(i.master_json)),
            "created_at": i.created_at,
            "location": {"lat": i.location_lat, "lng": i.location_lng} if i.location_lat else None
        }
        for i in incidents
    ]


# ── Narrative generation ─────────────────────────────────

@router.post("/{incident_id}/narrative")
def generate_narrative(incident_id: str, db: Session = Depends(get_db)):
    """
    Generate a legally coherent narrative report from stored incident data.
    For insurance claims, court documents, after-action reports.
    Uses the LLM to write prose — not fill fields.
    """
    incident = get_incident(db, incident_id)
    if not incident:
        raise AppError(f"Incident {incident_id} not found", status_code=404)

    master_data = json.loads(incident.master_json)
    fields_summary = "\n".join([f"- {k}: {v}" for k, v in master_data.items() if v])

    narrative_prompt = f"""You are a professional incident report writer for emergency services.
Based on the following structured incident data, write a clear, factual, legally coherent 
narrative report suitable for insurance claims and court documentation.

Incident ID: {incident_id}
Date/Time: {incident.created_at}
Original Transcript: {incident.transcript_text}

Extracted Data:
{fields_summary}

Write a professional narrative report in 3-4 paragraphs covering:
1. Incident summary (what happened, when, where)
2. Response and actions taken
3. Outcome and follow-up required

Use formal language appropriate for legal documentation."""

    try:
        import requests
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "mistral",
                "prompt": narrative_prompt,
                "stream": False
            },
            timeout=120
        )
        narrative = response.json().get("response", "").strip()
    except Exception as e:
        raise AppError(f"Narrative generation failed: {str(e)}", status_code=500)

    return {
        "incident_id": incident_id,
        "narrative": narrative,
        "format": "markdown",
        "generated_at": datetime.utcnow().isoformat()
    }