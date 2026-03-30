from typing import Optional, Dict, Any
from src.schemas import IncidentReport
import logging

logger = logging.getLogger("fireform_self_correction")

def check_missing_fields(report: IncidentReport) -> list[str]:
    """
    Validates semantic requirements beyond purely type/schema logic.
    For instance, if units_responding array is empty, we must prompt for it.
    If the location is extremely vague or missing entirely.
    """
    missing = []
    if not report.units_responding or len(report.units_responding) == 0:
        missing.append("units_responding")
        
    if report.location.strip() == "" or report.location.lower() == "unknown":
        missing.append("location")
        
    return missing

def self_correction_loop(original_narrative: str, prior_report: IncidentReport, attempts: int = 0) -> Optional[dict]:
    """
    Checks for missing fields. If any are missing, crafts a targeted prompt 
    that the UI/voice interface can use to ask the operator.
    Returns a dict with {"success": bool, "prompt": str} if more info needed.
    """
    MAX_ATTEMPTS = 2
    
    missing_fields = check_missing_fields(prior_report)
    
    if not missing_fields:
        return {"success": True, "report": prior_report}
        
    if attempts >= MAX_ATTEMPTS:
        logger.warning("Max attempts reached for self-correction. Falling back to manual review.")
        # Mark human review on confidence score pseudo-logic
        # For simplicity, returning failure forcing manual intervention
        return {
            "success": False, 
            "message": f"Could not extract {', '.join(missing_fields)} after {MAX_ATTEMPTS} attempts. Please enter manually.",
            "report": prior_report
        }
        
    # Craft a targeted question based on what's missing
    # E.g., The user's report is missing the number of injuries...
    user_prompt = "The report is missing some details. Please provide: "
    if "units_responding" in missing_fields:
        user_prompt += "Which fire or medical units responded? "
    if "location" in missing_fields:
        user_prompt += "What was the exact address or location? "
        
    return {
        "success": False,
        "prompt": user_prompt,
        "missing_fields": missing_fields
    }
