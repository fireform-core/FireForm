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
    # 🔒 Validate template_id
    if form.template_id is None or form.template_id <= 0:
        raise AppError("Invalid template_id provided", status_code=400)

    # 🔒 Validate input_text (empty or whitespace)
    if not form.input_text or not form.input_text.strip():
        raise AppError("Input text cannot be empty", status_code=400)

    # 🔒 Validate input length (prevent abuse / overload)
    if len(form.input_text) > 5000:
        raise AppError("Input text is too long (max 5000 characters)", status_code=400)

    # 📌 Fetch template once (avoid duplicate DB call)
    fetched_template = get_template(db, form.template_id)

    if not fetched_template:
        raise AppError("Template not found", status_code=404)

    # 🚀 Process form using controller
    controller = Controller()
    path = controller.fill_form(
        user_input=form.input_text,
        fields=fetched_template.fields,
        pdf_form_path=fetched_template.pdf_path
    )

    # 💾 Save submission
    submission = FormSubmission(
        **form.model_dump(),
        output_pdf_path=path
    )

    return create_form(db, submission)