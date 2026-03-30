from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from api.routes import templates, forms, transcribe, incidents
from api.errors.base import AppError
from typing import Union
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(AppError)
def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message}
    )

app.include_router(templates.router)
app.include_router(forms.router)
app.include_router(transcribe.router)
app.include_router(incidents.router)

if os.path.exists("mobile"):
    app.mount("/mobile", StaticFiles(directory="mobile", html=True), name="mobile")