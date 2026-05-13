from fastapi import APIRouter
from src.controller import Controller
from api.errors.base import AppError

router = APIRouter(prefix="/weather", tags=["weather"])

@router.get("/forecast")
def get_weather_forecast(latitude: float, longitude: float):
    """
    Fetch weather forecast data for the given coordinates.
    """
    controller = Controller()
    try:
        weather_data = controller.get_weather(latitude, longitude)
        return weather_data
    except Exception as e:
        raise AppError(str(e), status_code=500)
