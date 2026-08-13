from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

from app.core.logging import get_logger

logger = get_logger(__name__)

_GEOLOCATOR = Nominatim(user_agent="fireform", timeout=10)


class ZipCodeAPI:
    def __init__(self):
        pass

    def lookup_address(self, address: str) -> list[dict]:
        """
        Look up an address string via OpenStreetMap Nominatim and return a list
        of matching locations with their postal codes, coordinates, and names.

        Args:
            address: Full address string, e.g. "1600 Amphitheatre Parkway, Mountain View, CA, US"

        Returns:
            A list of dicts, each containing:
              - postal_code (str | None)
              - place_name (str)
              - latitude (float)
              - longitude (float)
              - display_name (str)
              - country (str | None)
              - state (str | None)
              - county (str | None)
        """
        try:
            locations = _GEOLOCATOR.geocode(
                address,
                exactly_one=False,
                addressdetails=True,
                limit=10,
            )
        except GeocoderTimedOut:
            logger.error("Nominatim geocoding timed out for address: %s", address)
            raise TimeoutError(f"Geocoding service timed out for address: '{address}'")
        except GeocoderServiceError as exc:
            logger.error("Nominatim geocoding service error: %s", exc)
            raise RuntimeError(f"Geocoding service error: {exc}")

        if not locations:
            logger.info("No results found for address: %s", address)
            return []

        results = []
        for loc in locations:
            addr = loc.raw.get("address", {})
            results.append({
                "postal_code": addr.get("postcode"),
                "place_name": addr.get("city")
                    or addr.get("town")
                    or addr.get("village")
                    or addr.get("hamlet")
                    or addr.get("municipality")
                    or "",
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "display_name": loc.address,
                "country": addr.get("country"),
                "state": addr.get("state"),
                "county": addr.get("county"),
            })
            logger.debug("Geocoded result: %s", results[-1])

        return results