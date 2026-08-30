from fastapi import APIRouter

from app.api.routes import (
    extraction,
    form_generation,
    forms,
    form_templates,
    incidents,
    input,
    jobs,
    system,
    weather,
    zipcode,
)
from app.core.config import API_PREFIX

api_router = APIRouter()
api_router.include_router(form_templates.router, prefix=API_PREFIX)
api_router.include_router(forms.router, prefix=API_PREFIX)
# v1 form generation — same "/forms" prefix as the legacy router above, kept
# in a separate file/router rather than added to forms.py. Included AFTER
# `forms` on purpose: the legacy router's literal GET paths (/forms/models,
# /forms/submissions, ...) must be matched before this router's catch-all
# GET /forms/{form_id}, same reasoning form_templates.py uses for /pdf vs
# /{template_id} — otherwise "models"/"submissions" would be read as a form_id.
api_router.include_router(form_generation.router, prefix=API_PREFIX)
api_router.include_router(system.router, prefix=API_PREFIX)
api_router.include_router(jobs.router, prefix=API_PREFIX)
api_router.include_router(weather.router, prefix=API_PREFIX)
api_router.include_router(zipcode.router, prefix=API_PREFIX)
api_router.include_router(input.router, prefix=API_PREFIX)
api_router.include_router(extraction.router, prefix=API_PREFIX)
api_router.include_router(incidents.router, prefix=API_PREFIX)