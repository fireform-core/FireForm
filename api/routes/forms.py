from fastapi import APIRouter, Depends, HTTPException
import logging
from sqlmodel import Session
from api.deps import get_db
from api.schemas.forms import FormFill, FormFillResponse
from api.db.repositories import create_form, get_template
from api.db.models import FormSubmission
from api.errors.base import AppError
from src.controller import Controller

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forms", tags=["forms"])

@router.post("/fill", response_model=FormFillResponse)
def fill_form(form: FormFill, db: Session = Depends(get_db)):
    if not get_template(db, form.template_id):
        raise AppError("Template not found", status_code=404)

    fetched_template = get_template(db, form.template_id)

    try:
        controller = Controller()
        path = controller.fill_form(user_input=form.input_text, fields=fetched_template.fields, pdf_form_path=fetched_template.pdf_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="The template PDF file is missing from disk. It may have been moved or deleted since the template was created.",
        )
    except ConnectionError:
        raise HTTPException(
            status_code=503,
            detail="Could not connect to the LLM service (Ollama). Please ensure it is running.",
        )
    except ImportError as exc:
        logger.error("Missing dependency during form fill: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="A required dependency for form processing is not installed in this environment.",
        )
    except PermissionError:
        raise HTTPException(
            status_code=500,
            detail="FireForm does not have write permission to save the filled PDF output.",
        )
    except Exception as exc:
        logger.exception("Unexpected error during form fill")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while filling the form. Check server logs for details.",
        )

    submission = FormSubmission(**form.model_dump(), output_pdf_path=path)
    return create_form(db, submission)


