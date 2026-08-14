from fastapi import APIRouter

from app.core.errors.base import AppError
from app.services.controller import Controller

router = APIRouter(prefix="/zipcode", tags=["zipcode"])


@router.get("/lookup-address")
def lookup_address(address: str):
    """
    Resolve a free-form address to one or more geographic locations including
    postal code, latitude, longitude, place name, state, county, and country.

    Returns a list of matching results ordered by relevance (most relevant first).
    Each result is guaranteed to include `latitude` and `longitude`; `postal_code`
    is present when the geocoding service can determine it for the given address.

    Example: 
        address = "1600 Amphitheatre Parkway, Mountain View, CA, US"
    """
    controller = Controller()
    try:
        return controller.lookup_address(address)
    except TimeoutError as e:
        raise AppError(str(e), status_code=504)
    except Exception as e:
        raise AppError(str(e), status_code=500)
