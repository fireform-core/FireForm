from unittest.mock import MagicMock
import pytest

from zip_resolver import ZipResolver, _is_missing, _normalize_state


class TestHelpers:
    def test_is_missing_none(self):
        assert _is_missing(None)

    def test_is_missing_empty(self):
        assert _is_missing("")

    def test_is_missing_minus_one(self):
        assert _is_missing("-1")

    def test_is_missing_na(self):
        assert _is_missing("N/A")

    def test_not_missing_valid_zip(self):
        assert not _is_missing("95814")

    def test_normalize_state_abbreviation(self):
        assert _normalize_state("CA") == "CA"

    def test_normalize_state_full_name(self):
        assert _normalize_state("California") == "CA"

    def test_normalize_state_lowercase(self):
        assert _normalize_state("california") == "CA"

    def test_normalize_state_unknown(self):
        assert _normalize_state("Nowhere") is None


def _mock_engine(zipcode: str = "95814"):
    result = MagicMock()
    result.zipcode = zipcode
    engine = MagicMock()
    engine.by_city_and_state.return_value = [result]
    return engine


class TestZipResolver:
    def test_fills_missing_zip_from_city_state(self):
        data = {"Incident City": "Sacramento", "State": "CA", "ZIP Code": "-1"}
        resolver = ZipResolver()
        resolver._engine = _mock_engine("95814")
        result = resolver.enrich(data)
        assert result["ZIP Code"] == "95814"

    def test_does_not_overwrite_existing_zip(self):
        data = {"City": "Sacramento", "State": "CA", "Zip": "90210"}
        resolver = ZipResolver()
        resolver._engine = _mock_engine("95814")
        result = resolver.enrich(data)
        assert result["Zip"] == "90210"

    def test_extracts_embedded_zip_from_address(self):
        data = {"Address": "123 Main St, Sacramento, CA 95814", "ZIP Code": ""}
        resolver = ZipResolver()
        resolver._engine = MagicMock()
        result = resolver.enrich(data)
        assert result["ZIP Code"] == "95814"

    def test_no_zip_field_returns_unchanged(self):
        data = {"City": "Sacramento", "State": "CA"}
        resolver = ZipResolver()
        resolver._engine = MagicMock()
        result = resolver.enrich(data)
        assert result == data

    def test_leaves_blank_when_no_context(self):
        data = {"ZIP Code": "-1"}
        resolver = ZipResolver()
        engine = MagicMock()
        engine.by_city_and_state.return_value = []
        resolver._engine = engine
        result = resolver.enrich(data)
        assert _is_missing(result["ZIP Code"])

    def test_handles_full_state_name(self):
        data = {"City": "Pine Valley", "State": "California", "Postal Code": "-1"}
        resolver = ZipResolver()
        resolver._engine = _mock_engine("91962")
        result = resolver.enrich(data)
        assert result["Postal Code"] == "91962"
        resolver._engine.by_city_and_state.assert_called_once_with("Pine Valley", "CA", returns=1)

    def test_parses_city_state_from_address_field(self):
        data = {"Incident Location": "Pine Valley, CA", "ZIP": ""}
        resolver = ZipResolver()
        resolver._engine = _mock_engine("91962")
        result = resolver.enrich(data)
        assert result["ZIP"] == "91962"

    def test_disabled_when_uszipcode_missing(self):
        data = {"City": "Sacramento", "State": "CA", "ZIP": "-1"}
        resolver = ZipResolver()
        resolver._engine = False
        result = resolver.enrich(data)
        assert _is_missing(result["ZIP"])

    def test_does_not_mutate_original_dict(self):
        original = {"City": "Sacramento", "State": "CA", "ZIP": "-1"}
        resolver = ZipResolver()
        resolver._engine = _mock_engine("95814")
        result = resolver.enrich(original)
        assert original["ZIP"] == "-1"
        assert result["ZIP"] == "95814"

    def test_county_field_used_for_city_state_parsing(self):
        data = {"County": "Sacramento County, CA", "zip_code": ""}
        resolver = ZipResolver()
        resolver._engine = _mock_engine("95814")
        result = resolver.enrich(data)
        assert result["zip_code"] == "95814"

    def test_case_insensitive_zip_field_detection(self):
        data = {"City": "Sacramento", "State": "CA", "zip code": ""}
        resolver = ZipResolver()
        resolver._engine = _mock_engine("95814")
        result = resolver.enrich(data)
        assert result["zip code"] == "95814"
