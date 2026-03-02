from fastapi import APIRouter, Depends
from sqlmodel import Session
from api.deps import get_db
from api.schemas.templates import TemplateCreate, TemplateResponse
from api.db.repositories import create_template
from api.db.models import Template
from api.errors.base import AppError
from src.controller import Controller

router = APIRouter(prefix="/templates", tags=["templates"])

@router.post("/create", response_model=TemplateResponse)
def create(template: TemplateCreate, db: Session = Depends(get_db)):
    controller = Controller()
    try:
        template_path = controller.create_template(template.pdf_path)
    except FileNotFoundError:
        raise AppError(f"PDF not found at path: {template.pdf_path}", status_code=404)
    except Exception as exc:
        raise AppError(f"Failed to process template: {exc}", status_code=422)
    tpl = Template(**template.model_dump(exclude={"pdf_path"}), pdf_path=template_path)
    return create_template(db, tpl)