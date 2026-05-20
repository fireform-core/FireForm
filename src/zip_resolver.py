import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_STATE_ABBREVIATIONS = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}

_ZIP_FIELD_RE = re.compile(r'\b(zip|postal|zip[\s_\-]?code|postal[\s_\-]?code)\b', re.I)
_CITY_FIELD_RE = re.compile(r'\b(city|town|municipality|district)\b', re.I)
_STATE_FIELD_RE = re.compile(r'\b(state|province)\b', re.I)
_ADDRESS_FIELD_RE = re.compile(r'\b(address|addr|location|street)\b', re.I)
_COUNTY_FIELD_RE = re.compile(r'\b(county)\b', re.I)
_EMBEDDED_ZIP_RE = re.compile(r'\b(\d{5})(?:-\d{4})?\b')
_CITY_STATE_RE = re.compile(r'([A-Za-z][A-Za-z\s]+),\s*([A-Za-z]{2})\b')


def _is_missing(value) -> bool:
    if value is None:
        return True
    return str(value).strip() in ("", "-1", "N/A", "n/a", "None", "none")


def _normalize_state(raw: str) -> Optional[str]:
    s = raw.strip()
    upper = s.upper()
    if len(s) == 2 and upper in _STATE_ABBREVIATIONS.values():
        return upper
    return _STATE_ABBREVIATIONS.get(s.lower())


class ZipResolver:
    """
    Offline US ZIP code enricher.

    Scans an extracted field dict for missing ZIP entries and attempts to
    fill them from sibling fields (city, state, address, county).
    Uses uszipcode for lookups — data is bundled as a local SQLite DB,
    so no network calls occur at fill time.
    """

    def __init__(self):
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            try:
                from uszipcode import SearchEngine
                self._engine = SearchEngine()
            except ImportError:
                logger.warning("uszipcode not installed; ZIP enrichment disabled")
                self._engine = False
        return self._engine if self._engine is not False else None

    def _lookup(self, city: str, state: str) -> Optional[str]:
        engine = self._get_engine()
        if engine is None:
            return None
        state_abbr = _normalize_state(state)
        if state_abbr is None:
            return None
        results = engine.by_city_and_state(city.strip(), state_abbr, returns=1)
        if results:
            return results[0].zipcode
        return None

    def _infer_zip(self, data: dict) -> Optional[str]:
        # 1. Look for embedded 5-digit ZIP in any address field
        for key, val in data.items():
            if _ADDRESS_FIELD_RE.search(key) and not _is_missing(val):
                m = _EMBEDDED_ZIP_RE.search(str(val))
                if m:
                    return m.group(1)

        # 2. city + state lookup
        city_val = next(
            (str(v) for k, v in data.items()
             if _CITY_FIELD_RE.search(k) and not _is_missing(v)),
            None,
        )
        state_val = next(
            (str(v) for k, v in data.items()
             if _STATE_FIELD_RE.search(k) and not _is_missing(v)),
            None,
        )
        if city_val and state_val:
            result = self._lookup(city_val, state_val)
            if result:
                return result

        # 3. Parse "City, ST" from address or county fields
        for key, val in data.items():
            if (_ADDRESS_FIELD_RE.search(key) or _COUNTY_FIELD_RE.search(key)) \
                    and not _is_missing(val):
                m = _CITY_STATE_RE.search(str(val))
                if m:
                    result = self._lookup(m.group(1), m.group(2))
                    if result:
                        return result
        return None

    def enrich(self, extracted_data: dict) -> dict:
        """
        Return a copy of extracted_data with missing ZIP fields inferred where
        possible. Existing non-empty ZIP values are never overwritten.
        """
        enriched = dict(extracted_data)
        for key in list(enriched.keys()):
            if _ZIP_FIELD_RE.search(key) and _is_missing(enriched[key]):
                inferred = self._infer_zip(enriched)
                if inferred:
                    logger.info("ZIP enriched for field '%s': %s", key, inferred)
                    enriched[key] = inferred
                else:
                    logger.debug("Could not infer ZIP for field '%s'", key)
        return enriched
