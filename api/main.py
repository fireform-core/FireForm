from fastapi import FastAPI
from api.routes import templates, forms
from api.similarity_api import router as similarity_router

app = FastAPI()
app.include_router(similarity_router)
app.include_router(templates.router)
app.include_router(forms.router)