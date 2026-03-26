import os

from fastapi import APIRouter, Depends
from sqlmodel import Session

from api.db.models import Template
from api.db.repositories import create_template
from api.deps import get_db
from api.errors.base import AppError
from api.schemas.error import ErrorResponse
from api.schemas.templates import TemplateCreate, TemplateResponse
from src.controller import Controller

router = APIRouter(prefix="/templates", tags=["templates"])


@router.post(
    "/create",
    response_model=TemplateResponse,
    responses={
        404: {
            "model": ErrorResponse,
            "description": "Source PDF not found at the given path",
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
def create(template: TemplateCreate, db: Session = Depends(get_db)):
    if not os.path.isfile(template.pdf_path):
        raise AppError(
            "PDF file not found",
            status_code=404,
            code="PDF_NOT_FOUND",
            details={"path": template.pdf_path},
        )

    controller = Controller()
    template_path = controller.create_template(template.pdf_path)
    tpl = Template(**template.model_dump(exclude={"pdf_path"}), pdf_path=template_path)
    return create_template(db, tpl)