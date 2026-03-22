from fastapi import FastAPI
from api.routes import templates, forms

app = FastAPI()

app.include_router(templates.router)
app.include_router(forms.router)