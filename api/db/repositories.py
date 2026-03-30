from sqlmodel import Session, select
from api.db.models import Template, FormSubmission


# ── Templates ─────────────────────────────────────────────────

def create_template(session: Session, template: Template) -> Template:
    session.add(template)
    session.commit()
    session.refresh(template)
    return template


def get_template(session: Session, template_id: int) -> Template | None:
    return session.get(Template, template_id)


def get_all_templates(session: Session, limit: int = 100, offset: int = 0) -> list[Template]:
    statement = select(Template).offset(offset).limit(limit)
    return session.exec(statement).all()


# ── Forms ─────────────────────────────────────────────────────

def create_form(session: Session, form: FormSubmission) -> FormSubmission:
    session.add(form)
    session.commit()
    session.refresh(form)
    return form


def get_form(session: Session, submission_id: int) -> FormSubmission | None:
    return session.get(FormSubmission, submission_id)


# ADD THESE FUNCTIONS TO api/db/repositories.py
# (append to existing file — don't replace)

import json
from api.db.models import IncidentMasterData
from datetime import datetime


def create_incident(db, incident: IncidentMasterData) -> IncidentMasterData:
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def get_incident(db, incident_id: str) -> IncidentMasterData:
    from sqlmodel import select
    return db.exec(
        select(IncidentMasterData).where(
            IncidentMasterData.incident_id == incident_id
        )
    ).first()


def get_all_incidents(db) -> list:
    from sqlmodel import select
    return db.exec(select(IncidentMasterData)).all()


def update_incident_json(db, incident_id: str, new_data: dict, new_transcript: str = None) -> IncidentMasterData:
    """
    Smart Merge new extracted data into existing master JSON to enable 
    Collaborative Incident Consensus. Protects existing data from being 
    wiped by LLM `null` hallucinations, and appends long-form text.
    """
    incident = get_incident(db, incident_id)
    if not incident:
        return None
        
    existing = json.loads(incident.master_json)
    
    for key, value in new_data.items():
        # 1. Ignore empty/null values to protect existing data
        if value is None or str(value).strip().lower() in ("null", "none", "", "n/a"):
            continue
            
        # 2. If the field exists, handle smart merging vs overwriting
        if key in existing and existing[key]:
            old_value = existing[key]
            
            # Use string representation for safe comparison
            old_str = str(old_value).strip() if not isinstance(old_value, list) else "\n".join(str(i) for i in old_value)
            new_str = str(value).strip() if not isinstance(value, list) else "\n".join(str(i) for i in value)
            
            # If the value is identical, do nothing
            if old_str.lower() == new_str.lower():
                continue
                
            # If it's a long-form text field (Notes, Description, Narrative, Summary, etc)
            long_fields = ("note", "desc", "narrative", "summary", "remark", "detail", "comment")
            if any(lf in key.lower() for lf in long_fields):
                # Prevent recursive appending
                if new_str not in old_str:
                    existing[key] = f"{old_str}\n\n[UPDATE]: {new_str}"
            else:
                # Standard Field Correction (e.g. ID, City) - overwrite the old value
                existing[key] = value
        else:
            # 3. Brand new field
            existing[key] = value

    incident.master_json = json.dumps(existing)
    
    # Safely append the new transcript segment for true consensus history
    if new_transcript and new_transcript.strip() not in incident.transcript_text:
        incident.transcript_text = f"{incident.transcript_text}\n\n---\n[UPDATE]: {new_transcript.strip()}"
        
    incident.updated_at = datetime.utcnow()
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident