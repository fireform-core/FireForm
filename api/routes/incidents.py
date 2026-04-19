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
        # Instead of pulling 1000+ unreadable AcroForm fields from all templates,
        # we provide a core Universal ICS Schema to guide the LLM, and let its dynamic 
        # schema-less extraction catch everything else. This prevents 503 timeouts!
        merged_fields = {
            "incident_name": "Incident Name",
            "incident_number": "Incident Number",
            "date_time_of_report": "Date and Time of Report",
            "report_version": "Report Version",
            "incident_commander": "Incident Commander",
            "incident_management_organization": "Incident Management Organization",
            "incident_description": "Incident Description / Sub-type",
            "location": "Location",
            "current_incident_size_acres": "Current Incident Size (Acres)",
            "percent_contained": "Percent Contained",
            "estimated_containment_date": "Estimated Containment Date",
            "cause_of_incident": "Cause of Incident",
            "weather_conditions": "Weather Conditions (Current)",
            "significant_events": "Significant Events / Critical Activity",
            "planned_actions": "Planned Actions for Next 24 Hours",
            "operational_period_from": "Operational Period From",
            "operational_period_to": "Operational Period To",
            "from": "From Time",
            "to": "To Time",
            "unit_name": "Unit Name / Designators",
            "unit_leader": "Unit Leader (Name and ICS Position)",
            "personnel_assigned": "Personnel Assigned",
            "activity_log": "Activity Log",
            "prepared_by": "Prepared By",
            "preparation_date_time": "Date and Time of Preparation"
        }
        print(f"[DATA LAKE] Using Universal ICS Schema ({len(merged_fields)} fields) to prevent LLM timeout.")

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
async def generate_pdf_from_lake(
    incident_id: str,
    template_id: int,
    db: Session = Depends(get_db)
):
    """
    Takes stored Master Incident JSON and generates a PDF for any agency template.
    Uses an AI Semantic Mapper to fluently match dynamically extracted Data Lake 
    fields into strict PDF keys without rigid hardcoding!
    """
    incident = get_incident(db, incident_id)
    if not incident:
        raise AppError(f"Incident {incident_id} not found in data lake", status_code=404)

    template = get_template(db, template_id)
    if not template:
        raise AppError(f"Template {template_id} not found", status_code=404)

    if not os.path.exists(template.pdf_path):
        raise AppError(f"Template PDF not found on disk: {template.pdf_path}", status_code=404)

    print(f"[DATA LAKE] Generating '{template.name}' from incident {incident_id} via Semantic Mapper")

    master_data = json.loads(incident.master_json)

    # Determine target fields based on whether this is a static or AcroForm PDF.
    from api.db.repositories import get_template_coordinates
    coords = get_template_coordinates(db, template_id)
    
    if coords:
        # Static PDF path: use the field labels from the scanned coordinates
        tpl_fields = [c.field_label for c in coords]
        print(f"[DATA LAKE] Static PDF detected — using {len(tpl_fields)} scanned coordinate labels as targets")
    else:
        # AcroForm path: use stored field names from template
        raw_fields = list(template.fields.keys()) if isinstance(template.fields, dict) else template.fields
        
        # --- JUNK FILTER ---
        import re
        tpl_fields = []
        for f in raw_fields:
            if not f: continue
            basename = str(f).split('.')[-1].split('[')[0].lower()
            if re.match(r'^(textfield|text|checkbox|check|button|btn|radio|listbox|combo|rectangle|line)\d*$', basename):
                continue
            tpl_fields.append(f)
            
        print(f"[DATA LAKE] Junk Filter: compressed {len(raw_fields)} raw structural fields down to {len(tpl_fields)} meaningful targets.")

    # --- THE MAGIC BRIDGE: AI Semantic Mapper ---
    from src.llm import LLM
    try:
        mapped_data = await LLM.async_semantic_map(master_json=master_data, target_pdf_fields=tpl_fields)
    except Exception as e:
        print(f"[DATA LAKE] Semantic Mapper Error: {e}, falling back to exact strings.")
        mapped_data = {k: master_data.get(k) for k in tpl_fields if master_data.get(k) is not None}

    # If the LLM failed entirely, fallback to string matching
    if not mapped_data:
        print("[DATA LAKE] Empty Semantic Map. Falling back to explicit string matching.")
        mapped_data = {k: master_data.get(k) for k in tpl_fields if master_data.get(k) is not None}

    print(f"[DATA LAKE] Template needs {len(tpl_fields)} fields, Semantic Mapper produced {len(mapped_data.keys() if isinstance(mapped_data, dict) else [])} fields")

    # Fill PDF
    filler = Filler()
    try:
        if coords:
            print(f"[DATA LAKE] Found {len(coords)} coordinates, using static PDF filler.")
            output_path = filler.fill_static_pdf(
                pdf_form=template.pdf_path,
                coordinates=coords,
                data=mapped_data
            )
        else:
            print("[DATA LAKE] No coordinates found, using dynamic AcroForm filler.")
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
        input_text=f"[DATA LAKE -> SEMANTIC MAPPER] {incident_id}",
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
        "message": "PDF physically generated via AI Semantic Mapping!"
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