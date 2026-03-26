"""
Validation utilities for FireForm extraction results.
"""
import logging

logger = logging.getLogger(__name__)


def requires_review(data: dict, required_fields: list) -> bool:
    """
    Check if extracted data requires manual review.
    
    Returns True if any required field is missing, empty, or has the default "-1" value.
    
    Args:
        data: Dictionary of extracted field values
        required_fields: List of field names that must be present
        
    Returns:
        bool: True if manual review is needed, False otherwise
        
    Thread-safe: Yes (read-only operations on immutable inputs)
    """
    # Input validation
    if not isinstance(data, dict):
        logger.warning(f"Invalid data type: {type(data)}, expected dict")
        return True
    
    if not isinstance(required_fields, (list, tuple, set)):
        logger.warning(f"Invalid required_fields type: {type(required_fields)}")
        return True
    
    # Empty data always needs review
    if not data:
        logger.debug("Empty data dictionary - review required")
        return True
    
    # No required fields means no review needed
    if not required_fields:
        logger.debug("No required fields specified - no review needed")
        return False
    
    # Check each required field
    for field in required_fields:
        # Validate field name
        if not isinstance(field, str):
            logger.warning(f"Invalid field name type: {type(field)} for field value: {repr(field)[:100]} - review required")
            return True  # Invalid field type requires review
        
        # Get value safely
        try:
            value = data.get(field)
        except (AttributeError, TypeError) as e:
            logger.error(f"Error accessing field '{field}': {e}")
            return True
        
        # Missing field
        if value is None:
            logger.debug(f"Field '{field}' is None - review required")
            return True
        
        # Check string values
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped or stripped == "-1":
                logger.debug(f"Field '{field}' is empty or default - review required")
                return True
        
        # Check list values
        elif isinstance(value, list):
            if not value:
                logger.debug(f"Field '{field}' is empty list - review required")
                return True
            # Check if all items are empty or default
            if all(
                (isinstance(v, str) and v.strip() in ["", "-1"]) or v is None
                for v in value
            ):
                logger.debug(f"Field '{field}' has only empty/default values - review required")
                return True
        
        # Other types (int, float, bool) are considered valid
        # unless they're 0/False, which we'll accept as valid values
    
    logger.debug("All required fields present and valid - no review needed")
    return False
