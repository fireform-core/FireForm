from fastapi import APIRouter, Depends
from sqlmodel import Session
from api.deps import get_db
from api.schemas.templates import TemplateCreate, TemplateResponse
from api.db.repositories import create_template
from api.db.models import Template
from src.controller import Controller

router = APIRouter(prefix="/templates", tags=["templates"])


@router.post("/create", response_model=TemplateResponse)
def create(template: TemplateCreate, db: Session = Depends(get_db)):
    controller = Controller()
    template_path = controller.create_template(template.pdf_path)

    tpl = Template(
        **template.model_dump(exclude={"pdf_path"}),
        pdf_path=template_path,
    )

    return create_template(db, tpl)
