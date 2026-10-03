from fastapi import Header, Request

from app.core.config import FIREFORM_API_KEY
from app.core.errors.base import AppError
from app.db.database import get_session


def get_db():
    yield from get_session()

def verify_api_key(request: Request, x_api_key: str | None = Header(None)):
    if not FIREFORM_API_KEY:
        return
    
    provided_key = x_api_key
    if not provided_key:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            provided_key = auth_header[len("Bearer "):]
            
    if not provided_key or provided_key != FIREFORM_API_KEY:
        raise AppError("Unauthorized", status_code=401, error_code="UNAUTHORIZED")