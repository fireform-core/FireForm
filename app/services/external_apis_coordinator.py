from app.services.external_apis.weather_api import WeatherAPI
from app.services.external_apis.zipcode_api import ZipCodeAPI


class ExternalAPIsCoordinator:
    def __init__(self):
        self.weather_api = WeatherAPI()
        self.zipcode_api = ZipCodeAPI()
    
    def get_weather(self, latitude: float, longitude: float, start_date: str, end_date: str, hourly_fields: list[str] | None = None):
        return self.weather_api.get_weather(latitude, longitude, start_date, end_date, hourly_fields)

    def lookup_address(self, address: str) -> list[dict]:
        return self.zipcode_api.lookup_address(address)