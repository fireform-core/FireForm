import os
from fastapi import APIRouter, Depends
from sqlmodel import Session
from api.deps import get_db
from api.schemas.forms import FormFill, FormFillResponse
from api.db.repositories import get_template
from api.db.models import FormSubmission
from api.errors.base import AppError
from src.controller import Controller

router = APIRouter(prefix="/forms", tags=["forms"])

@router.post("/fill", response_model=FormFillResponse)
def fill_form(form: FormFill, db: Session = Depends(get_db)):
    if not get_template(db, form.template_id):
        raise AppError("Template not found", status_code=404)

    fetched_template = get_template(db, form.template_id)
    
    try:
        controller = Controller()
        path = controller.fill_form(
            user_input=form.input_text,
            fields=fetched_template.fields,
            pdf_form_path=fetched_template.pdf_path
        )
        
        # Validate PDF file was created successfully
        if not os.path.exists(path):
            raise FileNotFoundError(f"PDF generation failed: file not found at {path}")
        
        file_size = os.path.getsize(path)
        if file_size == 0:
            raise ValueError(f"PDF generation created empty file at {path}")
        
        # Create database record only after validation
        submission = FormSubmission(**form.model_dump(), output_pdf_path=path)
        db.add(submission)
        db.commit()
        db.refresh(submission)
        
        return submission
        
    except (FileNotFoundError, ValueError) as e:
        db.rollback()
        raise AppError(f"PDF generation failed: {str(e)}", status_code=500)
    except Exception as e:
        db.rollback()
        raise


