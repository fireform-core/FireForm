from fastapi import APIRouter, Depends
from sqlmodel import Session
from api.deps import get_db
from api.schemas.forms import FormFill, FormFillResponse
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
    try:
        result = controller.fill_form(
            user_input=form.input_text,
            fields=fetched_template.fields,
            pdf_form_path=fetched_template.pdf_path,
            retry_input_texts=form.retry_input_texts,
            max_retry_rounds=form.max_retry_rounds,
        )
    except FileNotFoundError as exc:
        raise AppError(str(exc), status_code=400) from exc

    submission = FormSubmission(
        template_id=form.template_id,
        input_text=form.input_text,
        output_pdf_path=result["output_pdf_path"],
        status=result["status"],
        required_completion_pct=result["required_completion_pct"],
        completed_required_fields=result["completed_required_fields"],
        missing_required_fields=result["missing_required_fields"],
        attempts_used=result["attempts_used"],
        retry_prompt=result["retry_prompt"],
    )
    return create_form(db, submission)
