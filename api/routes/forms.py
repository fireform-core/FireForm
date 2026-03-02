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
    template = get_template(db, form.template_id)
    if not template:
        raise AppError("Template not found", status_code=404)

    controller = Controller()
    path = controller.fill_form(user_input=form.input_text, fields=template.fields, pdf_form_path=template.pdf_path)

    submission = FormSubmission(**form.model_dump(), output_pdf_path=path)
    return create_form(db, submission)

