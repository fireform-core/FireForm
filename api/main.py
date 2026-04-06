from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import templates, forms, report_schemas
from api.errors.handlers import register_exception_handlers

app = FastAPI()
register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(templates.router)
app.include_router(forms.router)
app.include_router(report_schemas.router)