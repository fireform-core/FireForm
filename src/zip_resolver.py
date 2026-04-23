import re
from typing import Any, Dict, List, Optional


# US state names mapped to postal abbreviations.
STATE_NAME_TO_CODE = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    "district of columbia": "DC",
}

STATE_CODES = set(STATE_NAME_TO_CODE.values())
ZIP_PATTERN = re.compile(r"\b(\d{5})(?:-\d{4})?\b")
LOCATION_KEYWORDS = (
    "address",
    "street",
    "city",
    "town",
    "district",
    "county",
    "state",
    "location",
)
ZIP_KEYWORDS = ("zip", "zipcode", "zip code", "postal", "postal code")


class OfflineUSZipResolver:
    """Resolve missing US ZIP/postal fields from other location fields offline."""

    def __init__(self) -> None:
        self._nominatim = None
        try:
            import pgeocode

            self._nominatim = pgeocode.Nominatim("us")
        except Exception:
            # Keep resolver non-fatal when dependency/environment is not available.
            self._nominatim = None

    def enrich_missing_zip_fields(self, field_answers: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fill ZIP/postal fields when missing, using existing location-related answers.

        Returns the same dictionary instance for convenience.
        """
        zip_keys = [k for k in field_answers if self._is_zip_field(k)]
        if not zip_keys:
            return field_answers

        inferred_zip = self.derive_zip_from_fields(field_answers)
        if inferred_zip is None:
            return field_answers

        for key in zip_keys:
            if self._is_missing(field_answers.get(key)):
                field_answers[key] = inferred_zip

        return field_answers

    def derive_zip_from_fields(self, field_answers: Dict[str, Any]) -> Optional[str]:
        """Infer a ZIP code from a dictionary of extracted field answers."""
        explicit_zip = self._extract_existing_zip(field_answers)
        if explicit_zip:
            return explicit_zip

        location_values = self._collect_location_values(field_answers)
        if not location_values:
            return None

        state_code = self._extract_state_code(" ".join(location_values))
        county_hint = self._extract_county_hint(field_answers)

        place_candidates = self._collect_place_candidates(field_answers)
        for place in place_candidates:
            rows = self._query_location(place)
            if not rows:
                continue

            zip_code = self._select_zip(rows, state_code=state_code, county_hint=county_hint)
            if zip_code:
                return zip_code

        # Fallback: parse full location text in case ZIP already appears in address text.
        combined_text = " ".join(location_values)
        return self._extract_zip_from_text(combined_text)

    def _query_location(self, place: str) -> List[Dict[str, Any]]:
        if self._nominatim is None or not place:
            return []

        try:
            result = self._nominatim.query_location(place)
        except Exception:
            return []

        return self._to_row_dicts(result)

    def _select_zip(
        self,
        rows: List[Dict[str, Any]],
        state_code: Optional[str] = None,
        county_hint: Optional[str] = None,
    ) -> Optional[str]:
        filtered_rows = rows

        if state_code:
            state_rows = [
                row
                for row in filtered_rows
                if str(row.get("state_code", "")).upper() == state_code
            ]
            if state_rows:
                filtered_rows = state_rows

        if county_hint:
            normalized_county = county_hint.lower()
            county_rows = [
                row
                for row in filtered_rows
                if normalized_county in str(row.get("county_name", "")).lower()
            ]
            if county_rows:
                filtered_rows = county_rows

        zip_candidates: List[str] = []
        for row in filtered_rows:
            zip_code = self._normalize_zip(row.get("postal_code"))
            if zip_code:
                zip_candidates.append(zip_code)

        unique_zips = sorted(set(zip_candidates))
        if not unique_zips:
            return None

        return unique_zips[0]

    def _extract_existing_zip(self, field_answers: Dict[str, Any]) -> Optional[str]:
        for value in field_answers.values():
            if isinstance(value, list):
                value = " ".join(str(v) for v in value)
            zip_code = self._extract_zip_from_text(str(value))
            if zip_code:
                return zip_code
        return None

    def _collect_location_values(self, field_answers: Dict[str, Any]) -> List[str]:
        values: List[str] = []
        for key, value in field_answers.items():
            key_lower = key.lower()
            if not any(keyword in key_lower for keyword in LOCATION_KEYWORDS):
                continue

            if self._is_missing(value):
                continue

            if isinstance(value, list):
                values.extend(str(v) for v in value if not self._is_missing(v))
            else:
                values.append(str(value))

        return values

    def _collect_place_candidates(self, field_answers: Dict[str, Any]) -> List[str]:
        candidates: List[str] = []

        for key, value in field_answers.items():
            if self._is_missing(value):
                continue

            key_lower = key.lower()
            if any(token in key_lower for token in ("city", "town", "district", "location")):
                candidates.append(str(value))

            if any(token in key_lower for token in ("address", "street")):
                parts = [part.strip() for part in str(value).split(",") if part.strip()]
                # Keep non-numeric chunks only to improve locality matches.
                for part in parts:
                    if any(char.isalpha() for char in part):
                        candidates.append(part)

        # Deduplicate while preserving order.
        seen = set()
        deduped: List[str] = []
        for candidate in candidates:
            normalized = self._normalize_text(candidate)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(candidate)

        return deduped

    def _extract_county_hint(self, field_answers: Dict[str, Any]) -> Optional[str]:
        for key, value in field_answers.items():
            if "county" in key.lower() and not self._is_missing(value):
                return str(value)
        return None

    def _extract_state_code(self, text: str) -> Optional[str]:
        if not text:
            return None

        upper_text = text.upper()
        for code in STATE_CODES:
            if re.search(rf"\b{re.escape(code)}\b", upper_text):
                return code

        lower_text = text.lower()
        for state_name, code in STATE_NAME_TO_CODE.items():
            if re.search(rf"\b{re.escape(state_name)}\b", lower_text):
                return code

        return None

    def _extract_zip_from_text(self, text: str) -> Optional[str]:
        if not text:
            return None

        match = ZIP_PATTERN.search(text)
        if not match:
            return None
        return match.group(1)

    def _normalize_zip(self, value: Any) -> Optional[str]:
        if value is None:
            return None

        match = ZIP_PATTERN.search(str(value))
        if not match:
            return None

        return match.group(1)

    def _to_row_dicts(self, result: Any) -> List[Dict[str, Any]]:
        if result is None:
            return []

        if isinstance(result, dict):
            return [result]

        if isinstance(result, list):
            return [row for row in result if isinstance(row, dict)]

        if hasattr(result, "to_dict"):
            try:
                records = result.to_dict(orient="records")
                if isinstance(records, list):
                    return [row for row in records if isinstance(row, dict)]
            except TypeError:
                pass

            try:
                row = result.to_dict()
                if isinstance(row, dict):
                    return [row]
            except Exception:
                return []

        return []

    def _is_zip_field(self, field_name: str) -> bool:
        lowered = field_name.lower()
        return any(keyword in lowered for keyword in ZIP_KEYWORDS)

    def _is_missing(self, value: Any) -> bool:
        if value is None:
            return True

        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized in {"", "-1", "none", "null", "n/a", "na", "unknown"}

        return False

    def _normalize_text(self, text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
        return re.sub(r"\s+", " ", cleaned).strip()
