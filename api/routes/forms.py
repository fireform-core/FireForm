from fastapi import APIRouter, Depends
from sqlmodel import Session
from api.deps import get_db
from api.schemas.forms import FormFill, FormFillResponse
from api.db.repositories import create_form, get_template
from api.db.models import FormSubmission
from api.errors.base import AppError, ValidationError
from src.controller import Controller
from src.validator import validate_transcript, validate_template_fields

router = APIRouter(prefix="/forms", tags=["forms"])

@router.post("/fill", response_model=FormFillResponse)
def fill_form(form: FormFill, db: Session = Depends(get_db)):
    # Validate transcript input before processing
    transcript_errors = validate_transcript(form.input_text)
    if transcript_errors:
        raise ValidationError(
            message="Invalid transcript input",
            errors=transcript_errors
        )

    # Check if template exists
    fetched_template = get_template(db, form.template_id)
    if not fetched_template:
        raise AppError("Template not found", status_code=404)

    # Validate template fields
    field_errors = validate_template_fields(fetched_template.fields)
    if field_errors:
        raise ValidationError(
            message="Invalid template configuration",
            errors=field_errors
        )

    controller = Controller()
    path = controller.fill_form(
        user_input=form.input_text,
        fields=fetched_template.fields,
        pdf_form_path=fetched_template.pdf_path
    )

    submission = FormSubmission(**form.model_dump(), output_pdf_path=path)
    return create_form(db, submission)


