"""Trusted context enrichment for incident reports.

This module defines a small provider-agnostic layer for enriching extracted
incident data with deterministic weather and geographic context. Real NOAA,
OpenStreetMap, or local boundary-data adapters can implement these interfaces
later without changing the orchestration logic.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class WeatherContext:
    """Weather fields resolved from a trusted provider."""

    temperature: str | None = None
    humidity: str | None = None
    wind_speed: str | None = None
    source: str = "unknown"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GeographicContext:
    """Geographic fields resolved from a trusted provider."""

    latitude: float | None = None
    longitude: float | None = None
    jurisdiction: str | None = None
    district: str | None = None
    source: str = "unknown"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ContextEnrichmentResult:
    """Combined enrichment output plus non-fatal warnings."""

    weather: WeatherContext | None = None
    geography: GeographicContext | None = None
    warnings: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "weather": self.weather.to_dict() if self.weather else None,
            "geography": self.geography.to_dict() if self.geography else None,
            "warnings": list(self.warnings or []),
        }


class WeatherProvider(Protocol):
    """Provider interface for incident-time weather lookup."""

    def get_weather(
        self,
        latitude: float,
        longitude: float,
        incident_time: str | datetime,
    ) -> WeatherContext | None:
        ...


class GeocodingProvider(Protocol):
    """Provider interface for geocoding and jurisdiction lookup."""

    def geocode(self, address: str) -> GeographicContext | None:
        ...


class ContextEnricher:
    """Enrich incident data using deterministic provider interfaces."""

    def __init__(
        self,
        weather_provider: WeatherProvider | None = None,
        geocoding_provider: GeocodingProvider | None = None,
    ):
        self.weather_provider = weather_provider
        self.geocoding_provider = geocoding_provider

    def enrich(
        self,
        incident_address: str | None = None,
        incident_time: str | datetime | None = None,
    ) -> ContextEnrichmentResult:
        """Return weather/geographic context without raising provider errors."""
        warnings: list[str] = []
        geography = self._resolve_geography(incident_address, warnings)
        weather = self._resolve_weather(geography, incident_time, warnings)

        return ContextEnrichmentResult(
            weather=weather,
            geography=geography,
            warnings=warnings,
        )

    def _resolve_geography(
        self,
        incident_address: str | None,
        warnings: list[str],
    ) -> GeographicContext | None:
        if not incident_address or not incident_address.strip():
            warnings.append("incident_address is required for geographic enrichment")
            return None

        if self.geocoding_provider is None:
            warnings.append("geocoding provider is not configured")
            return None

        try:
            geography = self.geocoding_provider.geocode(incident_address.strip())
        except Exception as exc:
            warnings.append(f"geocoding enrichment failed: {exc}")
            return None

        if geography is None:
            warnings.append("geocoding provider returned no result")

        return geography

    def _resolve_weather(
        self,
        geography: GeographicContext | None,
        incident_time: str | datetime | None,
        warnings: list[str],
    ) -> WeatherContext | None:
        if self.weather_provider is None:
            warnings.append("weather provider is not configured")
            return None

        if geography is None or geography.latitude is None or geography.longitude is None:
            warnings.append("weather enrichment requires latitude and longitude")
            return None

        if incident_time is None:
            warnings.append("incident_time is required for weather enrichment")
            return None

        try:
            weather = self.weather_provider.get_weather(
                latitude=geography.latitude,
                longitude=geography.longitude,
                incident_time=incident_time,
            )
        except Exception as exc:
            warnings.append(f"weather enrichment failed: {exc}")
            return None

        if weather is None:
            warnings.append("weather provider returned no result")

        return weather
