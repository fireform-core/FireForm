from fastapi import APIRouter, Depends
from sqlmodel import Session

from api.db.models import FormSubmission
from api.db.repositories import create_form, get_template
from api.deps import get_db
from api.errors.base import AppError
from api.schemas.error import ErrorResponse
from api.schemas.forms import FormFill, FormFillResponse
from src.controller import Controller

router = APIRouter(prefix="/forms", tags=["forms"])


@router.post(
    "/fill",
    response_model=FormFillResponse,
    responses={
        404: {
            "model": ErrorResponse,
            "description": "Template not found",
        },
        422: {
            "model": ErrorResponse,
            "description": "Request validation failed",
        },
        500: {
            "model": ErrorResponse,
            "description": "Unexpected server error",
        },
    },
)
def fill_form(form: FormFill, db: Session = Depends(get_db)):
    if not get_template(db, form.template_id):
        raise AppError(
            "Template not found",
            status_code=404,
            code="TEMPLATE_NOT_FOUND",
        )

    fetched_template = get_template(db, form.template_id)

    controller = Controller()
    path = controller.fill_form(user_input=form.input_text, fields=fetched_template.fields, pdf_form_path=fetched_template.pdf_path)

    submission = FormSubmission(**form.model_dump(), output_pdf_path=path)
    return create_form(db, submission)


