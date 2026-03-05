from fastapi import FastAPI
from api.routes import templates, forms
from api.errors.handlers import register_exception_handlers

app = FastAPI()

# Register custom exception handlers so AppError is turned into a proper
# JSON response (e.g. {"error": "Template not found"} with status 404)
# instead of crashing with an unhandled 500.
register_exception_handlers(app)

app.include_router(templates.router)
app.include_router(forms.router)