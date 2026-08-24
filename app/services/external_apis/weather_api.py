import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry

# All supported hourly fields exposed by this service
ALL_HOURLY_FIELDS = [
    "temperature_2m",
    "relative_humidity_2m",
    "rain",
    "apparent_temperature",
    "precipitation_probability",
    "precipitation",
    "wind_direction_10m",
    "wind_speed_10m",
    "soil_temperature_0cm",
    "uv_index",
]

class WeatherAPI:
    def __init__(self):
        pass

    def get_weather(self, latitude: float, longitude: float, start_date: str, end_date: str, hourly_fields: list[str] | None = None):
        """
        Get weather data for a given latitude and longitude.

        Args:
            latitude (float): The latitude of the location.
            longitude (float): The longitude of the location.
            hourly_fields (list[str] | None): Subset of hourly variables to request.
                Defaults to ALL_HOURLY_FIELDS when None or empty.
            
        Returns:
            dict: A dictionary containing the weather data.
        """
        requested = [f for f in (hourly_fields or []) if f in ALL_HOURLY_FIELDS]
        if not requested:
            requested = list(ALL_HOURLY_FIELDS)

        # Setup the Open-Meteo API client with cache and retry on error
        cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
        retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        openmeteo = openmeteo_requests.Client(session=retry_session)

        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": requested,
            "start_date": start_date,
	        "end_date": end_date,
        }
        responses = openmeteo.weather_api(url, params=params)

        response = responses[0]

        hourly = response.Hourly()

        hourly_data: dict = {
            "date": pd.date_range(
                start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
                end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
                freq=pd.Timedelta(seconds=hourly.Interval()),
                inclusive="left",
            )
        }

        for i, field in enumerate(requested):
            hourly_data[field] = hourly.Variables(i).ValuesAsNumpy().tolist()

        # Convert pandas Timestamp objects to ISO strings for JSON serialization
        hourly_data["date"] = [d.isoformat() for d in hourly_data["date"]]

        return {
            "latitude": response.Latitude(),
            "longitude": response.Longitude(),
            "elevation": response.Elevation(),
            "timezone": response.Timezone(),
            "timezone_abbreviation": response.TimezoneAbbreviation(),
            "utc_offset_seconds": response.UtcOffsetSeconds(),
            "hourly": hourly_data,
        }