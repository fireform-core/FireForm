from fastapi import FastAPI

from api.admin_sqladmin import setup_admin
from api.routes import templates, forms

app = FastAPI()

app.include_router(templates.router)
app.include_router(forms.router)

setup_admin(app)