from fastapi import APIRouter, Depends
from sqlmodel import Session
from api.deps import get_db
from api.schemas.forms import FormFill, FormFeedback, FormFillResponse
from api.db.repositories import create_form, get_template
from api.db.models import FormSubmission
from api.errors.base import AppError
from src.controller import Controller

router = APIRouter(prefix="/forms", tags=["forms"])

@router.post("/fill", response_model=FormFillResponse)
def fill_form(form: FormFill, db: Session = Depends(get_db)):
    fetched_template = get_template(db, form.template_id)
    if not fetched_template:
        raise AppError("Template not found", status_code=404)

    controller = Controller()
    
    extracted_data, missing_fields = controller.extract_data(
        user_input=form.input_text, 
        fields=fetched_template.fields
    )

    if missing_fields:
        status = "missing_data"
        path = None
    else:
        status = "completed"
        path = controller.fill_pdf(answers=extracted_data, pdf_form_path=fetched_template.pdf_path)

    submission = FormSubmission(
        template_id=form.template_id,
        input_text=form.input_text,
        output_pdf_path=path,
        status=status,
        extracted_data=extracted_data,
        missing_fields=missing_fields
    )
    return create_form(db, submission)


@router.post("/{submission_id}/feedback", response_model=FormFillResponse)
def form_feedback(submission_id: int, feedback: FormFeedback, db: Session = Depends(get_db)):
    submission = db.get(FormSubmission, submission_id)
    if not submission:
        raise AppError("Form submission not found", status_code=404)
        
    if submission.status == "completed":
        raise AppError("Form already completed", status_code=400)
        
    fetched_template = get_template(db, submission.template_id)
    if not fetched_template:
        raise AppError("Template not found", status_code=404)

    controller = Controller()
    
    # Only target missing fields from the template
    target_fields = {field: fetched_template.fields[field] for field in submission.missing_fields if field in fetched_template.fields}
    
    extracted_data, missing_fields = controller.extract_data(
        user_input=feedback.input_text,
        fields=target_fields,
        existing_data=submission.extracted_data
    )

    if missing_fields:
        submission.status = "missing_data"
        submission.output_pdf_path = None
    else:
        submission.status = "completed"
        submission.output_pdf_path = controller.fill_pdf(answers=extracted_data, pdf_form_path=fetched_template.pdf_path)

    submission.extracted_data = extracted_data
    submission.missing_fields = missing_fields
    
    db.add(submission)
    db.commit()
    db.refresh(submission)
    
    return submission


