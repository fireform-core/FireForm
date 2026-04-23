from src.zip_resolver import OfflineUSZipResolver


class StubZipResolver(OfflineUSZipResolver):
    def __init__(self):
        # Avoid loading pgeocode in unit tests.
        self._nominatim = object()

    def _query_location(self, place: str):
        dataset = {
            "sacramento": [
                {
                    "postal_code": "95814",
                    "state_code": "CA",
                    "county_name": "Sacramento",
                },
                {
                    "postal_code": "94203",
                    "state_code": "CA",
                    "county_name": "Sacramento",
                },
            ],
            "pine valley": [
                {
                    "postal_code": "91962",
                    "state_code": "CA",
                    "county_name": "San Diego",
                }
            ],
        }
        return dataset.get(place.lower(), [])


def test_enriches_missing_zip_from_city_and_state():
    resolver = StubZipResolver()
    answers = {
        "City": "Pine Valley",
        "State": "CA",
        "Zip Code": None,
    }

    enriched = resolver.enrich_missing_zip_fields(answers)

    assert enriched["Zip Code"] == "91962"


def test_does_not_override_existing_zip():
    resolver = StubZipResolver()
    answers = {
        "City": "Sacramento",
        "State": "California",
        "Postal Code": "95814",
    }

    enriched = resolver.enrich_missing_zip_fields(answers)

    assert enriched["Postal Code"] == "95814"


def test_uses_zip_found_in_address_text_before_lookup():
    resolver = StubZipResolver()
    answers = {
        "Address": "123 Main St, Sacramento, CA 95814",
        "ZIP": "-1",
    }

    enriched = resolver.enrich_missing_zip_fields(answers)

    assert enriched["ZIP"] == "95814"
