from pathlib import Path
from sqlite3 import IntegrityError
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select
from api.deps import get_db
from api.schemas.report_class import (
    ReportSchemaCreate,
    ReportSchemaUpdate,
    ReportSchemaResponse,
    TemplateAssociation,
    SchemaFieldResponse,
    SchemaFieldUpdate,
    CanonicalSchema,
    ReportFill,
    ReportFillResponse,
    FormSubmissionResponse,
)
from api.db import repositories as repo
from api.db.models import ReportSchema
from src.report_schema import ReportSchemaProcessor
from src.controller import Controller
from api.db.models import FormSubmission, ReportSchemaTemplate
from sqlalchemy.exc import IntegrityError

router = APIRouter(prefix="/schemas", tags=["schemas"])


@router.post("/create", response_model=ReportSchemaResponse)
def create_schema(data: ReportSchemaCreate, db: Session = Depends(get_db)):
    schema = ReportSchema(**data.model_dump())
    try:
        return repo.create_report_schema(db, schema)
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="A schema with this name already exists"
        )

@router.get("/", response_model=list[ReportSchemaResponse])
def list_schemas(db: Session = Depends(get_db)):
    return repo.list_report_schemas(db)

@router.get("/{schema_id}", response_model=ReportSchemaResponse)
def get_schema(schema_id: int, db: Session = Depends(get_db)):
    schema = repo.get_report_schema(db, schema_id)
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")
    return schema

@router.put("/{schema_id}", response_model=ReportSchemaResponse)
def update_schema(schema_id: int, data: ReportSchemaUpdate, db: Session = Depends(get_db)):
    updates = data.model_dump(exclude_none=True)
    schema = repo.update_report_schema(db, schema_id, updates)
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")
    return schema

@router.delete("/{schema_id}")
def delete_schema(schema_id: int, db: Session = Depends(get_db)):
    deleted = repo.delete_report_schema(db, schema_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Schema not found")
    return {"detail": "Schema deleted"}


@router.post("/{schema_id}/templates", response_model=list[SchemaFieldResponse])
def add_template(schema_id: int, data: TemplateAssociation, db: Session = Depends(get_db)):
    """Associate a template with a schema.

    Auto-creates SchemaField entries from template.fields and returns them.
    """
    try:
        repo.add_template_to_schema(db, schema_id, data.template_id)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Template is already added to schema")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return repo.get_schema_fields(db, schema_id)

@router.delete("/{schema_id}/templates/{template_id}")
def remove_template(schema_id: int, template_id: int, db: Session = Depends(get_db)):
    removed = repo.remove_template_from_schema(db, schema_id, template_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Template association not found")
    return {"detail": "Template disassociated"}



@router.get("/{schema_id}/fields", response_model=list[SchemaFieldResponse])
def list_fields(schema_id: int, db: Session = Depends(get_db)):
    return repo.get_schema_fields(db, schema_id)

@router.put("/{schema_id}/fields/{field_id}", response_model=SchemaFieldResponse)
def update_field(schema_id: int, field_id: int, data: SchemaFieldUpdate, db: Session = Depends(get_db)):
    updates = data.model_dump(exclude_none=True)
    field = repo.update_schema_field(db, schema_id, field_id, updates)
    if not field:
        raise HTTPException(status_code=404, detail="Field not found or does not belong to this schema")
    return field


@router.post("/{schema_id}/canonize", response_model=CanonicalSchema)
def canonize_schema(schema_id: int, db: Session = Depends(get_db)):
    """Trigger canonization: group fields, assign canonical names, generate field mappings."""
    schema = repo.get_report_schema(db, schema_id)
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")

    return ReportSchemaProcessor.canonize(db, schema_id)

@router.get("/mapping/{schema_id}/{template_id}")
def get_schema_template_mapping(schema_id: int, template_id: int, db: Session = Depends(get_db)):
    return repo.get_field_mapping(db, schema_id, template_id)

@router.post("/{schema_id}/fill", response_model=ReportFillResponse)
def fill_schema(schema_id: int, data: ReportFill, db: Session = Depends(get_db)):
    """
    End-to-end report generation.
    Takes a single transcript, extracts canonical fields, distributes to
    all schema templates, fills them, and logs the submissions.
    """
    schema = repo.get_report_schema(db, schema_id)
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")
    
    controller = Controller()
    
    output_paths = controller.fill_report(db, data.input_text, schema_id)

    # Log submissions
    submission_ids: list[int] = []
    for template_id, path in output_paths.items():
        submission = FormSubmission(
            template_id=template_id,
            report_schema_id=schema_id,
            name=data.name,
            input_text=data.input_text,
            output_pdf_path=path
        )
        db.add(submission)
        db.flush()
        submission_ids.append(submission.id)  # type: ignore
            
    db.commit()

    return ReportFillResponse(
        schema_id=schema_id,
        input_text=data.input_text,
        output_pdf_paths=list(output_paths.values()),
        submission_ids=submission_ids,
    )


@router.get("/{schema_id}/submissions", response_model=list[FormSubmissionResponse])
def list_submissions(schema_id: int, db: Session = Depends(get_db)):
    """List all form submissions for a given schema."""
    return db.exec(
        select(FormSubmission)
        .where(FormSubmission.report_schema_id == schema_id)
        .order_by(FormSubmission.created_at.desc())  # type: ignore
    ).all()


@router.get("/submissions/{submission_id}/pdf")
def get_submission_pdf(submission_id: int, db: Session = Depends(get_db)):
    """Serve a filled PDF for a given form submission."""
    submission = db.get(FormSubmission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    path = Path(submission.output_pdf_path).resolve()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="PDF file missing on disk")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"submission_{submission_id}.pdf",
    )
