"""Tests for trusted weather and geographic context enrichment."""

from src.context_enrichment import (
    ContextEnricher,
    GeographicContext,
    WeatherContext,
)


class FakeGeocodingProvider:
    def geocode(self, address):
        assert address == "142 Oak Street"
        return GeographicContext(
            latitude=37.7749,
            longitude=-122.4194,
            jurisdiction="Santa Cruz County",
            district="CAL FIRE CZU",
            source="mock-osm",
        )


class FakeWeatherProvider:
    def get_weather(self, latitude, longitude, incident_time):
        assert latitude == 37.7749
        assert longitude == -122.4194
        assert incident_time == "2026-04-20T18:40:00"
        return WeatherContext(
            temperature="72 F",
            humidity="31%",
            wind_speed="14 mph",
            source="mock-noaa",
        )


class FailingWeatherProvider:
    def get_weather(self, latitude, longitude, incident_time):
        raise RuntimeError("provider unavailable")


def test_context_enricher_combines_weather_and_geographic_context():
    enricher = ContextEnricher(
        weather_provider=FakeWeatherProvider(),
        geocoding_provider=FakeGeocodingProvider(),
    )

    result = enricher.enrich(
        incident_address="142 Oak Street",
        incident_time="2026-04-20T18:40:00",
    )

    assert result.to_dict() == {
        "weather": {
            "temperature": "72 F",
            "humidity": "31%",
            "wind_speed": "14 mph",
            "source": "mock-noaa",
        },
        "geography": {
            "latitude": 37.7749,
            "longitude": -122.4194,
            "jurisdiction": "Santa Cruz County",
            "district": "CAL FIRE CZU",
            "source": "mock-osm",
        },
        "warnings": [],
    }


def test_context_enricher_handles_missing_address_without_crashing():
    enricher = ContextEnricher(weather_provider=FakeWeatherProvider())

    result = enricher.enrich(incident_time="2026-04-20T18:40:00")

    assert result.weather is None
    assert result.geography is None
    assert "incident_address is required" in result.warnings[0]
    assert "weather enrichment requires latitude and longitude" in result.warnings[1]


def test_context_enricher_keeps_geography_when_weather_provider_fails():
    enricher = ContextEnricher(
        weather_provider=FailingWeatherProvider(),
        geocoding_provider=FakeGeocodingProvider(),
    )

    result = enricher.enrich(
        incident_address="142 Oak Street",
        incident_time="2026-04-20T18:40:00",
    )

    assert result.geography.jurisdiction == "Santa Cruz County"
    assert result.weather is None
    assert result.warnings == ["weather enrichment failed: provider unavailable"]


def test_context_enricher_warns_when_incident_time_is_missing():
    enricher = ContextEnricher(
        weather_provider=FakeWeatherProvider(),
        geocoding_provider=FakeGeocodingProvider(),
    )

    result = enricher.enrich(incident_address="142 Oak Street")

    assert result.geography.source == "mock-osm"
    assert result.weather is None
    assert result.warnings == ["incident_time is required for weather enrichment"]
