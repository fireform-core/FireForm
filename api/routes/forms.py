from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from api.deps import get_db
from api.schemas.forms import FormFill, FormFillResponse
from api.db.repositories import create_form, get_template
from api.db.models import FormSubmission
from api.errors.base import AppError
from src.controller import Controller
import logging
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forms", tags=["forms"])

@router.post("/fill", response_model=FormFillResponse)
def fill_form(form: FormFill, db: Session = Depends(get_db)):
    """
    Fill a PDF form with AI-extracted data.
    Uses database transactions to ensure data consistency.
    """
    generated_pdf_path = None
    
    try:
        logger.info(f"Processing form fill request for template_id: {form.template_id}")
        
        # Fetch and validate template
        fetched_template = get_template(db, form.template_id)
        if not fetched_template:
            logger.error(f"Template not found: {form.template_id}")
            raise HTTPException(status_code=404, detail="Template not found")

        # Validate template has required fields
        if not fetched_template.fields:
            logger.error(f"Template {form.template_id} has no fields defined")
            raise HTTPException(status_code=400, detail="Template has no fields defined")

        # Validate PDF file exists
        if not os.path.exists(fetched_template.pdf_path):
            logger.error(f"PDF template file not found: {fetched_template.pdf_path}")
            raise HTTPException(status_code=404, detail="PDF template file not found")

        # Create controller and process form
        controller = Controller()
        
        try:
            generated_pdf_path = controller.fill_form(
                user_input=form.input_text, 
                fields=fetched_template.fields, 
                pdf_form_path=fetched_template.pdf_path
            )
        except FileNotFoundError as e:
            logger.error(f"PDF template file not found: {e}", exc_info=True)
            raise HTTPException(status_code=404, detail="PDF template file not found")
        except ValueError as e:
            logger.error(f"Invalid input data: {e}", exc_info=True)
            raise HTTPException(status_code=400, detail="Invalid input data")
        except Exception as e:
            logger.error(f"PDF generation failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="PDF generation failed")

        # Create database record (let SQLModel handle transactions)
        try:
            submission = FormSubmission(
                template_id=form.template_id,
                input_text=form.input_text,
                output_pdf_path=generated_pdf_path
            )
            result = create_form(db, submission)
            
            logger.info(f"Form filled successfully: {result.id}")
            return result
            
        except Exception as e:
            logger.error(f"Database operation failed: {e}", exc_info=True)
            
            # Clean up generated PDF file on database failure
            if generated_pdf_path and os.path.exists(generated_pdf_path):
                try:
                    os.remove(generated_pdf_path)
                    logger.info(f"Cleaned up PDF file after DB failure: {generated_pdf_path}")
                except OSError as cleanup_error:
                    logger.warning(f"Failed to clean up PDF file {generated_pdf_path}: {cleanup_error}")
            
            raise HTTPException(status_code=500, detail="Database operation failed")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in form filling: {e}", exc_info=True)
        
        # Clean up any generated files on unexpected errors
        if generated_pdf_path and os.path.exists(generated_pdf_path):
            try:
                os.remove(generated_pdf_path)
                logger.info(f"Cleaned up PDF file after unexpected error: {generated_pdf_path}")
            except OSError:
                pass
                
        raise HTTPException(status_code=500, detail="Internal server error")


