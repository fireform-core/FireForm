from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from api.deps import get_db
from api.schemas.templates import TemplateCreate, TemplateResponse
from api.db.repositories import create_template
from api.db.models import Template
from src.controller import Controller
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/templates", tags=["templates"])

# Configure base uploads directory
BASE_UPLOADS_DIR = os.getenv("BASE_UPLOADS_DIR", "src/inputs")

@router.post("/create", response_model=TemplateResponse)
def create(template: TemplateCreate, db: Session = Depends(get_db)):
    """
    Create a new PDF template with proper validation and error handling.
    """
    try:
        logger.info(f"Creating template: {template.name}")
        
        # Resolve and validate path against base uploads directory
        try:
            pdf_path = Path(template.pdf_path)
            resolved_path = pdf_path.resolve()
            base_dir = Path(BASE_UPLOADS_DIR).resolve()
            
            if not str(resolved_path).startswith(str(base_dir)):
                logger.error(f"Path traversal attempt detected: {template.pdf_path}")
                raise HTTPException(status_code=403, detail="Access denied: path outside allowed directory")
            
            # Use the validated resolved path for all subsequent checks
            validated_path = resolved_path
            
        except (ValueError, OSError) as e:
            logger.error(f"Invalid path: {template.pdf_path} - {e}")
            raise HTTPException(status_code=400, detail="Invalid file path")
        
        # Validate PDF file exists before processing
        if not validated_path.exists():
            logger.error(f"PDF file not found: {validated_path}")
            raise HTTPException(status_code=404, detail="PDF file not found")
        
        # Check file permissions
        if not os.access(validated_path, os.R_OK):
            logger.error(f"Cannot read PDF file: {validated_path}")
            raise HTTPException(status_code=403, detail="Cannot read PDF file")
        
        # Create controller and process template
        controller = Controller()
        
        try:
            template_path = controller.create_template(str(validated_path))
        except FileNotFoundError as e:
            logger.error(f"Template creation failed - file not found: {e}", exc_info=True)
            raise HTTPException(status_code=404, detail="PDF file not found")
        except ValueError as e:
            logger.error(f"Template creation failed - invalid input: {e}", exc_info=True)
            raise HTTPException(status_code=400, detail="Invalid PDF file")
        except Exception as e:
            logger.error(f"Template creation failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Template creation failed")
        
        # Create database record
        try:
            tpl = Template(**template.model_dump(exclude={"pdf_path"}), pdf_path=template_path)
            result = create_template(db, tpl)
            
            logger.info(f"Template created successfully: {result.id}")
            return result
            
        except Exception as e:
            logger.error(f"Database operation failed: {e}", exc_info=True)
            
            # Clean up generated template file on database failure
            if template_path and os.path.exists(template_path):
                try:
                    os.remove(template_path)
                    logger.info(f"Cleaned up template file after DB failure: {template_path}")
                except OSError as cleanup_error:
                    logger.warning(f"Failed to clean up template file: {cleanup_error}")
            
            raise HTTPException(status_code=500, detail="Database operation failed")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in template creation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")