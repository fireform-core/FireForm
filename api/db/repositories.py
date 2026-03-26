from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError, OperationalError, DatabaseError as SQLAlchemyDatabaseError
from api.db.models import Template, FormSubmission
import logging

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom exception for database operations"""
    pass

# Templates
def create_template(session: Session, template: Template) -> Template:
    """
    Create a new template with validation.
    
    Args:
        session: Database session
        template: Template object to create
        
    Returns:
        Template: Created template with ID
        
    Raises:
        ValueError: If template data is invalid
    """
    if not template:
        raise ValueError("Template cannot be None")
    
    if not template.name or not template.name.strip():
        raise ValueError("Template name is required")
    
    if not template.pdf_path or not template.pdf_path.strip():
        raise ValueError("Template PDF path is required")
    
    if not template.fields or not isinstance(template.fields, dict):
        raise ValueError("Template fields must be a non-empty dictionary")
    
    try:
        session.add(template)
        session.commit()
        session.refresh(template)
        logger.info(f"Created template: {template.id}")
        return template
    except IntegrityError as e:
        session.rollback()
        logger.error(f"Integrity error creating template: {e}", exc_info=True)
        raise DatabaseError("Template integrity constraint violated") from e
    except OperationalError as e:
        session.rollback()
        logger.error(f"Database operational error creating template: {e}", exc_info=True)
        raise DatabaseError("Database operation failed") from e
    except SQLAlchemyDatabaseError as e:
        session.rollback()
        logger.error(f"Database error creating template: {e}", exc_info=True)
        raise DatabaseError("Database error occurred") from e
    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error creating template: {e}", exc_info=True)
        raise DatabaseError("Failed to create template") from e

def get_template(session: Session, template_id: int) -> Template | None:
    """
    Get template by ID with validation.
    
    Args:
        session: Database session
        template_id: Template ID to retrieve
        
    Returns:
        Template | None: Template if found, None otherwise
        
    Raises:
        ValueError: If template_id is invalid
        Exception: If database operation fails (propagated)
    """
    # Explicitly reject booleans (bool is a subclass of int)
    if isinstance(template_id, bool) or not isinstance(template_id, int) or template_id <= 0:
        raise ValueError("Template ID must be a positive integer")
    
    try:
        return session.get(Template, template_id)
    except Exception as e:
        logger.error(f"Failed to get template {template_id}: {e}", exc_info=True)
        raise

# Forms
def create_form(session: Session, form: FormSubmission) -> FormSubmission:
    """
    Create a new form submission with validation.
    
    Args:
        session: Database session
        form: FormSubmission object to create
        
    Returns:
        FormSubmission: Created form with ID
        
    Raises:
        ValueError: If form data is invalid
    """
    if not form:
        raise ValueError("Form cannot be None")
    
    # Explicitly reject booleans (bool is a subclass of int)
    if isinstance(form.template_id, bool) or not isinstance(form.template_id, int) or form.template_id <= 0:
        raise ValueError("Template ID must be a positive integer")
    
    if not form.input_text or not form.input_text.strip():
        raise ValueError("Input text is required")
    
    if not form.output_pdf_path or not form.output_pdf_path.strip():
        raise ValueError("Output PDF path is required")
    
    try:
        session.add(form)
        session.commit()
        session.refresh(form)
        logger.info(f"Created form submission: {form.id}")
        return form
    except IntegrityError as e:
        session.rollback()
        logger.error(f"Integrity error creating form submission: {e}", exc_info=True)
        raise DatabaseError("Form submission integrity constraint violated") from e
    except OperationalError as e:
        session.rollback()
        logger.error(f"Database operational error creating form submission: {e}", exc_info=True)
        raise DatabaseError("Database operation failed") from e
    except SQLAlchemyDatabaseError as e:
        session.rollback()
        logger.error(f"Database error creating form submission: {e}", exc_info=True)
        raise DatabaseError("Database error occurred") from e
    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error creating form submission: {e}", exc_info=True)
        raise DatabaseError("Failed to create form submission") from e