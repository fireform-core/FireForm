import pytest
from unittest.mock import patch, MagicMock
from src.geocoder import Geotagger
from geopy.exc import GeocoderTimedOut

class TestGeotagger:
    def test_get_coordinates_success(self):
        """Test that a valid location returns coordinates."""
        geotagger = Geotagger()
        
        # Mock the geolocator response
        mock_location = MagicMock()
        mock_location.latitude = 48.8584
        mock_location.longitude = 2.2945
        mock_location.address = "Eiffel Tower, Paris"
        
        with patch.object(geotagger.geolocator, 'geocode', return_value=mock_location):
            result = geotagger.get_coordinates("Eiffel Tower")
            
        assert result == (48.8584, 2.2945)

    def test_get_coordinates_not_found(self):
        """Test that an invalid location returns None."""
        geotagger = Geotagger()
        
        with patch.object(geotagger.geolocator, 'geocode', return_value=None):
            result = geotagger.get_coordinates("Some Fake Place That Does Not Exist")
            
        assert result is None
        
    def test_get_coordinates_timeout_handling(self):
        """Test that network timeouts are caught and return None gracefully."""
        geotagger = Geotagger()
        
        with patch.object(geotagger.geolocator, 'geocode', side_effect=GeocoderTimedOut("Timeout")):
            result = geotagger.get_coordinates("Eiffel Tower")
            
        assert result is None

    def test_empty_or_unknown_string_returns_none(self):
        """Test that empty or filler strings instantly return None without network calls."""
        geotagger = Geotagger()
        
        with patch.object(geotagger.geolocator, 'geocode') as mock_geocode:
            assert geotagger.get_coordinates("") is None
            assert geotagger.get_coordinates("unknown") is None
            assert geotagger.get_coordinates("-1") is None
            
        mock_geocode.assert_not_called()

    def test_generate_map_image_success(self):
        """Test map generation returns a path."""
        geotagger = Geotagger()
        
        # Patch the StaticMap methods so we don't actually hit the OSM tile servers in tests
        with patch('src.geocoder.StaticMap') as MockStaticMap:
            mock_map_instance = MagicMock()
            mock_image = MagicMock()
            mock_map_instance.render.return_value = mock_image
            MockStaticMap.return_value = mock_map_instance
            
            result = geotagger.generate_map_image(48.8584, 2.2945, output_path="test_map.png")
            
            assert result is not None
            assert "test_map.png" in result
            mock_image.save.assert_called_once_with("test_map.png")

    def test_generate_map_image_with_none_coords(self):
        """Test map generation with None coordinates."""
        geotagger = Geotagger()
        result = geotagger.generate_map_image(None, 2.2945)
        assert result is None
