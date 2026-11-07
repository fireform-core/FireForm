from fastapi import APIRouter

from app.api.routes import (
    forms,
    input,
    jobs,
    llm,
    llm_config,
    profiles,
    reports,
    system,
    templates,
    weather,
    zipcode,
)
from app.core.config import API_PREFIX

api_router = APIRouter()
api_router.include_router(templates.router, prefix=API_PREFIX)
api_router.include_router(forms.router, prefix=API_PREFIX)
api_router.include_router(system.router, prefix=API_PREFIX)
api_router.include_router(llm.router, prefix=API_PREFIX)
api_router.include_router(llm_config.router, prefix=API_PREFIX)
api_router.include_router(jobs.router, prefix=API_PREFIX)
api_router.include_router(weather.router, prefix=API_PREFIX)
api_router.include_router(zipcode.router, prefix=API_PREFIX)
api_router.include_router(input.router, prefix=API_PREFIX)
api_router.include_router(profiles.router, prefix=API_PREFIX)
api_router.include_router(profiles.router)
api_router.include_router(reports.router, prefix=API_PREFIX)
