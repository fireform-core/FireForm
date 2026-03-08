import os
from io import BytesIO
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from staticmap import StaticMap, CircleMarker

class Geotagger:
    def __init__(self, user_agent="fireform_geotagger_v1"):
        """
        Initialize the geocoding service using OpenStreetMap's Nominatim API.
        We use a specific user_agent to comply with their usage policy.
        """
        self.geolocator = Nominatim(user_agent=user_agent)

    def get_coordinates(self, location_description: str) -> tuple[float, float] | None:
        """
        Translates a natural language location description into Lat/Lon coordinates.
        Uses Nominatim under the hood. Fails gracefully.
        
        Args:
            location_description: String (e.g. "Eiffel Tower", "Agadir Beach")
            
        Returns:
            (latitude, longitude) tuple, or None if not found/error.
        """
        if not location_description or location_description.lower() in ("unknown", "n/a", "none", "-1"):
            return None

        print(f"\n[GEOCODER] Attempting to geocode: '{location_description}'")
        try:
            location = self.geolocator.geocode(location_description, timeout=10)
            if location:
                print(f"[GEOCODER] Found: {location.address} ({location.latitude}, {location.longitude})")
                return (location.latitude, location.longitude)
            else:
                print(f"[GEOCODER] No coordinates found for: '{location_description}'")
                return None
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            print(f"[GEOCODER] Error communicating with Geolocation API: {e}")
            return None
        except Exception as e:
            print(f"[GEOCODER] Unexpected error: {e}")
            return None

    def generate_map_image(self, lat: float, lon: float, output_path: str = "temp_map.png") -> str | None:
        """
        Generates a static map image centered on the given coordinates with a red pin.
        
        Args:
            lat: Latitude
            lon: Longitude
            output_path: Path to save the resulting .png image.
            
        Returns:
            The absolute path to the generated image, or None on failure.
        """
        if lat is None or lon is None:
            return None
            
        print(f"[GEOCODER] Generating static map image for ({lat}, {lon})...")
        try:
            m = StaticMap(400, 300)
            
            # Create a red circle marker to act as our pin
            marker = CircleMarker((lon, lat), 'red', 12)
            m.add_marker(marker)
            
            # Render and save the map (zoom level 14 is good for cities/landmarks)
            image = m.render(zoom=14)
            image.save(output_path)
            
            print(f"[GEOCODER] Map image saved to: {output_path}")
            return os.path.abspath(output_path)
        except Exception as e:
            print(f"[GEOCODER] Failed to generate map image: {e}")
            return None
