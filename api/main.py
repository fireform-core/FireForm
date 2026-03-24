from fastapi import FastAPI
from api.routes import templates, forms
from api.routes import transcribe

app = FastAPI()

app.include_router(templates.router)
app.include_router(forms.router)
app.include_router(transcribe.router)