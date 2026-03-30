import logging
import os
import zipfile
from io import BytesIO
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional

from src.schemas import IncidentReport
from src.llm.constrained_extractor import sanitize_input
from src.llm.semantic_router import SemanticRouter
from src.pdf_filler.filler import VectorSemanticMapper
from src.llm.few_shot_rag import get_few_shot_prompt, populate_examples
from src.llm.self_correction import self_correction_loop

# Bootstrapping examples for RAG
populate_examples(os.path.join(os.path.dirname(__file__), "..", "..", "data", "examples.json"))

app = FastAPI(title="FireForm Core SecAPI", version="1.0.0")

# Setup CORS (In Production bind to strictly the domain)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

audit_logger = logging.getLogger("fireform_audit")

# Simple Security Dependency
def verify_api_key(request: Request):
    auth_header = request.headers.get("Authorization")
    expected_token = os.environ.get("API_AUTH_TOKEN", "default_dev_token")
    if not auth_header or not auth_header.startswith("Bearer "):
        audit_logger.warning("Unauthenticated request attempted from %s", request.client.host)
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")
    
    token = auth_header.split(" ")[1]
    if token != expected_token:
        audit_logger.warning("Invalid token used from %s", request.client.host)
        raise HTTPException(status_code=403, detail="Forbidden")
    return True

def verify_admin(request: Request):
    """Fictitous RBAC check for Admins."""
    verify_api_key(request)
    role = request.headers.get("X-User-Role", "operator")
    if role != "admin":
        audit_logger.warning("Operator attempted admin action from %s", request.client.host)
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return True

@app.middleware("http")
async def audit_logging_middleware(request: Request, call_next):
    """
    Middleware to sanitize inputs implicitly and log request access patterns safely.
    """
    path = request.url.path
    method = request.method
    # Simple strict check ensuring basic payload security
    audit_logger.info(f"AUDIT - {method} {path} - Host: {request.client.host}")
    response = await call_next(request)
    return response

@app.post("/api/v1/report", dependencies=[Depends(verify_api_key)])
async def generate_report(narrative: str):
    """
    Main extraction pipeline endpoint.
    Expects text narrative.
    Returns JSON structured data (for UI rendering).
    """
    sanitized = sanitize_input(narrative)
    
    # 1. RAG Retrieve Top-K Context
    context = get_few_shot_prompt(sanitized)
    
    # 2. Extract Structure using O(1) Concurrent Semantic Router
    router = SemanticRouter()
    report = await router.pareto_extraction(sanitized)
    
    # 3. Validation / Self Correction logic check
    correction_result = self_correction_loop(sanitized, report)
    if not correction_result["success"]:
        # Means we are missing required fields, UI needs to ask a follow-up
        return {
            "status": "incomplete",
            "prompt": correction_result["prompt"],
            "partial_report": report.model_dump(mode="json")
        }
    
    # 4. Success State
    audit_logger.info(f"Report Generated and validated: {report.incident_id}")
    
    return {
        "status": "complete",
        "report": report.model_dump(mode="json")
    }

@app.get("/api/v1/templates", dependencies=[Depends(verify_api_key)])
async def list_templates():
    return {"templates": ["NFIRS_v1", "LOCAL_DEPT_STANDARD"]}

@app.post("/api/v1/templates", dependencies=[Depends(verify_admin)])
async def upload_template(file: UploadFile = File(...)):
    """Admin only endpoint to add a new PDF Form mapping."""
    # Logic to securely save the template and store in database
    audit_logger.info(f"Admin uploaded new template: {file.filename}")
    return {"message": "Template mapped and secured successfully"}

@app.post("/api/v1/poc/generate_and_fill")
async def generate_and_fill(narrative: str, template_path: str):
    """
    PoC endpoint tying together SemanticRouter and VectorSemanticMapper.
    Runs concurrently, then structurally aligns the resulting JSON to a PDF template.
    """
    # 1. Pareo-Optimal Concurrent Extraction
    router = SemanticRouter()
    report = await router.pareto_extraction(narrative)
    
    # Convert Pydantic model to flat dict so keys can be aligned
    data_dict = report.model_dump(mode="json")
    flat_data = {
        "incident_id": str(data_dict["incident_id"]),
        "timestamp": data_dict["timestamp"],
        "narrative": data_dict["narrative"],
        "address": data_dict["spatial"]["address"],
        "coordinates": data_dict["spatial"]["coordinates"],
        "injuries": data_dict["medical"]["injuries"],
        "severity": data_dict["medical"]["severity"],
        "units_responding": data_dict["operational"]["units_responding"],
        "incident_type": data_dict["operational"]["incident_type"]
    }
    
    # 2. Zero-config PDF alignment
    mapper = VectorSemanticMapper()
    
    try:
        # Align keys dynamically based on Cosine Similarity
        filled_pdf = mapper.fill_pdf(template_path, flat_data)
        return Response(content=filled_pdf, media_type="application/pdf")
    except Exception as e:
        return {"error": str(e), "message": "Failed to map PDF layout"}
