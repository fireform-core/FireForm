from fastapi import APIRouter, Depends, HTTPException
import logging
from sqlmodel import Session
from api.deps import get_db
from api.schemas.templates import TemplateCreate, TemplateResponse
from api.db.repositories import create_template
from api.db.models import Template
from src.controller import Controller

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/templates", tags=["templates"])

@router.post("/create", response_model=TemplateResponse)
def create(template: TemplateCreate, db: Session = Depends(get_db)):
    try:
        controller = Controller()
        template_path = controller.create_template(template.pdf_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="The PDF file could not be found at the provided path. Please verify the file exists.",
        )
    except ImportError as exc:
        logger.error("Missing dependency during template creation: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="A required dependency for template processing is not installed in this environment.",
        )
    except PermissionError:
        raise HTTPException(
            status_code=500,
            detail="FireForm does not have write permission to save the generated template file.",
        )
    except Exception as exc:
        logger.exception("Unexpected error during template creation")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while creating the template. Check server logs for details.",
        )
    tpl = Template(**template.model_dump(exclude={"pdf_path"}), pdf_path=template_path)
    return create_template(db, tpl)