import logging
import os
from contextlib import contextmanager
from typing import Optional
from openai import OpenAI
import instructor

from src.schemas import IncidentReport

# Configure audit logger
# In production, this logger should target an append-only file or remote logging service
audit_logger = logging.getLogger("fireform_audit")
audit_logger.setLevel(logging.INFO)
if not audit_logger.handlers:
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    audit_logger.addHandler(ch)

def get_instructor_client() -> instructor.Instructor:
    """
    Creates an OpenAI client pointed to the local Ollama instance
    and patches it with instructor for constrained generation.
    """
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    # Base URL must end with /v1 for Ollama's OpenAI API compatibility layer
    if not ollama_host.endswith("/v1"):
        ollama_host = f"{ollama_host.rstrip('/')}/v1"
        
    client = OpenAI(
        base_url=ollama_host,
        api_key="ollama",  # Any arbitrary string works for Ollama locally
    )
    return instructor.from_openai(client, mode=instructor.Mode.JSON)

def sanitize_input(text: str) -> str:
    """
    Basic sanitization to neutralize prompt injection tokens where possible.
    More aggressive filtering could be added here.
    """
    return text.replace("<|im_start|>", "").replace("<|im_end|>", "").strip()

def extract_incident(text: str, context: Optional[str] = None) -> IncidentReport:
    """
    Extracts an IncidentReport from unstructured text using local LLMs.
    Employs strict JSON response formats and validates against Pydantic rules.
    Retries automatically if the generated structure violates the business rules.
    """
    text = sanitize_input(text)
    
    # Audit trail: Log the access and the fact that an extraction is initializing.
    audit_logger.info("Initializing extraction sequence for narrative (length: %d)", len(text))
    
    client = get_instructor_client()
    
    system_prompt = (
        "You are an expert fire department data extraction AI. "
        "Your task is to extract an IncidentReport from the provided narrative strictly following "
        "the provided schema. Ensure accuracy, don't invent details."
    )
    if context:
        system_prompt += f"\n\nHere are some successful examples for reference:\n{context}"

    # We use instructor's built-in validation retry pipeline
    try:
        report = client.chat.completions.create(
            # Using 'llama3' as standard for Ollama, can be parameterized
            model="llama3", 
            response_model=IncidentReport,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract the IncidentReport from this narrative:\n\n{text}"}
            ],
            max_retries=3,
        )
        audit_logger.info("Extraction completed successfully for incident type: %s", report.incident_type.value)
        return report
    except Exception as e:
        audit_logger.error("Extraction failed: %s", str(e))
        raise ValueError(f"Failed to extract structured data: {e}")
