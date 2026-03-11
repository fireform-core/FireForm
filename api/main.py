from fastapi import FastAPI
from api.routes import templates, forms, profiles

app = FastAPI()

app.include_router(templates.router)
app.include_router(forms.router)
app.include_router(profiles.router)