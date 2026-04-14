from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import forms, templates
from api.db.db import engine
from api.db.models import Template, FormSubmission

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Template.metadata.create_all(bind=engine)
FormSubmission.metadata.create_all(bind=engine)

app.include_router(templates.router)
app.include_router(forms.router)